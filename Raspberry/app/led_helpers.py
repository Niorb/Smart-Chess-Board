"""
app/led_helpers.py

Shared WS2812B LED strip helpers for the Smart Chess Board.
Provides DualPixelStrip wrapper for serial-based LED control on the ESP32 coprocessor,
serpentine LED index routing for the physical 8x8 chessboard, and animation routines.
"""

import logging

logger = logging.getLogger("smart-chess-app.led")

try:
    from app.config import (
        COLOR_AZURE,
        COLOR_BOARD_READY_AMBIENT,
        COLOR_BOARD_READY_PRIMARY,
        COLOR_BOARD_READY_SECONDARY,
        COLOR_CAPTURE_AURA_ATTACKER,
        COLOR_CAPTURE_AURA_TARGET,
        COLOR_CAPTURE_CONFIRM,
        COLOR_CAPTURE_TRACE,
        COLOR_CHECK,
        COLOR_CLOCK_CRIT,
        COLOR_CLOCK_OK,
        COLOR_CLOCK_WARN,
        COLOR_DAY_INDICATOR,
        COLOR_DEFEAT_RED,
        COLOR_DRAW_BLUE,
        COLOR_DRAW_EQUILIBRIUM,
        COLOR_DRAW_PEARL,
        COLOR_DRAW_SAPPHIRE,
        COLOR_DRAW_TWILIGHT,
        COLOR_DRAW_WHITE,
        COLOR_ECLIPSE_ASH,
        COLOR_ECLIPSE_CRIMSON,
        COLOR_ECLIPSE_EMBER,
        COLOR_ECLIPSE_FLASH,
        COLOR_ECLIPSE_GARNET,
        COLOR_ECLIPSE_GOLD,
        COLOR_ECLIPSE_RUBY,
        COLOR_EVAL_BLACK,
        COLOR_EVAL_WHITE,
        COLOR_GUARDRAIL_MISSING,
        COLOR_GUARDRAIL_UNEXPECTED,
        COLOR_ILLEGAL,
        COLOR_LEGAL_CAPTURE,
        COLOR_LEGAL_TARGET,
        COLOR_MINT_EMERALD,
        COLOR_MOVE_BEST,
        COLOR_MOVE_BLUNDER,
        COLOR_MOVE_CONFIRM,
        COLOR_MOVE_GOOD,
        COLOR_MOVE_INACCURACY,
        COLOR_MOVE_TRACE,
        COLOR_NIGHT_AZURE,
        COLOR_NIGHT_BOARD_READY_AMBIENT,
        COLOR_NIGHT_BOARD_READY_PRIMARY,
        COLOR_NIGHT_BOARD_READY_SECONDARY,
        COLOR_NIGHT_CAPTURE_AURA_ATTACKER,
        COLOR_NIGHT_CAPTURE_AURA_TARGET,
        COLOR_NIGHT_CAPTURE_TRACE,
        COLOR_NIGHT_CHECK,
        COLOR_NIGHT_CLOCK_CRIT,
        COLOR_NIGHT_CLOCK_OK,
        COLOR_NIGHT_CLOCK_WARN,
        COLOR_NIGHT_DRAW_BLUE,
        COLOR_NIGHT_DRAW_EQUILIBRIUM,
        COLOR_NIGHT_DRAW_PEARL,
        COLOR_NIGHT_DRAW_SAPPHIRE,
        COLOR_NIGHT_DRAW_TWILIGHT,
        COLOR_NIGHT_ECLIPSE_CRIMSON,
        COLOR_NIGHT_ECLIPSE_EMBER,
        COLOR_NIGHT_ECLIPSE_FLASH,
        COLOR_NIGHT_ECLIPSE_GARNET,
        COLOR_NIGHT_ECLIPSE_GOLD,
        COLOR_NIGHT_ECLIPSE_RUBY,
        COLOR_NIGHT_EVAL_BLACK,
        COLOR_NIGHT_EVAL_NEUTRAL,
        COLOR_NIGHT_EVAL_WHITE,
        COLOR_NIGHT_GUARDRAIL_MISSING,
        COLOR_NIGHT_GUARDRAIL_UNEXPECTED,
        COLOR_NIGHT_ILLEGAL,
        COLOR_NIGHT_INDICATOR,
        COLOR_NIGHT_LEGAL_CAPTURE,
        COLOR_NIGHT_LEGAL_TARGET,
        COLOR_NIGHT_MINT_EMERALD,
        COLOR_NIGHT_MODE,
        COLOR_NIGHT_MOVE_BEST,
        COLOR_NIGHT_MOVE_BLUNDER,
        COLOR_NIGHT_MOVE_GOOD,
        COLOR_NIGHT_MOVE_INACCURACY,
        COLOR_NIGHT_MOVE_TRACE,
        COLOR_NIGHT_NOVELTY_FLARE,
        COLOR_NIGHT_OPPONENT_CAPTURE,
        COLOR_NIGHT_OPPONENT_FROM,
        COLOR_NIGHT_OPPONENT_TO,
        COLOR_NIGHT_PIECE_LIFTED,
        COLOR_NIGHT_PROMO_BISHOP,
        COLOR_NIGHT_PROMO_KNIGHT,
        COLOR_NIGHT_PROMO_QUEEN,
        COLOR_NIGHT_PROMO_ROOK,
        COLOR_NIGHT_PROMO_ROOT,
        COLOR_NIGHT_RESIGN_HALO,
        COLOR_NIGHT_RESIGN_PRIMARY,
        COLOR_NIGHT_RETURN_HOME,
        COLOR_NIGHT_ROYAL_VIOLET,
        COLOR_NIGHT_SEEKING_BODY,
        COLOR_NIGHT_SEEKING_HEAD,
        COLOR_NIGHT_SEEKING_TAIL,
        COLOR_NIGHT_SETUP_MISPLACED,
        COLOR_NIGHT_SETUP_MISSING,
        COLOR_NIGHT_START_BLACK_PRIMARY,
        COLOR_NIGHT_START_BLACK_SECONDARY,
        COLOR_NIGHT_TURN_BLACK,
        COLOR_NIGHT_TURN_WHITE,
        COLOR_NOVELTY_FLARE,
        COLOR_OFF,
        COLOR_OPPONENT_CAPTURE,
        COLOR_OPPONENT_DISCONNECTED,
        COLOR_OPPONENT_FROM,
        COLOR_OPPONENT_TO,
        COLOR_PIECE_LIFTED,
        COLOR_PROMO_BISHOP,
        COLOR_PROMO_KNIGHT,
        COLOR_PROMO_QUEEN,
        COLOR_PROMO_ROOK,
        COLOR_PROMO_ROOT,
        COLOR_RESIGN_HALO,
        COLOR_RESIGN_PRIMARY,
        COLOR_RETURN_HOME,
        COLOR_ROYAL_VIOLET,
        COLOR_SEEKING_BODY,
        COLOR_SEEKING_HEAD,
        COLOR_SEEKING_TAIL,
        COLOR_SETUP_MISPLACED,
        COLOR_SETUP_MISSING,
        COLOR_START_BLACK_PRIMARY,
        COLOR_START_BLACK_SECONDARY,
        COLOR_START_WHITE_PRIMARY,
        COLOR_START_WHITE_SECONDARY,
        COLOR_TURN_BLACK,
        COLOR_TURN_WHITE,
        COLOR_VICTORY_GOLD,
        COLOR_VICTORY_GREEN,
        LEDS_PER_STRIP,
        NUM_LEDS,
    )
