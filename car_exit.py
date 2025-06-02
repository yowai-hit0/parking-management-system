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
import random
# Load YOLOv8 model (same model as entry)
model = YOLO('best.pt')


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

        # Create table if it doesn't exist (should already exist from entry system)
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


def is_payment_complete(plate_number):
    """Check payment status in PostgreSQL database for the most recent entry"""
    if not postgres_conn:
        return False

    try:
        cur = postgres_conn.cursor()
        cur.execute("""
                    SELECT payment_status
                    FROM plates_log
                    WHERE plate_number = %s
                    ORDER BY entry_time DESC LIMIT 1
                    """, (plate_number,))
        result = cur.fetchone()

        if result:
            return result[0] == 1
        return False
    except Exception as e:
        print(f"[POSTGRES ERROR] Payment check failed: {e}")
        return False


def update_exit_time(plate_number):
    """Update the exit time for the most recent entry of this plate"""
    if not postgres_conn:
        return False

    try:
        cur = postgres_conn.cursor()
        # First find the most recent entry for this plate that hasn't exited yet
        cur.execute("""
                    SELECT id
                    FROM plates_log
                    WHERE plate_number = %s
                      AND exit_time IS NULL
                    ORDER BY entry_time DESC LIMIT 1
                    """, (plate_number,))
        result = cur.fetchone()

        if result:
            record_id = result[0]
            # Now update just that specific record
            cur.execute("""
                        UPDATE plates_log
                        SET exit_time = %s
                        WHERE id = %s
                        """, (datetime.now(), record_id))
            postgres_conn.commit()
            print(f"[POSTGRES] Updated exit time for {plate_number}")
            return True
        else:
            print(f"[POSTGRES] No open record found for {plate_number}")
            return False
    except Exception as e:
        print(f"[POSTGRES ERROR] Failed to update exit time: {e}")
        postgres_conn.rollback()
        return False

# ===== Auto-detect Arduino Serial Port =====
def detect_arduino_port():
    ports = list(serial.tools.list_ports.comports())
    for port in ports:
        if "usbmodem" in port.device or "wchusbmodem" in port.device:
            return "COM7"
    return "COM7"


arduino_port = detect_arduino_port()
if arduino_port:
    arduino_port = "COM7"
    print(f"[CONNECTED] Arduino on {arduino_port}")
    arduino = serial.Serial(arduino_port, 9600, timeout=1)
    time.sleep(2)
else:
    print("[ERROR] Arduino not detected.")
    arduino = None


# ===== Ultrasonic Sensor (mock for now) =====
def mock_ultrasonic_distance():
    if arduino:
        try:
            raw = arduino.readline()
            distance = float(raw.decode('utf-8').strip())
            return distance
        except ValueError:
            print("Received invalid data from serial:", raw)
    return random.choice([random.randint(10, 40)])


# ===== Webcam and Main Loop =====
cap = cv2.VideoCapture(0)
plate_buffer = []

print("[EXIT SYSTEM] Ready. Press 'q' to quit.")

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

                # Preprocessing
                gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

                # OCR
                plate_text = pytesseract.image_to_string(
                    thresh, config='--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                ).strip().replace(" ", "")

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

                            if len(plate_buffer) >= 3:
                                most_common = Counter(plate_buffer).most_common(1)[0][0]
                                plate_buffer.clear()

                                if is_payment_complete(most_common):
                                    print(f"[ACCESS GRANTED] Payment complete for {most_common}")
                                    if arduino:
                                        arduino.write(b'1')  # Open gate
                                        print("[GATE] Opening gate (sent '1')")
                                        update_exit_time(most_common)  # Record exit time
                                        time.sleep(15)
                                        arduino.write(b'0')  # Close gate
                                        print("[GATE] Closing gate (sent '0')")
                                else:
                                    print(f"[ACCESS DENIED] Payment NOT complete for {most_common}")
                                    if arduino:
                                        arduino.write(b'2')  # Trigger warning buzzer
                                        print("[ALERT] Buzzer triggered (sent '2')")

                cv2.imshow("Plate", plate_img)
                cv2.imshow("Processed", thresh)
                time.sleep(0.5)

    annotated_frame = results[0].plot() if distance <= 50 else frame
    cv2.imshow("Exit Webcam Feed", annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
if arduino:
    arduino.close()
if postgres_conn:
    postgres_conn.close()
cv2.destroyAllWindows()