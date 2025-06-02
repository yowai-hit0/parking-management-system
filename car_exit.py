import cv2
from ultralytics import YOLO
import pytesseract
import time
import serial
import serial.tools.list_ports
import psycopg2
from collections import Counter
from datetime import datetime
import random

# Load YOLOv8 model
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
        return conn
    except Exception as e:
        print(f"[POSTGRES ERROR] Connection failed: {e}")
        return None


def log_system_event(conn, plate, event_type, details):
    """Log system events to database"""
    if not conn:
        print(f"[EVENT LOG] {event_type}: {details}")
        return False

    try:
        cur = conn.cursor()
        cur.execute("""
                    INSERT INTO system_logs
                        (plate_number, event_type, details)
                    VALUES (%s, %s, %s)
                    """, (plate, event_type, details))
        conn.commit()
        return True
    except Exception as e:
        print(f"[POSTGRES ERROR] Failed to log event: {e}")
        conn.rollback()
        return False


def log_alert(conn, plate, alert_type, details):
    """Log alerts to database"""
    if not conn:
        print(f"[ALERT] {alert_type}: {details}")
        return False

    try:
        cur = conn.cursor()
        cur.execute("""
                    INSERT INTO system_alerts
                        (plate_number, alert_type, details)
                    VALUES (%s, %s, %s)
                    """, (plate, alert_type, details))
        conn.commit()
        return True
    except Exception as e:
        print(f"[POSTGRES ERROR] Failed to log alert: {e}")
        conn.rollback()
        return False


def get_active_record(plate, conn):
    """Find the most recent active parking session"""
    if not conn:
        return None

    try:
        cur = conn.cursor()
        cur.execute("""
                    SELECT id, payment_status
                    FROM plates_log
                    WHERE plate_number = %s
                      AND exit_time IS NULL
                    ORDER BY entry_time DESC LIMIT 1
                    """, (plate,))
        return cur.fetchone()
    except Exception as e:
        print(f"[POSTGRES ERROR] Query failed: {e}")
        return None