except ImportError:
    from .config import (
        COLOR_AZURE,
        COLOR_BOARD_READY_AMBIENT,
        COLOR_BOARD_READY_PRIMARY,
        COLOR_BOARD_READY_SECONDARY,
        COLOR_CAPTURE_AURA_ATTACKER,
        COLOR_CAPTURE_AURA_TARGET,
        COLOR_CAPTURE_CONFIRM,
        COLOR_CAPTURE_TRACE,
        COLOR_CHECK,
        COLOR_CLOCK_CRIT,
        COLOR_CLOCK_OK,
        COLOR_CLOCK_WARN,
        COLOR_DAY_INDICATOR,
        COLOR_DEFEAT_RED,
        COLOR_DRAW_BLUE,
        COLOR_DRAW_EQUILIBRIUM,
        COLOR_DRAW_PEARL,
        COLOR_DRAW_SAPPHIRE,
        COLOR_DRAW_TWILIGHT,
        COLOR_DRAW_WHITE,
        COLOR_ECLIPSE_ASH,
        COLOR_ECLIPSE_CRIMSON,
        COLOR_ECLIPSE_EMBER,
        COLOR_ECLIPSE_FLASH,
        COLOR_ECLIPSE_GARNET,
        COLOR_ECLIPSE_GOLD,
        COLOR_ECLIPSE_RUBY,
        COLOR_EVAL_BLACK,
        COLOR_EVAL_WHITE,
        COLOR_GUARDRAIL_MISSING,
        COLOR_GUARDRAIL_UNEXPECTED,
        COLOR_ILLEGAL,
        COLOR_LEGAL_CAPTURE,
        COLOR_LEGAL_TARGET,
        COLOR_MINT_EMERALD,
        COLOR_MOVE_BEST,
        COLOR_MOVE_BLUNDER,
        COLOR_MOVE_CONFIRM,
        COLOR_MOVE_GOOD,
        COLOR_MOVE_INACCURACY,
        COLOR_MOVE_TRACE,
        COLOR_NIGHT_AZURE,
        COLOR_NIGHT_BOARD_READY_AMBIENT,
        COLOR_NIGHT_BOARD_READY_PRIMARY,
        COLOR_NIGHT_BOARD_READY_SECONDARY,
        COLOR_NIGHT_CAPTURE_AURA_ATTACKER,
        COLOR_NIGHT_CAPTURE_AURA_TARGET,
        COLOR_NIGHT_CAPTURE_TRACE,
        COLOR_NIGHT_CHECK,
        COLOR_NIGHT_CLOCK_CRIT,
        COLOR_NIGHT_CLOCK_OK,
        COLOR_NIGHT_CLOCK_WARN,
        COLOR_NIGHT_DRAW_BLUE,
        COLOR_NIGHT_DRAW_EQUILIBRIUM,
        COLOR_NIGHT_DRAW_PEARL,
        COLOR_NIGHT_DRAW_SAPPHIRE,
        COLOR_NIGHT_DRAW_TWILIGHT,
        COLOR_NIGHT_ECLIPSE_CRIMSON,
        COLOR_NIGHT_ECLIPSE_EMBER,
        COLOR_NIGHT_ECLIPSE_FLASH,
        COLOR_NIGHT_ECLIPSE_GARNET,
        COLOR_NIGHT_ECLIPSE_GOLD,
        COLOR_NIGHT_ECLIPSE_RUBY,
        COLOR_NIGHT_EVAL_BLACK,
        COLOR_NIGHT_EVAL_NEUTRAL,
        COLOR_NIGHT_EVAL_WHITE,
        COLOR_NIGHT_GUARDRAIL_MISSING,
        COLOR_NIGHT_GUARDRAIL_UNEXPECTED,
        COLOR_NIGHT_ILLEGAL,
        COLOR_NIGHT_INDICATOR,
        COLOR_NIGHT_LEGAL_CAPTURE,
        COLOR_NIGHT_LEGAL_TARGET,
        COLOR_NIGHT_MINT_EMERALD,
        COLOR_NIGHT_MODE,
        COLOR_NIGHT_MOVE_BEST,
        COLOR_NIGHT_MOVE_BLUNDER,
        COLOR_NIGHT_MOVE_GOOD,
        COLOR_NIGHT_MOVE_INACCURACY,
        COLOR_NIGHT_MOVE_TRACE,
        COLOR_NIGHT_NOVELTY_FLARE,
        COLOR_NIGHT_OPPONENT_CAPTURE,
        COLOR_NIGHT_OPPONENT_FROM,
        COLOR_NIGHT_OPPONENT_TO,
        COLOR_NIGHT_PIECE_LIFTED,
        COLOR_NIGHT_PROMO_BISHOP,
        COLOR_NIGHT_PROMO_KNIGHT,
        COLOR_NIGHT_PROMO_QUEEN,
        COLOR_NIGHT_PROMO_ROOK,
        COLOR_NIGHT_PROMO_ROOT,
        COLOR_NIGHT_RESIGN_HALO,
        COLOR_NIGHT_RESIGN_PRIMARY,
        COLOR_NIGHT_RETURN_HOME,
        COLOR_NIGHT_ROYAL_VIOLET,
        COLOR_NIGHT_SEEKING_BODY,
        COLOR_NIGHT_SEEKING_HEAD,
        COLOR_NIGHT_SEEKING_TAIL,
        COLOR_NIGHT_SETUP_MISPLACED,
        COLOR_NIGHT_SETUP_MISSING,
        COLOR_NIGHT_START_BLACK_PRIMARY,
        COLOR_NIGHT_START_BLACK_SECONDARY,
        COLOR_NIGHT_TURN_BLACK,
        COLOR_NIGHT_TURN_WHITE,
        COLOR_NOVELTY_FLARE,
        COLOR_OFF,
        COLOR_OPPONENT_CAPTURE,
        COLOR_OPPONENT_DISCONNECTED,
        COLOR_OPPONENT_FROM,
        COLOR_OPPONENT_TO,
        COLOR_PIECE_LIFTED,
        COLOR_PROMO_BISHOP,
        COLOR_PROMO_KNIGHT,
        COLOR_PROMO_QUEEN,
        COLOR_PROMO_ROOK,
        COLOR_PROMO_ROOT,
        COLOR_RESIGN_HALO,
        COLOR_RESIGN_PRIMARY,
        COLOR_RETURN_HOME,
        COLOR_ROYAL_VIOLET,
        COLOR_SEEKING_BODY,
        COLOR_SEEKING_HEAD,
        COLOR_SEEKING_TAIL,
        COLOR_SETUP_MISPLACED,
        COLOR_SETUP_MISSING,
        COLOR_START_BLACK_PRIMARY,
        COLOR_START_BLACK_SECONDARY,
        COLOR_START_WHITE_PRIMARY,
        COLOR_START_WHITE_SECONDARY,
        COLOR_TURN_BLACK,
        COLOR_TURN_WHITE,
        COLOR_VICTORY_GOLD,
        COLOR_VICTORY_GREEN,
        LEDS_PER_STRIP,
        NUM_LEDS,
    )

