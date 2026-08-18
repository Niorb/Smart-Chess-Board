"""
app/config.py

Centralized configuration for the Smart Chess Board system.
Defines matrix dimensions, serial parameters, GPIO pins, LED strips, colors, and timings.
"""

# =============================================================================
# SERIAL / ANALOG (ESP32)
# =============================================================================

SERIAL_PORT = "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0"
BAUD_RATE = 921600
ADC_BASELINE = 1550
ADC_DEVIATION = 180
ANALOG_THRESHOLD = 2000  # Legacy compatibility

# =============================================================================
# GPIO PINS
# =============================================================================

BUTTON_PIN = 26  # BCM pin for "seek game" button
BUTTON_DEBOUNCE_MS = 500  # Debounce window in milliseconds

# =============================================================================
# LED STRIP SPECIFICATIONS
# =============================================================================

BOARD_ROWS = 8
BOARD_COLS = 8
LED_ROWS = 8
LED_COLS = 8
LED_PIN = 23  # ESP32 GPIO 23 — Strip 1 (files a-d)
LED_PIN_2 = 22  # ESP32 GPIO 22 — Strip 2 (files e-h)
LEDS_PER_STRIP = 76
LED_STRIP_COUNT = 2
NUM_LEDS = LEDS_PER_STRIP * LED_STRIP_COUNT  # 152 total
LED_BRIGHTNESS = 40  # 20% power reduction (from 50)
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_DMA_2 = 11
LED_INVERT = False
LED_CHANNEL = 0
LED_CHANNEL_2 = 1

# =============================================================================
# LED COLOR DEFINITIONS — (R, G, B) tuples (scaled for 20% power reduction)
# =============================================================================

COLOR_OFF = (0, 0, 0)
COLOR_IDLE = (204, 204, 204)  # Dim white pulse while idle (online)
COLOR_CONNECTING = (204, 64, 0)  # Orange pulse while connecting
COLOR_CONNECTED = (0, 204, 0)  # Green flash — connected
COLOR_SEARCHING = (0, 0, 204)  # Blue chase while seeking a game
COLOR_FOUND_WHITE = (204, 204, 204)  # White flash — playing White
COLOR_FOUND_BLACK = (0, 204, 0)  # Green flash — playing Black
COLOR_CANCELLED = (204, 0, 0)  # Red flash — search cancelled
COLOR_ERROR = (204, 0, 0)  # Red flash — error occurred

# Setup & Game State Layered LED Colors — (R, G, B) tuples
COLOR_SETUP_MISSING = (16, 16, 16)  # Dim white for missing starting pieces
COLOR_SETUP_MISPLACED = (28, 8, 0)  # Dim amber warning for misplaced pieces during setup
COLOR_PIECE_LIFTED = (144, 80, 0)  # Amber / Gold for lifted piece origin
COLOR_LEGAL_TARGET = (0, 24, 48)  # Subtle deep cyan for legal quiet target dots
COLOR_LEGAL_CAPTURE = (64, 10, 24)  # Subtle deep ruby/rose for legal capture target dots
COLOR_OPPONENT_FROM = (176, 56, 0)  # Orange for opponent move origin
COLOR_OPPONENT_TO = (0, 112, 176)  # Cyan/blue for opponent move destination
COLOR_OPPONENT_CAPTURE = (192, 0, 32)  # Ruby red for opponent capture target square
COLOR_CHECK = (176, 0, 0)  # Red highlight on King in check
COLOR_HIGHLIGHT = (204, 64, 0)  # Orange for diagnostic highlight
COLOR_ILLEGAL = (144, 0, 0)  # Red for invalid placement
COLOR_MOVE_CONFIRM = (48, 255, 128)  # Vibrant emerald/spring green arrival confirmation flash
COLOR_CAPTURE_CONFIRM = (255, 32, 64)  # Radiant ruby/crimson capture confirmation flash

# Coach & Blunder Guard Move Quality Colors — (R, G, B) tuples (scaled 20% for power)
COLOR_MOVE_BEST = (0, 204, 76)        # Emerald Green for Best Move
COLOR_MOVE_GOOD = (0, 180, 220)       # Cyan / Sky Blue for Good Move
COLOR_MOVE_INACCURACY = (220, 160, 0) # Amber / Yellow for Inaccuracy
COLOR_MOVE_BLUNDER = (220, 24, 40)    # Crimson / Red for Blunder

# Live Evaluation Bar Colors — (R, G, B) tuples (subtle, scaled for low power)
COLOR_EVAL_WHITE = (80, 80, 100)      # Cool light tone for White advantage
COLOR_EVAL_BLACK = (10, 20, 60)       # Dim navy tone for Black advantage
COLOR_EVAL_NEUTRAL = (30, 30, 48)     # Neutral midpoint tone

# Lifecycle & Trace Animation Colors — (R, G, B) tuples
COLOR_MOVE_TRACE = (176, 16, 144)  # Vibrant magenta/violet pulse along move trajectory
COLOR_CAPTURE_TRACE = (204, 32, 64)  # High-energy rose-crimson pulse along capture trajectory
COLOR_VICTORY_GOLD = (204, 172, 0)  # Shimmering gold for victory
COLOR_VICTORY_GREEN = (0, 204, 48)  # Emerald green wave for victory
COLOR_DEFEAT_RED = (176, 0, 16)  # Crimson wave for defeat
COLOR_DRAW_BLUE = (0, 96, 204)  # Sapphire blue for draw curtain
COLOR_DRAW_WHITE = (160, 160, 204)  # Cool white for draw curtain
COLOR_SEEKING_HEAD = (140, 240, 255)  # Bright icy cyan head for seeking orbit
COLOR_SEEKING_BODY = (0, 140, 255)  # Electric blue body for seeking orbit
COLOR_SEEKING_TAIL = (0, 36, 160)  # Deep royal blue tail for seeking orbit

# =============================================================================
# ANIMATION & TIMING CONSTANTS
# =============================================================================

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

# Procedural Animation Timings (seconds)
MOVE_TRACE_PERIOD_S = 0.8  # Traversal period for move trace pulse
ANIM_CASTLE_PERIOD_S = 2.0  # Traversal period for 2-phase King + Rook castling cycle
ANIM_MOVE_CONFIRM_DURATION_S = 0.45  # Snappy 450ms exponential decay
ANIM_GAME_START_DURATION_S = 1.5  # Duration for game start radial burst
ANIM_GAME_WON_DURATION_S = 3.0  # Duration for victory celebration waves
ANIM_GAME_LOST_DURATION_S = 2.5  # Duration for defeat collapsing wave
ANIM_GAME_DRAWN_DURATION_S = 2.0  # Duration for draw curtain wave
ANIM_SEEKING_PERIOD_S = 2.8  # Full perimeter orbital period during matchmaking
ANIM_SEEKING_DURATION_S = 5.6  # Duration for one-shot seeking test animation

