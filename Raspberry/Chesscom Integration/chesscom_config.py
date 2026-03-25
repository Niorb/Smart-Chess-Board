"""
chesscom_config.py

Centralized configuration for the chess.com browser integration (Selenium).
All DOM selectors, GPIO pins, LED colors, and timing constants live here.

When chess.com updates their UI, only this file needs editing.
To find new selectors: open chess.com in a browser, press F12 (DevTools),
right-click elements -> Inspect, and note their CSS selectors.
"""

# =============================================================================
# GPIO
# =============================================================================

BUTTON_PIN = 26                # BCM pin for "seek game" button
BUTTON_DEBOUNCE_MS = 500       # Ignore presses within this window

# =============================================================================
# LED STRIP (must match smart_chess_board.py / hardware_test.py)
# =============================================================================

BOARD_ROWS = 4
BOARD_COLS = 4
LED_PIN        = 18            # GPIO 18 (PWM0) — required by rpi_ws281x
NUM_LEDS       = BOARD_ROWS * BOARD_COLS
LED_BRIGHTNESS = 50
LED_FREQ_HZ    = 800000
LED_DMA        = 10
LED_INVERT     = False
LED_CHANNEL    = 0

# =============================================================================
# LED PATTERNS — (R, G, B) tuples
# =============================================================================

COLOR_CONNECTING    = (255, 80, 0)       # Orange pulse while browser launches
COLOR_CONNECTED     = (0, 255, 0)       # Green flash — connected & logged in
COLOR_SEARCHING     = (0, 0, 255)       # Blue chase while seeking a game
COLOR_FOUND_WHITE   = (255, 255, 255)   # White flash — you play White
COLOR_FOUND_BLACK   = (0, 255, 0)       # Green flash — you play Black
COLOR_CANCELLED     = (255, 0, 0)       # Red flash — search cancelled
COLOR_ERROR         = (255, 0, 0)       # Red flash — error occurred

CONNECT_PULSE_STEP_S = 0.03  # Delay between brightness steps during pulse
SEARCH_CHASE_DELAY_S = 0.15  # Delay between LED chase steps during search
FLASH_ON_S           = 0.3   # Duration of LED on during flash
FLASH_OFF_S          = 0.3   # Duration of LED off during flash
FLASH_COUNT_FOUND    = 3     # Number of flashes when game found
FLASH_COUNT_ERROR    = 3     # Number of flashes on error
FLASH_COUNT_CANCEL   = 1     # Number of flashes on cancel
FLASH_COUNT_CONNECT  = 2     # Number of flashes on successful connection

# =============================================================================
# SELENIUM / BROWSER
# =============================================================================

USER_DATA_DIR       = "./chesscom_session"
CHESS_COM_PLAY_URL  = "https://www.chess.com/play/online"
WINDOW_SIZE         = "1280,720"
GAME_SEARCH_TIMEOUT = 120   # 2 minutes max wait for a match (seconds)
POLL_INTERVAL       = 0.5   # How often to check for game found (seconds)

# =============================================================================
# TIME CONTROL
# =============================================================================

# The text label of the time control to select on chess.com's play page.
# Examples: "1 min", "3 min", "5 min", "10 min", "15 | 10", "30 min"
TIME_CONTROL = "10 min"

# =============================================================================
# DOM SELECTORS
# =============================================================================
# These MUST be filled in by manually inspecting chess.com's DOM.
# Open chess.com → F12 → Inspect the elements below.
#
# Use CSS selectors (e.g., "div.board", "#board-vs-personalities").
#
# How to inspect:
#   1. Log in to chess.com in any browser
#   2. Navigate to /play/online
#   3. Open DevTools (F12)
#   4. Right-click on each element below → Inspect
#   5. Copy the CSS selector or note the class/id
#   6. Replace "PLACEHOLDER" with the real selector
#
# When chess.com updates their UI, re-inspect and update these values.

SELECTORS = {
    # Element visible ONLY when logged in (e.g., user avatar, profile link)
    "logged_in_indicator": "#sidebar-main-menu > a:nth-child(9)",

    # The time control button/option matching TIME_CONTROL text
    "time_control_button": "#board-layout-sidebar > div.sidebar-content > div.new-game-component > div.new-game-primary > div > div:nth-child(4) > div:nth-child(2) > div.time-selector-field-component > button:nth-child(1)",

    # The main "Play" button that starts matchmaking
    "play_button": "#board-layout-sidebar > div.sidebar-content > div.new-game-component > div.new-game-primary > button",

    # Indicator visible while searching for an opponent
    "searching_indicator": "#toaster-center > div > div > div.toaster-controller-toast-body > div > div.composable-toast-content-container",

    # Button to cancel matchmaking (appears during search)
    "cancel_search": "#board-layout-sidebar > div.sidebar-content > div > div.outgoing-challenges-content > div > button",

    # The board container element (visible = game has started)
    "board_container": "#board-single",

    # CSS class on the board element when you play as Black (board is flipped)
    # This is a CLASS NAME, not a full selector (e.g., "flipped")
    "board_flipped_class": "flipped",
}