# Try to import LED hardware library — degrades gracefully on non-Pi environments
try:
    from rpi_ws281x import Color
except ImportError:
    def Color(red, green, blue, white=0):
        return (white << 24) | (red << 16) | (green << 8) | blue


# =============================================================================
# BINARY PACKET PROTOCOL & CRC-8 DEFINITIONS
# =============================================================================

HEADER_BYTES = b'\xaa\x55'

CMD_SCAN_ADC = 0x01
CMD_SET_SETTLE = 0x02
CMD_SET_LEDS = 0x10
CMD_SET_ALL = 0x11
CMD_CLEAR_LEDS = 0x12
CMD_SHOW_LEDS = 0x13
CMD_SET_AND_SHOW = 0x14

RESP_ADC_DATA = 0x81

# CRC-8-CCITT lookup table (polynomial 0x07, init 0x00)
CRC8_TABLE = [
    0x00, 0x07, 0x0E, 0x09, 0x1C, 0x1B, 0x12, 0x15, 0x38, 0x3F, 0x36, 0x31, 0x24, 0x23, 0x2A, 0x2D,
    0x70, 0x77, 0x7E, 0x79, 0x6C, 0x6B, 0x62, 0x65, 0x48, 0x4F, 0x46, 0x41, 0x54, 0x53, 0x5A, 0x5D,
    0xE0, 0xE7, 0xEE, 0xE9, 0xFC, 0xFB, 0xF2, 0xF5, 0xD8, 0xDF, 0xD6, 0xD1, 0xC4, 0xC3, 0xCA, 0xCD,
    0x90, 0x97, 0x9E, 0x99, 0x8C, 0x8B, 0x82, 0x85, 0xA8, 0xAF, 0xA6, 0xA1, 0xB4, 0xB3, 0xBA, 0xBD,
    0xC7, 0xC0, 0xC9, 0xCE, 0xDB, 0xDC, 0xD5, 0xD2, 0xFF, 0xF8, 0xF1, 0xF6, 0xE3, 0xE4, 0xED, 0xEA,
    0xB7, 0xB0, 0xB9, 0xBE, 0xAB, 0xAC, 0xA5, 0xA2, 0x8F, 0x88, 0x81, 0x86, 0x93, 0x94, 0x9D, 0x9A,
    0x27, 0x20, 0x29, 0x2E, 0x3B, 0x3C, 0x35, 0x32, 0x1F, 0x18, 0x11, 0x16, 0x03, 0x04, 0x0D, 0x0A,
    0x57, 0x50, 0x59, 0x5E, 0x4B, 0x4C, 0x45, 0x42, 0x6F, 0x68, 0x61, 0x66, 0x73, 0x74, 0x7D, 0x7A,
    0x89, 0x8E, 0x87, 0x80, 0x95, 0x92, 0x9B, 0x9C, 0xB1, 0xB6, 0xBF, 0xB8, 0xAD, 0xAA, 0xA3, 0xA4,
    0xF9, 0xFE, 0xF7, 0xF0, 0xE5, 0xE2, 0xEB, 0xEC, 0xC1, 0xC6, 0xCF, 0xC8, 0xDD, 0xDA, 0xD3, 0xD4,
    0x69, 0x6E, 0x67, 0x60, 0x75, 0x72, 0x7B, 0x7C, 0x51, 0x56, 0x5F, 0x58, 0x4D, 0x4A, 0x43, 0x44,
    0x19, 0x1E, 0x17, 0x10, 0x05, 0x02, 0x0B, 0x0C, 0x21, 0x26, 0x2F, 0x28, 0x3D, 0x3A, 0x33, 0x34,
    0x4E, 0x49, 0x40, 0x47, 0x52, 0x55, 0x5C, 0x5B, 0x76, 0x71, 0x78, 0x7F, 0x6A, 0x6D, 0x64, 0x63,
    0x3E, 0x39, 0x30, 0x37, 0x22, 0x25, 0x2C, 0x2B, 0x06, 0x01, 0x08, 0x0F, 0x1A, 0x1D, 0x14, 0x13,
    0xAE, 0xA9, 0xA0, 0xA7, 0xB2, 0xB5, 0xBC, 0xBB, 0x96, 0x91, 0x98, 0x9F, 0x8A, 0x8D, 0x84, 0x83,
    0xDE, 0xD9, 0xD0, 0xD7, 0xC2, 0xC5, 0xCC, 0xCB, 0xE6, 0xE1, 0xE8, 0xEF, 0xFA, 0xFD, 0xF4, 0xF3
]


