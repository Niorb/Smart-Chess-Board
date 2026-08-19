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
- [x] Fixed file-axis (column) reversal in `board_hardware.py` (`scan_board` & `calibrate_board`) and `hardware_test.py` (`read_active_values`) where `c` was iterated in reverse (`range(BOARD_COLS - 1, -1, -1)`). This ensures magnet detection on square `a1` correctly maps to `matrix[0][0]` and illuminates LEDs on square `a1` (instead of `h1`). All 34 pytest unit test suites pass on the physical Raspberry Pi over SSH and Playwright browser integration tests pass.
- [x] Configured exact serpentine physical LED strip routing in [`led_helpers.py`](file:///home/robin/Smart-Chess-Board/Raspberry/playwright_chesscom/led_helpers.py) and documented in [`WIRING_GUIDE.txt`](file:///home/robin/Smart-Chess-Board/Raspberry/ESP32_firmware/WIRING_GUIDE.txt):
  - **Strip 1 (left side / files a-d)**: Starts at `a8` (LED 0, 1) -> `a1` (LED 16, 17) [Down], `b1` -> `b8` [Up], `c8` -> `c1` [Down], `d1` -> `d8` [Up].
  - **Strip 2 (right side / files e-h)**: Starts at `h8` (LED 76, 77) -> `h1` (LED 90, 91) [Down], `g1` -> `g8` [Up], `f8` -> `f1` [Down], `e1` -> `e8` [Up].
- [x] Standardized Antigravity Custom Agent YAML frontmatter format across all agent files in `.agents/agents/` (`arch.md`, `automation.md`, `creative.md`, `dev.md`, `explorer.md`, `hardware.md`, `qa.md`).
- [x] Implemented thread-safe `SettingsManager` in `board_hardware.py` with atomic JSON persistence, locking controls, auto-migration, and backward-compatible dictionary magic methods.
- [x] Cleaned up fragile `sys.path.append` hacks across FastAPI `main.py`, `board_state.py`, and `chess_engine_async.py`.
- [x] Successfully deployed and verified code changes on Raspberry Pi over SSH: frontend build succeeded (`vite build`) and all 34 pytest unit/integration tests passed cleanly.
- [x] Migrated Playwright browser automation driver (`chesscom_browser.py`, `game_seeker.py`, `interactive_game.py`, `test_connection.py`, `chess_engine_async.py`) from synchronous `playwright.sync_api` to asynchronous `playwright.async_api`, enabling native `asyncio` execution in FastAPI without thread starvation. Verified via 34 passing pytest tests on Raspberry Pi over SSH.
- [x] Implemented Lichess Board API async integration (`Raspberry/app/lichess_engine.py`), replacing legacy Playwright automation with direct NDJSON streaming and OAuth authentication.
- [x] Created centralized config (`Raspberry/app/config.py`) and standalone LED helper library (`Raspberry/app/led_helpers.py`), decoupling board hardware from web scrapers.
- [x] Archived legacy Playwright automation scripts into `Raspberry/legacy_chesscom_backup/` and updated `.gitignore` and `Raspberry/requirements.txt`.
- [x] Implemented Virtual-Only mode with real-time UI toggle, pawn promotion modal dialog, active turn clock glowing indicator with low-time warning, check indicator ring, and legal move dots in `Raspberry/frontend/src/App.tsx`.
- [x] Added unit tests for Lichess engine (`test_lichess_engine.py`) and updated test suites (`test_board_state.py`, `test_api_routes.py`, `test_led_helpers.py`, `test_highlight_row_swap.py`).
- [x] Resolved Lichess Board API time control restriction (`Invalid time control` on Blitz seeks) by adding native Stockfish AI challenge support (`POST /api/challenge/ai`), difficulty levels 1–8, and auto-routing matches < 8 minutes (Bullet/Blitz) to instant AI play while preserving live human matchmaking for Rapid/Classical. Verified live virtual board game creation, move execution (`e2e4` -> Stockfish `e7e5`), and 52 passing pytest tests on the Raspberry Pi over SSH.
- [x] Added configurable ELO rating boundaries (`ratingRange` parameter in `POST /api/board/seek`) to backend and web frontend, supporting presets (`Any`, `±100`, `±200`, `±300`, `±500`) and custom Min/Max ELO filters. All 53 unit/integration tests and frontend production build verified on Raspberry Pi.
- [x] Restored dynamic baseline drift tracking for empty middle ranks (Ranks 3-6) in `scan_board()` with starting piece ranks (Ranks 1-2 and 7-8) inheriting Rank 3 and Rank 6 baseline updates per column, preventing piece magnet absorption while maintaining live ambient temperature/voltage drift compensation.
- [x] Implemented smart piece auto-detection against reference ranks 3 & 6, 3-way mode switch (`Auto` / `Pieces Placed` / `Empty Board`), ±100 default thresholds, 1000 max slider cap, and live Web UI status badge.
- [x] Fixed LED flickering on physical player moves by implementing `in_flight_move` state locking in `PhysicalMoveTracker` (suppressing 50-100Hz re-trigger loops during network latency) and differential zero-blackout LED updates in `DualPixelStrip.show()`.
- [x] Implemented animated move traces and full-board lifecycle animations:
  - **Move Trace Flow**: Dynamic Gaussian comet pulse flowing along piece trajectory (orthogonal ranks/files, diagonals, Knight L-shapes, Bresenham lines) rendered in vibrant magenta (`COLOR_MOVE_TRACE`), while keep start (amber) and arrival (cyan) squares continuously lit.
  - **Game Lifecycle Animations**: Procedural non-blocking animations for **Game Start** (radial expanding emerald wave), **Victory** (cascading gold & emerald celebration waves), **Defeat** (collapsing perimeter crimson wave), and **Draw** (symmetrical sapphire & white curtain sweep).
  - **API & Web UI Controls**: Added `/api/leds/trigger_animation` and `/api/leds/test_trace` endpoints and debug testing buttons in `App.tsx`.
  - **Verification & Deployment**: All 94 unit/integration test suites and frontend production build verified cleanly on the physical Raspberry Pi over SSH.
- [x] Applied 20% power and brightness reduction across all LED color channels and `LED_BRIGHTNESS` (from 50 to 40) in [`config.py`](file:///home/robin/Smart-Chess-Board/Raspberry/app/config.py) to stabilize the 5V power rail, eliminate transient voltage drops, and protect Hall sensor analog baseline stability during dense full-board animations. Verified on Pi with 94 passing pytest tests.
- [x] Implemented baseline freezing and sensor reading suppression during animations:
  - **Baseline Freezing**: Snapshots analog baselines before full-board lifecycle animations and LED diagnostic tests, suppresses dynamic baseline drift tracking during animation frames, and cleanly restores original baselines and resets drift window upon animation completion.
  - **Reading Suppression**: Freezes physical piece state and disables debounce move tracking during active animations, preventing power-drop voltage ripples from triggering false piece lifts or invalid placements.
  - **Default Thresholds Updated**
- [x] Implemented animated move trace arrival pulse, capture move distinction, and settings protection:
  - **Arrival Square Pulse Flare**: Enhanced `render_move_trace()` with virtual trajectory overshoot and additive luminance flare on the arrival square upon comet arrival, supporting 1-step moves (e.g. `e2e3`) and seamless wrap-around continuity.
  - **Capture Move Visual Distinction**: Added `COLOR_OPPONENT_CAPTURE` (`(192, 0, 32)`) and `COLOR_CAPTURE_TRACE` (`(204, 32, 64)`). Wired `is_capture` detection in `PhysicalMoveTracker.sync_game()` and `LichessEngine.get_game_payload()`, layering distinct ruby/crimson destination highlights and fiery trace pulses on capture moves.
  - **Hardware Settings Isolation & Git Protection**: Untracked `board_settings.json` from git, added it to `.gitignore`, created tracked default template `Raspberry/board_settings.default.json`, and implemented 3-tier fallback initialization in `board_hardware.load_settings()` to guarantee user baselines/thresholds are never overwritten on `git pull`.
  - **Web UI & REST API**: Extended `POST /api/leds/test_trace` and frontend UI with capture move trace testing (`d4 ⚔ e5`).
- [x] Redesigned victory animation (`render_game_won`) to be lightweight and low-power:
  - Replaced full-board 64-square sinusoidal wash with dual high-speed sweeping diagonal laser comets ($a1 \to h8$ gold beam and $a8 \to h1$ emerald counter-beam), sparse high-threshold stardust twinkles (1-2 squares max), and a central diamond flare ($d4, d5, e4, e5$).
  - Reduced peak active simultaneous squares from 64 down to 3-6 squares (< 10% of board) and reduced power draw by > 90% while dramatically improving visual contrast and fluidity.

- [x] Configured default positive and negative analog deviation thresholds to **±200** across backend defaults, fallback templates, and web UI.
- [x] Implemented continuous settings remembering in Web UI:
  - All slider movements and mode toggles (positive/negative shift, scan delay, col mode, pieces mode, settle time, debounce threshold, baseline window) immediately sync to `localStorage` and debounced auto-persist to the FastAPI backend (`board_settings.json`).
- [x] Implemented continuous "Waiting for Opponent" (Seeking) radar animation:
  - **Perimeter Orbital Comet**: Clockwise orbital pulse along the 28 perimeter squares ($a1 \to h1 \to h8 \to a8 \to a1$) with bright cyan-white head (`(140, 240, 255)`), electric azure body (`(0, 140, 255)`), and deep sapphire decay (`(0, 36, 160)`).
- [x] Implemented immediate visual confirmation flash on move arrival square:
  - **Arrival Registration Feedback**: Whenever a physical move or opponent mirror move is registered on the physical board, triggers an instant 450ms exponential-decay flash on the destination square.
  - **Color Coding**: High-contrast vibrant emerald green (`COLOR_MOVE_CONFIRM = (48, 255, 128)`) for standard quiet moves; radiant ruby crimson (`COLOR_CAPTURE_CONFIRM = (255, 32, 64)`) for capture moves.
- [x] Implemented distinct color differentiation for legal capture targets:
- [x] Implemented choreographed 2-phase castling animation and physical dual-piece mirror tracking:
  - **2-Phase Choreography**: For Kingside and Queenside castling (e1g1, e1c1, e8g8, e8c8), Phase 1 ($\tau \in [0.0, 0.5]$) animates the King's 2-square move with destination flare, and Phase 2 ($\tau \in [0.5, 1.0]$) animates the Rook's move with destination flare (`render_castle_trace()`).
  - **Player & Opponent Symmetry**:
    - When the opponent castles, both King and Rook moves are animated in sequence and 4 squares are illuminated until both pieces are physically mirrored.
- [x] Implemented Live Perimeter Evaluation Bar & Blunder Guard (Color-Coded Move Quality):
  - **Asynchronous Coach Engine (`Raspberry/app/coach_engine.py`)**: Real-time position analysis with multi-PV candidate evaluation, logistic win probability ($W = \frac{100}{1 + 10^{-cp / 400}}$), move delta classification (`best` $\le 10$ cp, `good` $\le 50$ cp, `inaccuracy` $\le 150$ cp, `blunder` $> 150$ cp), FEN caching, and graceful offline heuristic fallback.
  - **Physical LED File 'h' Perimeter Eval Bar (`app/board_state.py`)**: Ranks 1–8 along File 'h' (Strip 2, row 7) continuously render a smooth White vs Black win chance gauge when enabled during AI matches.
  - **Blunder Guard Destination Color Tiers**: When a piece is physically lifted or selected on the digital board during an AI match, destination squares are dynamically illuminated in Emerald Green (`BEST`), Cyan (`GOOD`), Amber (`INACCURACY`), or Crimson (`BLUNDER`).
  - **Strict Fair-Play Invariant**: All coaching hints and live evaluation bars are strictly active only in matches against Stockfish AI, and hard-disabled in online matches against human opponents on Lichess.
- [x] Implemented Automated & Manual Lichess Victory Claiming on Opponent Disconnection:
  - **Automated Stream Countdown & Task Scheduler (`Raspberry/app/lichess_engine.py`)**: Listens to Lichess `opponentGone` NDJSON events. When an opponent leaves, tracks remaining seconds (`claimWinInSeconds`) and automatically claims victory via `POST /api/board/game/{game_id}/claim-victory` as soon as the waiting window expires without requiring browser intervention.
  - **Reconnection & Lifecycle Task Cancellation**: Seamlessly cancels pending auto-claim timers if the opponent returns before the timer elapses, or if the game finishes, is resigned, or is aborted.
  - **Real-Time WebSocket State**: Streams `opponent_gone: { gone: bool, claim_win_in: number }` across `/ws/state`.
  - **REST API Endpoints (`Raspberry/app/main.py`)**: Added `POST /api/lichess/claim-victory` and `POST /api/game/claim-victory`.
  - **React UI Banner & Manual Claim**: Animated "Opponent Disconnected" countdown banner in the Play tab with smooth 1-second countdown and active "Claim Victory" button.
- [x] Implemented In-Loop Auto Calibration Toggle (Active by Default, Switchable In-Game):
  - **Dynamic Baseline Drift Gating (`Raspberry/board_hardware.py`)**: Gated the continuous background analog baseline drift compensation on `settings["in_loop_calibration"]` (defaults to `True`). When disabled, baseline drift calculations are suppressed and static baselines are preserved.
  - **FastAPI & REST Persistence (`Raspberry/app/main.py`)**: Added `in_loop_calibration` to `ThresholdSettings` model and `POST /api/board/settings` with auto-save to `board_settings.json`.
  - **React UI In-Game Switch (`Raspberry/frontend/src/App.tsx`)**: Added an accessible **"In-Loop Auto Calibration"** toggle switch in both the **Play Tab** (for live adjustments during ongoing matches) and the **Debug Tab** (in the Initial Pieces Detection panel), with full local storage caching and server state synchronization.
- [x] Implemented Single-Square Baseline Calibration on Left-Click (Replaced Highlight Feature):
  - **Individual Square Baseline Setting (`Raspberry/board_hardware.py`)**: Added `set_square_baseline(col, row, value)` to immediately adopt the current ADC reading as that square's baseline and flush any stale drift history.
  - **REST API (`Raspberry/app/main.py`)**: Added `POST /api/board/calibrate_square` taking `{ col, row, value? }` with atomic persistence to `board_settings.json`.
  - **React UI Integration (`Raspberry/frontend/src/App.tsx`)**: Left-clicking any square in the **Play tab sensor matrix overlay** or **Debug tab physical ADC matrix** immediately calibrates that specific square's baseline to its live reading and displays a confirmation status toast.
- [x] Resolved Raspberry Pi `git pull` hanging issue:
  - **SSH Firewall / Outbound Block**: Identified that outbound SSH port 22 and 443 connections on the Raspberry Pi's local network timed out when connecting to GitHub.
  - **Remote Switch to HTTPS**: Reconfigured `origin` remote URL in `~/chess_git` on the Pi to HTTPS (`https://github.com/Niorb/Smart-Chess-Board.git`), enabling instant pulls.
  - **Physical Tracker & Test Isolation Fixes**: Initialized `_last_synced_move_uci` in `PhysicalMoveTracker.__init__` and isolated `test_board_hardware.py` in-loop calibration unit tests. Verified all 170 unit and integration tests passing on the physical Pi.
- [x] Implemented In-Game Safety Guardrails & Capture-in-Progress Handling:
  - **Live State Guardrail Synchronization (`Raspberry/app/setup_validator.py`)**: Continuously compares physical board matrix against digital engine state (`lichess_engine.board`), intelligently filtering out legitimate transient states (lifted friendly piece, legal capture destinations, pending capture target, pending opponent mirror, castling rook movement, and in-flight move locks).
  - **Capture-First State Machine (`Raspberry/app/physical_tracker.py`)**: Seamlessly supports player lifting opponent's piece first when taking a piece. Identifies valid candidate friendly attackers, preserves capture intent, supports lifting candidate attacker or direct piece placement, and cancels intent if the opponent piece is returned.
  - **Dynamic LED Animations & Alerts (`Raspberry/app/led_animations.py` & `board_state.py`)**:
    - **Capture-in-Progress Aura**: Sinusoidal pulsing radiant ruby aura (`(255, 32, 64)`) on capture destination with warm golden breathing glow (`(220, 160, 20)`) on candidate attacking squares.
    - **Guardrail Mismatch Feedback**: Rapid amber pulse (`(204, 120, 0)`) on missing piece squares and alert crimson pulse (`(204, 0, 0)`) on unexpected piece squares.
  - **Frontend UI Overlays & Alerts (`Raspberry/frontend/src/App.tsx` & `useBoardState.ts`)**: Real-time "Capture in Progress" banner, "Board State Mismatch" alert banner, and virtual chessboard square highlight rings/badges.
  - **Unit Test Coverage (`Raspberry/tests/`)**: Added test suites in `test_setup_validator.py`, `test_physical_tracker.py`, `test_board_state.py`, and `test_led_animations.py`.

## Task Backlog

## Active Blockers
- None


