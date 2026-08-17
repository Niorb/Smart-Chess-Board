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
ADC_DEVIATION = 150
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
LED_BRIGHTNESS = 50
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_DMA_2 = 11
LED_INVERT = False
LED_CHANNEL = 0
LED_CHANNEL_2 = 1

# =============================================================================
# LED COLOR DEFINITIONS — (R, G, B) tuples
# =============================================================================

COLOR_OFF = (0, 0, 0)
COLOR_IDLE = (255, 255, 255)  # Dim white pulse while idle (online)
COLOR_CONNECTING = (255, 80, 0)  # Orange pulse while connecting
COLOR_CONNECTED = (0, 255, 0)  # Green flash — connected
COLOR_SEARCHING = (0, 0, 255)  # Blue chase while seeking a game
COLOR_FOUND_WHITE = (255, 255, 255)  # White flash — playing White
COLOR_FOUND_BLACK = (0, 255, 0)  # Green flash — playing Black
COLOR_CANCELLED = (255, 0, 0)  # Red flash — search cancelled
COLOR_ERROR = (255, 0, 0)  # Red flash — error occurred

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