def update_exit_time(record_id, conn):
    """Update the exit time for a specific record"""
    if not conn:
        return False

    try:
        cur = conn.cursor()
        cur.execute("""
                    UPDATE plates_log
                    SET exit_time = %s
                    WHERE id = %s
                    """, (datetime.now(), record_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"[POSTGRES ERROR] Update failed: {e}")
        conn.rollback()
        return False


# Auto-detect Arduino Serial Port
def detect_arduino_port():
    ports = list(serial.tools.list_ports.comports())
    for port in ports:
        if "COM" in port.device or "wchusbmodem" in port.device:
            return "COM7"
    return "COM7"  # Default to COM7 for simulation


# Initialize connections
postgres_conn = setup_postgres()
arduino_port = detect_arduino_port()

if arduino_port:
    arduino_port ="COM7"
    print(f"[CONNECTED] Arduino on {arduino_port}")
    arduino = serial.Serial(arduino_port, 9600, timeout=1)
    time.sleep(2)
else:
    print("[WARNING] Arduino not detected - running in simulation mode")
    arduino = None


def get_ultrasonic_distance():
    """Read distance from ultrasonic sensor or simulate if no Arduino"""
    if arduino:
        try:
            raw = arduino.readline()
            distance = float(raw.decode('utf-8').strip())
            # log_system_event(postgres_conn, None, "sensor_reading", f"Distance: {distance}cm")
            return distance
        except (ValueError, UnicodeDecodeError):
            # log_system_event(postgres_conn, None, "sensor_error", "Invalid distance reading")
            return random.randint(10, 40)
    return random.choice([random.randint(10, 40)])


def generate_dummy_data(conn):
    """Generate dummy data for testing dashboard"""
    plates = ["RAB123C", "RAC456D", "RAD789E", "RAF012G"]
    events = ["entry", "exit", "payment", "alert"]
    alerts = ["unauthorized_exit", "payment_required", "tampering_detected"]

    # Generate system logs
    for i in range(5):
        plate = random.choice(plates)
        event = random.choice(events)
        log_system_event(conn, plate, event, f"Test {event} event for {plate}")

    # Generate alerts
    for i in range(5):
        plate = random.choice(plates)
        alert = random.choice(alerts)
        log_alert(conn, plate, alert, f"Test {alert} for {plate}")


def main():
    last_processed = None  # Initialize to avoid UnboundLocalError

    # Generate dummy data if needed
    if postgres_conn:
        generate_dummy_data(postgres_conn)

    cap = cv2.VideoCapture(0)
    plate_buffer = []
    cooldown = 5  # seconds between processing same plate

    print("[EXIT SYSTEM] Ready. Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        distance = get_ultrasonic_distance()
        print(f"[SENSOR] Distance: {distance} cm")

        if distance <= 50:
            results = model(frame)
            # log_system_event(postgres_conn, None, "object_detected", f"Object detected at {distance}cm")

            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    plate_img = frame[y1:y2, x1:x2]

                    # Preprocessing for OCR
                    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
                    blur = cv2.GaussianBlur(gray, (5, 5), 0)
                    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

                    # OCR processing
                    plate_text = pytesseract.image_to_string(
                        thresh,
                        config='--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                    ).strip().replace(" ", "")

                    # Plate validation
                    if "RA" in plate_text:
                        start_idx = plate_text.find("RA")
                        plate_candidate = plate_text[start_idx:start_idx + 7]

                        if (len(plate_candidate) == 7 and
                                plate_candidate[:3].isalpha() and
                                plate_candidate[3:6].isdigit() and
                                plate_candidate[6].isalpha()):

                            print(f"[VALID] Plate Detected: {plate_candidate}")
                            plate_buffer.append(plate_candidate)
                            log_system_event(postgres_conn, plate_candidate, "plate_detected",
                                             "Potential plate detected")

                            # Process after 3 consistent reads
                            if len(plate_buffer) >= 1:
                                most_common = Counter(plate_buffer).most_common(1)[0][0]
                                plate_buffer.clear()

                                # Check cooldown
                                current_time = time.time()
                                if (last_processed and
                                        (current_time - last_processed[1]) < cooldown and
                                        last_processed[0] == most_common):
                                    print(f"[COOLDOWN] Skipping recently processed plate: {most_common}")
                                    continue

                                # Check database
                                record = get_active_record(most_common, postgres_conn)
                                if record:
                                    record_id, payment_status = record

                                    if payment_status == 1:  # Payment complete
                                        print(f"[ACCESS GRANTED] Paid plate: {most_common}")
                                        log_system_event(postgres_conn, most_common, "exit_granted",
                                                         "Payment verified - opening gate")

                                        if arduino:
                                            arduino.write(b'1')  # Open gate
                                            # log_system_event(postgres_conn, most_common, "gate_command",
                                            #                  "Sent open gate command")

                                        if update_exit_time(record_id, postgres_conn):
                                            log_system_event(postgres_conn, most_common, "exit_recorded",
                                                             "Exit time updated in database")

                                        time.sleep(15)  # Keep gate open
                                        if arduino:
                                            arduino.write(b'0')  # Close gate
                                            # log_system_event(postgres_conn, most_common, "gate_command",
                                            #                  "Sent close gate command")
                                    else:
                                        print(f"[ACCESS DENIED] Unpaid plate: {most_common}")
                                        log_alert(postgres_conn, most_common, "payment_required",
                                                  "Attempted exit without payment")
                                        if arduino:
                                            arduino.write(b'2')  # Payment alert
                                            log_system_event(postgres_conn, most_common, "alert_triggered",
                                                             "Sent payment alert")
                                else:
                                    print(f"[WARNING] No active record found for {most_common}")
                                    log_alert(postgres_conn, most_common, "unauthorized_exit",
                                              "No active parking session found")

                                last_processed = (most_common, current_time)

                    # Display processing windows
                    cv2.imshow("Plate", plate_img)
                    cv2.imshow("Processed", thresh)
                    time.sleep(0.5)

        # Display main feed
        annotated_frame = results[0].plot() if distance <= 50 else frame
        cv2.imshow("Exit System", annotated_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Cleanup
    cap.release()
    if arduino:
        arduino.close()
    if postgres_conn:
        postgres_conn.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

