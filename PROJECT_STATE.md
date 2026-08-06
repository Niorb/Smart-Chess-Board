# PROJECT_STATE.md

## Current Sprint Goal
Maintain AI Sub-Agent Roster and Implement Smart Chess Board Core Features.

## Active Agents Roster
- **Architect** (`.agents/arch.md`) - System design, protocols, state machines.
- **Developer** (`.agents/dev.md`) - FastAPI backend, React/Vite frontend, stockfish engine integration.
- **QA Specialist** (`.agents/qa.md`) - Unit tests, mock hardware drivers, edge cases.
- **Hardware Specialist** (`.agents/hardware.md`) - ESP32 firmware, GPIO, matrix inversion, LED strip driver.
- **Automation Specialist** (`.agents/automation.md`) - Playwright browser scripts, Chess.com online sync.
- **Creative Innovator** (`.agents/creative.md`) - Feature brainstorming & ideas (Invoked ONLY on explicit user request).
- **Code Explorer** (`.agents/explorer.md`) - Search, index, trace, and locate codebase information and symbol definitions.

## Completed Tasks
- [x] Fixed persistent LED activation and desync issue by adding thread-safe serial locking (`serial_lock`), ESP32 RX buffer recovery on timeout, and reliable `shown_colors` cache updates.
- [x] Reworked LED ordering to a clean 2 LEDs/square base for Strip 1 (files a-d) and disabled Strip 2 (files e-h) completely.
- [x] Fixed software bug causing duplicate transposed square highlighting (e.g., lighting A4 also lighting D1) in `BoardStateManager._update_leds()`.
- [x] Configured real 18-LED column offset positions for Strip 1 (accounting for 2 skipped OFF LEDs after Rank 7 and Rank 3).
- [x] Implemented Strip 2 (files e-h) 2 LEDs/square base serpentine mapping starting at h8 down to h1, g1 to g8, f8 to f1, and e1 to e8.
- [x] Updated board recalibration function (`calibrate_board`) and baseline window (`baseline_window_s`) to use a 2-second continuous sampling window.
- [x] Implemented automatic 5-second ±1000 threshold recalibration sequence upon webapp WebSocket connection establishment.
- [x] Added webapp UI visual feedback banner during initial calibration and auto-restore parameter controls in the Calibration & Threshold tab upon completion.
- [x] Made row quadrant swap (1-4 ↔ 5-8) for right-side files e-h active by default when `swap_row_quadrants_right` is `False`.
- [x] Removed "Swap Row Quadrants a-d (1-4 ↔ 5-8)" and "Swap Row Quadrants e-h (1-4 ↔ 5-8)" options from the webapp frontend UI.

## Task Backlog

## Active Blockers
- None
