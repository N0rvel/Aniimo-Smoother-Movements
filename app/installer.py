"""Offline, reversible installer. Never changes executables, DLLs or game manifests."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid
from archive_patch import transform, read_json, sha
from luajit_patch import need
from platform_windows import ensure_closed, mutation_lock

VERSION = "1.0.1"
STATE = ".aniimo-turn-fix"
BASES = tuple(Path(data) / sub / "cvs/res/lua"
              for data in ("Aniimo_Data", "worldx_Data")
              for sub in ("StreamingAssets", ""))
ALLOWED = {str(base / ("LuaScripts."+ext)).replace("\\", "/")
           for base in BASES for ext in ("xdf", "xdt")}


def digest_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024*1024), b""):
            h.update(b)
    return h.hexdigest()


def game_root(path):
    root = Path(path).resolve(strict=True)
    need(root.is_dir() and (root / "Aniimo.exe").is_file(), "Select the game folder containing Aniimo.exe.")
    return root


def safe(root, relative):
    relative = str(relative).replace("\\", "/")
    need(relative and not relative.startswith("/") and ":" not in relative
         and all(p not in ("", ".", "..") for p in relative.split("/")), "Invalid relative file path.")
    path = root / relative
    for p in (path, *path.parents):
        if p.exists() or p.is_symlink():
            need(not p.is_symlink() and not (getattr(p.lstat(), "st_file_attributes", 0) & 0x400),
                 "Links inside the game/backup directories are unsupported: " + str(p))
        if p == root:
            break
    return path


def write_atomic(path, data, expected=None, create_only=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".acaf-" + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("xb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        if expected:
            need(digest_file(tmp) == expected, "Temporary file verification failed.")
        if create_only:
            # Windows rename does not replace an existing destination.
            need(not path.exists(), "Backup destination already exists.")
            os.rename(tmp, path)
        else:
            os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def journal(root, doc):
    payload = (json.dumps(doc, indent=2) + "\n").encode("utf-8")
    write_atomic(safe(root, STATE + "/active.json"), payload)


def load_journal(root):
    file = safe(root, STATE + "/active.json")
    if not file.exists():
        return None
    need(file.stat().st_size < 1024*1024, "Oversized backup manifest.")
    doc = read_json(file.read_bytes())
    need(doc.get("schema") == 1 and re.fullmatch(r"[0-9a-f]{32}", doc.get("generation", ""))
         and doc.get("status") in ("prepared", "installed", "restored", "rolled_back"), "Invalid backup manifest.")
    records = doc.get("files", [])
    need(isinstance(records, list) and 0 < len(records) <= len(ALLOWED), "Invalid backup file list.")
    seen = set()
    for r in records:
        need(isinstance(r, dict) and r.get("relative") in ALLOWED and r["relative"] not in seen,
             "Invalid or duplicate backup path.")
        seen.add(r["relative"])
        need(all(re.fullmatch(r"[0-9a-f]{64}", r.get(k, "")) for k in ("before", "after")), "Invalid backup hashes.")
    return doc


def backup_path(root, doc, record):
    return safe(root, STATE + "/backups/" + doc["generation"] + "/" + record["relative"])


@dataclass
class Change:
    relative: str
    before: str
    after: str
    data: bytes


def plan(root):
    root = game_root(root)
    changes, details, recognized = [], [], []
    for base in BASES:
        archive, index = safe(root, base / "LuaScripts.xdf"), safe(root, base / "LuaScripts.xdt")
        if not archive.exists() and not index.exists():
            continue
        need(archive.is_file() and index.is_file(), "Incomplete resource pair: " + str(base))
        original_archive, original_index = archive.read_bytes(), index.read_bytes()
        new_archive, new_index, detail = transform(original_archive, original_index)
        detail["resource"] = base.as_posix()
        details.append(detail)
        for path, before, after in ((archive, original_archive, new_archive), (index, original_index, new_index)):
            rel = path.relative_to(root).as_posix()
            recognized.append(rel)
            if before != after:
                changes.append(Change(rel, sha(before), sha(after), after))
    need(details, "No supported Aniimo Lua resource archives were found.")
    return root, changes, details, recognized


def check(root):
    root = game_root(root)
    doc = load_journal(root)
    if doc and doc["status"] in ("prepared", "installed"):
        paths = [safe(root, r["relative"]) for r in doc["files"]]
        hashes = [digest_file(p) if p.is_file() else None for p in paths]
        if (doc["status"] == "prepared" or not all(h == r["after"] for h, r in zip(hashes, doc["files"]))) \
                and all(h in (r["before"], r["after"]) for h, r in zip(hashes, doc["files"])):
            return {"version": VERSION, "state": "recovery_required", "resources": doc["resources"]}
    root, changes, details, _ = plan(root)
    state = "compatible" if changes else "already_equal"
    if doc and doc["status"] in ("prepared", "installed"):
        state = "installed" if all(h == r["after"] for h, r in zip(hashes, doc["files"])) else "game_updated_or_modified"
        if state == "installed" and doc.get("tool_version") != VERSION and changes:
            state = "upgrade_required"
    return {"version": VERSION, "state": state, "files_to_change": len(changes), "resources": details}


def install(root):
    with mutation_lock():
        root = game_root(root)
        ensure_closed(root)
        old_doc = load_journal(root)
        if old_doc and old_doc["status"] == "prepared":
            raise RuntimeError("Interrupted installation: Restore first, then install again.")
        if old_doc and old_doc["status"] == "installed" and old_doc.get("tool_version") != VERSION:
            need(False, "Previous movement version installed. Use Remove movement fix first, then Install fix. The camera fix is preserved.")
        root, changes, details, recognized = plan(root)
        if not changes:
            return {"state": "already_equal", "resources": details}
        if old_doc and old_doc["status"] == "installed":
            old_hashes = [digest_file(safe(root, r["relative"])) for r in old_doc["files"]]
            # A fully replaced/repaired game may receive a fresh generation.
            # Never overwrite remnants of a partially installed previous patch.
            need(all(h != r["after"] for h, r in zip(old_hashes, old_doc["files"]))
                 and all(d["state"] == "original" for d in details),
                 "Mixed previous patch/update detected. Restore before reinstalling.")
        needed = sum(len(c.data) for c in changes) * 2 + 32*1024*1024
        need(shutil.disk_usage(root).free >= needed, "Insufficient free space for verified backups and replacement files.")
        doc = {"schema": 1, "tool_version": VERSION, "generation": uuid.uuid4().hex,
               "created_utc": datetime.now(timezone.utc).isoformat(), "status": "prepared",
               "files": [{"relative": c.relative, "before": c.before, "after": c.after} for c in changes],
               "resources": details}
        for c, r in zip(changes, doc["files"]):
            original = safe(root, c.relative).read_bytes()
            need(sha(original) == c.before, "Game files changed while preparing. Try again with the launcher closed.")
            write_atomic(backup_path(root, doc, r), original, c.before, create_only=True)
        # The durable manifest exists before any game resource can change.
        if old_doc:
            write_atomic(safe(root, STATE + "/history/" + old_doc["generation"] + ".json"),
                         json.dumps(old_doc, indent=2).encode("utf-8"))
        journal(root, doc)
        written = []
        try:
            for i, c in enumerate(changes):
                ensure_closed(root)
                dest = safe(root, c.relative)
                need(digest_file(dest) == c.before, "A game resource changed during installation.")
                write_atomic(dest, c.data, c.after)
                written.append(i)
            need(all(digest_file(safe(root, c.relative)) == c.after for c in changes), "Final file verification failed.")
            doc["status"] = "installed"
            journal(root, doc)
        except BaseException:
            errors = []
            for i in written:
                r = doc["files"][i]
                try:
                    dest = safe(root, r["relative"])
                    need(digest_file(dest) == r["after"], "External change: refusing automatic rollback.")
                    source = backup_path(root, doc, r)
                    need(digest_file(source) == r["before"], "Backup corrupted during rollback.")
                    write_atomic(dest, source.read_bytes(), r["before"])
                except Exception as exc:
                    errors.append(str(exc))
            doc["status"] = "prepared" if errors else "rolled_back"
            try:
                journal(root, doc)
            except OSError:
                pass
            if errors:
                raise RuntimeError("Rollback incomplete. Do not launch the game; use Restore. " + "; ".join(errors))
            raise
        return {"state": "installed", "files_changed": len(changes), "resources": details}


def restore(root):
    with mutation_lock():
        root = game_root(root)
        ensure_closed(root)
        doc = load_journal(root)
        if doc is None:
            raise RuntimeError("No backups from the movement mod were found.")
        records = doc["files"]
        # Validate the entire operation before replacing even one file.
        for r in records:
            dest, source = safe(root, r["relative"]), backup_path(root, doc, r)
            need(dest.is_file() and digest_file(dest) in (r["before"], r["after"]),
                 "Game updated or another mod changed a resource. Refusing to overwrite it with an old backup.")
            need(source.is_file() and digest_file(source) == r["before"], "A required backup is missing or damaged.")
        changed = 0
        for r in records:
            ensure_closed(root)
            dest = safe(root, r["relative"])
            current = digest_file(dest)
            need(current in (r["before"], r["after"]), "Game files changed during restoration.")
            if current == r["after"]:
                original = backup_path(root, doc, r).read_bytes()
                need(sha(original) == r["before"], "Backup changed during restoration.")
                write_atomic(dest, original, r["before"])
                changed += 1
        need(all(digest_file(safe(root, r["relative"])) == r["before"] for r in records), "Restoration verification failed.")
        doc["status"] = "restored"
        journal(root, doc)
        return {"state": "restored", "files_changed": changed}

