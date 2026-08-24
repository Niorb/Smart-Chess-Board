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

# =============================================================================
# LED STRIP SPECIFICATIONS
# =============================================================================

BOARD_ROWS = 8
BOARD_COLS = 8
LED_PIN = 23  # ESP32 GPIO 23 — Strip 1 (files a-d)
LED_PIN_2 = 22  # ESP32 GPIO 22 — Strip 2 (files e-h)
LEDS_PER_STRIP = 76
LED_STRIP_COUNT = 2
NUM_LEDS = LEDS_PER_STRIP * LED_STRIP_COUNT  # 152 total

# =============================================================================
# LED COLOR DEFINITIONS — (R, G, B) tuples (scaled for 20% power reduction)
# =============================================================================

COLOR_OFF = (0, 0, 0)
# Setup & Game State Layered LED Colors — (R, G, B) tuples
COLOR_SETUP_MISSING = (16, 16, 16)  # Dim white for missing starting pieces
COLOR_SETUP_MISPLACED = (28, 8, 0)  # Dim amber warning for misplaced pieces during setup
COLOR_PIECE_LIFTED = (144, 80, 0)  # Amber / Gold for lifted piece origin
COLOR_LEGAL_TARGET = (0, 24, 48)  # Subtle deep cyan for legal quiet target dots
COLOR_LEGAL_CAPTURE = (64, 10, 24)  # Subtle deep ruby/rose for legal capture target dots
COLOR_OPPONENT_FROM = (220, 100, 0)  # Solar Orange for opponent piece that needs to move
COLOR_OPPONENT_TO = (0, 150, 240)  # Electric Sky Azure for opponent move destination (unified with move trace)
COLOR_OPPONENT_CAPTURE = (220, 20, 50)  # Radiant Ruby Crimson for opponent capture target (unified with capture trace)
COLOR_CHECK = (176, 0, 0)  # Red highlight on King in check
COLOR_ILLEGAL = (144, 0, 0)  # Red for invalid placement
COLOR_MOVE_CONFIRM = (48, 255, 128)  # Vibrant emerald/spring green arrival confirmation flash
COLOR_CAPTURE_CONFIRM = (255, 32, 64)  # Radiant ruby/crimson capture confirmation flash
COLOR_GUARDRAIL_MISSING = (204, 120, 0)  # Amber warning for missing piece during game
COLOR_GUARDRAIL_UNEXPECTED = (204, 0, 0)  # Red alert for unexpected piece during game
COLOR_CAPTURE_AURA_TARGET = (255, 32, 64)  # Radiant ruby for target capture square
COLOR_CAPTURE_AURA_ATTACKER = (220, 160, 20)  # Warm gold glow for friendly candidate pieces that can capture target

# Coach & Blunder Guard Move Quality Colors — (R, G, B) tuples (scaled 20% for power)
COLOR_MOVE_BEST = (0, 204, 76)        # Emerald Green for Best Move
COLOR_MOVE_GOOD = (0, 180, 220)       # Cyan / Sky Blue for Good Move
COLOR_MOVE_INACCURACY = (220, 160, 0) # Amber / Yellow for Inaccuracy
COLOR_MOVE_BLUNDER = (220, 24, 40)    # Crimson / Red for Blunder

# Live Evaluation Bar Colors — (R, G, B) tuples (subtle, scaled for low power)
COLOR_EVAL_WHITE = (80, 80, 100)      # Cool light tone for White advantage
COLOR_EVAL_BLACK = (10, 20, 60)       # Dim navy tone for Black advantage

# Chess Clock Drain Bar Colors — (R, G, B) tuples (subtle, scaled for low power)
COLOR_CLOCK_OK = (0, 80, 32)          # Dim emerald green for ample time remaining
COLOR_CLOCK_WARN = (96, 64, 0)        # Dim amber/orange for low time warning
COLOR_CLOCK_CRIT = (88, 8, 8)         # Dim red for critical time scramble

# Analysis Divergence Return-Home Guide Colors — (R, G, B) tuples
COLOR_RETURN_HOME = (110, 85, 0)      # Dim gold halo marking the branch move to un-play next

# Active Player Turn Ambient Indicator Colors — (R, G, B) tuples (subtle breathing halo on active King)
COLOR_TURN_WHITE = (140, 130, 90)     # Warm ivory tone for White's turn King
COLOR_TURN_BLACK = (20, 70, 140)      # Cool azure tone for Black's turn King

# Opponent Disconnected & Victory Claim Indicator Colors — (R, G, B) tuples
COLOR_OPPONENT_DISCONNECTED = (220, 100, 0)  # Alert amber beacon & countdown gauge

