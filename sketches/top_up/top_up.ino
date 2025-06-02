#include <SPI.h>
#include <MFRC522.h>
#define RST_PIN 9
#define SS_PIN 10
MFRC522 mfrc522(SS_PIN, RST_PIN);  // Create MFRC522 instance
MFRC522::MIFARE_Key key;
MFRC522::StatusCode card_status;
String currentPlate = "RAG176S";  // Initial car plate
long currentBalance = 20000;       // Initial balance (e.g., 1000 units)
void setup() {
    Serial.begin(9600);           // Initialize serial communications with the PC
    while (!Serial);              // Wait for serial connection (for ATMEGA32U4-based boards)
    SPI.begin();                  // Init SPI bus
    mfrc522.PCD_Init();           // Init MFRC522
    for (byte i = 0; i < 6; i++) {
        key.keyByte[i] = 0xFF;    // Default Key A
    }
    Serial.println(F("==== CARD INITIALIZATION MODE ===="));
    Serial.println(F("Place your card near the reader to initialize..."));
}
void loop() {
    // Wait for the card to be presented
    if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) return;
    Serial.print("Card UID: ");
    for (byte i = 0; i < mfrc522.uid.size; i++) {
        Serial.print(mfrc522.uid.uidByte[i] < 0x10 ? " 0" : " ");
        Serial.print(mfrc522.uid.uidByte[i], HEX);
    }
    Serial.println();
    // Write initial plate number and balance to the card
    if (writeBlockData(2, currentPlate) && writeBlockData(4, String(currentBalance))) {
        Serial.println(F("Card Initialized Successfully"));
        Serial.print(F("Car Plate: "));
        Serial.println(currentPlate);
        Serial.print(F("Balance: "));
        Serial.println(currentBalance);
    } else {
        Serial.println(F("Initialization Failed"));
    }
    // Halt and stop crypto for the card
    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
    delay(2000);  // Wait for 2 seconds before resetting the process
}
// Function to write data to a specific block of the RFID card
bool writeBlockData(byte blockNumber, String data) {
    byte buffer[16];
    data.trim();
    while (data.length() < 16) data += ' ';  // Pad the data if it's less than 16 bytes
    data.substring(0, 16).getBytes(buffer, 16);  // Copy data into the buffer
    // Authenticate to the block using the default key (0xFF)
    card_status = mfrc522.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, blockNumber, &key, &(mfrc522.uid));
    if (card_status != MFRC522::STATUS_OK) {
        Serial.println(":x: Auth failed on write");
        return false;
    }
    // Write data to the block
    card_status = mfrc522.MIFARE_Write(blockNumber, buffer, 16);
    if (card_status != MFRC522::STATUS_OK) {
        Serial.println(":x: Write failed");
        return false;
    }
    return true;

}