def calc_crc8(data: bytes, initial: int = 0x00) -> int:
    """Calculates table-accelerated CRC-8-CCITT checksum (polynomial 0x07)."""
    crc = initial
    for b in data:
        crc = CRC8_TABLE[crc ^ b]
    return crc


def build_packet(cmd_id: int, payload: bytes = b'') -> bytes:
    """
    Constructs a robust binary packet frame:
    [0xAA, 0x55, CMD, LEN_LO, LEN_HI, ...PAYLOAD..., CRC8]
    CRC8 covers: [CMD, LEN_LO, LEN_HI] + PAYLOAD.
    """
    length = len(payload)
    cmd_byte = cmd_id & 0xFF
    len_bytes = bytes([length & 0xFF, (length >> 8) & 0xFF])
    crc = calc_crc8(payload, initial=calc_crc8(len_bytes, initial=CRC8_TABLE[cmd_byte]))
    return HEADER_BYTES + bytes([cmd_byte]) + len_bytes + payload + bytes([crc])


# Integer color constants for layered rendering pipeline
COLOR_INT_OFF = Color(*COLOR_OFF)
COLOR_INT_SETUP_MISSING = Color(*COLOR_SETUP_MISSING)
COLOR_INT_SETUP_MISPLACED = Color(*COLOR_SETUP_MISPLACED)
COLOR_INT_PIECE_LIFTED = Color(*COLOR_PIECE_LIFTED)
COLOR_INT_LEGAL_TARGET = Color(*COLOR_LEGAL_TARGET)
COLOR_INT_LEGAL_CAPTURE = Color(*COLOR_LEGAL_CAPTURE)
COLOR_INT_MOVE_BEST = Color(*COLOR_MOVE_BEST)
COLOR_INT_MOVE_GOOD = Color(*COLOR_MOVE_GOOD)
COLOR_INT_MOVE_INACCURACY = Color(*COLOR_MOVE_INACCURACY)
COLOR_INT_MOVE_BLUNDER = Color(*COLOR_MOVE_BLUNDER)
COLOR_INT_EVAL_WHITE = Color(*COLOR_EVAL_WHITE)
COLOR_INT_EVAL_BLACK = Color(*COLOR_EVAL_BLACK)
COLOR_INT_CLOCK_OK = Color(*COLOR_CLOCK_OK)
COLOR_INT_CLOCK_WARN = Color(*COLOR_CLOCK_WARN)
COLOR_INT_CLOCK_CRIT = Color(*COLOR_CLOCK_CRIT)
COLOR_INT_RETURN_HOME = Color(*COLOR_RETURN_HOME)
COLOR_INT_TURN_WHITE = Color(*COLOR_TURN_WHITE)
COLOR_INT_TURN_BLACK = Color(*COLOR_TURN_BLACK)
COLOR_INT_OPPONENT_DISCONNECTED = Color(*COLOR_OPPONENT_DISCONNECTED)
COLOR_INT_OPPONENT_FROM = Color(*COLOR_OPPONENT_FROM)
COLOR_INT_OPPONENT_TO = Color(*COLOR_OPPONENT_TO)
COLOR_INT_OPPONENT_CAPTURE = Color(*COLOR_OPPONENT_CAPTURE)
COLOR_INT_CAPTURE_TRACE = Color(*COLOR_CAPTURE_TRACE)
COLOR_INT_CHECK = Color(*COLOR_CHECK)
COLOR_INT_ILLEGAL = Color(*COLOR_ILLEGAL)
COLOR_INT_MOVE_CONFIRM = Color(*COLOR_MOVE_CONFIRM)
COLOR_INT_CAPTURE_CONFIRM = Color(*COLOR_CAPTURE_CONFIRM)
COLOR_INT_MOVE_TRACE = Color(*COLOR_MOVE_TRACE)
COLOR_INT_VICTORY_GOLD = Color(*COLOR_VICTORY_GOLD)
COLOR_INT_VICTORY_GREEN = Color(*COLOR_VICTORY_GREEN)
COLOR_INT_DEFEAT_RED = Color(*COLOR_DEFEAT_RED)
COLOR_INT_DRAW_BLUE = Color(*COLOR_DRAW_BLUE)
COLOR_INT_DRAW_WHITE = Color(*COLOR_DRAW_WHITE)
COLOR_INT_GUARDRAIL_MISSING = Color(*COLOR_GUARDRAIL_MISSING)
COLOR_INT_GUARDRAIL_UNEXPECTED = Color(*COLOR_GUARDRAIL_UNEXPECTED)
COLOR_INT_CAPTURE_AURA_TARGET = Color(*COLOR_CAPTURE_AURA_TARGET)
COLOR_INT_CAPTURE_AURA_ATTACKER = Color(*COLOR_CAPTURE_AURA_ATTACKER)
COLOR_INT_SEEKING_HEAD = Color(*COLOR_SEEKING_HEAD)
COLOR_INT_SEEKING_BODY = Color(*COLOR_SEEKING_BODY)
COLOR_INT_SEEKING_TAIL = Color(*COLOR_SEEKING_TAIL)
COLOR_INT_START_WHITE_PRIMARY = Color(*COLOR_START_WHITE_PRIMARY)
COLOR_INT_START_WHITE_SECONDARY = Color(*COLOR_START_WHITE_SECONDARY)
COLOR_INT_START_BLACK_PRIMARY = Color(*COLOR_START_BLACK_PRIMARY)
COLOR_INT_START_BLACK_SECONDARY = Color(*COLOR_START_BLACK_SECONDARY)
COLOR_INT_BOARD_READY_PRIMARY = Color(*COLOR_BOARD_READY_PRIMARY)
COLOR_INT_BOARD_READY_SECONDARY = Color(*COLOR_BOARD_READY_SECONDARY)
COLOR_INT_BOARD_READY_AMBIENT = Color(*COLOR_BOARD_READY_AMBIENT)
COLOR_INT_MINT_EMERALD = Color(*COLOR_MINT_EMERALD)
COLOR_INT_AZURE = Color(*COLOR_AZURE)
COLOR_INT_ROYAL_VIOLET = Color(*COLOR_ROYAL_VIOLET)
COLOR_INT_PROMO_ROOT = Color(*COLOR_PROMO_ROOT)
COLOR_INT_PROMO_QUEEN = Color(*COLOR_PROMO_QUEEN)
COLOR_INT_PROMO_KNIGHT = Color(*COLOR_PROMO_KNIGHT)
COLOR_INT_PROMO_ROOK = Color(*COLOR_PROMO_ROOK)
COLOR_INT_PROMO_BISHOP = Color(*COLOR_PROMO_BISHOP)
COLOR_INT_NOVELTY_FLARE = Color(*COLOR_NOVELTY_FLARE)
COLOR_INT_RESIGN_PRIMARY = Color(*COLOR_RESIGN_PRIMARY)
COLOR_INT_RESIGN_HALO = Color(*COLOR_RESIGN_HALO)
COLOR_INT_ECLIPSE_FLASH = Color(*COLOR_ECLIPSE_FLASH)
COLOR_INT_ECLIPSE_GOLD = Color(*COLOR_ECLIPSE_GOLD)
COLOR_INT_ECLIPSE_RUBY = Color(*COLOR_ECLIPSE_RUBY)
COLOR_INT_ECLIPSE_CRIMSON = Color(*COLOR_ECLIPSE_CRIMSON)
COLOR_INT_ECLIPSE_GARNET = Color(*COLOR_ECLIPSE_GARNET)
COLOR_INT_ECLIPSE_EMBER = Color(*COLOR_ECLIPSE_EMBER)
COLOR_INT_ECLIPSE_ASH = Color(*COLOR_ECLIPSE_ASH)
COLOR_INT_DRAW_PEARL = Color(*COLOR_DRAW_PEARL)
COLOR_INT_DRAW_SAPPHIRE = Color(*COLOR_DRAW_SAPPHIRE)
COLOR_INT_DRAW_EQUILIBRIUM = Color(*COLOR_DRAW_EQUILIBRIUM)
COLOR_INT_DRAW_TWILIGHT = Color(*COLOR_DRAW_TWILIGHT)
COLOR_INT_NIGHT_MODE = Color(*COLOR_NIGHT_MODE)
COLOR_INT_NIGHT_INDICATOR = Color(*COLOR_NIGHT_INDICATOR)
COLOR_INT_DAY_INDICATOR = Color(*COLOR_DAY_INDICATOR)
COLOR_INT_NIGHT_SETUP_MISSING = Color(*COLOR_NIGHT_SETUP_MISSING)
COLOR_INT_NIGHT_SETUP_MISPLACED = Color(*COLOR_NIGHT_SETUP_MISPLACED)
COLOR_INT_NIGHT_PIECE_LIFTED = Color(*COLOR_NIGHT_PIECE_LIFTED)
COLOR_INT_NIGHT_LEGAL_TARGET = Color(*COLOR_NIGHT_LEGAL_TARGET)
COLOR_INT_NIGHT_LEGAL_CAPTURE = Color(*COLOR_NIGHT_LEGAL_CAPTURE)
COLOR_INT_NIGHT_OPPONENT_FROM = Color(*COLOR_NIGHT_OPPONENT_FROM)
COLOR_INT_NIGHT_OPPONENT_TO = Color(*COLOR_NIGHT_OPPONENT_TO)
COLOR_INT_NIGHT_OPPONENT_CAPTURE = Color(*COLOR_NIGHT_OPPONENT_CAPTURE)
COLOR_INT_NIGHT_MOVE_TRACE = Color(*COLOR_NIGHT_MOVE_TRACE)
COLOR_INT_NIGHT_CAPTURE_TRACE = Color(*COLOR_NIGHT_CAPTURE_TRACE)
COLOR_INT_NIGHT_CHECK = Color(*COLOR_NIGHT_CHECK)
COLOR_INT_NIGHT_TURN_WHITE = Color(*COLOR_NIGHT_TURN_WHITE)
COLOR_INT_NIGHT_TURN_BLACK = Color(*COLOR_NIGHT_TURN_BLACK)
COLOR_INT_NIGHT_ILLEGAL = Color(*COLOR_NIGHT_ILLEGAL)
COLOR_INT_NIGHT_GUARDRAIL_MISSING = Color(*COLOR_NIGHT_GUARDRAIL_MISSING)
COLOR_INT_NIGHT_GUARDRAIL_UNEXPECTED = Color(*COLOR_NIGHT_GUARDRAIL_UNEXPECTED)
COLOR_INT_NIGHT_CAPTURE_AURA_TARGET = Color(*COLOR_NIGHT_CAPTURE_AURA_TARGET)
COLOR_INT_NIGHT_CAPTURE_AURA_ATTACKER = Color(*COLOR_NIGHT_CAPTURE_AURA_ATTACKER)
COLOR_INT_NIGHT_MOVE_BEST = Color(*COLOR_NIGHT_MOVE_BEST)
COLOR_INT_NIGHT_MOVE_GOOD = Color(*COLOR_NIGHT_MOVE_GOOD)
COLOR_INT_NIGHT_MOVE_INACCURACY = Color(*COLOR_NIGHT_MOVE_INACCURACY)
COLOR_INT_NIGHT_MOVE_BLUNDER = Color(*COLOR_NIGHT_MOVE_BLUNDER)
COLOR_INT_NIGHT_EVAL_WHITE = Color(*COLOR_NIGHT_EVAL_WHITE)
COLOR_INT_NIGHT_EVAL_BLACK = Color(*COLOR_NIGHT_EVAL_BLACK)
COLOR_INT_NIGHT_EVAL_NEUTRAL = Color(*COLOR_NIGHT_EVAL_NEUTRAL)
COLOR_INT_NIGHT_RETURN_HOME = Color(*COLOR_NIGHT_RETURN_HOME)
COLOR_INT_NIGHT_CLOCK_OK = Color(*COLOR_NIGHT_CLOCK_OK)
COLOR_INT_NIGHT_CLOCK_WARN = Color(*COLOR_NIGHT_CLOCK_WARN)
COLOR_INT_NIGHT_CLOCK_CRIT = Color(*COLOR_NIGHT_CLOCK_CRIT)
COLOR_INT_NIGHT_DRAW_BLUE = Color(*COLOR_NIGHT_DRAW_BLUE)
COLOR_INT_NIGHT_SEEKING_HEAD = Color(*COLOR_NIGHT_SEEKING_HEAD)
COLOR_INT_NIGHT_SEEKING_BODY = Color(*COLOR_NIGHT_SEEKING_BODY)
COLOR_INT_NIGHT_SEEKING_TAIL = Color(*COLOR_NIGHT_SEEKING_TAIL)
COLOR_INT_NIGHT_START_BLACK_PRIMARY = Color(*COLOR_NIGHT_START_BLACK_PRIMARY)
COLOR_INT_NIGHT_START_BLACK_SECONDARY = Color(*COLOR_NIGHT_START_BLACK_SECONDARY)
COLOR_INT_NIGHT_BOARD_READY_PRIMARY = Color(*COLOR_NIGHT_BOARD_READY_PRIMARY)
COLOR_INT_NIGHT_BOARD_READY_SECONDARY = Color(*COLOR_NIGHT_BOARD_READY_SECONDARY)
COLOR_INT_NIGHT_BOARD_READY_AMBIENT = Color(*COLOR_NIGHT_BOARD_READY_AMBIENT)
COLOR_INT_NIGHT_MINT_EMERALD = Color(*COLOR_NIGHT_MINT_EMERALD)
COLOR_INT_NIGHT_AZURE = Color(*COLOR_NIGHT_AZURE)
COLOR_INT_NIGHT_ROYAL_VIOLET = Color(*COLOR_NIGHT_ROYAL_VIOLET)
COLOR_INT_NIGHT_PROMO_ROOT = Color(*COLOR_NIGHT_PROMO_ROOT)
COLOR_INT_NIGHT_PROMO_QUEEN = Color(*COLOR_NIGHT_PROMO_QUEEN)
COLOR_INT_NIGHT_PROMO_KNIGHT = Color(*COLOR_NIGHT_PROMO_KNIGHT)
COLOR_INT_NIGHT_PROMO_ROOK = Color(*COLOR_NIGHT_PROMO_ROOK)
COLOR_INT_NIGHT_PROMO_BISHOP = Color(*COLOR_NIGHT_PROMO_BISHOP)
COLOR_INT_NIGHT_NOVELTY_FLARE = Color(*COLOR_NIGHT_NOVELTY_FLARE)
COLOR_INT_NIGHT_RESIGN_PRIMARY = Color(*COLOR_NIGHT_RESIGN_PRIMARY)
COLOR_INT_NIGHT_RESIGN_HALO = Color(*COLOR_NIGHT_RESIGN_HALO)
COLOR_INT_NIGHT_ECLIPSE_FLASH = Color(*COLOR_NIGHT_ECLIPSE_FLASH)
COLOR_INT_NIGHT_ECLIPSE_GOLD = Color(*COLOR_NIGHT_ECLIPSE_GOLD)
COLOR_INT_NIGHT_ECLIPSE_RUBY = Color(*COLOR_NIGHT_ECLIPSE_RUBY)
COLOR_INT_NIGHT_ECLIPSE_CRIMSON = Color(*COLOR_NIGHT_ECLIPSE_CRIMSON)
COLOR_INT_NIGHT_ECLIPSE_GARNET = Color(*COLOR_NIGHT_ECLIPSE_GARNET)
COLOR_INT_NIGHT_ECLIPSE_EMBER = Color(*COLOR_NIGHT_ECLIPSE_EMBER)
COLOR_INT_NIGHT_DRAW_PEARL = Color(*COLOR_NIGHT_DRAW_PEARL)
COLOR_INT_NIGHT_DRAW_SAPPHIRE = Color(*COLOR_NIGHT_DRAW_SAPPHIRE)
COLOR_INT_NIGHT_DRAW_EQUILIBRIUM = Color(*COLOR_NIGHT_DRAW_EQUILIBRIUM)
COLOR_INT_NIGHT_DRAW_TWILIGHT = Color(*COLOR_NIGHT_DRAW_TWILIGHT)


