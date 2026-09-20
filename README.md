# Aniimo Smooth Movement — 1.0.1

Removes turn-related slowdown using Aniimo's own steering-deceleration command,
without changing maximum-speed, acceleration settings or input axis values.

## Fix in 1.0.1

Version 1.0 only applied the setting on control gain. If the native movement state
was reset during a transition, its Lua marker could remain set while steering
deceleration returned. Version 1.0.1 reasserts the setting immediately before
permitted nonzero movement input reaches the native controller. It uses the pawn
that receives that input, including after switching characters/models.

All original movement gates remain in place. Zero or blocked input does not
reassert the setting. There is no timer, external background process or input
substitution. Control-loss cleanup from 1.0 is retained.

The regression was reproduced in an isolated Lua test and the corrected version
passed simulated resets, model switches, movement blocks and cleanup tests.
Actual fusion/cinematic transitions still need confirmation in game.

## Install or upgrade

Requirements: Windows, Aniimo resource build **3551601**, and **Python 3.10+ with
Tkinter**. Python is not included. No extra Python packages are required.

1. Close Aniimo and its repair tool; extract the entire ZIP.
2. Open **Aniimo Smooth Movement.py** with Python and select the game folder.
3. If 1.0.0 or the beta is installed, click **Remove movement fix** first.
4. Click **Check compatibility**, then **Install fix**.
5. Close the manager and restart Aniimo.

The 1.0.1 manager recognizes the old backup journal. Removing the previous patch
before upgrading ensures future removal restores the original resources, not the
old buggy patch. Unknown external modifications are refused.

## Camera compatibility and removal

Install Camera Axis Fix first, then Smooth Movement. Remove in reverse order.
The camera script is kept identical. Close the game and click **Remove movement
fix** to restore the exact pre-installation resources, including an earlier camera
fix. Keep `.aniimo-turn-fix` until removal is complete. Later updates/mods may cause
restoration to be refused to protect newer resource files.

## Implementation

Two Lua entries are patched: ClientMotionComponent (control lifecycle) and
PawnController (permitted movement input). All other entry payloads remain
unchanged. ZIP CRCs, lengths, offsets and index checksums are updated. Only the
audited scripts and resource build are accepted. No game payload is distributed.
See VALIDATION.json for evidence and limitations.
