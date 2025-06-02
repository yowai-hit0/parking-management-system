import cv2
from ultralytics import YOLO
import pytesseract
import os
import time
import serial
import serial.tools.list_ports
import psycopg2
from collections import Counter
from datetime import datetime

# Load YOLOv8 model
model = YOLO('best.pt')

# Plate save directory
save_dir = 'plates'
os.makedirs(save_dir, exist_ok=True)


# PostgreSQL connection setup
def setup_postgres():
    try:
        conn = psycopg2.connect(
            dbname="parking_db",
            user="postgres",
            password="gomgom1029",
            host="localhost"
        )
        cur = conn.cursor()

        # Create table if it doesn't exist
        cur.execute("""
                    CREATE TABLE IF NOT EXISTS plates_log
                    (
                        id
                        SERIAL
                        PRIMARY
                        KEY,
                        plate_number
                        VARCHAR
                    (
                        20
                    ),
                        payment_status INTEGER,
                        entry_time TIMESTAMP,
                        exit_time TIMESTAMP NULL,
                        amount NUMERIC
                        )
                    """)
        conn.commit()
        return conn
    except Exception as e:
        print(f"[POSTGRES ERROR] Connection failed: {e}")
        return None


postgres_conn = setup_postgres()


def can_enter(plate_number):
    """Check if vehicle can enter (has no active parking session)"""
    if not postgres_conn:
        return True  # Assume can enter if DB not available

    try:
        cur = postgres_conn.cursor()
        cur.execute("""
                    SELECT exit_time, payment_status
                    FROM plates_log
                    WHERE plate_number = %s
                    ORDER BY entry_time DESC LIMIT 1
                    """, (plate_number,))
        result = cur.fetchone()

        if not result:
            return True  # No previous records

        exit_time, payment_status = result
        # Can enter if either:
        # 1. Has exited (exit_time not NULL) OR
        # 2. Has paid (payment_status = 1) but hasn't exited yet
        return exit_time is not None or payment_status == 1
    except Exception as e:
        print(f"[POSTGRES ERROR] Check entry failed: {e}")
        return True  # Fail-safe: allow entry


# ===== Auto-detect Arduino Serial Port =====
def detect_arduino_port():
    ports = list(serial.tools.list_ports.comports())
    for port in ports:
        if "COM" in port.device or "wchusbmodem" in port.device:
            return port.device
    return None


arduino_port = detect_arduino_port()
if arduino_port:
    arduino_port = "COM7"
    print(f"[CONNECTED] Arduino on {arduino_port}")
    arduino = serial.Serial(arduino_port, 9600, timeout=1)
    print(f"[CONNECTED] Arduino on {arduino_port}")
    time.sleep(2)
else:
    print("[ERROR] Arduino not detected.")
    arduino = None

# ===== Ultrasonic Sensor Setup =====
import random


def mock_ultrasonic_distance():
    raw = arduino.readline()
    try:
        distance = float(raw.decode('utf-8').strip())
        print(f"{distance} cm")
        return distance
    except ValueError:
        print("Received invalid data from serial:", raw)
        return random.choice([random.randint(10, 40)])


# Initialize webcam
cap = cv2.VideoCapture(0)
plate_buffer = []
entry_cooldown = 300  # 5 minutes
last_saved_plate = None
last_entry_time = 0

print("[SYSTEM] Ready. Press 'q' to exit.")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    distance = mock_ultrasonic_distance()
    print(f"[SENSOR] Distance: {distance} cm")

    if distance <= 50:
        results = model(frame)

        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                plate_img = frame[y1:y2, x1:x2]

                # Plate Image Processing
                gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

                # OCR Extraction
                plate_text = pytesseract.image_to_string(
                    thresh, config='--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                ).strip().replace(" ", "")

                # Plate Validation
                if "RA" in plate_text:
                    start_idx = plate_text.find("RA")
                    plate_candidate = plate_text[start_idx:]
                    if len(plate_candidate) >= 7:
                        plate_candidate = plate_candidate[:7]
                        prefix, digits, suffix = plate_candidate[:3], plate_candidate[3:6], plate_candidate[6]
                        if (prefix.isalpha() and prefix.isupper() and
                                digits.isdigit() and suffix.isalpha() and suffix.isupper()):
                            print(f"[VALID] Plate Detected: {plate_candidate}")
                            plate_buffer.append(plate_candidate)

                            # Decision after 3 captures
                            if len(plate_buffer) >= 1:
                                most_common = Counter(plate_buffer).most_common(1)[0][0]
                                current_time = time.time()

                                if (most_common != last_saved_plate or
                                        (current_time - last_entry_time) > entry_cooldown):

                                    # Check if vehicle can enter
                                    if not can_enter(most_common):
                                        print(f"[DENIED] Vehicle {most_common} already has an active parking session")
                                        plate_buffer.clear()
                                        continue

                                    if postgres_conn:
                                        try:
                                            cur = postgres_conn.cursor()
                                            cur.execute("""
                                                        INSERT INTO plates_log
                                                            (plate_number, payment_status, entry_time, exit_time, amount)
                                                        VALUES (%s, %s, %s, %s, %s)
                                                        """, (most_common, 0, datetime.now(), None, 0))
                                            postgres_conn.commit()
                                            print(f"[SAVED] {most_common} logged to PostgreSQL.")
                                        except Exception as e:
                                            print(f"[POSTGRES ERROR] Failed to insert record: {e}")
                                            postgres_conn.rollback()

                                    if arduino:
                                        arduino.write(b'1')
                                        print("[GATE] Opening gate (sent '1')")
                                        time.sleep(15)  # Gate open duration
                                        arduino.write(b'0')
                                        print("[GATE] Closing gate (sent '0')")

                                    last_saved_plate = most_common
                                    last_entry_time = current_time
                                else:
                                    print("[SKIPPED] Duplicate within 5 min window.")

                                plate_buffer.clear()

                cv2.imshow("Plate", plate_img)
                cv2.imshow("Processed", thresh)
                time.sleep(0.5)

    annotated_frame = results[0].plot() if distance <= 50 else frame
    cv2.imshow('Webcam Feed', annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
if arduino:
    arduino.close()
if postgres_conn:
    postgres_conn.close()
cv2.destroyAllWindows()