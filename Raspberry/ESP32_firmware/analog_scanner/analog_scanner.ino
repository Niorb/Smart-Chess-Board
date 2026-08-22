/**
 * analog_scanner.ino
 *
 * ESP32 firmware for the Smart Chess Board.
 * Acts as an on-demand ADC coprocessor & WS2812B dual-strip LED controller over Serial.
 *
 * Supports:
 * - High-speed binary framing protocol (0xAA 0x55, CMD, LEN LE, PAYLOAD, CRC8-CCITT)
 * - Commands:
 *     CMD_PING (0x00) -> RESP_PONG (0x80)
 *     CMD_SCAN_ADC (0x01) -> RESP_ADC_DATA (0x81) with 128 bytes ADC data + CRC8
 *                           (served from the freshness-gated cache; rescanned only when stale)
 *     CMD_SET_SETTLE (0x02) -> sets settle_us
 *     CMD_SET_LEDS (0x10) -> batch set (idx, r, g, b)
 *     CMD_SET_ALL (0x11) -> set all LEDs to (r, g, b) + show
 *     CMD_CLEAR_LEDS (0x12) -> clear all LEDs + show
 *     CMD_SHOW_LEDS (0x13) -> show()
 *     CMD_SET_AND_SHOW (0x14) -> batch set (idx, r, g, b) + show()
 * - Rate-limited continuous matrix scanning during idle time (keeps the cache warm)
 */

#include <Adafruit_NeoPixel.h>

#define PIN_STRIP1 23
#define PIN_STRIP2 22
#define NUM_LEDS_PER_STRIP 76

