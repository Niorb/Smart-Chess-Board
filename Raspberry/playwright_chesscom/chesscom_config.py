"""
chesscom_config.py

Centralized configuration for the chess.com browser integration (Playwright).
All DOM selectors, GPIO pins, LED colors, and timing constants live here.

When chess.com updates their UI, only this file needs editing.
To find new selectors: open chess.com in a browser, press F12 (DevTools),
right-click elements -> Inspect, and note their CSS selectors.
"""

# =============================================================================
# SERIAL / ANALOG (ESP32)
# =============================================================================

SERIAL_PORT = "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0"
BAUD_RATE = 921600
ADC_BASELINE = 1550
ADC_DEVIATION = 150
ANALOG_THRESHOLD = 2000  # Deprecated, keep for backwards compatibility

# =============================================================================
# GPIO
# =============================================================================

BUTTON_PIN = 26  # BCM pin for "seek game" button
BUTTON_DEBOUNCE_MS = 500  # Ignore presses within this window

# =============================================================================
# LED STRIP (must match smart_chess_board.py / hardware_test.py)
# =============================================================================

BOARD_ROWS = 8
BOARD_COLS = 8
LED_ROWS = 8
LED_COLS = 8
LED_PIN = 23  # ESP32 GPIO 23 — first strip
LED_PIN_2 = 22  # ESP32 GPIO 22 — second strip
NUM_LEDS = 144
LED_BRIGHTNESS = 50
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_DMA_2 = 11
LED_INVERT = False
LED_CHANNEL = 0
LED_CHANNEL_2 = 1


# =============================================================================
# LED PATTERNS — (R, G, B) tuples
# =============================================================================

COLOR_CONNECTING = (255, 80, 0)  # Orange pulse while browser launches
COLOR_CONNECTED = (0, 255, 0)  # Green flash — connected & logged in
COLOR_SEARCHING = (0, 0, 255)  # Blue chase while seeking a game
COLOR_FOUND_WHITE = (255, 255, 255)  # White flash — you play White
COLOR_FOUND_BLACK = (0, 255, 0)  # Green flash — you play Black
COLOR_CANCELLED = (255, 0, 0)  # Red flash — search cancelled
COLOR_ERROR = (255, 0, 0)  # Red flash — error occurred
COLOR_IDLE = (255, 255, 255)  # Dim white pulse while idle (online)

IDLE_PULSE_MAX_FRAC = 0.08  # Max brightness fraction for idle pulse (0-1)
IDLE_PULSE_STEP_S = 0.02  # Delay between brightness steps during idle pulse
IDLE_PULSE_STEPS = 80  # Number of steps per half-cycle
CONNECT_PULSE_STEP_S = 0.03  # Delay between brightness steps during pulse
SEARCH_CHASE_DELAY_S = 0.15  # Delay between LED chase steps during search
FLASH_ON_S = 0.3  # Duration of LED on during flash
FLASH_OFF_S = 0.3  # Duration of LED off during flash
FLASH_COUNT_FOUND = 3  # Number of flashes when game found
FLASH_COUNT_ERROR = 3  # Number of flashes on error
FLASH_COUNT_CANCEL = 1  # Number of flashes on cancel
FLASH_COUNT_CONNECT = 2  # Number of flashes on successful connection

# =============================================================================
# PLAYWRIGHT / BROWSER
# =============================================================================

USER_DATA_DIR = "./chesscom_session"
CHESS_COM_PLAY_URL = "https://www.chess.com/play/online"
VIEWPORT_WIDTH = 1500
VIEWPORT_HEIGHT = 1000
GAME_SEARCH_TIMEOUT = 120  # 2 minutes max wait for a match (seconds)
POLL_INTERVAL = 0.5  # How often to check for game found (seconds)
MOVE_CLICK_DELAY_S = 0.15  # Pause between source and destination click (seconds)
BROWSER_LOCALE = "en-US"  # Default locale for browser emulation/keyboard layout support


# =============================================================================
# TIME CONTROL
# =============================================================================

# The text label of the time control to select on chess.com's play page.
# Examples: "1 min", "3 min", "5 min", "10 min", "15 | 10", "30 min"
TIME_CONTROL = "10 min"


def GetCadence(time_control):
    if time_control in ["1 min", "2 min", "1 | 1", "2 | 1"]:
        return "Bullet"
    elif time_control in ["3 min", "5 min", "3 | 2"]:
        return "Blitz"
    elif time_control in ["10 min", "15 | 10", "30 min", "60 min"]:
        return "Rapid"
    else:
        return None


CADENCE = GetCadence(TIME_CONTROL)


# =============================================================================
# DOM LOCATORS
# =============================================================================
# Describes chess.com UI elements using ARIA roles and visible text labels
# rather than fragile CSS paths.
#
# When chess.com updates their UI, only these values need updating — no
# code changes required. To find the right label, open chess.com in a browser,
# hover over or inspect the target element, and look at its visible text or
# aria-label attribute.
#
# How each value is used in chesscom_browser.py:
#   plain text string → page.get_by_role("button", name=value)
#   CSS selector (#…)  → page.locator(value)   or   page.query_selector(value)
#   class name string  → element.get_attribute("class") check
#
# Login detection is handled by URL check ("/login" in page.url) — no DOM
# selector needed.
#
# The time control option button is looked up dynamically from TIME_CONTROL,
# so it has no entry here.

LOCATORS = {
    # Button that opens the time control dropdown panel.
    "logged_in_indicator": "#sidebar-main-menu > a:nth-child(10)",
    # Clocks when playing as White (white at bottom, black at top)
    "white_clock_white": "#board-layout-player-bottom > div.clock-component.clock-bottom.clock-white > span",
    "black_clock_white": "#board-layout-player-top > div.clock-component.clock-top.clock-black > span",
    # Clocks when playing as Black (board flipped: black at bottom, white at top)
    "black_clock_black": "#board-layout-player-bottom > div.clock-component.clock-bottom.clock-black > span",
    "white_clock_black": "#board-layout-player-top > div.clock-component.clock-top.clock-white.clock-player-turn > span",
    # Update "Time" if chess.com renames or relabels this button.
    # "time_control_show_options": f"{TIME_CONTROL} ({CADENCE})",  # e.g. "10 min (Rapid)",
    # Real time control option button
    # "time_control_select": TIME_CONTROL,
    # The main "Play" button that starts matchmaking.
    "play_button": "Start Game",
    # Button to cancel matchmaking (appears during search).
    "cancel_search": "Cancel",
    # The board container element (visible = game has started).
    # Stable chess.com element ID — kept as a CSS selector.
    "resign_button": "#board-layout-sidebar > div.sidebar-content > div.game-icons-container-component > button.resign-button-component > span.resign-button-label",
    "second_resign_button": "#board-layout-sidebar > div.sidebar-content > div.game-icons-container-component > div:nth-child(2) > span > button > span.resign-button-label",
    # Board container
    "board_container": "#board-single",
    # CSS class on the board element when you play as Black (board is flipped).
    # This is a CLASS NAME, not a full selector.
    "board_flipped_class": "flipped",
}