_settings_ref = None


def _get_led_intensity_factor() -> float:
    """Reads the master LED intensity factor (0.10..1.0) from shared settings.

    Caches the settings dict reference to avoid a module import on every frame;
    board_hardware keeps the dict object identity across load/update cycles.
    """
    global _settings_ref
    if _settings_ref is None:
        try:
            from board_hardware import settings
            _settings_ref = settings
        except Exception:
            return 1.0
    pct = _settings_ref.get("led_intensity", 100)
    if pct is None:
        return 1.0
    return max(0.10, min(1.0, float(pct) / 100.0))


class DualPixelStrip:
    """
    Controls two serial WS2812B strips mapped as a single 152-LED buffer
    via framed binary commands to the ESP32 coprocessor.
    Features:
    - Chunked binary packet transmission (up to 38 LEDs / 152 bytes per packet)
    - Atomic CMD_SET_AND_SHOW execution
    - Periodic self-healing keyframe sync every 60 frames (~2-3s)
    - Thread-safety with external serial_lock
    """
    def __init__(self, num_leds_per_strip=76):
        self.num_leds_per_strip = num_leds_per_strip
        self.ser = None
        self.lock = None
        self.current_colors = [0] * (2 * num_leds_per_strip)
        self.shown_colors = [0] * (2 * num_leds_per_strip)
        self.frame_count = 0
        self.last_applied_intensity = 1.0

    def set_serial_conn(self, ser, lock=None):
        self.ser = ser
        self.lock = lock

    def show(self):
        ser = self.ser
        if ser is None:
            return

        def _do_show():
            self.frame_count += 1
            is_keyframe = (self.frame_count % 60 == 0)

            # Get master LED intensity factor (10% to 100%)
            intensity_factor = _get_led_intensity_factor()
            intensity_changed = (intensity_factor != self.last_applied_intensity)

            # Skip if frame hasn't changed, not keyframe, and intensity hasn't changed
            if not is_keyframe and not intensity_changed and self.current_colors == self.shown_colors:
                return

            try:
                all_current_off = not any(self.current_colors)
                all_shown_off = not any(self.shown_colors)

                if all_current_off:
                    if is_keyframe or not all_shown_off:
                        packet = build_packet(CMD_CLEAR_LEDS)
                        ser.write(packet)
                    self.shown_colors[:] = self.current_colors
                    self.last_applied_intensity = intensity_factor
                    return

                # Collect changed LEDs (or all active/modified LEDs on keyframe or intensity change)
                changes = []
                for idx in range(len(self.current_colors)):
                    curr = self.current_colors[idx]
                    if is_keyframe or intensity_changed or (curr != self.shown_colors[idx]):
                        r_raw = (curr >> 16) & 0xFF
                        g_raw = (curr >> 8) & 0xFF
                        b_raw = curr & 0xFF
                        if intensity_factor < 1.0:
                            r = round(r_raw * intensity_factor)
                            g = round(g_raw * intensity_factor)
                            b = round(b_raw * intensity_factor)
                        else:
                            r, g, b = r_raw, g_raw, b_raw
                        changes.append((idx, r, g, b))

                if not changes:
                    self.shown_colors[:] = self.current_colors
                    self.last_applied_intensity = intensity_factor
                    return

                # Chunk changes in batches of up to 38 LEDs (38 * 4 = 152 bytes payload)
                chunk_size = 38
                num_chunks = (len(changes) + chunk_size - 1) // chunk_size

                for chunk_idx in range(num_chunks):
                    chunk = changes[chunk_idx * chunk_size : (chunk_idx + 1) * chunk_size]
                    payload_bytes = bytearray()
                    for idx, r, g, b in chunk:
                        payload_bytes.extend([idx, r, g, b])

                    # Last chunk uses CMD_SET_AND_SHOW, preceding chunks use CMD_SET_LEDS
                    cmd = CMD_SET_AND_SHOW if chunk_idx == num_chunks - 1 else CMD_SET_LEDS

                    packet = build_packet(cmd, bytes(payload_bytes))
                    ser.write(packet)

                self.shown_colors[:] = self.current_colors
                self.last_applied_intensity = intensity_factor
            except Exception as e:
                logger.error(f"Error writing LED commands: {e}")

        if self.lock:
            with self.lock:
                _do_show()
        else:
            _do_show()

    def setPixelColor(self, index, color):
        if 0 <= index < len(self.current_colors):
            if isinstance(color, int):
                val = color
            else:
                try:
                    r, g, b = color
                    val = (r << 16) | (g << 8) | b
                except (TypeError, ValueError):
                    val = 0
            self.current_colors[index] = val


