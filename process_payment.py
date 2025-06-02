import serial
import time
import psycopg2
import re
from datetime import datetime

# === CONFIG ===
SERIAL_PORT = 'COM8'  # Change this to your actual serial port
BAUD_RATE = 9600
RATE_PER_HOUR = 200


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


# Find the latest unpaid session for a plate
def find_latest_unpaid(plate, conn):
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, entry_time
            FROM plates_log
            WHERE plate_number = %s
              AND payment_status = 0
              AND exit_time IS NULL
            ORDER BY entry_time DESC
            LIMIT 1
        """, (plate,))
        return cur.fetchone()
    except Exception as e:
        print(f"[POSTGRES ERROR] Query failed: {e}")
        return None


# Mark a record as paid
def mark_as_paid(record_id, amount, conn):
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE plates_log
            SET payment_status = 1,
                amount = %s
            WHERE id = %s
        """, (amount, record_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"[POSTGRES ERROR] Update failed: {e}")
        conn.rollback()
        return False


# Clean plate string
def clean_plate(plate_raw):
    return plate_raw.replace('\x00', '').strip().upper()


# Main loop
def main():
    postgres_conn = setup_postgres()
    if not postgres_conn:
        print("Failed to connect to PostgreSQL.")
        return

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=10)
        print(f"Listening on {SERIAL_PORT}...")

        while True:
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                print(f"Received: {line}")

                # Skip empty or invalid Arduino signals
                if not line or line.lower() == "ready":
                    continue

                # Remove any 'output:' prefix
                line = re.sub(r'^output:', '', line, flags=re.IGNORECASE)

                # Use regex to extract plate and balance
                match = re.search(r'([A-Z0-9]{5,10})\s*,\s*(\d+)', line)
                if not match:
                    print("Invalid format.")
                    continue

                plate = clean_plate(match.group(1))
                balance_str = match.group(2)

                try:
                    balance = int(balance_str)
                except ValueError:
                    print("Invalid balance received.")
                    continue

                record = find_latest_unpaid(plate, postgres_conn)
                if not record:
                    print(f"No unpaid entry for {plate}")
                    ser.write(b'0\n')
                    continue

                record_id, entry_time = record
                duration = (datetime.now() - entry_time).total_seconds() / 3600
                due = int(RATE_PER_HOUR * max(1, round(duration)))

                print(f"Due for {plate}: {due} RWF (Parked for {duration:.2f} hours)")

                # Payment loop
                while balance < due:
                    print(f"Insufficient balance: {balance} < {due}")
                    ser.write(b'-1\n')  # Notify Arduino

                    # Wait for Arduino response
                    start_time = time.time()
                    confirmation = None
                    while time.time() - start_time < 5:
                        if ser.in_waiting:
                            response = ser.readline().decode().strip()
                            if response == "insufficient":
                                confirmation = "insufficient"
                                break

                    if confirmation != "insufficient":
                        break  # Exit if no confirmation

                    # Handle top-up
                    choice = input("Would you like to top-up? (yes/no): ").strip().lower()
                    if choice != 'yes':
                        print("Payment aborted.")
                        break

                    try:
                        topup = int(input("Enter top-up amount (positive integer): "))
                        if topup <= 0:
                            print("Amount must be positive.")
                            continue
                    except ValueError:
                        print("Invalid input. Enter a number.")
                        continue

                    # Send top-up to Arduino
                    ser.write(f"topup,{topup}\n".encode())
                    print(f"Sent top-up: {topup}")

                    # Wait for new balance
                    start_time = time.time()
                    topped = False
                    while time.time() - start_time < 5:
                        if ser.in_waiting:
                            response = ser.readline().decode().strip()
                            if response.startswith("topped,"):
                                try:
                                    new_balance = int(response.split(',')[1])
                                    balance = new_balance
                                    print(f"New balance: {balance} RWF")
                                    topped = True
                                    break
                                except:
                                    print("Error processing top-up.")
                                    break

                    if not topped:
                        continue  # Retry top-up

                    # Recalculate due
                    duration = (datetime.now() - entry_time).total_seconds() / 3600
                    due = int(RATE_PER_HOUR * max(1, round(duration)))
                    print(f"Updated due: {due} RWF")

                # Final payment processing
                if balance >= due:
                    ser.write(f"{due}\n".encode())
                    start_time = time.time()
                    paid = False

                    while time.time() - start_time < 5:
                        if ser.in_waiting:
                            response = ser.readline().decode().strip()
                            if response == "done":
                                if mark_as_paid(record_id, due, postgres_conn):
                                    print("Payment successful and recorded!")
                                    paid = True
                                break
                            elif response == "insufficient":
                                print("Unexpected insufficient balance after top-up.")
                                break

                    if not paid:
                        print("Payment confirmation timeout.")

            except KeyboardInterrupt:
                print("Exiting...")
                break
            except Exception as e:
                print(f"Error: {e}")

    finally:
        ser.close()
        postgres_conn.close()


if __name__ == "__main__":
    main()
