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
- [x] Disabled and suppressed LED illumination during initial webapp connection recalibration and manual board baseline calibration.
- [x] Fixed serial lock deadlock during webapp connection recalibration by upgrading `serial_lock` from non-reentrant `threading.Lock` to re-entrant `threading.RLock`.
- [x] Fixed row 1-4 ↔ 5-8 quadrant swap mismatch between webapp and physical board by setting row quadrant swap flags to false by default and correcting Strip 1 serpentine `sq_idx` calculation in `led_helpers.py` so rank 1 (`col=0`) maps to physical LED index 0 at `a1` and rank 8 (`col=7`) maps to physical LED index 16 at `a8`.
- [x] Added "Force All LEDs Off" button to webapp control interface and created corresponding `/api/board/clear_leds` backend endpoint.
- [x] Completely removed quadrant swapping logic and options from backend, hardware scanner, LED helpers, webapp frontend, and tests.
- [x] Removed inverted channel mapping (`7 - rank_idx`) for `COL_MUX` in ESP32 firmware [`analog_scanner.ino`](file:///home/robin/Smart-Chess-Board/Raspberry/ESP32_firmware/analog_scanner/analog_scanner.ino#L48-L51), mapping `COL_MUX` channels 0–7 directly to Ranks 1–8.
- [x] Fixed "Force Recalibrate Baselines" button by clearing `baseline_history` upon calibration completion in [`board_hardware.py`](file:///home/robin/Smart-Chess-Board/Raspberry/board_hardware.py#L313) (preventing background scan loop from immediately overwriting new baselines with pre-calibration averages) and adding serial buffer resync on framing timeout.
- [x] Updated [`Raspberry/ESP32_firmware/WIRING_GUIDE.txt`](file:///home/robin/Smart-Chess-Board/Raspberry/ESP32_firmware/WIRING_GUIDE.txt) to reflect 8x8 matrix topology using analog linear Hall effect sensors (VCC/2 ratiometric output), active ADC reading on `GPIO 34`, and current [`analog_scanner.ino`](file:///home/robin/Smart-Chess-Board/Raspberry/ESP32_firmware/analog_scanner/analog_scanner.ino) pinouts.
- [x] Migrated `WIRING_GUIDE.txt` to [`Raspberry/ESP32_firmware/WIRING_GUIDE.txt`](file:///home/robin/Smart-Chess-Board/Raspberry/ESP32_firmware/WIRING_GUIDE.txt) and deleted the obsolete top-level `ESP32/` prototype directory.
- [x] Increased upper and lower deviation threshold limits to 3000 in the webapp UI (range sliders up to 3000 and direct numeric inputs).
- [x] Fixed row/column transposition between physical board and webapp by updating MUX scan order (`file_idx` outer loop, `rank_idx` inner loop) in [`analog_scanner.ino`](file:///home/robin/Smart-Chess-Board/Raspberry/ESP32_firmware/analog_scanner/analog_scanner.ino) and [`board_hardware.py`](file:///home/robin/Smart-Chess-Board/Raspberry/board_hardware.py) so selecting a column in webapp manual mode activates the corresponding column (Files a-h) on the physical board.
- [x] Created `codebase-optimization` skill (`.agents/skills/codebase-optimization/SKILL.md`), reference guides (`python-optimization.md`, `typescript-optimization.md`), and automated static analysis audit script (`run_audit.py`).
- [x] Executed full codebase optimization pass across Python backend, hardware drivers, Playwright scripts, and React frontend: eliminated dead functions/unused constants, resolved all Mypy static type errors, removed inline module imports from tight loop execution paths, and optimized React state/effect dependencies and piece rendering allocations. All audit gates (`ruff`, `vulture`, `mypy --check-untyped-defs`, `tsc`, `knip`, `eslint`, `vite build`) pass cleanly with 0 errors.

## Task Backlog

## Active Blockers
- None