# Lifecycle & Trace Animation Colors — (R, G, B) tuples
COLOR_MOVE_TRACE = (0, 150, 240)  # Electric Sky Azure pulse along quiet move trajectory (unified with arrival)
COLOR_CAPTURE_TRACE = (220, 20, 50)  # Radiant Ruby Crimson pulse along capture trajectory (unified with arrival)
COLOR_VICTORY_GOLD = (204, 172, 0)  # Shimmering gold for victory
COLOR_VICTORY_GREEN = (0, 204, 48)  # Emerald green wave for victory
COLOR_DEFEAT_RED = (176, 0, 16)  # Crimson wave for defeat
COLOR_DRAW_BLUE = (0, 96, 204)  # Sapphire blue for draw curtain
COLOR_DRAW_WHITE = (160, 160, 204)  # Cool white for draw curtain
COLOR_SEEKING_HEAD = (140, 240, 255)  # Bright icy cyan head for seeking orbit
COLOR_SEEKING_BODY = (0, 140, 255)  # Electric blue body for seeking orbit
COLOR_SEEKING_TAIL = (0, 36, 160)  # Deep royal blue tail for seeking orbit
COLOR_START_WHITE_PRIMARY = (255, 230, 160)  # Radiant ivory gold for White start scan
COLOR_START_WHITE_SECONDARY = (200, 180, 120)  # Warm gold for White start tail
COLOR_START_BLACK_PRIMARY = (0, 180, 255)  # Electric cyan-azure for Black start scan
COLOR_START_BLACK_SECONDARY = (80, 60, 220)  # Royal violet for Black start tail
COLOR_BOARD_READY_PRIMARY = (32, 220, 100)  # Luminous emerald for setup completion sweep
COLOR_BOARD_READY_SECONDARY = (200, 220, 60)  # Luminous gold-lime accent
COLOR_BOARD_READY_AMBIENT = (14, 70, 36)  # Subtle emerald breathing glow for persistent ready state

# Analysis Mode Dedicated Colors — (R, G, B) tuples
COLOR_MINT_EMERALD = (0, 220, 140)    # Mint Emerald for Best Move in Analysis (delta <= 15 cp)
COLOR_AZURE = (0, 160, 255)           # Cyan Azure for Good Move in Analysis (15 < delta <= 60 cp)
COLOR_ROYAL_VIOLET = (140, 40, 240)   # Royal Violet for Analysis Divergence Anchor & Corner Beacons

# Royal Promotion Scepter (Day Mode)
COLOR_PROMO_ROOT = (255, 230, 160)      # Warm Gold halo on promotion square
COLOR_PROMO_QUEEN = (140, 40, 240)     # Royal Violet
COLOR_PROMO_KNIGHT = (0, 220, 140)     # Mint Emerald
COLOR_PROMO_ROOK = (0, 160, 255)       # Azure Cyan
COLOR_PROMO_BISHOP = (220, 140, 0)     # Warm Sun Amber

# Cartographer's Path / Opening Novelty Flare (Day Mode)
COLOR_NOVELTY_FLARE = (255, 200, 40)   # Luminous golden solar flare for uncharted novelty moves

# The King's Bow Resignation Gesture (Day Mode)
COLOR_RESIGN_PRIMARY = (220, 24, 40)    # Laser Crimson for King's Bow resignation origin square
COLOR_RESIGN_HALO = (140, 10, 25)       # Radiant Garnet for resignation aura cross-halo

# =============================================================================
# NIGHT MODE DEDICATED HIGH-CONTRAST PALETTE — (R, G, B) tuples
# (Engineered for crystal-clear contrast and vibrancy against moonlight blue floor)
# =============================================================================
COLOR_NIGHT_MODE = (4, 12, 28)  # Deep moonlight sapphire ambient background (low current draw)
COLOR_NIGHT_INDICATOR = (0, 70, 220)  # Dark Blue indicator when board is in Night Mode
COLOR_DAY_INDICATOR = (255, 160, 0)  # Warm Sun Amber indicator when board is in Day Mode

# Setup & Pieces
COLOR_NIGHT_SETUP_MISSING = (70, 80, 110)  # Luminous starlight silver for missing starting pieces
COLOR_NIGHT_SETUP_MISPLACED = (220, 60, 0)  # Vivid amber warning for misplaced pieces
COLOR_NIGHT_PIECE_LIFTED = (230, 130, 0)  # Radiant solar gold for lifted piece origin

# Move Targets & Captures (tuned for extreme contrast against deep blue background)
COLOR_NIGHT_LEGAL_TARGET = (0, 210, 140)  # Luminous mint emerald / aqua green (crystal-clear against blue)
COLOR_NIGHT_LEGAL_CAPTURE = (240, 20, 60)  # Pure radiant crimson for legal captures

