/*
 * HardwareTest.ino
 *
 * Standalone test script for the Smart Chess Board hardware.
 * Runs two tests in sequence:
 *   1. LED strip chase — lights each LED one by one, then flashes all.
 *   2. Live sensor monitor — scans the Hall sensor matrix and mirrors
 *      sensor state onto the LED strip in real time.
 *
 * Uses the same pinout as SmartChessBoard.ino.
 *
 * Requires: Adafruit NeoPixel library (install via Arduino IDE Library Manager).
 */

#include <Adafruit_NeoPixel.h>

// ============================================================================
// CONFIGURATION — must match SmartChessBoard.ino
// ============================================================================

#define BOARD_ROWS 4
#define BOARD_COLS 4

// Row MUX select pins
#define ROW_MUX_S0 25
#define ROW_MUX_S1 26
#define ROW_MUX_S2 27

// Column MUX select pins
#define COL_MUX_S0 16
#define COL_MUX_S1 17
#define COL_MUX_S2 18

// Read pin
#define MUX_READ_PIN 32

// WS2812B LED strip
#define LED_PIN        13
#define NUM_LEDS       (BOARD_ROWS * BOARD_COLS)
#define LED_BRIGHTNESS 50

// Timing
#define MUX_SETTLE_US      100000
#define SCAN_INTERVAL_MS   5000
#define DEBOUNCE_THRESHOLD 1

// ============================================================================
// STATE
// ============================================================================

bool sensorState[BOARD_ROWS][BOARD_COLS];
bool rawState[BOARD_ROWS][BOARD_COLS];
uint8_t stableCount[BOARD_ROWS][BOARD_COLS];

Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);

unsigned long lastScanTime = 0;

// ============================================================================
// SHARED HELPERS
// ============================================================================

void setMuxChannel(int s0Pin, int s1Pin, int s2Pin, int channel) {
  digitalWrite(s0Pin, (channel     ) & 1);
  digitalWrite(s1Pin, (channel >> 1) & 1);
  digitalWrite(s2Pin, (channel >> 2) & 1);
}

// Serpentine LED index mapping
int getLedIndex(int row, int col) {
  if (row % 2 == 0) {
    return row * BOARD_COLS + col;
  } else {
    return row * BOARD_COLS + (BOARD_COLS - 1 - col);
  }
}

void scanBoard() {
  for (int row = 0; row < BOARD_ROWS; row++) {
    setMuxChannel(ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, row);
    delayMicroseconds(MUX_SETTLE_US);
    digitalRead(MUX_READ_PIN);
    delayMicroseconds(MUX_SETTLE_US);

    for (int col = 0; col < BOARD_COLS; col++) {
      setMuxChannel(COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, col);
      delayMicroseconds(MUX_SETTLE_US);
      rawState[row][col] = (digitalRead(MUX_READ_PIN) == LOW);
    }
  }
  setMuxChannel(ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, 5);
  setMuxChannel(COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, 5);
}

bool applyDebounce() {
  bool changed = false;
  for (int r = 0; r < BOARD_ROWS; r++) {
    for (int c = 0; c < BOARD_COLS; c++) {
      if (rawState[r][c] == sensorState[r][c]) {
        stableCount[r][c] = 0;
      } else {
        stableCount[r][c]++;
        if (stableCount[r][c] >= DEBOUNCE_THRESHOLD) {
          sensorState[r][c] = rawState[r][c];
          stableCount[r][c] = 0;
          changed = true;
        }
      }
    }
  }
  return changed;
}

// ============================================================================
// TEST 1: LED STRIP CHASE
// ============================================================================

void testLedChase() {
  Serial.println("========================================");
  Serial.println("  TEST 1: LED Strip Chase");
  Serial.println("========================================");
  Serial.println();
  Serial.println("Each LED will light GREEN one by one.");
  Serial.println("Watch the strip and verify the order.");
  Serial.println();

  // Chase: light each LED individually
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.clear();
    strip.setPixelColor(i, strip.Color(0, 255, 0));  // Green
    strip.show();

    Serial.print("  LED ");
    Serial.print(i);
    Serial.print(" ON  (row ");
    // Reverse-map LED index to row,col for reference
    int row = i / BOARD_COLS;
    int col;
    if (row % 2 == 0) {
      col = i % BOARD_COLS;
    } else {
      col = (BOARD_COLS - 1) - (i % BOARD_COLS);
    }
    Serial.print(row);
    Serial.print(", col ");
    Serial.print(col);
    Serial.println(")");

    delay(200);
  }

  strip.clear();
  strip.show();
  delay(300);

  // Flash all LEDs white 3 times
  Serial.println();
  Serial.println("Flashing all LEDs WHITE 3 times...");
  for (int flash = 0; flash < 3; flash++) {
    for (int i = 0; i < NUM_LEDS; i++) {
      strip.setPixelColor(i, strip.Color(255, 255, 255));
    }
    strip.show();
    delay(300);

    strip.clear();
    strip.show();
    delay(300);
  }

  Serial.println("LED chase test DONE.");
  Serial.println();
}

