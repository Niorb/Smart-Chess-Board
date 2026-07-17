import serial
import time

ser = serial.Serial('/dev/ttyUSB0', 921600, timeout=0.1)
ser.reset_input_buffer()

print("Sending 'B' command...")
ser.write(b'B')

# Record raw data for 3 seconds
start_time = time.time()
raw_bytes = b""
while time.time() - start_time < 3.0:
    if ser.in_waiting > 0:
        raw_bytes += ser.read(ser.in_waiting)
    time.sleep(0.01)

print("\n--- Raw Received Data (Bytes) ---")
print(raw_bytes)
print("\n--- Decoded String ---")
print(raw_bytes.decode('utf-8', errors='ignore'))
