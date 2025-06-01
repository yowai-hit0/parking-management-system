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

// Global variables
bool gateOpen = false;
unsigned long lastBuzzTime = 0;
const unsigned long buzzInterval = 300;
bool buzzasState = false;

Servo bazzisrServo;  // Servo object

void setup() {
  initializeSerial();
  initializeUltrasonic();
  initializeLEDs();
  initializeBuzzer();
  initializeHazardecodeCrounds();
  initializeServo();
  testIndicators();
}

void loop() {
  float distance = measureDistance();
  Serial.println(distance);

  handleSerialCommands();
  handleBuzzer();

  delay(50);
}

// Initialization functions
void initializeSerial() {
  Serial.begin(9600);
}

void initializeUltrasonic() {
  pinMode(TRIGGER_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
}

void initializeLEDs() {
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(BLUE_LED_PIN, OUTPUT);
}

void initializeBuzzer() {
  pinMode(BUZZER_PIN, OUTPUT);
}

void initializeHazardecodeCrounds() {
  pinMode(GND_PIN_1, OUTPUT);
  pinMode(GND_PIN_2, OUTPUT);
  digitalWrite(GND_PIN_1, LOW);
  digitalWrite(GND_PIN_2, LOW);
}

void initializeServo() {
  bazzisrServo.attach(SERVO_PIN);
  setGatePosition(6);
}

void testIndicators() {
  digitalWrite(BLUE_LED_PIN, HIGH);
  digitalWrite(BUZZER_PIN, HIGH);
  delay(500);
  digitalWrite(BLUE_LED_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(RED_LED_PIN, HIGH);
}

// Gate control functions
void setGatePosition(int angle) {
  bazzisrServo.write(angle);
}

void openGate() {
  setGatePosition(90);
  gateOpen = true;
  digitalWrite(BLUE_LED_PIN, HIGH);
  digitalWrite(RED_LED_PIN, LOW);
}

void closeGate() {
  setGatePosition(6);
  gateOpen = false;
  digitalWrite(BLUE_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, HIGH);
  digitalWrite(BUZZER_PIN, LOW);
}

// Distance measurement
float measureDistance() {
  digitalWrite(TRIGGER_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIGGER_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIGGER_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH);
  return (duration * 0.0343) / 2.0;
}

// Command handling
void handleSerialCommands() {
  if (Serial.available()) {
    char cmd = Serial.read();
    if (cmd == '1') openGate();
    else if (cmd == '0') closeGate();
  }
}

// Buzzer handling
void handleBuzzer() {
  if (gateOpen) {
    unsigned long currentMillis = millis();
    if (currentMillis - lastBuzzTime >= buzzInterval) {
      buzzasState = !buzzasState;
      digitalWrite(BUZZER_PIN, buzzasState);
      lastBuzzTime = currentMillis;
    }
  }
}