// ============================================================================
// TEST 2: LIVE SENSOR → LED MONITOR
// ============================================================================

void printSensorGrid() {
  Serial.println();
  Serial.print("   ");
  for (int c = 0; c < BOARD_COLS; c++) {
    Serial.print(" ");
    Serial.print(c);
  }
  Serial.println();

  Serial.print("   ");
  for (int c = 0; c < BOARD_COLS; c++) {
    Serial.print("--");
  }
  Serial.println();

  for (int r = 0; r < BOARD_ROWS; r++) {
    Serial.print(" ");
    Serial.print(r);
    Serial.print("|");
    for (int c = 0; c < BOARD_COLS; c++) {
      Serial.print(" ");
      Serial.print(sensorState[r][c] ? "1" : "0");
    }
    Serial.println();
  }
  Serial.println();
}

void updateLedsFromSensors() {
  for (int r = 0; r < BOARD_ROWS; r++) {
    for (int c = 0; c < BOARD_COLS; c++) {
      int idx = getLedIndex(r, c);
      if (sensorState[r][c]) {
        strip.setPixelColor(idx, strip.Color(0, 255, 0));  // Green = magnet
      } else {
        strip.setPixelColor(idx, strip.Color(0, 0, 0));    // Off = no magnet
      }
    }
  }
  strip.show();
}

// ============================================================================
// SETUP & LOOP
// ============================================================================

void setup() {
  Serial.begin(115200);
  while (!Serial) { delay(10); }

  // Configure pins
  pinMode(ROW_MUX_S0, OUTPUT);
  pinMode(ROW_MUX_S1, OUTPUT);
  pinMode(ROW_MUX_S2, OUTPUT);
  pinMode(COL_MUX_S0, OUTPUT);
  pinMode(COL_MUX_S1, OUTPUT);
  pinMode(COL_MUX_S2, OUTPUT);
  pinMode(MUX_READ_PIN, INPUT);

  // Initialize LED strip
  strip.begin();
  strip.setBrightness(LED_BRIGHTNESS);
  strip.show();

  // Initialize sensor state
  for (int r = 0; r < BOARD_ROWS; r++) {
    for (int c = 0; c < BOARD_COLS; c++) {
      sensorState[r][c] = false;
      rawState[r][c]    = false;
      stableCount[r][c] = 0;
    }
  }

  Serial.println();
  Serial.println("========================================");
  Serial.println("  Smart Chess Board — Hardware Test");
  Serial.println("========================================");
  Serial.println();

  // ----- TEST 1: LED Chase -----
  testLedChase();

  // ----- TEST 2: Sensor Monitor starts here -----
  Serial.println("========================================");
  Serial.println("  TEST 2: Live Sensor -> LED Monitor");
  Serial.println("========================================");
  Serial.println();
  Serial.println("Place/remove magnets on the board.");
  Serial.println("LED lights GREEN where a magnet is detected.");
  Serial.println("Grid: 1 = magnet, 0 = empty.");
  Serial.println();

  // Initial scan
  scanBoard();
  for (int r = 0; r < BOARD_ROWS; r++) {
    for (int c = 0; c < BOARD_COLS; c++) {
      sensorState[r][c] = rawState[r][c];
    }
  }
  updateLedsFromSensors();
  printSensorGrid();

  lastScanTime = millis();
}

void loop() {
  unsigned long now = millis();

  if (now - lastScanTime >= SCAN_INTERVAL_MS) {
    lastScanTime = now;

    scanBoard();
    bool changed = applyDebounce();

    if (changed) {
      updateLedsFromSensors();
      printSensorGrid();
    }
  }
}
