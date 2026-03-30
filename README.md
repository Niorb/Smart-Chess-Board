# Smart Chess Board

An intelligent chess board that automatically detects piece movements using Hall effect sensors and integrates with [chess.com](https://www.chess.com) for online gameplay. Press a physical button, get matched with an opponent, and see your assigned color flash on the board's LED strip — all hands-free.

Currently a **4x4 prototype**, designed to scale to a full 8x8 board with no code changes.

## How It Works

Each square has a **digital Hall effect sensor** underneath. Neodymium magnets glued into chess piece bases trigger the sensors when placed on a square. Two **CD74HC4067 multiplexer** chips route 16 sensors through just 9 GPIO pins. A **WS2812B LED strip** in serpentine layout under the board provides visual feedback.

The system has two phases:

### Phase 1: Game Seeking (Functional)

1. Press the physical **seek button** (GPIO 26)
2. A headless **Chromium browser** (via Selenium or Playwright) navigates to chess.com and starts matchmaking
3. LEDs animate a **blue chase** around the board perimeter while searching
4. Game found — LEDs flash **white** (you play White) or **green** (you play Black)
5. Press the button again during search to **cancel**

Session cookies persist across runs, so you only log in once.

### Phase 2: Board Scanning (Standalone)

The board scanner detects which pieces are on which squares in real time:
- Tracks piece **identity** (type + color) using a known starting position and lift/place detection
- Lights up squares with LEDs when pieces are lifted or placed
- Outputs a live board state to the terminal

Phase 2 code is written and working but **not yet integrated** with the game seeker — the end goal is to sync physical board moves to chess.com during a game.

## Hardware

### Components

| Component | Quantity | Purpose |
|-----------|----------|---------|
| Raspberry Pi 4 Model B | 1 | Main controller |
| CD74HC4067 16-ch MUX | 2 | Row/column sensor multiplexing |
| Digital Hall effect sensors (A3144 / OH3144) | 16 (4x4) | Piece detection (active-low) |
| 10K pull-up resistors | 16 | One per sensor output |
| WS2812B LED strip | 16+ LEDs | Visual feedback (serpentine layout) |
| Momentary push button | 1 | Seek/cancel game |
| Neodymium magnets (6mm x 2-3mm) | 16 | Glued into chess piece bases |

### GPIO Pinout (Raspberry Pi 4)

| Function | BCM Pin | Direction |
|----------|---------|-----------|
| Row MUX S0 | GPIO 17 | Output |
| Row MUX S1 | GPIO 27 | Output |
| Row MUX S2 | GPIO 22 | Output |
| Col MUX S0 | GPIO 5 | Output |
| Col MUX S1 | GPIO 6 | Output |
| Col MUX S2 | GPIO 13 | Output |
| MUX Read (SIG) | GPIO 24 | Input |
| LED Strip DIN | GPIO 18 | Output (PWM0) |
| Seek Button | GPIO 26 | Input (pull-up) |

Both MUX S3 and EN pins are hardwired to GND.

### Sensor Matrix

```
        Col 0    Col 1    Col 2    Col 3
          |        |        |        |
Row 0 ─ [Hall]   [Hall]   [Hall]   [Hall]    ← Row MUX grounds one row at a time
Row 1 ─ [Hall]   [Hall]   [Hall]   [Hall]    ← Col MUX routes column to read pin
Row 2 ─ [Hall]   [Hall]   [Hall]   [Hall]    ← GPIO 24 reads HIGH (empty) or LOW (magnet)
Row 3 ─ [Hall]   [Hall]   [Hall]   [Hall]
```

Each sensor's VCC goes to 3.3V, GND goes to the row wire (via Row MUX), and output goes through a 10K pull-up to the column wire (via Col MUX).

### LED Strip Layout (Serpentine)

```
Row 0:  LED 0  →  1  →  2  →  3
                               ↓
Row 1:  LED 7  ←  6  ←  5  ←  4
        ↓
Row 2:  LED 8  →  9  → 10  → 11
                               ↓
Row 3:  LED 15 ← 14  ← 13  ← 12
```

For detailed wiring instructions, see [`Raspberry/WIRING_GUIDE_RPI.txt`](Raspberry/WIRING_GUIDE_RPI.txt).

## Software Setup

### Prerequisites

- Raspberry Pi 4 running Raspberry Pi OS 64-bit (Bookworm or newer)
- Python 3.9+
- Hardware wired per the wiring guide

### Installation

Choose one browser backend (or install both):

```bash
sudo apt update

# Selenium backend
sudo apt install chromium-browser chromium-chromedriver
sudo pip3 install selenium lgpio rpi-ws281x

# Playwright backend (alternative)
sudo pip3 install playwright lgpio rpi-ws281x
playwright install chromium
```

### Verify Installation

```bash
sudo python3 -c "import lgpio; h = lgpio.gpiochip_open(0); print('lgpio OK'); lgpio.gpiochip_close(h)"
sudo python3 -c "from rpi_ws281x import PixelStrip; print('rpi_ws281x OK')"

# Selenium
sudo python3 -c "from selenium import webdriver; print('Selenium OK')"
chromedriver --version

# Playwright
sudo python3 -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

## Usage

All scripts require **sudo** (GPIO and PWM access).

### First-Time Login

You only need to do this once (per backend). It opens a real Chromium window so you can log in to chess.com — the cookies are saved and reused by the headless browser.

```bash
# Selenium backend
sudo python3 Raspberry/selenium_chesscom/game_seeker.py --first-login

# Playwright backend
sudo python3 Raspberry/playwright_chesscom/game_seeker.py --first-login
```

1. A `chromium-browser ...` command is printed — run it in a **second terminal**
2. Log in to chess.com in the browser window
3. Close the browser, then press **Enter** in the first terminal

### Run the Game Seeker

```bash
# Selenium backend
sudo python3 Raspberry/selenium_chesscom/game_seeker.py

# Playwright backend
sudo python3 Raspberry/playwright_chesscom/game_seeker.py
```

The browser runs headless (invisible). Press the physical button to seek a game.

### Run the Board Scanner

```bash
sudo python3 Raspberry/smart_chess_board.py
```

Displays a live board state in the terminal and mirrors sensor activity to the LED strip.

### Hardware Diagnostics

```bash
sudo python3 Raspberry/hardware_test.py
```

Runs an LED chase test followed by a live sensor monitor — useful for verifying wiring.

## LED Reference

| Pattern | Meaning |
|---------|---------|
| Orange breathing pulse | Connecting — browser launching |
| Green flash x2 | Connected — logged in and ready |
| All LEDs off | Idle — waiting for button press |
| Dim white breathing pulse | Idle (online) — system is running |
| Blue chase around perimeter | Searching for a game |
| White flash x3 | Game found — you play as **White** |
| Green flash x3 | Game found — you play as **Black** |
| Red flash x1 | Search cancelled |
| Red flash x3 | Error — session expired, network issue, or timeout |

## Configuration

Each backend has its own config file with the same settings:

- [`Raspberry/selenium_chesscom/chesscom_config.py`](Raspberry/selenium_chesscom/chesscom_config.py)
- [`Raspberry/playwright_chesscom/chesscom_config.py`](Raspberry/playwright_chesscom/chesscom_config.py)

Settings include:

- **GPIO pins** — button, LED strip
- **LED colors and timing** — animation speeds, flash counts, brightness
- **Time control** — which chess.com time format to select (default: "10 min")
- **CSS selectors** — DOM selectors for chess.com elements

### Updating CSS Selectors

Chess.com occasionally updates their UI, which breaks the selectors. Update **both** config files when this happens. To fix:

1. Open chess.com in a browser and go to `/play/online`
2. Press **F12** to open DevTools
3. Right-click the target element and select **Inspect**
4. Update the corresponding entry in the `SELECTORS` dict in `chesscom_config.py`

## Scaling to 8x8

The board scales from 4x4 to 8x8 with hardware changes only — no code modifications needed:

1. Set `BOARD_ROWS = BOARD_COLS = 8` in the Python files
2. Wire 48 additional Hall sensors + pull-up resistors to rows/cols 4–7
3. Connect MUX channels C4–C7 for additional rows and columns
4. Extend the LED strip to 64 LEDs
5. Use an external 5V power supply for the LED strip (64 LEDs draw too much from the Pi)

Same 9 GPIO pins. Same 2 MUX chips.

## ESP32 Alternative

An alternative implementation using an **ESP32-WROOM-32** is available in the [`ESP32/`](ESP32/) directory:

- [`ESP32/SmartChessBoard/SmartChessBoard.ino`](ESP32/SmartChessBoard/SmartChessBoard.ino) — Full board scanner
- [`ESP32/HardwareTest/HardwareTest.ino`](ESP32/HardwareTest/HardwareTest.ino) — LED + sensor diagnostics

Upload via Arduino IDE with an ESP32 board selected. See [`ESP32/WIRING_GUIDE.txt`](ESP32/WIRING_GUIDE.txt) for pin assignments (different from RPi).

Note: The ESP32 version handles board scanning only — the chess.com browser integration (Selenium/Playwright) runs exclusively on the Raspberry Pi.

## Project Structure

```
Smart Chess Board/
├── Raspberry/
│   ├── selenium_chesscom/
│   │   ├── game_seeker.py        # Main entry point — button + browser + LEDs
│   │   ├── chesscom_browser.py   # Selenium wrapper — login, seek, detect color
│   │   └── chesscom_config.py    # All settings — GPIO, LED, selectors, timing
│   ├── playwright_chesscom/
│   │   ├── game_seeker.py        # Main entry point — same logic, Playwright API
│   │   ├── chesscom_browser.py   # Playwright wrapper — login, seek, detect color
│   │   └── chesscom_config.py    # All settings — same as Selenium version
│   ├── smart_chess_board.py      # Standalone board scanner with piece tracking
│   ├── hardware_test.py          # LED + sensor diagnostic tool
│   ├── USER_GUIDE.md             # Detailed user guide
│   └── WIRING_GUIDE_RPI.txt     # RPi GPIO pinout and wiring reference
├── ESP32/
│   ├── SmartChessBoard/
│   │   └── SmartChessBoard.ino   # Full board scanner sketch
│   ├── HardwareTest/
│   │   └── HardwareTest.ino      # Diagnostic sketch
│   └── WIRING_GUIDE.txt         # ESP32 wiring reference
└── README.md
```

## License

This project is provided as-is for personal and educational use.
