# Smart Chess Board — User Guide

## 1. Prerequisites

Before using the chess.com integration, make sure you have:

- **Raspberry Pi 4** running Raspberry Pi OS 64-bit (Bookworm or newer)
- **Hardware wired** — Hall sensors, MUX chips, WS2812B LED strip, and the seek-game button on **GPIO 26** (connect one side to GPIO 26, other side to GND; the internal pull-up is enabled by software)
- **lgpio** library installed (`sudo pip3 install lgpio` or `sudo apt install python3-lgpio`)
- **Python 3.9+** installed (comes with Raspberry Pi OS)
- An **SSH client** on your laptop/PC (PuTTY, terminal, etc.)

---

## 2. Installation

Run these commands on the Raspberry Pi:

```bash
# 1. Install Chromium
sudo apt update
sudo apt install chromium-browser

# 2. Install Python libraries — pick one browser backend (or both)

# Selenium backend
sudo apt install chromium-chromedriver
sudo pip3 install selenium lgpio rpi-ws281x

# Playwright backend (alternative)
sudo pip3 install playwright lgpio rpi-ws281x
playwright install chromium
```

Verify everything works:

```bash
sudo python3 -c "import lgpio; h = lgpio.gpiochip_open(0); print('lgpio OK'); lgpio.gpiochip_close(h)"
sudo python3 -c "from rpi_ws281x import PixelStrip; print('rpi_ws281x OK')"

# Selenium
sudo python3 -c "from selenium import webdriver; print('Selenium OK')"
chromedriver --version

# Playwright
sudo python3 -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

---

## 3. First-Time Login

You only need to do this once per backend (or when your session expires). The idea is to open a regular Chromium browser that shares the same profile folder as the game seeker, so the cookies you get by logging in are reused later.

**Step 1:** Start the game seeker with the `--first-login` flag:

```bash
# Selenium backend
cd selenium_chesscom && sudo python3 game_seeker.py --first-login

# Playwright backend
cd playwright_chesscom && sudo python3 game_seeker.py --first-login
```

It will print a `chromium-browser ...` command for you.

**Step 2:** Open a **second terminal** (or SSH session) and run that command. A Chromium window opens — navigate to chess.com and log in normally.

**Step 3:** Once logged in, **close the browser**, go back to the first terminal and press **Enter**.

The script verifies the session and launches headless. You're all set!

**Why this way?** Running Chromium directly (not through Selenium/Playwright) avoids the white-screen issues on RPi. The `--user-data-dir` flag ensures the login cookies are stored in the same `chesscom_session/` folder that the browser backend reads from.

---

## 4. Daily Usage

After the first login, just run:

```bash
# Selenium backend
cd selenium_chesscom && sudo python3 game_seeker.py

# Playwright backend
cd playwright_chesscom && sudo python3 game_seeker.py
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
| **Orange** breathing pulse | Connecting — browser launching & checking login |
| **Green** flash ×2 | Connected — logged in and ready |
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

1. Run: `sudo python3 <backend>/game_seeker.py --first-login` (replace `<backend>` with `selenium_chesscom` or `playwright_chesscom`)
2. Follow the instructions — open Chromium in a second terminal, log in, close it
3. Press Enter in the first terminal

---

## 8. Troubleshooting

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

### "Could not find the Play button" / selectors broken

Chess.com updated their website. You need to re-inspect the DOM and update `chesscom_config.py`. See Section 9 below.

### Button not responding

- Verify wiring: one pin of the button to **GPIO 26**, other pin to **GND**
- Test with: `sudo python3 -c "import lgpio, time; h=lgpio.gpiochip_open(0); lgpio.gpio_claim_input(h,26,lgpio.SET_PULL_UP); [print(lgpio.gpio_read(h,26)) or time.sleep(0.5) for _ in range(10)]; lgpio.gpiochip_close(h)"`
- Should print `1` normally and `0` when pressed

---

## 9. Updating Selectors (When Chess.com Changes)

Each backend has a `chesscom_config.py` file containing CSS selectors that tell the browser automation where to find buttons and elements on chess.com. If chess.com updates their website, these may break. Update **both** config files when this happens.

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

| File / Directory | Purpose |
|------------------|---------|
| `selenium_chesscom/` | Selenium-based browser backend |
| `selenium_chesscom/game_seeker.py` | Run this — button + Selenium browser + LEDs |
| `selenium_chesscom/chesscom_config.py` | All settings and DOM selectors — edit when chess.com changes |
| `selenium_chesscom/chesscom_browser.py` | Selenium automation (session, seek, detect) |
| `playwright_chesscom/` | Playwright-based browser backend (same logic) |
| `playwright_chesscom/game_seeker.py` | Run this — button + Playwright browser + LEDs |
| `playwright_chesscom/chesscom_config.py` | All settings and DOM selectors — keep in sync with Selenium version |
| `playwright_chesscom/chesscom_browser.py` | Playwright automation (session, seek, detect) |
| `smart_chess_board.py` | Standalone board scanner with piece tracking (not used by game seeker yet) |
| `hardware_test.py` | LED and sensor test script |
| `*/chesscom_session/` | Auto-created by Chromium — stores your login cookies and profile |
