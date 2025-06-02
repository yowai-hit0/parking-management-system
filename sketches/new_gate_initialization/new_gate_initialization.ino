#include <Servo.h>

// Pin definitions
#define TRIGGER_PIN 2
#define ECHO_PIN 3
#define RED_LED_PIN 4
#define BLUE_LED_PIN 5
#define SERVO_PIN 6
#define GND_PIN_1 7
#define GND_PIN_2 8
#define BUZZER_PIN 12

#define GATE_CLOSED_POS 6
#define GATE_OPEN_POS 90

enum AlertType {
  NONE,
  PAYMENT_PENDING,
  TAMPERING
};

AlertType currentAlert = NONE;
unsigned long alertStartTime = 0;
unsigned long lastBlinkTime = 0;
unsigned long lastBeepStartTime = 0;
bool buzzerOn = false;

#define BLINK_INTERVAL_PAYMENT 300
#define BEEP_INTERVAL_PAYMENT 600
#define BEEP_DURATION_PAYMENT 150
#define BLINK_INTERVAL_TAMPER 150
#define BEEP_INTERVAL_TAMPER 300
#define BEEP_DURATION_TAMPER 100

unsigned long lastDistanceSendTime = 0;
#define DISTANCE_SEND_INTERVAL 50

Servo barrierServo;
bool isGateOpen = false;

// For gate-open beep
bool gateOpenBeepInProgress = false;
unsigned long gateOpenBeepStart = 0;
#define GATE_OPEN_BEEP_DURATION 200

void setup() {
  Serial.begin(9600);
  pinMode(TRIGGER_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(BLUE_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  pinMode(GND_PIN_1, OUTPUT);
  pinMode(GND_PIN_2, OUTPUT);
  digitalWrite(GND_PIN_1, LOW);
  digitalWrite(GND_PIN_2, LOW);

  barrierServo.attach(SERVO_PIN);
  closeGateAction();
  digitalWrite(BUZZER_PIN, LOW);

  Serial.println("MSG:Gate Controller Ready.");
  Serial.println("MSG:Commands: '0'-Close, '1'-Open, '2'-PaymentAlert, '3'-TamperAlert, 'S'-StopAlert");
}

void loop() {
  handleSerialCommands();
  handleAlerts();
  handleGateOpenBeep();
  sendDistanceData();
}
unsigned long lastBuzzTime = 0;
const unsigned long buzzInterval = 300;
bool buzzasState = false;

void handleSerialCommands() {
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    Serial.print("MSG:Received command: ");
    Serial.println(cmd);

    switch (cmd) {
      case '0':
        stopAlertAction();
        closeGateAction();
        break;
      case '1':
        stopAlertAction();
        openGateAction();
        break;
      case '2':
        startAlert(PAYMENT_PENDING);
        break;
      case '3':
        startAlert(TAMPERING);
        break;
      case 'S':
        stopAlertAction();
        if (isGateOpen) {
          digitalWrite(BLUE_LED_PIN, HIGH);
          digitalWrite(RED_LED_PIN, LOW);
        } else {
          digitalWrite(RED_LED_PIN, HIGH);
          digitalWrite(BLUE_LED_PIN, LOW);
        }
        break;
      default:
        Serial.println("MSG:Unknown command.");
        break;
    }
  }
}

void openGateAction() {
  barrierServo.write(GATE_OPEN_POS);
  isGateOpen = true;

  // Gate Open LED indication
  if (currentAlert == NONE) {
    digitalWrite(BLUE_LED_PIN, HIGH);
    digitalWrite(RED_LED_PIN, LOW);
  }

  // Trigger short beep
  gateOpenBeepInProgress = true;
  gateOpenBeepStart = millis();
  digitalWrite(BUZZER_PIN, HIGH);

  Serial.println("MSG:Gate Opened");
}

void handleGateOpenBeep() {
  if (gateOpenBeepInProgress && millis() - gateOpenBeepStart >= GATE_OPEN_BEEP_DURATION) {
    digitalWrite(BUZZER_PIN, LOW);
    gateOpenBeepInProgress = false;
  }
}

void closeGateAction() {
  barrierServo.write(GATE_CLOSED_POS);
  isGateOpen = false;

  if (currentAlert == NONE) {
    digitalWrite(RED_LED_PIN, HIGH);
    digitalWrite(BLUE_LED_PIN, LOW);
  }

  Serial.println("MSG:Gate Closed");
}

void startAlert(AlertType type) {
  currentAlert = type;
  alertStartTime = millis();
  lastBlinkTime = millis();
  lastBeepStartTime = millis();
  buzzerOn = false;

  Serial.print("MSG:ALERT STARTED: ");
  if (type == PAYMENT_PENDING) Serial.println("Payment Pending");
  if (type == TAMPERING) Serial.println("Tampering Detected");
}

void stopAlertAction() {
  if (currentAlert != NONE) {
    currentAlert = NONE;
    digitalWrite(BUZZER_PIN, LOW);
    digitalWrite(RED_LED_PIN, LOW);
    digitalWrite(BLUE_LED_PIN, LOW);
    buzzerOn = false;
    Serial.println("MSG:Alert Stopped.");
  }
}

void handleAlerts() {
  if (currentAlert == NONE) return;

  unsigned long currentTime = millis();

  int blinkInterval = (currentAlert == PAYMENT_PENDING) ? BLINK_INTERVAL_PAYMENT : BLINK_INTERVAL_TAMPER;
  int beepInterval = (currentAlert == PAYMENT_PENDING) ? BEEP_INTERVAL_PAYMENT : BEEP_INTERVAL_TAMPER;
  int beepDuration = (currentAlert == PAYMENT_PENDING) ? BEEP_DURATION_PAYMENT : BEEP_DURATION_TAMPER;

  // Handle LED blinking
  if (currentTime - lastBlinkTime >= blinkInterval) {
    lastBlinkTime = currentTime;
    digitalWrite(RED_LED_PIN, !digitalRead(RED_LED_PIN));
    digitalWrite(BLUE_LED_PIN, LOW);
  }

  // Handle buzzer beep only if the gate is open
  if (isGateOpen) {
    if (!buzzerOn && (currentTime - lastBeepStartTime >= beepInterval)) {
      digitalWrite(BUZZER_PIN, HIGH);
      buzzerOn = true;
      lastBeepStartTime = currentTime;
    } else if (buzzerOn && (currentTime - lastBeepStartTime >= beepDuration)) {
      digitalWrite(BUZZER_PIN, LOW);
      buzzerOn = false;
    }
  } else {
    // Optional: Ensure buzzer is off if gate is closed, even during an alert
    digitalWrite(BUZZER_PIN, LOW);
    buzzerOn = false;
  }
}

float getDistanceCm() {
  digitalWrite(TRIGGER_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIGGER_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIGGER_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 25000);
  if (duration == 0) return 999.99;
  return (duration * 0.0343) / 2.0;
}

void sendDistanceData() {
  if (millis() - lastDistanceSendTime >= DISTANCE_SEND_INTERVAL) {
    lastDistanceSendTime = millis();
    float distance = getDistanceCm();
    Serial.println(distance, 2);
  }
}