# =============================================================================
# STRIP INIT & COORDINATE MAPPING
# =============================================================================

def init_strip():
    """Initialise and return the DualPixelStrip instance, or None if unavailable."""
    return DualPixelStrip(num_leds_per_strip=LEDS_PER_STRIP)


_OFFSETS_STRIP1 = {
    0: (0, 1),
    1: (2, 3),
    2: (5, 6),
    3: (7, 8),
    4: (9, 10),
    5: (11, 12),
    6: (14, 15),
    7: (16, 17)
}

_OFFSETS_STRIP2 = {
    0: (0, 1),    # Square 0 (2 LEDs)
    1: (2, 3),    # Square 1 (2 active + 1 extra/skipped at offset 4)
    2: (5, 6),    # Square 2 (2 LEDs)
    3: (7, 8),    # Square 3 (2 active + 1 OFF/skipped at offset 9)
    4: (10, 11),  # Square 4 (2 LEDs)
    5: (12, 13),  # Square 5 (2 LEDs)
    6: (14, 15),  # Square 6 (2 active + 1 extra/skipped at offset 16)
    7: (17, 18),  # Square 7 (2 LEDs)
}


def _compute_led_indices(col, row):
    c_phys = col
    r_phys = 7 - row

    if c_phys < 4:
        # Strip 1 (Ranks 1-4 / physical columns 0-3)
        base = c_phys * 18
        sq_idx = 7 - r_phys if c_phys % 2 == 0 else r_phys
        return tuple(base + o for o in _OFFSETS_STRIP1[sq_idx])

    # Strip 2 (Ranks 5-8 / physical columns 4-7)
    # Relative rank from top to bottom: Rank 8 = 0, Rank 7 = 1, Rank 6 = 2, Rank 5 = 3
    c_rel = 7 - c_phys
    base = LEDS_PER_STRIP + c_rel * 19
    sq_idx = 7 - r_phys if c_rel % 2 == 0 else r_phys
    return tuple(base + o for o in _OFFSETS_STRIP2[sq_idx])


