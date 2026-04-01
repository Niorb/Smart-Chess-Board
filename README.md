# Smart Chess Board

An intelligent chess board that automatically detects piece movements using Hall effect sensors and integrates with [chess.com](https://www.chess.com) for online gameplay. Press a physical button, get matched with an opponent, and see your assigned color flash on the board's LED strip — all hands-free.

Currently a **4x4 prototype**, designed to scale to a full 8x8 board with no code changes.

## How It Works

Each square has a **digital Hall effect sensor** underneath. Neodymium magnets glued into chess piece bases trigger the sensors when placed on a square. Two **CD74HC4067 multiplexer** chips route 16 sensors through just 9 GPIO pins. A **WS2812B LED strip** in serpentine layout under the board provides visual feedback.

The system has two phases:

### Phase 1: Game Seeking (Functional)

1. Press the physical **seek button** (GPIO 26)
2. A headless **Chromium browser** (via Playwright) navigates to chess.com and starts matchmaking
3. LEDs animate a **blue chase** around the board perimeter while searching
4. Game found — LEDs flash **white** (you play White) or **green** (you play Black)
5. Press the button again during search to **cancel**

Session cookies persist across runs, so you only log in once.

### Phase 2: Board Scanning (Standalone)

The board scanner detects which pieces are on which squares in real time:
- Tracks piece **identity** (type + color) using a known starting position and lift/place detection
- Lights up squares with LEDs when pieces are lifted or placed
- Outputs a live board state to the terminal

Phase 2 code is written and working. `interactive_game.py` connects board-reading and move-clicking into a playable terminal session — the remaining step is wiring the physical Hall sensor board state into that loop.

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
| LED Strip DIN | GPIO 10 | Output (SPI0 MOSI) |
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

### Hardware Notes

- Hall effect sensors are **active-low**: `gpio_read() == 0` means a magnet is present.
- After each scan, the multiplexer code deselects both MUXes to channel `5`, which is treated as an unused channel.
- The board uses serpentine LED indexing: even rows map left-to-right, odd rows right-to-left.
- `Raspberry/hardware_test.py` and `Raspberry/smart_chess_board.py` are currently **not aligned** on LED topology:
  - `Raspberry/smart_chess_board.py` assumes **1 LED per square** for a total of 16 LEDs on a 4x4 board.
  - `Raspberry/hardware_test.py` assumes **2 LEDs per square** for a total of 32 LEDs on a 4x4 board.
  - Check which file you are editing before changing LED mapping or LED counts.

## Software Setup

### Prerequisites

- Raspberry Pi 4 running Raspberry Pi OS 64-bit (Bookworm or newer)
- Python 3.9+
- Hardware wired per the wiring guide

### Installation

```bash
sudo apt update
pip3 install playwright lgpio rpi-ws281x
playwright install chromium
```

**Enable SPI** (required for LED strip without root):

```bash
sudo raspi-config nonint do_spi 0
```

**Permissions** (add your user to the `gpio` and `spi` groups, then reboot):

```bash
sudo usermod -a -G gpio,spi $USER
sudo reboot
```

### Verify Installation

```bash
python3 -c "import lgpio; h = lgpio.gpiochip_open(0); print('lgpio OK'); lgpio.gpiochip_close(h)"
python3 -c "from rpi_ws281x import PixelStrip; print('rpi_ws281x OK')"
python3 -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

## Usage

All scripts require **sudo** (GPIO and PWM access).

### First-Time Login

You only need to do this once. A browser window opens directly — no second terminal needed.

```bash
sudo python3 Raspberry/playwright_chesscom/game_seeker.py --first-login
```

1. A Chromium window opens automatically to chess.com
2. Log in to chess.com in that window
3. Press **Enter** in the terminal — the session is saved and the browser relaunches headless

### Run the Game Seeker

```bash
sudo python3 Raspberry/playwright_chesscom/game_seeker.py
```

The browser runs headless (invisible). Press the physical button to seek a game.

### Interactive Terminal Chess

Play a game directly from the terminal — no button or LEDs needed. The browser can run headless or visible.

```bash
python3 Raspberry/playwright_chesscom/interactive_game.py
python3 Raspberry/playwright_chesscom/interactive_game.py --visible        # show the browser
python3 Raspberry/playwright_chesscom/interactive_game.py --time "10 min"  # pick a time control
```

The script walks through each step with Enter-key confirmation:
1. Launches the browser and verifies login
2. Navigates to the play page
3. Opens the time control dropdown and selects the chosen format
4. Clicks Play and waits for an opponent (polls for the resign button)
5. Prints the board and your color
6. **White:** prompts for a move (`e2 e4` format) and clicks it on the board
7. **Black:** polls the board every 0.5 s for the opponent's move, then prompts for yours

Ctrl+C exits cleanly at any point.

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
| Dim white breathing pulse | Idle (online) — system is running |
| Blue chase around perimeter | Searching for a game |
| White flash x3 | Game found — you play as **White** |
| Green flash x3 | Game found — you play as **Black** |
| Red flash x1 | Search cancelled |
| Red flash x3 | Error — session expired, network issue, or timeout |

## Button Controls

| Action | What happens |
|--------|-------------|
| **Press once** (while idle) | Starts searching for a game |
| **Press once** (while searching) | Cancels the search |
| **Ctrl+C** (in terminal) | Stops the program, turns off LEDs |

## Configuration

All settings live in [`Raspberry/playwright_chesscom/chesscom_config.py`](Raspberry/playwright_chesscom/chesscom_config.py):

- **GPIO pins** — button, LED strip
- **LED colors and timing** — animation speeds, flash counts, brightness
- **Time control** — which chess.com time format to select (default: "10 min")
- **Locators** — how chess.com UI elements are identified

### Updating Locators

`chesscom_config.py` uses Playwright's semantic locator API instead of fragile CSS paths. Elements are found by their **ARIA role + visible text label**, so they survive DOM restructuring as long as the button text doesn't change. Login detection uses a URL check (chess.com redirects to `/login` when unauthenticated) — no DOM element needed.

If chess.com updates their UI and something stops working, update the corresponding entry in `LOCATORS` in `chesscom_config.py`:

| Locator key | What it targets | How it's matched |
|-------------|----------------|-----------------|
| `time_control_show_options` | Button that opens the time control dropdown | `get_by_role("button", name=...)` — update value if label changes |
| *(TIME_CONTROL)* | The specific time control option (e.g. "10 min") | `get_by_role("button", name=TIME_CONTROL)` — set via `TIME_CONTROL` config |
| `play_button` | The main "Play" button that starts matchmaking | `get_by_role("button", name=...)` |
| `cancel_search` | The cancel button that appears while searching | `get_by_role("button", name=...)` |
| `board_container` | The chess board element (appears when a game starts) | CSS ID `#board-single` — stable, unlikely to change |
| `board_flipped_class` | CSS class added to the board when you play as Black | Class name string — checked against element's `class` attribute |

To find the right label for a button: open chess.com in a browser, hover over the element — the visible text (or `aria-label` in DevTools) is what goes in `LOCATORS`.

## Session Expired?

Chess.com sessions typically last days/weeks, but if yours expires you'll see:

```
Session expired! Re-run with --first-login.
```

Plus 3 red LED flashes. To fix:

1. Run: `sudo python3 Raspberry/playwright_chesscom/game_seeker.py --first-login`
2. Log in in the browser window that opens
3. Press Enter in the terminal

## Troubleshooting

### "Could not open GPIO chip"

The script needs access to `/dev/gpiochip0`. Make sure you're running with `sudo`:

```bash
sudo python3 game_seeker.py
```

If it still fails, check that the GPIO device exists: `ls -l /dev/gpiochip0`

### Browser window doesn't appear with `--first-login`

- Make sure the RPi's display is on and the desktop environment is running
- Try running from the RPi's own terminal (not SSH) if the display server isn't forwarding
- Check `DISPLAY` environment variable: `echo $DISPLAY` (should be `:0` or similar)

### Chromium crashes on Raspberry Pi

- Check available RAM: `free -h` (Chromium needs ~300MB)
- Try adding `--disable-gpu` to the browser args in `chesscom_browser.py`
- Close other running programs to free memory

### "Could not find the Play button" / locators broken

Chess.com updated their website. Check the visible text of the broken button in a browser and update the corresponding value in the `LOCATORS` dict in `chesscom_config.py` — see the [Updating Locators](#updating-locators) section.

### Button not responding

- Verify wiring: one pin of the button to **GPIO 26**, other pin to **GND**
- Test with: `sudo python3 -c "import lgpio, time; h=lgpio.gpiochip_open(0); lgpio.gpio_claim_input(h,26,lgpio.SET_PULL_UP); [print(lgpio.gpio_read(h,26)) or time.sleep(0.5) for _ in range(10)]; lgpio.gpiochip_close(h)"`
- Should print `1` normally and `0` when pressed

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

Note: The ESP32 version handles board scanning only — the chess.com browser integration runs exclusively on the Raspberry Pi.

## Project Structure

```
Smart Chess Board/
├── Raspberry/
│   ├── playwright_chesscom/         # Active browser backend
│   │   ├── game_seeker.py           # Main entry point — button + browser + LEDs
│   │   ├── interactive_game.py      # Terminal chess session — seek, move, wait for opponent
│   │   ├── chesscom_browser.py      # Playwright wrapper — login, seek, read board, make moves
│   │   └── chesscom_config.py       # All settings — GPIO, LED, selectors, timing
│   ├── selenium_chesscom/           # Legacy (not actively maintained)
│   ├── smart_chess_board.py         # Standalone board scanner with piece tracking
│   ├── hardware_test.py             # LED + sensor diagnostic tool
│   └── WIRING_GUIDE_RPI.txt        # RPi GPIO pinout and wiring reference
├── ESP32/
│   ├── SmartChessBoard/
│   │   └── SmartChessBoard.ino      # Full board scanner sketch
│   ├── HardwareTest/
│   │   └── HardwareTest.ino         # Diagnostic sketch
│   └── WIRING_GUIDE.txt            # ESP32 wiring reference
└── README.md
```

## License

This project is provided as-is for personal and educational use.
