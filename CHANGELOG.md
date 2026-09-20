# 1.0.1

- Reapply steering-deceleration suppression immediately before permitted movement
  input reaches the controlled pawn, recovering from native state resets.
- Preserve zero-input, cinematic movement blocks, input values and cleanup.
- Add explicit old-version detection and safe restore-before-upgrade instructions.
- Test the 1.0 failure and 1.0.1 recovery in the installed Lua VM with stub engine
  methods; validate both resource archives and exact restore after upgrade.
- In-game confirmation of fusion/cinematic recovery is pending.

# 1.0.0

Initial release. The original tester confirmed the turn-slowdown fix, then reported
that it stopped applying after fusion/cinematic transitions.
