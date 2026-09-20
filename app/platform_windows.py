import ctypes
from ctypes import wintypes
import os
from pathlib import Path
from contextlib import contextmanager
from luajit_patch import need

def running_game(root):
    """Read only: processes in this exact game directory; no access to game memory."""
    need(os.name == "nt", "Installation/restauration prévues pour Windows.")
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.Process32NextW.argtypes = kernel.Process32FirstW.argtypes
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    need(snapshot != ctypes.c_void_p(-1).value, "Impossible de vérifier si le jeu est ouvert.")
    target = os.path.normcase(os.path.abspath(root))
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        if not ok and ctypes.get_last_error() != 18:
            raise RuntimeError("Impossible d'énumérer les processus.")
        while ok:
            if entry.szExeFile.lower() in ("aniimo.exe", "worldx.exe", "repair.exe"):
                handle = kernel.OpenProcess(0x1000, False, entry.th32ProcessID)
                if not handle:
                    return True  # Fail closed if the game process cannot be identified.
                try:
                    buffer = ctypes.create_unicode_buffer(32768)
                    length = wintypes.DWORD(len(buffer))
                    if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                        return True
                    if os.path.normcase(os.path.dirname(buffer.value)) == target:
                        return True
                finally:
                    kernel.CloseHandle(handle)
            ok = kernel.Process32NextW(snapshot, ctypes.byref(entry))
            if not ok and ctypes.get_last_error() != 18:
                raise RuntimeError("Énumération des processus interrompue.")
        return False
    finally:
        kernel.CloseHandle(snapshot)


def ensure_closed(root):
    need(not running_game(root), "Aniimo ou son outil de réparation est ouvert. Ferme-le normalement avant d'appliquer/restaurer le patch.")


@contextmanager
def mutation_lock():
    need(os.name == "nt", "Windows is required to install or restore the patch.")
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateMutexW.restype = wintypes.HANDLE
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k.CreateMutexW(None, True, "Local\\AniimoCameraAxisFix")
    error = ctypes.get_last_error()
    need(handle, "Unable to lock the installer.")
    try:
        need(error != 183, "Another instance is currently installing/restoring.")
        yield
    finally:
        k.CloseHandle(handle)


def parse_vdf(text):
    """Read Steam's small quoted-string/object subset, including escaped slashes."""
    import re
    tokens = re.findall(r'"((?:\\.|[^"\\])*)"|([{}])', text)
    stream = [(a.replace(r'\\', '\\').replace(r'\"', '"') if not b else b) for a, b in tokens]
    pos = 0
    def obj(nested=False):
        nonlocal pos
        result = {}
        while pos < len(stream):
            key = stream[pos]; pos += 1
            if key == "}":
                need(nested, "Invalid VDF closing brace.")
                return result
            need(key != "{" and pos < len(stream), "Invalid VDF entry.")
            val = stream[pos]; pos += 1
            result[key] = obj(True) if val == "{" else val
        need(not nested, "Truncated VDF object.")
        return result
    return obj()


def steam_libraries(steam):
    libraries = [Path(steam)]
    file = Path(steam) / "steamapps/libraryfolders.vdf"
    if file.is_file():
        try:
            entries = parse_vdf(file.read_text(encoding="utf-8-sig"))["libraryfolders"]
            for key, value in entries.items():
                if key.isdigit():
                    path = value.get("path") if isinstance(value, dict) else value
                    if path:
                        libraries.append(Path(path))
        except (ValueError, OSError, KeyError, TypeError):
            pass
    return libraries


def discover_games():
    seeds = [Path.cwd(), Path(__file__).resolve().parent.parent]
    steam = []
    for var in ("ProgramFiles(x86)", "ProgramFiles"):
        if os.environ.get(var):
            steam.append(Path(os.environ[var]) / "Steam")
    if os.name == "nt":
        import winreg
        for hive, key, value in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        ):
            try:
                with winreg.OpenKey(hive, key) as reg:
                    steam.append(Path(winreg.QueryValueEx(reg, value)[0]))
            except OSError:
                pass
    for location in steam:
        for library in steam_libraries(location):
            seeds.append(library / "steamapps/common/Aniimo")
            manifest = library / "steamapps/appmanifest_4126040.acf"
            if manifest.is_file():
                try:
                    name = parse_vdf(manifest.read_text(encoding="utf-8-sig"))["AppState"]["installdir"]
                    seeds.append(library / "steamapps/common" / name)
                except (ValueError, OSError, KeyError, TypeError):
                    pass
    result, seen = [], set()
    for candidate in seeds:
        if candidate.is_dir() and (candidate / "Aniimo.exe").is_file():
            key = os.path.normcase(os.path.abspath(candidate))
            if key not in seen:
                result.append(Path(os.path.abspath(candidate)))
                seen.add(key)
    return result


