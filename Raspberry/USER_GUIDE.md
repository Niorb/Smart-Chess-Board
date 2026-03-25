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
# 1. Install Python libraries
sudo pip3 install pigpio rpi-ws281x playwright

# 2. Install Chromium for Playwright (downloads the ARM64 build)
sudo python3 -m playwright install chromium

# 3. Install system dependencies for Chromium
sudo python3 -m playwright install-deps

# 4. Enable the pigpio daemon to start on boot
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

Verify everything works:

```bash
sudo python3 -c "import pigpio; pi = pigpio.pi(); print('pigpio OK:', pi.connected); pi.stop()"
sudo python3 -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
sudo python3 -c "from rpi_ws281x import PixelStrip; print('rpi_ws281x OK')"
```

---

## 3. First-Time Login

Since the Raspberry Pi is headless (no monitor), you need to use **SSH X11 forwarding** to see the browser window on your laptop for the first login.

### Windows

1. Install **VcXsrv** (https://sourceforge.net/projects/vcxsrv/) or **Xming**
2. Start VcXsrv with default settings (click Next → Next → Finish)
3. Connect via SSH with X11 forwarding enabled:
   - **PuTTY:** Connection → SSH → X11 → check "Enable X11 forwarding"
   - **Windows Terminal / PowerShell:**
     ```bash
     ssh -X robin@<your-rpi-ip>
     ```

### macOS

1. Install **XQuartz** (https://www.xquartz.org/)
2. Log out and back in after installation
3. Connect via SSH:
   ```bash
   ssh -X robin@<your-rpi-ip>
   ```

### Linux

No extra software needed. Just connect:

```bash
ssh -X robin@<your-rpi-ip>
```

### Run the first login

Once connected via SSH with X11 forwarding:

```bash
sudo pigpiod          # if not already running
sudo python3 game_seeker.py --first-login
```

A Chromium browser window will appear **on your laptop screen**. Log in to chess.com as you normally would. Once you see your dashboard/play page:

1. Come back to the terminal
2. Press **Enter**
3. You'll see "Login successful! Session saved."

**Done!** The session is now saved. You won't need to log in again unless the session expires.

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

1. Connect via SSH with X11 forwarding (see Section 3)
2. Run: `sudo python3 game_seeker.py --first-login`
3. Log in again in the browser window
4. Press Enter

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

### X11 forwarding not working (no browser window appears)

- Make sure your SSH connection uses `-X` flag
- On the RPi, check that X11 forwarding is enabled:
  ```bash
  grep X11Forwarding /etc/ssh/sshd_config
  # Should show: X11Forwarding yes
  ```
  If not, edit the file and restart SSH: `sudo systemctl restart sshd`
- On Windows, make sure VcXsrv/Xming is running **before** you SSH in
- On macOS, make sure XQuartz is installed and you logged out/in after install

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

The file `chesscom_config.py` contains CSS selectors that tell Playwright where to find buttons and elements on chess.com. If chess.com updates their website, these may break.

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

**Tip:** Use Playwright's text selectors for resilience: `"text=Play"` matches any element containing the text "Play". These survive CSS class changes.

---

## 10. File Overview

| File | Purpose |
|------|---------|
| `game_seeker.py` | Run this — button + browser + LEDs |
| `chesscom_config.py` | All settings and DOM selectors — edit this when chess.com changes |
| `chesscom_browser.py` | Playwright automation (session, seek, detect) |
| `smart_chess_board.py` | Standalone board scanner with piece tracking (not used by game seeker yet) |
| `hardware_test.py` | LED and sensor test script |
| `chesscom_session/` | Auto-created — stores your chess.com login cookies |
