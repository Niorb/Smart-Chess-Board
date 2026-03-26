/*
 * SmartChessBoard.ino
 *
 * Scans a 4x4 matrix of digital Hall effect sensors using two CD74HC4067
 * 16-channel multiplexers. Detects chess piece presence via magnets.
 * Tracks real piece identities (type + color) using a known starting position
 * and lift/place move detection. Lights up squares with WS2812B LEDs.
 *
 * Piece encoding: standard chess notation characters.
 *   White: R N B Q K P   (uppercase)
 *   Black: r n b q k p   (lowercase)
 *   Empty: '.'
 *
 * Hardware: ESP32-WROOM-32, 2x CD74HC4067, digital Hall effect sensors,
 *           WS2812B LED strip (serpentine layout).
 *
 * Requires: Adafruit NeoPixel library (install via Arduino IDE Library Manager).
 * Random change
 */

#include <Adafruit_NeoPixel.h>

// ============================================================================
// CONFIGURATION — change these to scale or rewire
// ============================================================================

// Board dimensions (change both to 8 for full-size board)
#define BOARD_ROWS 4
#define BOARD_COLS 4

// Row MUX select pins (directly drive CD74HC4067 S0-S2; S3 tied to GND)
#define ROW_MUX_S0 25
#define ROW_MUX_S1 26
#define ROW_MUX_S2 27

// Column MUX select pins (directly drive CD74HC4067 S0-S2; S3 tied to GND)
#define COL_MUX_S0 16
#define COL_MUX_S1 17
#define COL_MUX_S2 18

// Read pin — column MUX SIG output
#define MUX_READ_PIN 34

// Timing
#define SCAN_INTERVAL_MS  100   // Full board scan interval (milliseconds)
#define MUX_SETTLE_US     10    // Wait after MUX channel switch (microseconds)

// Debouncing — require this many consecutive identical reads to accept change
#define DEBOUNCE_THRESHOLD 3

// WS2812B LED strip
#define LED_PIN        13
#define NUM_LEDS       (BOARD_ROWS * BOARD_COLS)
#define LED_BRIGHTNESS 50    // 0-255, keep low to avoid power issues

// ============================================================================
// PIECE DEFINITIONS
// ============================================================================

// Piece characters: uppercase = White, lowercase = Black, '.' = empty.
// Standard chess notation: K/k=King, Q/q=Queen, R/r=Rook, B/b=Bishop,
//                          N/n=Knight, P/p=Pawn.

// Check if a piece character is white
bool isWhite(char piece) { return (piece >= 'A' && piece <= 'Z'); }

// Check if a piece character is black
bool isBlack(char piece) { return (piece >= 'a' && piece <= 'z'); }

// Check if a square is empty
bool isEmpty(char piece) { return (piece == '.'); }

// Get a human-readable name for a piece character
const char* pieceName(char piece) {
  switch (piece) {
    case 'K': return "White King";
    case 'Q': return "White Queen";
    case 'R': return "White Rook";
    case 'B': return "White Bishop";
    case 'N': return "White Knight";
    case 'P': return "White Pawn";
    case 'k': return "Black King";
    case 'q': return "Black Queen";
    case 'r': return "Black Rook";
    case 'b': return "Black Bishop";
    case 'n': return "Black Knight";
    case 'p': return "Black Pawn";
    default:  return "Empty";
  }
}

// ============================================================================
// STARTING POSITION
// ============================================================================

// Standard chess starting position (8x8).
// Row 0 = White's back rank (rank 1), Row 7 = Black's back rank (rank 8).
// Only the first BOARD_ROWS x BOARD_COLS are used.
//
// Full 8x8 layout:
//   Row 0: R N B Q K B N R   (White back rank)
//   Row 1: P P P P P P P P   (White pawns)
//   Row 2: . . . . . . . .
//   Row 3: . . . . . . . .
//   Row 4: . . . . . . . .
//   Row 5: . . . . . . . .
//   Row 6: p p p p p p p p   (Black pawns)
//   Row 7: r n b q k b n r   (Black back rank)
//
// For the 4x4 prototype we use a condensed layout with pieces on every row:
//   Row 0: R N B Q   (White back rank, files a-d)
//   Row 1: P P P P   (White pawns)
//   Row 2: p p p p   (Black pawns)
//   Row 3: r n b q   (Black back rank, files a-d)