# Precomputed square -> LED index map (avoids rebuilding offset dicts on every
# call from the per-frame render loops)
_SQUARE_LED_INDICES = {
    (col, row): _compute_led_indices(col, row)
    for col in range(8)
    for row in range(8)
}


def get_led_indices(col, row):
    """
    Convert board coordinates to serpentine physical LED indices for the 90-degree rotated board.
    col: rank index 0..7 (0 = Rank 1, 7 = Rank 8)
    row: file index 0..7 (0 = file a, 7 = file h)

    Physical transformation (90-deg CCW rotation):
      - Physical column (c_phys) = rank (col)
      - Physical row (r_phys)    = 7 - file (7 - row)

    Strip 1 (Ranks 1-4 / col 0-3): 18 LEDs per column (16 active + 2 skipped OFF LEDs).
    Strip 2 (Ranks 5-8 / col 4-7): 19 LEDs per column (16 active + 3 skipped OFF LEDs).
    """
    return _SQUARE_LED_INDICES[(col, row)]


def all_leds_off(strip):
    """Turn off all LEDs using hardware batch clear binary packet CMD_CLEAR_LEDS when possible."""
    if not strip:
        return
    if hasattr(strip, 'ser') and strip.ser:
        def _do_off():
            try:
                packet = build_packet(CMD_CLEAR_LEDS)
                strip.ser.write(packet)
                if hasattr(strip, 'current_colors'):
                    strip.current_colors[:] = [0] * len(strip.current_colors)
                    strip.shown_colors[:] = strip.current_colors
                return True
            except Exception:
                return False

        lock = getattr(strip, 'lock', None)
        if lock:
            with lock:
                if _do_off():
                    return
        else:
            if _do_off():
                return

    # Fallback
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def all_leds_color(strip, rgb):
    """Set all LEDs to the same color using hardware batch command CMD_SET_ALL when possible."""
    if not strip:
        return
    if isinstance(rgb, int):
        r = (rgb >> 16) & 0xFF
        g = (rgb >> 8) & 0xFF
        b = rgb & 0xFF
        val = rgb
    else:
        r, g, b = rgb
        val = (r << 16) | (g << 8) | b

    if hasattr(strip, 'ser') and strip.ser:
        def _do_color():
            try:
                packet = build_packet(CMD_SET_ALL, bytes([r, g, b]))
                strip.ser.write(packet)
                if hasattr(strip, 'current_colors'):
                    strip.current_colors[:] = [val] * len(strip.current_colors)
                    strip.shown_colors[:] = strip.current_colors
                return True
            except Exception:
                return False

        lock = getattr(strip, 'lock', None)
        if lock:
            with lock:
                if _do_color():
                    return
        else:
            if _do_color():
                return

    # Fallback
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(r, g, b))
    strip.show()
