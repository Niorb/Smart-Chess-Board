# Smart Chess Board Agent Guide

## Scope

This repository should be treated as having only two active areas:

- Raspberry Pi board scanning and hardware validation
- Raspberry Pi chess.com integration through Playwright

Completely ignore the ESP32 code and the Selenium chess.com code. Do not document them, do not update them, and do not use them as references unless a task explicitly overrides this rule.

## Ignore Rules

When reading this repository, ignore anything excluded by `.gitignore`. The ignored paths are:

- `Raspberry/test.py`
- `Raspberry/selenium_chesscom/chesscom_session`
- `Raspberry/playwright_chesscom/chesscom_session`
- `Raspberry/chesscom_session`
- `profile.ps1`
- `CLAUDE.md`
- `*.png`
- `*.jpg`
- `*.jpeg`

This guide is based on the non-ignored files only.

## Active Files

### Core docs

- `README.md`
- `Raspberry/WIRING_GUIDE_RPI.txt`

### Board scan and hardware test

- `Raspberry/smart_chess_board.py`
- `Raspberry/hardware_test.py`

### Playwright chess.com integration

- `Raspberry/playwright_chesscom/game_seeker.py`
- `Raspberry/playwright_chesscom/chesscom_browser.py`
- `Raspberry/playwright_chesscom/chesscom_config.py`
- `Raspberry/playwright_chesscom/integration_test.py`

## Project Intent

The project is a 4x4 smart chess board prototype designed to scale to 8x8. The active Raspberry Pi implementation has two separate but related flows:

- Physical board scanning with Hall sensors, multiplexers, and LEDs
- Online game seeking on chess.com using a button, LEDs, and Playwright

The key unfinished seam is that board scanning and chess.com gameplay are not yet integrated into one move-sync pipeline.

## Board Scan Area

`Raspberry/smart_chess_board.py` is the main standalone scanner.

It does the following:

- Scans a sensor matrix through two CD74HC4067 multiplexers
- Treats Hall sensors as active-low
- Debounces per-square changes
- Tracks piece identity from a known initial position
- Detects lift/place events
- Prints board state in chess notation
- Maps board squares to LEDs using serpentine indexing

`Raspberry/hardware_test.py` is the hardware diagnostic path.

It does the following:

- Runs an LED chase test
- Scans the board live
- Mirrors sensor detections to LEDs
- Prints a simple sensor grid to the terminal

## Chess.com Area

The active online integration is `Raspberry/playwright_chesscom/`.

`game_seeker.py` is the main entry point and state machine:

- Initializes GPIO and button handling
- Starts LED status animations
- Launches a persistent Playwright Chromium session
- Verifies login state
- Starts matchmaking on button press
- Waits for a game and signals assigned color
- Cancels search if the button is pressed during matchmaking

`chesscom_browser.py` contains the browser-only logic:

- Launch and shutdown
- Persistent session storage
- Login detection
- First-login flow
- Start search
- Wait for game start
- Cancel search
- Detect whether the player is white or black

`chesscom_config.py` is the configuration source for:

- GPIO settings
- LED settings
- Time control
- Browser settings
- DOM selectors

`integration_test.py` is a selector validation utility for the Playwright path.

## Canonical References

Use these as the primary sources when making changes:

- Product and usage overview: `README.md`
- Raspberry wiring details: `Raspberry/WIRING_GUIDE_RPI.txt`
- Board scanner behavior: `Raspberry/smart_chess_board.py`
- Chess.com Playwright behavior: `Raspberry/playwright_chesscom/game_seeker.py`

## Known Caveats

- Raspberry Pi LED pin assumptions are inconsistent across the repo.
  - `README.md`, `Raspberry/smart_chess_board.py`, `Raspberry/hardware_test.py`, and Playwright config use GPIO 10.
  - `Raspberry/WIRING_GUIDE_RPI.txt` documents GPIO 18 and says `rpi_ws281x` requires PWM0.
- Raspberry Pi LED topology assumptions are inconsistent.
  - `Raspberry/smart_chess_board.py` uses 1 LED per square.
  - `Raspberry/hardware_test.py` uses 2 LEDs per square.
  - `README.md` now documents this mismatch.
- The Playwright path depends on hard-coded chess.com selectors, so UI changes can break matchmaking or login detection.
- The repository is in active iteration. Keep edits narrow and do not revert unrelated work.

## Working Rules For Future Agents

- Stay inside the active scope only:
  - `Raspberry/smart_chess_board.py`
  - `Raspberry/hardware_test.py`
  - `Raspberry/playwright_chesscom/*`
  - related Raspberry Pi documentation
- Completely ignore:
  - `ESP32/*`
  - `Raspberry/selenium_chesscom/*`
- If you change hardware assumptions, sync code and docs together.
- If you change LED behavior, confirm whether the target script expects 16 LEDs or 32 LEDs.
- If you change board dimensions, verify the initial piece layout and serpentine mapping assumptions.
- If you change chess.com automation, update selectors in `Raspberry/playwright_chesscom/chesscom_config.py` and verify whether `integration_test.py` should change too.

## Practical Commands

- `python Raspberry/smart_chess_board.py`
- `python Raspberry/hardware_test.py`
- `python Raspberry/playwright_chesscom/game_seeker.py`
- `python Raspberry/playwright_chesscom/game_seeker.py --first-login`
- `python Raspberry/playwright_chesscom/integration_test.py`