#if BOARD_ROWS == 8 && BOARD_COLS == 8
  const char INITIAL_POSITION[8][8] = {
    { 'R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R' },  // Row 0 — White back rank
    { 'P', 'P', 'P', 'P', 'P', 'P', 'P', 'P' },  // Row 1 — White pawns
    { '.', '.', '.', '.', '.', '.', '.', '.' },  // Row 2
    { '.', '.', '.', '.', '.', '.', '.', '.' },  // Row 3
    { '.', '.', '.', '.', '.', '.', '.', '.' },  // Row 4
    { '.', '.', '.', '.', '.', '.', '.', '.' },  // Row 5
    { 'p', 'p', 'p', 'p', 'p', 'p', 'p', 'p' },  // Row 6 — Black pawns
    { 'r', 'n', 'b', 'q', 'k', 'b', 'n', 'r' },  // Row 7 — Black back rank
  };
#elif BOARD_ROWS == 4 && BOARD_COLS == 4
  const char INITIAL_POSITION[4][4] = {
    { 'R', 'N', 'B', 'Q' },  // Row 0 — White back rank (a-d)
    { 'P', 'P', 'P', 'P' },  // Row 1 — White pawns
    { 'p', 'p', 'p', 'p' },  // Row 2 — Black pawns
    { 'r', 'n', 'b', 'q' },  // Row 3 — Black back rank (a-d)
  };
#else
  #error "Define an INITIAL_POSITION for your BOARD_ROWS x BOARD_COLS"
#endif

// ============================================================================
// STATE
// ============================================================================

// Physical sensor state (true = magnet detected = piece physically present)
bool sensorState[BOARD_ROWS][BOARD_COLS];
bool rawState[BOARD_ROWS][BOARD_COLS];
uint8_t stableCount[BOARD_ROWS][BOARD_COLS];

// Logical piece map — tracks which piece is on each square
char pieceMap[BOARD_ROWS][BOARD_COLS];

// Lifted piece tracking — remembers a piece that is currently "in the air"
char  liftedPiece    = '.';   // The piece character being held
int   liftedFromRow  = -1;    // Where it was lifted from
int   liftedFromCol  = -1;

unsigned long lastScanTime = 0;

Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);

// ============================================================================
// MUX CONTROL
// ============================================================================

// Set the 3 address pins of a CD74HC4067 to select a channel (0-7).
// S3 is hardwired to GND, so channels 0-7 are accessible.
void setMuxChannel(int s0Pin, int s1Pin, int s2Pin, int channel) {
  digitalWrite(s0Pin, (channel     ) & 1);
  digitalWrite(s1Pin, (channel >> 1) & 1);
  digitalWrite(s2Pin, (channel >> 2) & 1);
}

// ============================================================================
// BOARD SCANNING
// ============================================================================

// Scan every cell in the matrix and store results in rawState[][].
void scanBoard() {
  for (int row = 0; row < BOARD_ROWS; row++) {
    setMuxChannel(ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, row);
    delayMicroseconds(MUX_SETTLE_US);

    for (int col = 0; col < BOARD_COLS; col++) {
      setMuxChannel(COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, col);
      delayMicroseconds(MUX_SETTLE_US);

      // LOW = magnet detected = piece present (active-low sensor)
      rawState[row][col] = (digitalRead(MUX_READ_PIN) == LOW);
    }
  }
}

// ============================================================================
// DEBOUNCING
// ============================================================================

// Apply debouncing on the raw sensor readings.
// Returns true if any square's physical state changed.
bool applyDebounce() {
  bool changed = false;

  for (int row = 0; row < BOARD_ROWS; row++) {
    for (int col = 0; col < BOARD_COLS; col++) {
      if (rawState[row][col] == sensorState[row][col]) {
        stableCount[row][col] = 0;
      } else {
        stableCount[row][col]++;
        if (stableCount[row][col] >= DEBOUNCE_THRESHOLD) {
          sensorState[row][col] = rawState[row][col];
          stableCount[row][col] = 0;
          changed = true;
        }
      }
    }
  }

  return changed;
}

// ============================================================================
// PIECE TRACKING
// ============================================================================