Adafruit_NeoPixel strip1(NUM_LEDS_PER_STRIP, PIN_STRIP1, NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel strip2(NUM_LEDS_PER_STRIP, PIN_STRIP2, NEO_GRB + NEO_KHZ800);

// Pin definitions
const int MUX_ANALOG_IN = 34;

// MUX Select pins (CD74HC4067)
const int COL_MUX_S0 = 25;
const int COL_MUX_S1 = 26;
const int COL_MUX_S2 = 27;
const int COL_MUX_S3 = 14;

const int ROW_MUX_S0 = 16;
const int ROW_MUX_S1 = 17;
const int ROW_MUX_S2 = 18;
const int ROW_MUX_S3 = 19;

// Default MUX settling delay (us)
int settle_us = 100;

// Scan freshness / cadence tuning
#define SCAN_CACHE_MAX_AGE_MS 20   // Max age of a cached scan served to CMD_SCAN_ADC
#define IDLE_SCAN_INTERVAL_MS 5    // Minimum interval between idle background scans
#define PARSER_STALE_TIMEOUT_MS 50 // Reset the parser when a partial packet stalls

// Cache to store the latest raw scan of the 8x8 matrix
uint16_t latest_scan[64] = {0};
unsigned long latest_scan_ms = 0;

// Binary packet protocol constants
#define PKT_HEADER1      0xAA
#define PKT_HEADER2      0x55

#define CMD_PING         0x00
#define CMD_SCAN_ADC     0x01
#define CMD_SET_SETTLE   0x02
#define CMD_SET_LEDS     0x10
#define CMD_SET_ALL      0x11
#define CMD_CLEAR_LEDS   0x12
#define CMD_SHOW_LEDS    0x13
#define CMD_SET_AND_SHOW 0x14

#define RESP_PONG        0x80
#define RESP_ADC_DATA    0x81

// CRC-8-CCITT lookup table (polynomial 0x07, init 0x00)
static const uint8_t crc8_table[256] = {
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
};

uint8_t calc_crc8(const uint8_t* data, size_t len, uint8_t initial = 0x00) {
  uint8_t crc = initial;
  for (size_t i = 0; i < len; i++) {
    crc = crc8_table[crc ^ data[i]];
  }
  return crc;
}

// Parser state machine definitions
enum ParserState {
  STATE_IDLE = 0,
  STATE_HEADER_2,
  STATE_CMD,
  STATE_LEN_LO,
  STATE_LEN_HI,
  STATE_PAYLOAD,
  STATE_CRC
};

ParserState parser_state = STATE_IDLE;
uint8_t rx_cmd = 0;
uint16_t rx_len = 0;
uint16_t rx_payload_idx = 0;
uint8_t rx_payload[1024];
unsigned long last_rx_time = 0;

void setMuxChannel(int s0, int s1, int s2, int s3, int channel) {
  digitalWrite(s0, (channel & 1) ? HIGH : LOW);
  digitalWrite(s1, (channel & 2) ? HIGH : LOW);
  digitalWrite(s2, (channel & 4) ? HIGH : LOW);
  digitalWrite(s3, (channel & 8) ? HIGH : LOW);
}

void scanMatrix() {
  for (int file_idx = 0; file_idx < 8; file_idx++) {
    // COL_MUX select pins control Files a-h (Columns 0-7)
    setMuxChannel(COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, COL_MUX_S3, file_idx);
    for (int rank_idx = 0; rank_idx < 8; rank_idx++) {
      // ROW_MUX select pins control Ranks 1-8 (Rows 0-7)
      setMuxChannel(ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, ROW_MUX_S3, rank_idx);

      delayMicroseconds(settle_us);

      // Double read to settle the internal ESP32 sample-and-hold circuit
      analogRead(MUX_ANALOG_IN);
      latest_scan[file_idx * 8 + rank_idx] = analogRead(MUX_ANALOG_IN);
    }
  }
  latest_scan_ms = millis();
}

void sendPacket(uint8_t cmd_id, const uint8_t* payload, uint16_t length) {
  uint8_t header[3];
  header[0] = cmd_id;
  header[1] = (uint8_t)(length & 0xFF);
  header[2] = (uint8_t)((length >> 8) & 0xFF);
  
  uint8_t crc = calc_crc8(header, 3);
  if (length > 0 && payload != NULL) {
    crc = calc_crc8(payload, length, crc);
  }
  
  Serial.write(PKT_HEADER1);
  Serial.write(PKT_HEADER2);
  Serial.write(header, 3);
  if (length > 0 && payload != NULL) {
    Serial.write(payload, length);
  }
  Serial.write(crc);
}

void executeCommand(uint8_t cmd, const uint8_t* payload, uint16_t len) {
  switch (cmd) {
    case CMD_PING: {
      sendPacket(RESP_PONG, NULL, 0);
      break;
    }
    case CMD_SCAN_ADC: {
      // Serve the continuously-maintained cache when fresh; rescan only if stale.
      // Avoids re-running a full blocking scan on every host poll (previously the
      // request path AND loop()'s idle branch could each scan per request).
      if (millis() - latest_scan_ms > SCAN_CACHE_MAX_AGE_MS) {
        scanMatrix();
      }
      sendPacket(RESP_ADC_DATA, (const uint8_t*)latest_scan, 128);
      break;
    }
    case CMD_SET_SETTLE: {
      if (len >= 1) {
        settle_us = payload[0];
      }
      break;
    }
    case CMD_SET_LEDS: {
      for (size_t i = 0; i + 3 < len; i += 4) {
        uint8_t idx = payload[i];
        uint8_t r = payload[i + 1];
        uint8_t g = payload[i + 2];
        uint8_t b = payload[i + 3];
        if (idx < NUM_LEDS_PER_STRIP) {
          strip1.setPixelColor(idx, strip1.Color(r, g, b));
        } else if (idx < 2 * NUM_LEDS_PER_STRIP) {
          strip2.setPixelColor(idx - NUM_LEDS_PER_STRIP, strip2.Color(r, g, b));
        }
      }
      break;
    }
    case CMD_SET_ALL: {
      if (len >= 3) {
        uint8_t r = payload[0];
        uint8_t g = payload[1];
        uint8_t b = payload[2];
        for (int i = 0; i < NUM_LEDS_PER_STRIP; i++) {
          strip1.setPixelColor(i, strip1.Color(r, g, b));
          strip2.setPixelColor(i, strip2.Color(r, g, b));
        }
        strip1.show();
        strip2.show();
      }
      break;
    }
    case CMD_CLEAR_LEDS: {
      for (int i = 0; i < NUM_LEDS_PER_STRIP; i++) {
        strip1.setPixelColor(i, 0);
        strip2.setPixelColor(i, 0);
      }
      strip1.show();
      strip2.show();
      break;
    }
    case CMD_SHOW_LEDS: {
      strip1.show();
      strip2.show();
      break;
    }
    case CMD_SET_AND_SHOW: {
      for (size_t i = 0; i + 3 < len; i += 4) {
        uint8_t idx = payload[i];
        uint8_t r = payload[i + 1];
        uint8_t g = payload[i + 2];
        uint8_t b = payload[i + 3];
        if (idx < NUM_LEDS_PER_STRIP) {
          strip1.setPixelColor(idx, strip1.Color(r, g, b));
        } else if (idx < 2 * NUM_LEDS_PER_STRIP) {
          strip2.setPixelColor(idx - NUM_LEDS_PER_STRIP, strip2.Color(r, g, b));
        }
      }
      strip1.show();
      strip2.show();
      break;
    }
    default:
      break;
  }
}

void setup() {
  Serial.setRxBufferSize(2048);
  Serial.begin(921600);

  // Configure MUX column select pins as outputs
  pinMode(COL_MUX_S0, OUTPUT);
  pinMode(COL_MUX_S1, OUTPUT);
  pinMode(COL_MUX_S2, OUTPUT);
  pinMode(COL_MUX_S3, OUTPUT);

  // Configure MUX row select pins
  pinMode(ROW_MUX_S0, OUTPUT);
  pinMode(ROW_MUX_S1, OUTPUT);
  pinMode(ROW_MUX_S2, OUTPUT);
  pinMode(ROW_MUX_S3, OUTPUT);

  // Default to channel 0
  setMuxChannel(COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, COL_MUX_S3, 0);
  setMuxChannel(ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, ROW_MUX_S3, 0);

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
  // Resynchronize the parser when a partially received stream stalls mid-packet,
  // independent of whether new bytes keep arriving.
  if (parser_state != STATE_IDLE && (millis() - last_rx_time > PARSER_STALE_TIMEOUT_MS)) {
    parser_state = STATE_IDLE;
  }

  if (Serial.available() > 0) {
    last_rx_time = millis();

    uint8_t c = (uint8_t)Serial.read();

    switch (parser_state) {
      case STATE_IDLE: {
        if (c == PKT_HEADER1) {
          parser_state = STATE_HEADER_2;
        }
        break;
      }
      case STATE_HEADER_2: {
        if (c == PKT_HEADER2) {
          parser_state = STATE_CMD;
        } else if (c != PKT_HEADER1) {
          parser_state = STATE_IDLE;
        }
        break;
      }
      case STATE_CMD: {
        rx_cmd = c;
        parser_state = STATE_LEN_LO;
        break;
      }
      case STATE_LEN_LO: {
        rx_len = c;
        parser_state = STATE_LEN_HI;
        break;
      }
      case STATE_LEN_HI: {
        rx_len |= ((uint16_t)c << 8);
        rx_payload_idx = 0;
        if (rx_len > sizeof(rx_payload)) {
          parser_state = STATE_IDLE;
        } else if (rx_len == 0) {
          parser_state = STATE_CRC;
        } else {
          parser_state = STATE_PAYLOAD;
        }
        break;
      }
      case STATE_PAYLOAD: {
        rx_payload[rx_payload_idx++] = c;
        if (rx_payload_idx >= rx_len) {
          parser_state = STATE_CRC;
        }
        break;
      }
      case STATE_CRC: {
        uint8_t received_crc = c;
        parser_state = STATE_IDLE;

        uint8_t header_buf[3];
        header_buf[0] = rx_cmd;
        header_buf[1] = (uint8_t)(rx_len & 0xFF);
        header_buf[2] = (uint8_t)((rx_len >> 8) & 0xFF);

        uint8_t expected_crc = calc_crc8(header_buf, 3);
        if (rx_len > 0) {
          expected_crc = calc_crc8(rx_payload, rx_len, expected_crc);
        }

        if (received_crc == expected_crc) {
          executeCommand(rx_cmd, rx_payload, rx_len);
        }
        break;
      }
    }
  } else if (millis() - latest_scan_ms >= IDLE_SCAN_INTERVAL_MS) {
    // Rate-limited background scan keeps the cache warm without pinning the CPU/ADC
    scanMatrix();
  }
}


