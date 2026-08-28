# Original User Request

## 2026-08-26T22:22:12Z

This is a single self-contained test and refinement task; keep it small and focused.

Working directory: `/home/robin/Smart-Chess-Board`
Integrity mode: development

Define explicit behavioral specifications for the Smart Chess Board's Tactical Puzzles (Blunder Blitz) and Endgame Academy (Tablebase Trainer) features, author comprehensive adversarial test suites testing all edge cases, verify correct behavior across both web and physical board interfaces, and fix any remaining bugs sitting around.

## Requirements

### R1. Behavioral Specification & State Machine Verification
Define and verify the exact expected behavior and invariants for:
- **Opponent Moves (The side we don't play)**:
  - When the player plays a move in a puzzle or endgame drill, the opponent's defensive reply is computed by Stockfish.
  - On the **Web UI**: Opponent reply is automatically executed on the active board with arrival animations and history updates without requiring manual intervention.
  - On the **Physical Board**: Opponent reply lights up the origin in Solar Orange and target in Cyan Azure with move trace; physical movement of the opponent piece immediately confirms the move and transfers the turn back to the player.
- **Strict Solution Concealment**:
  - Grandmaster continuation lines and theoretical winning technique descriptions must **never** be rendered automatically or leaked in payloads when the player makes a move.
  - Solution lines are only revealed on the webapp if the user explicitly toggles the `💡 Solution` button.
- **Turn & Goal Management**:
  - Multi-ply tactical sequences correctly step through player plies and opponent replies.
  - Endgame tablebase goals (win, mate, draw) correctly complete drills when achieved, updating progress metrics.

### R2. Adversarial Test Suite & Bug Hunting
Author and execute exhaustive test suites covering:
- **Illegal and Out-of-Order Moves**: Playing illegal moves, wrong piece types, or making moves out of turn in puzzles and drills.
- **Physical Sensor Desynchronizations**: Piece pickups without dropoffs, simultaneous piece displacements, and physical board reset transitions.
- **Rapid/Concurrent Inputs**: Rapid move submissions from web or REST API while Stockfish is computing defensive replies.
- **UI State Transitions**: Switching between blunder puzzles, restarting endgame drills, and resetting progress to confirm no state leakage.

### R3. Remote Raspberry Pi Verification & Fix Application
- If any latent bugs, race conditions, or state machine desyncs are discovered during testing, implement the minimal, robust fix.
- Execute full regression testing on the physical Raspberry Pi (`ssh pi@pi`) running all unit/integration tests and Vite frontend build.

## Acceptance Criteria

### Behavioral & Functional Verification
- [ ] Explicit test cases verify that `solution_line` and continuation moves are never rendered automatically upon playing moves, and only display when `showSolution` is toggled.
- [ ] Web and physical board flows for opponent defensive replies function cleanly without getting stuck or desynchronized.
- [ ] Illegal moves in both Blunder Blitz and Endgame Academy return descriptive error feedback without corrupting internal board state.

### Automated Regression Gates
- [ ] All new adversarial test cases and existing test suites (369+ tests) pass 100% on the Raspberry Pi environment (`ssh pi@pi`).
- [ ] Frontend builds with zero TypeScript errors (`tsc -b && vite build`).
- [ ] System service `smart-chess.service` restarts cleanly and reports active status.