// Process sensor changes and update the logical piece map.
// Handles lift (piece removed) and place (piece set down) events.
void processChanges(bool oldSensor[BOARD_ROWS][BOARD_COLS]) {
  // First pass: detect all lifts (removals)
  for (int row = 0; row < BOARD_ROWS; row++) {
    for (int col = 0; col < BOARD_COLS; col++) {
      if (oldSensor[row][col] && !sensorState[row][col]) {
        // Piece was LIFTED from this square
        char piece = pieceMap[row][col];

        if (piece != '.') {
          // If we already had a piece in the air, something unexpected
          // happened (e.g. two pieces lifted at once). Put the previous
          // lifted piece back where it came from as a safety fallback.
          if (liftedPiece != '.') {
            Serial.print("WARNING: ");
            Serial.print(pieceName(liftedPiece));
            Serial.print(" was still in the air from [");
            Serial.print(liftedFromRow);
            Serial.print(",");
            Serial.print(liftedFromCol);
            Serial.println("] — placing it back.");
            pieceMap[liftedFromRow][liftedFromCol] = liftedPiece;
          }

          liftedPiece   = piece;
          liftedFromRow  = row;
          liftedFromCol  = col;
          pieceMap[row][col] = '.';

          Serial.print(pieceName(liftedPiece));
          Serial.print(" lifted from [");
          Serial.print(row);
          Serial.print(",");
          Serial.print(col);
          Serial.println("]");
        }
      }
    }
  }

  // Second pass: detect all places (arrivals)
  for (int row = 0; row < BOARD_ROWS; row++) {
    for (int col = 0; col < BOARD_COLS; col++) {
      if (!oldSensor[row][col] && sensorState[row][col]) {
        // Piece was PLACED on this square
        if (liftedPiece != '.') {
          // We know which piece was in the air — place it here
          char captured = pieceMap[row][col];

          if (captured != '.') {
            Serial.print(pieceName(captured));
            Serial.print(" captured at [");
            Serial.print(row);
            Serial.print(",");
            Serial.print(col);
            Serial.println("]!");
          }

          pieceMap[row][col] = liftedPiece;

          if (row == liftedFromRow && col == liftedFromCol) {
            Serial.print(pieceName(liftedPiece));
            Serial.println(" placed back on its square.");
          } else {
            Serial.print(pieceName(liftedPiece));
            Serial.print(" moved [");
            Serial.print(liftedFromRow);
            Serial.print(",");
            Serial.print(liftedFromCol);
            Serial.print("] -> [");
            Serial.print(row);
            Serial.print(",");
            Serial.print(col);
            Serial.println("]");
          }

          liftedPiece   = '.';
          liftedFromRow  = -1;
          liftedFromCol  = -1;
        } else {
          // No piece was tracked as lifted — unknown piece placed.
          // This can happen if the board is set up differently than expected.
          Serial.print("WARNING: Unknown piece placed at [");
          Serial.print(row);
          Serial.print(",");
          Serial.print(col);
          Serial.println("] — marking as '?'");
          pieceMap[row][col] = '?';
        }
      }
    }
  }
}

// ============================================================================
// SERIAL OUTPUT
// ============================================================================

// Print the piece map as a grid with file/rank labels.
// Uses chess notation characters (uppercase=White, lowercase=Black, .=empty).
void printBoardState() {
  Serial.println();

  // Column headers (files)
  Serial.print("   ");
  for (int col = 0; col < BOARD_COLS; col++) {
    Serial.print(" ");
    Serial.print((char)('a' + col));  // a, b, c, d, ...
  }
  Serial.println();

  Serial.print("   ");
  for (int col = 0; col < BOARD_COLS; col++) {
    Serial.print("--");
  }
  Serial.println();

  // Board rows (ranks, numbered from bottom in chess but row 0 = rank 1)
  for (int row = BOARD_ROWS - 1; row >= 0; row--) {
    Serial.print(" ");
    Serial.print(row + 1);  // Rank number (1-based)
    Serial.print("|");
    for (int col = 0; col < BOARD_COLS; col++) {
      Serial.print(" ");
      Serial.print(pieceMap[row][col]);
    }
    Serial.println();
  }
  Serial.println();

  // Show lifted piece if any
  if (liftedPiece != '.') {
    Serial.print("In the air: ");
    Serial.print(pieceName(liftedPiece));
    Serial.print(" (from [");
    Serial.print(liftedFromRow);
    Serial.print(",");
    Serial.print(liftedFromCol);
    Serial.println("])");
    Serial.println();
  }
}

// ============================================================================
// LED CONTROL
// ============================================================================

// Convert board [row, col] to serpentine LED strip index.
// Even rows (0, 2, 4...): left-to-right.  Odd rows (1, 3, 5...): right-to-left.
int getLedIndex(int row, int col) {
  if (row % 2 == 0) {
    return row * BOARD_COLS + col;
  } else {
    return row * BOARD_COLS + (BOARD_COLS - 1 - col);
  }
}

