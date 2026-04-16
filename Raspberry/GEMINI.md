# Smart Chess Board - Project Context

An intelligent, physical chess board that detects piece movements using Hall effect sensors and integrates with Chess.com for online gameplay via a headless Playwright browser.

## Project Overview

- **Core Tech:** Raspberry Pi 4 (Python), ESP32 (Arduino/C++), Playwright, lgpio, rpi-ws281x.
- **Hardware Architecture:** 
  - **Sensors:** Digital Hall effect sensors (active-low) in a matrix.
  - **Multiplexing:** Two CD74HC4067 16-channel MUX chips route row/column selection to minimize GPIO usage.
  - **Feedback:** WS2812B LED strip in a **serpentine layout** provides visual cues (e.g., your turn, game found).
  - **Scalability:** Designed for a 4x4 prototype but scales to 8x8 with hardware changes only.
- **Key Features:**
  - Headless Chess.com matchmaking and gameplay.
  - Real-time physical board scanning and piece identity tracking.
  - Physical button for seeking/canceling games.
  - LED animations for game states (Connecting, Searching, White/Black found).

## Directory Structure

- `Raspberry/`: Primary Python implementation for RPi 4.
  - `playwright_chesscom/`: Browser automation and integration.
    - `chesscom_config.py`: **Central configuration** for GPIO, LEDs, and UI selectors.
    - `game_seeker.py`: Main entry point for matching via physical button.
    - `interactive_game.py`: Terminal-based chess session with full LED feedback.
    - `interactive_game_light.py`: (Experimental) Lightweight alternative using Lightpanda; currently incompatible with Chess.com due to missing WebWorker support.
  - `smart_chess_board.py`: Standalone board scanner and piece tracker.
  - `hardware_test.py`: Diagnostic tool for LEDs and sensors.
- `ESP32/`: Alternative implementation for board scanning (no browser integration).

## Development Conventions

### Configuration First
- All project-wide constants (GPIO pins, LED colors, UI locators) MUST be updated in `Raspberry/playwright_chesscom/chesscom_config.py`.
- Do not hardcode magic numbers or selectors in logic files.

### Hardware Abstraction
- `Raspberry/board_hardware.py` contains the shared logic for MUX control and board scanning. 
- Use `scan_board()` and `apply_debounce()` for all sensor-related tasks.

### LED Topology
- The board uses a **serpentine layout**:
  - Even rows (0, 2): Left-to-right.
  - Odd rows (1, 3): Right-to-left.
- **Warning:** `hardware_test.py` and `smart_chess_board.py` may differ in LED density (1 vs 2 LEDs per square). Always verify `NUM_LEDS` before modifying.

### Playwright Integration
- Uses Playwright's **semantic locators** (ARIA roles and labels) to stay resilient against Chess.com UI updates.
- Session state is persisted in `Raspberry/playwright_chesscom/chesscom_session/`.

## Key Workflows

### Setup & Installation
```bash
# Install dependencies
pip3 install playwright lgpio rpi-ws281x
playwright install chromium

# Enable SPI for LEDs (no root)
sudo raspi-config nonint do_spi 0
sudo usermod -a -G gpio,spi $USER
```

### Running the System
- **First-time login:** `python Raspberry/playwright_chesscom/game_seeker.py --first-login`
- **Main Game Seeker:** `python Raspberry/playwright_chesscom/game_seeker.py`
- **Interactive Session:** `python Raspberry/playwright_chesscom/interactive_game.py`
- **Interactive (Lightweight):** `python Raspberry/playwright_chesscom/interactive_game_light.py`
- **Hardware Diagnostics:** `python Raspberry/hardware_test.py`

### Testing & Validation
- Use `hardware_test.py` to verify wiring before running game logic.
- Use the `--visible` flag in `interactive_game.py` to debug browser interaction.

## Hardware Reference (BCM Pins)
- **MUX Select:** Row (17, 27, 22), Col (5, 6, 13)
- **MUX Read:** 24
- **LED DIN:** 10 (SPI0 MOSI)
- **Seek Button:** 26 (Internal pull-up)
