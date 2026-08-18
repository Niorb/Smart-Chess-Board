# GEMINI.md - Smart Chess Board Master Instructions

This document defines the core architecture, development workflow, SSH deployment procedures, and hardware specifications for the Smart Chess Board project.

---

## 1. Remote Environment & SSH Deployment Workflow

> [!IMPORTANT]
> The backend, physical GPIO multiplexers, ESP32 serial communication, WS2812B LED strips, and test suites run on a physical **Raspberry Pi**.
> **STRICT RULE**: Never execute `npm` build/install commands or `pytest` suites locally. All `npm` and `pytest` operations must be executed remotely on the Raspberry Pi over SSH.

### Raspberry Pi Connection Details
- **SSH Command**: `ssh pi@pi`
- **Project Directory on Pi**: `~/chess_git`
- **Python Virtual Environment**: `source ~/venv/chess/bin/activate`

### Mandatory Post-Change Deployment Pipeline
After modifying code locally, ALWAYS execute this sequence:

1. **Stage, Commit, and Push Locally**:
   ```bash
   git add -A
   git commit -m "Description of changes"
   git push origin main
   ```
2. **SSH into the Raspberry Pi & Pull Updates**:
   ```bash
   ssh pi@pi "cd ~/chess_git && git pull origin main"
   ```
   *(Note: Local hardware calibration settings in `Raspberry/board_settings.json` are preserved).*
3. **Build Frontend (if UI or client hooks changed)**:
   ```bash
   ssh pi@pi "cd ~/chess_git/Raspberry/frontend && npm run build"
   ```
4. **Run Backend Test Suite**:
   ```bash
   ssh pi@pi "source ~/venv/chess/bin/activate && cd ~/chess_git/Raspberry && pytest -v"
   ```

---

## 2. Hardware Architecture & Sensor Polarities

### Matrix & Sensor Topology
- **Board Grid**: 8 columns (Files a–h, index `0..7`) $\times$ 8 rows (Ranks 1–8, index `0..7`).
- **Sensors**: 64 Linear Analog Hall-effect sensors read via CD74HC4067 multiplexers and a 12-bit ADC on ESP32 (GPIO 34).
- **Communication Protocol**: Binary packet request (`'B'`) over high-speed serial UART (`921600` baud).

### Magnetic Polarity Convention & Calibration Modes
- **White Pieces**: **Negative magnetic pole** (`-1` / South).
  - Expected on **Ranks 1 and 2** during initial setup.
- **Black Pieces**: **Positive magnetic pole** (`+1` / North).
  - Expected on **Ranks 7 and 8** during initial setup.
- **Empty Squares**: Neutral (`0`).
  - Expected on **Ranks 3, 4, 5, and 6**.
- **Calibration Options**:
  - *Calibrate With Pieces Placed*: Only reads the empty middle columns 3–6 (`c in 2..5`) and maps Column 3 (`c=2`) baselines to Columns 1 & 2 (`c=0, 1`) and Column 6 (`c=5`) baselines to Columns 7 & 8 (`c=6, 7`) for all rows.
  - *Force Recalibrate (Empty Board)*: Directly samples all 64 squares (requires an empty board).

### WS2812B LED Strips
- **Total LEDs**: 152 LEDs across 2 physical strips (76 LEDs per strip / 2 LEDs per square + serpentine skipped spacers).
  - **Strip 1**: Left side (Files a–d).
  - **Strip 2**: Right side (Files e–h).
- **Control Strategy**:
  - Always issue a hardware batch clear (`'C'`) prior to applying active LED updates to prevent stale/lingering LED glitches.
  - Serpentine coordinate translation is handled by `get_led_indices(rank, file)` in `Raspberry/app/led_helpers.py`.

---

## 3. Subsystem Architecture & Key Modules