// Update LEDs based on sensor state changes.
// Lights up blue where a piece was just lifted; turns off where a piece landed.
void updateLeds(bool oldSensor[BOARD_ROWS][BOARD_COLS]) {
  bool needShow = false;

  for (int row = 0; row < BOARD_ROWS; row++) {
    for (int col = 0; col < BOARD_COLS; col++) {
      if (sensorState[row][col] != oldSensor[row][col]) {
        int idx = getLedIndex(row, col);
        if (!sensorState[row][col]) {
          // Piece was LIFTED → light up blue
          strip.setPixelColor(idx, strip.Color(0, 0, 255));
        } else {
          // Piece was PLACED → turn off LED
          strip.setPixelColor(idx, strip.Color(0, 0, 0));
        }
        needShow = true;
      }
    }
  }

  if (needShow) {
    strip.show();
  }
}

// ============================================================================
// SETUP
// ============================================================================

void setup() {
  Serial.begin(115200);
  while (!Serial) { delay(10); }

  // Configure MUX select pins as outputs
  pinMode(ROW_MUX_S0, OUTPUT);
  pinMode(ROW_MUX_S1, OUTPUT);
  pinMode(ROW_MUX_S2, OUTPUT);
  pinMode(COL_MUX_S0, OUTPUT);
  pinMode(COL_MUX_S1, OUTPUT);
  pinMode(COL_MUX_S2, OUTPUT);

  // Configure read pin as input (GPIO 35 is input-only, no internal pull-up)
  pinMode(MUX_READ_PIN, INPUT);

  // Initialize LED strip
  strip.begin();
  strip.setBrightness(LED_BRIGHTNESS);
  strip.show();  // All LEDs off

  // Initialize sensor states and debounce counters
  for (int r = 0; r < BOARD_ROWS; r++) {
    for (int c = 0; c < BOARD_COLS; c++) {
      sensorState[r][c] = false;
      rawState[r][c]    = false;
      stableCount[r][c] = 0;
    }
  }

  // Load starting position into piece map
  for (int r = 0; r < BOARD_ROWS; r++) {
    for (int c = 0; c < BOARD_COLS; c++) {
      pieceMap[r][c] = INITIAL_POSITION[r][c];
    }
  }

  // Startup banner
  Serial.println("========================================");
  Serial.println("  Smart Chess Board - 4x4 Prototype");
  Serial.println("========================================");
  Serial.println();
  Serial.println("Pin assignments:");
  Serial.println("  Row MUX S0-S2 : GPIO 25, 26, 27");
  Serial.println("  Col MUX S0-S2 : GPIO 16, 17, 18");
  Serial.println("  MUX Read      : GPIO 35");
  Serial.println("  MUX S3 (both) : tied to GND");
  Serial.println("  MUX EN (both) : tied to GND");
  Serial.println("  LED strip     : GPIO 13");
  Serial.println();
  Serial.print("Board size: ");
  Serial.print(BOARD_ROWS);
  Serial.print("x");
  Serial.println(BOARD_COLS);
  Serial.print("Scan interval: ");
  Serial.print(SCAN_INTERVAL_MS);
  Serial.println(" ms");
  Serial.print("Debounce threshold: ");
  Serial.print(DEBOUNCE_THRESHOLD);
  Serial.println(" reads");
  Serial.println();

  // Initial sensor scan — accept raw state directly (no debounce)
  scanBoard();
  for (int r = 0; r < BOARD_ROWS; r++) {
    for (int c = 0; c < BOARD_COLS; c++) {
      sensorState[r][c] = rawState[r][c];
    }
  }

  Serial.println("Starting position loaded:");
  printBoardState();

  lastScanTime = millis();
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
  unsigned long now = millis();

  if (now - lastScanTime >= SCAN_INTERVAL_MS) {
    lastScanTime = now;

    // Save old sensor state for change detection
    bool oldSensor[BOARD_ROWS][BOARD_COLS];
    for (int r = 0; r < BOARD_ROWS; r++) {
      for (int c = 0; c < BOARD_COLS; c++) {
        oldSensor[r][c] = sensorState[r][c];
      }
    }

    // Scan and debounce
    scanBoard();
    bool changed = applyDebounce();

    if (changed) {
      // Update piece tracking, LEDs, and print state
      processChanges(oldSensor);
      updateLeds(oldSensor);
      printBoardState();
    }
  }
}
