# Smart Chess Board — User Guide

## 1. Prerequisites

Before using the chess.com integration, make sure you have:

- **Raspberry Pi 4** running Raspberry Pi OS 64-bit (Bookworm or newer)
- **Hardware wired** — Hall sensors, MUX chips, WS2812B LED strip, and the seek-game button on **GPIO 26** (connect one side to GPIO 26, other side to GND; the internal pull-up is enabled by software)
- **pigpio daemon** installed and running
- **Python 3.9+** installed (comes with Raspberry Pi OS)
- An **SSH client** on your laptop/PC (PuTTY, terminal, etc.)

---

## 2. Installation

Run these commands on the Raspberry Pi:

```bash
# 1. Install Chromium and its matching chromedriver
sudo apt update
sudo apt install chromium-browser chromium-chromedriver

# 2. Install Python libraries
sudo pip3 install selenium pigpio rpi-ws281x

# 3. Enable the pigpio daemon to start on boot
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

Verify everything works:

```bash
sudo python3 -c "import pigpio; pi = pigpio.pi(); print('pigpio OK:', pi.connected); pi.stop()"
sudo python3 -c "from selenium import webdriver; print('Selenium OK')"
sudo python3 -c "from rpi_ws281x import PixelStrip; print('rpi_ws281x OK')"
chromedriver --version
```

---

## 3. First-Time Login

You only need to do this once (or when your session expires). Since the RPi has a monitor, a Chromium browser window will open directly on screen.

```bash
sudo pigpiod          # if not already running
sudo python3 game_seeker.py --first-login
```

A Chromium browser window will appear on the RPi's display. Log in to chess.com as you normally would. Once you see your dashboard/play page:

1. Go back to the terminal
2. Press **Enter**
3. You'll see "Login successful! Session saved."

**Done!** The session is now saved in the `chesscom_session/` folder. All subsequent runs use headless mode (no browser window) and reuse the saved cookies.

---

## 4. Daily Usage

After the first login, just run:

```bash
sudo python3 game_seeker.py
```

The browser runs **headless** (invisible). You'll see:

```
Launching browser (headless)...
Ready! Press the button to seek a game.
Press Ctrl+C to exit.
```

Now press the **physical button** (GPIO 26) to start searching for a game. Watch the LEDs!

---

## 5. LED Reference

| LED Pattern | Meaning |
|-------------|---------|
| All LEDs **off** | Idle — waiting for button press |
| **Blue** chase around perimeter | Searching for a game on chess.com |
| **White** flash ×3 | Game found — you play as **White** |
| **Green** flash ×3 | Game found — you play as **Black** |
| **Red** flash ×1 | Search cancelled (you pressed the button again) |
| **Red** flash ×3 | Error — session expired, network issue, or timeout |

---

## 6. Button Controls

| Action | What happens |
|--------|-------------|
| **Press once** (while idle) | Starts searching for a game |
| **Press once** (while searching) | Cancels the search |
| **Ctrl+C** (in terminal) | Stops the program, turns off LEDs |

---

## 7. Session Expired?

Chess.com sessions typically last days/weeks, but if yours expires you'll see:

```
Session expired! Re-run with --first-login.
```

Plus 3 red LED flashes. To fix:

1. Run on the RPi: `sudo python3 game_seeker.py --first-login`
2. Log in again in the browser window
3. Press Enter

---

## 8. Troubleshooting

### "Could not connect to pigpiod"

The pigpio daemon isn't running:

```bash
sudo pigpiod
# or, to auto-start on boot:
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

### Browser window doesn't appear with `--first-login`

- Make sure the RPi's display is on and the desktop environment is running
- Try running from the RPi's own terminal (not SSH) if the display server isn't forwarding
- Check `DISPLAY` environment variable: `echo $DISPLAY` (should be `:0` or similar)

### Chromium crashes on Raspberry Pi

- Check available RAM: `free -h` (Chromium needs ~300MB)
- Try adding `--disable-gpu` to the browser args in `chesscom_browser.py`
- Close other running programs to free memory

### "Could not find the Play button" / selectors broken

Chess.com updated their website. You need to re-inspect the DOM and update `chesscom_config.py`. See Section 9 below.

### Button not responding

- Verify wiring: one pin of the button to **GPIO 26**, other pin to **GND**
- Test with: `sudo python3 -c "import pigpio, time; pi=pigpio.pi(); pi.set_mode(26,pigpio.INPUT); pi.set_pull_up_down(26,pigpio.PUD_UP); [print(pi.read(26)) or time.sleep(0.5) for _ in range(10)]; pi.stop()"`
- Should print `1` normally and `0` when pressed

---

## 9. Updating Selectors (When Chess.com Changes)

The file `chesscom_config.py` contains CSS selectors that tell Selenium where to find buttons and elements on chess.com. If chess.com updates their website, these may break.

**How to find new selectors:**

1. Open chess.com in Chrome/Chromium on any computer
2. Log in and go to `/play/online`
3. Press **F12** to open DevTools
4. Right-click on the element you need → **Inspect**
5. In the Elements panel, note the element's:
   - **ID** (e.g., `#board-vs-personalities`) → use as `"#board-vs-personalities"`
   - **Class** (e.g., `class="play-button"`) → use as `".play-button"`
   - **Tag + class** (e.g., `<chess-board class="board">`) → use as `"chess-board.board"`
6. Update the corresponding entry in `SELECTORS` in `chesscom_config.py`

**Elements you need to find:**

| Selector key | What to look for |
|-------------|-----------------|
| `logged_in_indicator` | Your avatar, username, or any element that only appears when logged in |
| `time_control_button` | The button/tab for your preferred time control (e.g., "10 min") |
| `play_button` | The main "Play" button that starts matchmaking |
| `searching_indicator` | The "Searching..." text or animation during matchmaking |
| `cancel_search` | The cancel/X button that appears while searching |
| `board_container` | The chess board element (appears when a game starts) |
| `board_flipped_class` | The CSS class name added to the board when you play as Black |

**Tip:** Prefer shorter, ID-based selectors (e.g. `#board-single`) over long nth-child chains — they are more resilient to layout changes.

---

## 10. File Overview

| File | Purpose |
|------|---------|
| `game_seeker.py` | Run this — button + browser + LEDs |
| `chesscom_config.py` | All settings and DOM selectors — edit this when chess.com changes |
| `chesscom_browser.py` | Selenium automation (session, seek, detect) |
| `smart_chess_board.py` | Standalone board scanner with piece tracking (not used by game seeker yet) |
| `hardware_test.py` | LED and sensor test script |
| `chesscom_session/` | Auto-created by Chromium — stores your login cookies and profile |