# Opponent Moves & Traces
COLOR_NIGHT_OPPONENT_FROM = (240, 140, 0)  # Radiant solar gold for opponent piece that needs to move
COLOR_NIGHT_OPPONENT_TO = (0, 220, 230)  # Vivid electric aqua cyan for opponent destination (unified with move trace)
COLOR_NIGHT_OPPONENT_CAPTURE = (255, 10, 40)  # Pure laser crimson for opponent capture target (unified with capture trace)
COLOR_NIGHT_MOVE_TRACE = (0, 220, 230)  # Vivid electric aqua cyan pulse along move trajectory (unified with arrival)
COLOR_NIGHT_CAPTURE_TRACE = (255, 10, 40)  # Pure laser crimson pulse along capture trajectory (unified with arrival)

# King Status & Turn Breathing Halos
COLOR_NIGHT_CHECK = (255, 10, 10)  # Laser red on King in check
COLOR_NIGHT_TURN_WHITE = (240, 210, 120)  # Radiant warm sunlight gold halo for White's turn
COLOR_NIGHT_TURN_BLACK = (170, 40, 230)  # Electric amethyst purple halo for Black's turn (distinct from blue)

# Diagnostics & Guardrails
COLOR_NIGHT_ILLEGAL = (220, 0, 0)  # High-visibility red for invalid placement
COLOR_NIGHT_GUARDRAIL_MISSING = (240, 150, 0)  # Vivid amber warning
COLOR_NIGHT_GUARDRAIL_UNEXPECTED = (255, 20, 20)  # Vivid red alert
COLOR_NIGHT_CAPTURE_AURA_TARGET = (255, 40, 80)
COLOR_NIGHT_CAPTURE_AURA_ATTACKER = (255, 190, 30)

# Coach & Move Quality
COLOR_NIGHT_MOVE_BEST = (0, 255, 90)  # Neon Emerald for Best Move
COLOR_NIGHT_MOVE_GOOD = (0, 230, 210)  # Electric Mint Aqua for Good Move
COLOR_NIGHT_MOVE_INACCURACY = (255, 180, 0)  # Vivid Goldenrod for Inaccuracy
COLOR_NIGHT_MOVE_BLUNDER = (255, 30, 40)  # Laser Crimson for Blunder

# Live Evaluation Bar
COLOR_NIGHT_EVAL_WHITE = (150, 150, 190)  # Bright pearl silver for White advantage
COLOR_NIGHT_EVAL_BLACK = (60, 10, 95)  # Velvet violet for Black advantage (distinct from blue floor)
COLOR_NIGHT_EVAL_NEUTRAL = (40, 35, 60)  # Neutral midpoint

# Analysis Divergence Return-Home Guide Colors
COLOR_NIGHT_RETURN_HOME = (255, 200, 40)  # Vivid gold halo marking the branch move to un-play next

# Chess Clock Drain Bar
COLOR_NIGHT_CLOCK_OK = (0, 230, 110)  # Vivid neon emerald for ample time remaining
COLOR_NIGHT_CLOCK_WARN = (255, 180, 0)  # Vivid goldenrod for low time warning
COLOR_NIGHT_CLOCK_CRIT = (255, 20, 20)  # Laser red for critical time scramble

# Lifecycle & Animation Colors
COLOR_NIGHT_DRAW_BLUE = (0, 140, 255)  # Luminous sky sapphire for draw curtain
COLOR_NIGHT_SEEKING_HEAD = (240, 255, 220)  # Radiant starlight head
COLOR_NIGHT_SEEKING_BODY = (0, 230, 200)  # Electric mint-cyan body
COLOR_NIGHT_SEEKING_TAIL = (0, 80, 180)  # Royal twilight tail
COLOR_NIGHT_START_BLACK_PRIMARY = (0, 210, 255)  # Vivid electric cyan
COLOR_NIGHT_START_BLACK_SECONDARY = (130, 60, 240)  # Electric royal violet
COLOR_NIGHT_BOARD_READY_PRIMARY = (0, 240, 160)  # Vivid neon aqua for night setup completion sweep
COLOR_NIGHT_BOARD_READY_SECONDARY = (0, 180, 255)  # Electric cyan accent
COLOR_NIGHT_BOARD_READY_AMBIENT = (10, 60, 60)  # Subtle starlight mint breathing glow for ready state
COLOR_NIGHT_MINT_EMERALD = (0, 255, 160)  # Vivid neon mint emerald (Night Mode)
COLOR_NIGHT_AZURE = (0, 210, 255)         # Vivid electric cyan azure (Night Mode)
COLOR_NIGHT_ROYAL_VIOLET = (170, 50, 255) # Luminous royal violet (Night Mode)

