"""Public entry point. GUI by default; source-friendly command-line mode."""
import argparse
import json
from pathlib import Path
import sys

# Also works with isolated (-I) portable Python, without PYTHONPATH/site packages.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from installer import VERSION, check, install, restore
from platform_windows import discover_games


def main():
    p = argparse.ArgumentParser(description="Aniimo Smooth Movement " + VERSION)
    p.add_argument("action", nargs="?", choices=("check", "install", "restore"))
    p.add_argument("--game-dir", type=Path)
    p.add_argument("--json", action="store_true", help="Print a machine-readable report.")
    args = p.parse_args()
    if args.action is None:
        from gui import launch
        launch(args.game_dir)
        return 0
    root = args.game_dir
    if root is None:
        found = discover_games()
        if len(found) != 1:
            raise ValueError("Select a game directory with --game-dir, or run without arguments for the interface.")
        root = found[0]
    result = {"check": check, "install": install, "restore": restore}[args.action](root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        # pythonw has no console; show startup/dependency failures visibly.
        if sys.stderr is None:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(error), "Aniimo Smooth Movement", 0x10)
        else:
            print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
