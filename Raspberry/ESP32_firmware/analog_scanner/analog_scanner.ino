/**
 * analog_scanner.ino
 *
 * ESP32 firmware for the Smart Chess Board.
 * Acts as an on-demand ADC coprocessor over Serial.
 * 
 * Batch scan mode: controlled by 'B' command.
 * MUX settling delay: controlled by 'S<ms>' command.
 */

#include <Adafruit_NeoPixel.h>

#define PIN_STRIP1 23
#define PIN_STRIP2 22
#define NUM_LEDS_PER_STRIP 72

Adafruit_NeoPixel strip1(NUM_LEDS_PER_STRIP, PIN_STRIP1, NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel strip2(NUM_LEDS_PER_STRIP, PIN_STRIP2, NEO_GRB + NEO_KHZ800);

// Pin definitions
const int MUX_ANALOG_IN = 34;

// MUX Select pins (CD74HC4067)
const int ROW_MUX_S0 = 25;
const int ROW_MUX_S1 = 26;
const int ROW_MUX_S2 = 27;
const int ROW_MUX_S3 = 14;

const int COL_MUX_S0 = 16;
const int COL_MUX_S1 = 17;
const int COL_MUX_S2 = 18;
const int COL_MUX_S3 = 19;

// Default MUX settling delay (us)
int settle_us = 100;

// Cache to store the latest raw scan of the 4x8 matrix
uint16_t latest_scan[32] = {0};

void setMuxChannel(int s0, int s1, int s2, int s3, int channel) {
  digitalWrite(s0, (channel & 1) ? HIGH : LOW);
  digitalWrite(s1, (channel & 2) ? HIGH : LOW);
  digitalWrite(s2, (channel & 4) ? HIGH : LOW);
  digitalWrite(s3, (channel & 8) ? HIGH : LOW);
}

void scanMatrix() {
  for (int r = 0; r < 4; r++) {
    setMuxChannel(ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, ROW_MUX_S3, r);
    for (int col = 0; col < 8; col++) {
      // Hardware column mapping swap: 0-3 is reversed, 4-7 is direct
      int hw_col = (col < 4) ? (3 - col) : col;
      setMuxChannel(COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, COL_MUX_S3, hw_col);
      
      delayMicroseconds(settle_us);
      
      // Double read to settle the internal ESP32 sample-and-hold circuit
      analogRead(MUX_ANALOG_IN);
      latest_scan[r * 8 + col] = analogRead(MUX_ANALOG_IN);
    }
  }
}

void setup() {
  Serial.begin(921600);
  
  // Configure MUX select pins as outputs
  pinMode(ROW_MUX_S0, OUTPUT);
  pinMode(ROW_MUX_S1, OUTPUT);
  pinMode(ROW_MUX_S2, OUTPUT);
  pinMode(ROW_MUX_S3, OUTPUT);
  
  // Configure MUX column select pins
  pinMode(COL_MUX_S0, OUTPUT);
  pinMode(COL_MUX_S1, OUTPUT);
  pinMode(COL_MUX_S2, OUTPUT);
  pinMode(COL_MUX_S3, OUTPUT);
  
  // Default to channel 0
  setMuxChannel(ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, ROW_MUX_S3, 0);
  setMuxChannel(COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, COL_MUX_S3, 0);

  // Configure ADC: 11dB attenuation provides ~0V to 3.6V range.
  analogSetAttenuation(ADC_11db); 
  analogSetWidth(12);

  // Initialize LED Strips
  strip1.begin();
  strip2.begin();
  strip1.show();
  strip2.show();
}

void loop() {
  if (Serial.available() > 0) {
    char c = Serial.read();
    
    if (c == 'B') {
      // Write binary packet header
      Serial.write(0xAA);
      Serial.write(0x55);
      // Write 64 bytes of raw ADC data (32 uint16_t values)
      Serial.write((uint8_t*)latest_scan, 64);
    } 
    else if (c == 'L') {
      // Set pixel color
      unsigned long start = millis();
      while (Serial.available() < 4 && (millis() - start) < 10) {
        // Wait for index, R, G, B with 10ms timeout
      }
      if (Serial.available() >= 4) {
        int idx = Serial.read();
        int r = Serial.read();
        int g = Serial.read();
        int b = Serial.read();
        
        if (idx >= 0 && idx < NUM_LEDS_PER_STRIP) {
          strip1.setPixelColor(idx, strip1.Color(r, g, b));
        } else if (idx >= NUM_LEDS_PER_STRIP && idx < 2 * NUM_LEDS_PER_STRIP) {
          strip2.setPixelColor(idx - NUM_LEDS_PER_STRIP, strip2.Color(r, g, b));
        }
      }
    }
    else if (c == 'W') {
      // Show (write) changes
      strip1.show();
      strip2.show();
    }
    else if (c == 'C') {
      // Clear all
      for (int i = 0; i < NUM_LEDS_PER_STRIP; i++) {
        strip1.setPixelColor(i, 0);
        strip2.setPixelColor(i, 0);
      }
      strip1.show();
      strip2.show();
    }
    else if (c == 'A') {
      // Set all to color
      unsigned long start = millis();
      while (Serial.available() < 3 && (millis() - start) < 10) {
        // Wait for R, G, B with 10ms timeout
      }
      if (Serial.available() >= 3) {
        int r = Serial.read();
        int g = Serial.read();
        int b = Serial.read();
        for (int i = 0; i < NUM_LEDS_PER_STRIP; i++) {
          strip1.setPixelColor(i, strip1.Color(r, g, b));
          strip2.setPixelColor(i, strip2.Color(r, g, b));
        }
        strip1.show();
        strip2.show();
      }
    }
    else if (c == 'S') {
      // Read 1 raw byte for settling delay
      unsigned long start = millis();
      while (Serial.available() == 0 && (millis() - start) < 10) {
        // wait for the byte with 10ms timeout
      }
      if (Serial.available() > 0) {
        int val = Serial.read();
        if (val >= 0 && val <= 255) {
          settle_us = val;
        }
      }
    }
  } else {
    // Perform continuous background scan
    scanMatrix();
  }
}

