/**
 * analog_scanner.ino
 *
 * ESP32 firmware for the Smart Chess Board.
 * Acts as an on-demand ADC coprocessor over Serial.
 * 
 * FIX: Only sends data when 'R' is received.
 */

const int MUX_ANALOG_IN = 34; 

void setup() {
  Serial.begin(115200);
  
  // Configure ADC: 11dB attenuation provides ~0V to 3.6V range.
  analogSetAttenuation(ADC_11db); 
  analogSetWidth(12);
  
  // No pinMode(MUX_ANALOG_IN, INPUT) here for ADC1 pins.
}

void loop() {
  if (Serial.available() > 0) {
    char c = Serial.read();
    if (c == 'R') {
      analogRead(MUX_ANALOG_IN);
      long value = analogRead(MUX_ANALOG_IN);
      Serial.println(value);
    }
  }
}
