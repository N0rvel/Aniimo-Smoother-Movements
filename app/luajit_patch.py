"""Audited control-lifecycle hooks. No game bytecode is distributed here.

This release accepts one known ClientMotionComponent script. It retains all original
instructions and adds SetSteeringDeceleration calls on control gain/loss only.
"""
import hashlib
import struct
from luajit_base import Reader, need, prototypes, PatchError

ORIGINAL_SHA = "59846f3340b361a76ef66f371f76415ed2a0180934d36b2b805fad3c400e725c"
PATCHED_SHA = "15aa119399bace39d91748aa10c5d32a3015fbea42096787a17f8db49f016dc2"
MARKER = "_aniimoTurnFixActive"


def uleb(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def abc(op, a, b=0, c=0):
    return op | (a << 8) | (c << 16) | (b << 24)


def ad(op, a, d):
    return op | (a << 8) | (d << 16)


def edit_proto(raw, proto, gaining, const_upvalue):
    r = Reader(raw)
    flags, params, frame, n_uv = r.take(4)
    n_gc, n_num, n_bc = r.uleb(), r.uleb(), r.uleb()
    n_debug = r.uleb()
    if n_debug:
        r.uleb(); r.uleb()
    words = list(struct.unpack('<' + 'I' * n_bc, r.take(n_bc * 4)))
    uv = r.take(n_uv * 2)
    constants_and_numbers = raw[r.pos:len(raw)-n_debug if n_debug else len(raw)]
    consts = list(proto.constants)
    extra = []
    def key(name):
        if name not in consts:
            consts.append(name)
            encoded = name.encode('utf-8')
            extra.insert(0, uleb(len(encoded)+5)+encoded)
        return consts.index(name)
    model, method, component, marker = map(key, ('eModel', 'SetSteeringDeceleration', 'COMPONENT_MOTION', MARKER))
    need(max(model, method, component, marker) < 256, 'Too many table constants.')
    if gaining:
        need(uv == const_upvalue and len(words) == 18, 'Unexpected control-gain structure.')
    else:
        need(not uv and len(words) == 8, 'Unexpected control-loss structure.')
        uv = const_upvalue
        n_uv = 1
    # eModel:SetSteeringDeceleration(Const.COMPONENT_MOTION, enabled, Logic=1)
    call = [abc(54,1,0,model), ad(18,3,1), abc(54,1,1,method),
            ad(48,4,0), abc(54,4,4,component), ad(43,5,1 if gaining else 2),
            ad(41,6,1), abc(66,1,1,5)]
    if gaining:
        inserted = call + [ad(43,1,2), abc(63,1,0,marker)]
        need(words[9] == ad(88,2,32768+6), 'Unexpected component guard.')
        words[9] = ad(88,2,32768+6+len(inserted))
        words[16:16] = inserted
    else:
        clear = [ad(43,1,1), abc(63,1,0,marker)]
        inserted = [abc(54,1,0,marker), ad(15,0,1), ad(88,2,32768+len(call)+len(clear))] + call + clear
        words[-1:-1] = inserted
    # Only the edited functions lose their debug section. All other prototypes
    # and the original chunk header are retained byte for byte.
    return (bytes((flags, params, max(frame,7), n_uv)) + uleb(len(consts)) +
            uleb(n_num) + uleb(len(words)) + b'\0' +
            struct.pack('<'+'I'*len(words), *words) + uv +
            b''.join(extra) + constants_and_numbers)


def patch(data):
    digest = hashlib.sha256(data).hexdigest()
    if digest == PATCHED_SHA:
        return data, {'state':'equal', 'hook':'control lifecycle', 'experimental':False}
    need(digest == ORIGINAL_SHA,
         'Unsupported movement script. This release supports the audited build only; no files were changed.')
    ps = prototypes(data)
    need(len(ps) == 90 and ps[76].params == ps[77].params == 1, 'Unexpected movement module.')
    r = Reader(data)
    need(r.take(4) == b'\x1bLJ\x02' and r.uleb() == 8, 'Unsupported debug format.')
    r.take(r.uleb())
    output = bytearray(data[:r.pos])
    ordinal = 0
    while True:
        start = r.pos
        size = r.uleb()
        if not size:
            output += b'\0'
            break
        raw = r.take(size)
        if ordinal in (76,77):
            new = edit_proto(raw, ps[ordinal], ordinal == 76, struct.pack('<H', 0xc004))
            output += uleb(len(new)) + new
        else:
            output += data[start:r.pos]
        ordinal += 1
    need(r.pos == len(data), 'Trailing movement data.')
    changed = bytes(output)
    checked = prototypes(changed)
    need(len(checked) == len(ps), 'Movement prototype count changed.')
    for i, (before, after) in enumerate(zip(ps, checked)):
        if i not in (76,77):
            need(before.code == after.code and before.constants == after.constants,
                 'An unrelated function changed.')
    need(hashlib.sha256(changed).hexdigest() == PATCHED_SHA, 'Patched script hash mismatch.')
    return changed, {'state':'original', 'hook':'control lifecycle', 'experimental':False}
