# Aniimo Smooth Movement — 1.0.0

Removes turn-related slowdown using Aniimo's own steering-deceleration command.
The original tester confirmed the fix works in game on resource build 3551601.
Maximum-speed and acceleration settings are unchanged. Other movement modes
have not all been tested.

## Install

Close Aniimo and its repair tool. Extract the entire ZIP, open **Aniimo Smooth
Movement.py** using **Python 3.10+ with Tkinter**, select the folder containing
Aniimo.exe, check compatibility and install. Close the manager and restart Aniimo.
Python is required and is not bundled; no extra Python packages are needed.

Install the camera fix first if using both mods. Remove mods in reverse order:
Smooth Movement first, then Camera Axis Fix. The camera payload is kept identical.

## Remove or upgrade from the beta

Close the game and choose **Remove movement fix**. Verified backups restore the
exact previous resources. Keep `.aniimo-turn-fix` until removal is complete.
Restoration refuses unknown changes from game updates or later-installed mods.

The gameplay patch is identical to Aniimo Turn Fix 0.1.0-beta. Existing beta users
do not need to reinstall. The 1.0.0 manager recognizes its patch and backups.

## Implementation and validation

Only the ClientMotionComponent entry in recognized LuaScripts.xdf/.xdt resource
pairs is patched. Control-gain/loss handlers invoke SetSteeringDeceleration with
the existing Logic reason; a local marker tracks application to an entity.
Original callbacks remain intact. All other entry payloads are preserved.
ZIP CRCs, sizes, offsets and resource-index checksums are updated.

Only resource build 3551601 and the audited movement-script SHA-256 are accepted.
No proprietary game payload is shipped. No DLL injection, executable modification,
network requests or background app are involved. See VALIDATION.json for tests,
SECURITY-REVIEW.md for reviewer notes, and NEXUS-DESCRIPTION.md for the mod page text.