# Royal Promotion Scepter (Night Mode - High-Contrast Palettes)
COLOR_NIGHT_PROMO_ROOT = (240, 210, 120)    # Radiant Warm Gold
COLOR_NIGHT_PROMO_QUEEN = (170, 50, 255)   # Luminous Royal Violet
COLOR_NIGHT_PROMO_KNIGHT = (0, 255, 160)   # Vivid Mint Emerald
COLOR_NIGHT_PROMO_ROOK = (0, 210, 255)     # Vivid Azure Cyan
COLOR_NIGHT_PROMO_BISHOP = (255, 160, 20)  # Radiant Sun Amber

# Cartographer's Path / Opening Novelty Flare (Night Mode)
COLOR_NIGHT_NOVELTY_FLARE = (240, 180, 20)  # Vivid Golden Solar Flare

# The King's Bow Resignation Gesture (Night Mode)
COLOR_NIGHT_RESIGN_PRIMARY = (160, 16, 36) # Velvet Ruby
COLOR_NIGHT_RESIGN_HALO = (80, 8, 18)      # Midnight Crimson

# "The Sovereign's Eclipse" (GAME_LOST Palette)
COLOR_ECLIPSE_FLASH = (255, 245, 235)  # White-hot fractured crown detonation
COLOR_ECLIPSE_GOLD = (255, 175, 25)    # Flying molten crown shards
COLOR_ECLIPSE_RUBY = (255, 18, 48)     # Blazing laser strike ruby
COLOR_ECLIPSE_CRIMSON = (196, 12, 32)  # Blood crimson shockwave
COLOR_ECLIPSE_GARNET = (110, 8, 20)    # Obsidian garnet perimeter fissure
COLOR_ECLIPSE_EMBER = (75, 10, 6)      # Smoldering ember cinder
COLOR_ECLIPSE_ASH = (20, 3, 4)         # Charcoal ash dying hearth

# "The Celestial Equilibrium" (GAME_DRAWN Palette)
COLOR_DRAW_PEARL = (240, 242, 255)       # Luminous pearl ivory (White army tide)
COLOR_DRAW_SAPPHIRE = (0, 110, 235)      # Celestial royal sapphire (Black army tide)
COLOR_DRAW_EQUILIBRIUM = (0, 210, 230)   # Radiant equilibrium aqua vortex
COLOR_DRAW_TWILIGHT = (60, 85, 170)      # Horizon twilight dissolve

# Night Mode variants for high-contrast visibility against moonlight sapphire background
COLOR_NIGHT_ECLIPSE_FLASH = (220, 210, 240)
COLOR_NIGHT_ECLIPSE_GOLD = (210, 140, 20)
COLOR_NIGHT_ECLIPSE_RUBY = (180, 16, 40)
COLOR_NIGHT_ECLIPSE_CRIMSON = (140, 10, 28)
COLOR_NIGHT_ECLIPSE_GARNET = (70, 8, 25)
COLOR_NIGHT_ECLIPSE_EMBER = (45, 8, 12)

COLOR_NIGHT_DRAW_PEARL = (180, 195, 235)
COLOR_NIGHT_DRAW_SAPPHIRE = (0, 80, 200)
COLOR_NIGHT_DRAW_EQUILIBRIUM = (0, 180, 210)
COLOR_NIGHT_DRAW_TWILIGHT = (30, 45, 95)

# =============================================================================
# ANIMATION & TIMING CONSTANTS
# =============================================================================

# Procedural Animation Timings (seconds)
MOVE_TRACE_PERIOD_S = 0.8  # Traversal period for move trace pulse
ANIM_CASTLE_PERIOD_S = 2.0  # Traversal period for 2-phase King + Rook castling cycle
ANIM_MOVE_CONFIRM_DURATION_S = 0.45  # Snappy 450ms exponential decay
ANIM_GAME_START_DURATION_S = 1.2  # Fast, snappy duration for choreographed army scan & royal focus
ANIM_GAME_WON_DURATION_S = 3.0  # Duration for victory celebration waves
ANIM_GAME_LOST_DURATION_S = 2.8  # Duration for defeat Sovereign's Eclipse sequence
ANIM_GAME_DRAWN_DURATION_S = 2.6  # Duration for draw Celestial Equilibrium sequence
ANIM_BOARD_READY_DURATION_S = 0.5  # Duration for board setup ready snap-flash
ANIM_SEEKING_PERIOD_S = 2.8  # Full perimeter orbital period during matchmaking
ANIM_SEEKING_DURATION_S = 5.6  # Duration for one-shot seeking test animation
ANIM_ANALYSIS_COMPUTING_DURATION_S = 10.0  # Duration for analysis computing animation
ANIM_UNCHARTED_NOVELTY_DURATION_S = 0.35  # High-speed 350ms outward radial starburst pulse
RESIGNATION_HOLD_DURATION_S = 3.0  # Holding King for 3.0s arms King's Bow resignation
RESIGNATION_ABANDON_DURATION_S = 5.0  # Leaving King off board for 5.0s auto-resigns