| Module Path | Role & Responsibilities |
| :--- | :--- |
| [`Raspberry/app/main.py`](file:///home/robin/Smart-Chess-Board/Raspberry/app/main.py) | FastAPI backend server, `/ws/state` WebSocket broadcaster, REST API endpoints for matchmaking, moves, and board settings. |
| [`Raspberry/app/board_state.py`](file:///home/robin/Smart-Chess-Board/Raspberry/app/board_state.py) | Singleton `BoardStateManager`, background polling loop `update_loop`, debounced sensor readings, and layered LED pipeline. |
| [`Raspberry/app/setup_validator.py`](file:///home/robin/Smart-Chess-Board/Raspberry/app/setup_validator.py) | Validates starting board piece setup, detects missing pieces and polarity inversions, and guides placement with dim LEDs. |
| [`Raspberry/app/physical_tracker.py`](file:///home/robin/Smart-Chess-Board/Raspberry/app/physical_tracker.py) | Physical move state machine (piece lifts, legal targets, drops, captures, castling, promotions, illegal moves, and opponent move mirroring). |
| [`Raspberry/app/lichess_engine.py`](file:///home/robin/Smart-Chess-Board/Raspberry/app/lichess_engine.py) | Async Lichess Board API integration (NDJSON streaming, matchmaking seeks, and Stockfish AI challenges). |
| [`Raspberry/app/led_helpers.py`](file:///home/robin/Smart-Chess-Board/Raspberry/app/led_helpers.py) | `DualPixelStrip` serial wrapper, serpentine routing, color palettes, and animations. |
| [`Raspberry/board_hardware.py`](file:///home/robin/Smart-Chess-Board/Raspberry/board_hardware.py) | ESP32 serial packet parsing, dynamic baseline tracking, forced calibration, and `board_settings.json` persistence. |
| [`Raspberry/frontend/`](file:///home/robin/Smart-Chess-Board/Raspberry/frontend/) | React / Vite / TypeScript web interface with live digital board, diagnostic matrix, clock displays, and game controls. |

---

## 4. Layered LED Priority System

To prevent conflicting visual cues, `_update_leds()` applies lighting using strict layer priorities:

1. **Diagnostic & Calibration Layer (Highest)**:
   - Recalibration in progress $\rightarrow$ All LEDs OFF.
   - Sequential LED Test $\rightarrow$ Diagnostic chase animation.
   - Debug Square Highlight $\rightarrow$ Solid Orange (`COLOR_HIGHLIGHT`).
2. **Live Game Play Layer**:
   - **King in Check** $\rightarrow$ Red ring on King's square (`COLOR_CHECK`).
   - **Opponent Move Pending** $\rightarrow$ Origin square Orange (`COLOR_OPPONENT_FROM`), destination Cyan/Blue (`COLOR_OPPONENT_TO`) until physically mirrored.
   - **Player Lifted Piece** $\rightarrow$ Lifted square Gold (`COLOR_PIECE_LIFTED`), legal destination squares dim Cyan dots (`COLOR_LEGAL_TARGET`).
   - **Invalid Move Placement** $\rightarrow$ Red alert (`COLOR_ILLEGAL`).
3. **Setup & Idle Guidance Layer**:
   - **Missing Starting Squares** $\rightarrow$ Dim neutral white (`COLOR_SETUP_MISSING`, non-glaring).
   - **Misplaced / Inverted Pieces** $\rightarrow$ Dim warning amber (`COLOR_SETUP_MISPLACED`).
   - **Correctly Placed Squares** $\rightarrow$ OFF (`Color(0, 0, 0)`).
   - **Setup Complete** $\rightarrow$ All LEDs turn OFF.

---

## 5. Development Guidelines & Best Practices

- **Never Blindly Poll**: When invoking background tasks or timers, let the reactive system notify you rather than looping with `sleep`.
- **Thread Safety**: Access to serial communications (`self.ser`) must always be wrapped in `self.serial_lock` (`threading.RLock`) to avoid interleaving scan requests and LED commands.
- **Atomic Settings Updates**: Persistent hardware configuration in `board_settings.json` uses atomic writes (`.tmp` + `os.fsync` + `os.replace`).
