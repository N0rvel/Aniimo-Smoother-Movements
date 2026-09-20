"""Bounded LuaJIT dump reader and conservative Aniimo camera recognizer.

No game code/data is included. The blueprint describes the audited instruction
shape; all locations and string-constant indexes are discovered in the input.
Unknown bytecode dialects or changed camera routines are rejected.
"""
from dataclasses import dataclass
import struct


class PatchError(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise PatchError(message)


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, n):
        need(0 <= n <= len(self.data) - self.pos, "Truncated LuaJIT bytecode.")
        out = self.data[self.pos:self.pos+n]
        self.pos += n
        return out

    def uleb(self):
        value = 0
        for shift in range(0, 70, 7):
            b = self.take(1)[0]
            value |= (b & 127) << shift
            if b < 128:
                return value
        raise PatchError("Invalid LuaJIT ULEB value.")

    def table_value(self):
        tag = self.uleb()
        if tag >= 5:
            self.take(tag - 5)
        elif tag == 3:
            self.uleb()
        elif tag == 4:
            self.uleb(); self.uleb()
        else:
            need(tag in (0, 1, 2), "Unknown LuaJIT table type.")


@dataclass
class Prototype:
    offset: int
    code: list
    constants: list
    numbers: int
    params: int
    frame: int


def prototypes(data):
    need(5 <= len(data) <= 16 * 1024 * 1024, "Unsupported script size.")
    r = Reader(data)
    need(r.take(4) == b"\x1bLJ\x02", "Expected LuaJIT bytecode version 2.")
    flags = r.uleb()
    need(flags in (8, 10), "Unsupported LuaJIT flags/endianness (expected little-endian FR2).")
    stripped = bool(flags & 2)
    if not stripped:
        r.take(r.uleb())
    result, children = [], []
    while True:
        size = r.uleb()
        if not size:
            break
        end = r.pos + size
        need(end <= len(data) and len(result) < 10000, "Invalid LuaJIT prototype size/count.")
        _pf, params, frame, n_uv = r.take(4)
        n_gc, n_num, n_bc = r.uleb(), r.uleb(), r.uleb()
        need(n_gc <= size and n_num <= size and n_bc <= size // 4, "Invalid prototype counts.")
        n_debug = 0 if stripped else r.uleb()
        if n_debug:
            r.uleb(); r.uleb()
        offset = r.pos
        code = list(struct.unpack("<" + "I" * n_bc, r.take(n_bc * 4)))
        r.take(n_uv * 2)
        constants = []
        for _ in range(n_gc):
            tag = r.uleb()
            if tag >= 5:
                # Game strings unrelated to matching need not be UTF-8 text.
                value = r.take(tag - 5).decode("utf-8", "replace")
            elif tag == 0:
                need(bool(children), "Invalid LuaJIT child prototype.")
                value = ("child", children.pop())
            elif tag == 1:
                n_array, n_hash = r.uleb(), r.uleb()
                need(n_array + n_hash * 2 <= size, "Invalid LuaJIT table size.")
                for _ in range(n_array + n_hash * 2):
                    r.table_value()
                value = None
            elif tag in (2, 3, 4):
                for _ in range(4 if tag == 4 else 2):
                    r.uleb()
                value = None
            else:
                raise PatchError("Unknown LuaJIT constant type.")
            constants.append(value)
        for _ in range(n_num):
            lo = r.uleb()
            if lo & 1:
                r.uleb()
        r.take(n_debug)
        need(r.pos == end, "LuaJIT prototype boundaries do not match.")
        result.append(Prototype(offset, code, list(reversed(constants)), n_num, params, frame))
        children.append(len(result)-1)
    need(r.pos == len(data) and len(children) == 1, "Trailing data or invalid LuaJIT prototype tree.")
    return result


