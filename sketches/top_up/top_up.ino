#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN         9 
#define SS_PIN          10         
MFRC522 mfrc522(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;

void setup() {
  Serial.begin(9600);
  SPI.begin();
  mfrc522.PCD_Init();

  // Initialize default key (0xFFFFFFFFFFFF)
  for (byte i = 0; i < 6; i++) {
    key.keyByte[i] = 0xFF;
  }

  Serial.println(F("==== RFID DATA WRITER ===="));
  Serial.println(F("Place your card on the reader..."));
  Serial.println();
}

void loop() {
  // Look for new card
  if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) {
    return;
  }

  Serial.println(F("📶 Card detected!"));

  // Get car plate from user
  byte plateBlock[16] = {0};
  getInput("Enter car plate (7 chars, e.g., RAG234H):", plateBlock, 7);

  // Get balance from user
  byte balanceBlock[16] = {0};
  getInput("Enter balance (max 16 chars):", balanceBlock, 16);

  // Write data to blocks
  writeBlockWithLog(2, plateBlock, "Car Plate");
  writeBlockWithLog(4, balanceBlock, "Balance");

  Serial.println(F("🔄 Please remove the card to write again."));
  Serial.println(F("--------------------------\n"));

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
  delay(2000);
}

// Helper function to get user input
void getInput(const char* prompt, byte* buffer, byte requiredLen) {
  while (true) {
    Serial.println(prompt);
    Serial.setTimeout(20000L); // 20-second timeout
    byte len = Serial.readBytesUntil('\n', (char*)buffer, 16);

    // Pad buffer with spaces if needed
    for (byte i = len; i < 16; i++) {
      buffer[i] = ' ';
    }

    if (len >= (requiredLen == 7 ? 7 : 1)) break; // Validate length

    Serial.print(F("❌ Invalid input (needs "));
    Serial.print(requiredLen);
    Serial.println(F(" chars). Try again."));
    flushSerial();
  }
}

// Improved write function with logging
bool writeBlockWithLog(byte blockAddr, byte* data, const char* dataType) {
  // Authenticate
  MFRC522::StatusCode status = mfrc522.PCD_Authenticate(
    MFRC522::PICC_CMD_MF_AUTH_KEY_A,
    blockAddr,
    &key,
    &(mfrc522.uid)
  );

  if (status != MFRC522::STATUS_OK) {
    Serial.print(F("❌ Auth failed for "));
    Serial.print(dataType);
    Serial.print(F(": "));
    Serial.println(mfrc522.GetStatusCodeName(status));
    return false;
  }

  // Write block
  status = mfrc522.MIFARE_Write(blockAddr, data, 16);
  if (status != MFRC522::STATUS_OK) {
    Serial.print(F("❌ Write failed for "));
    Serial.print(dataType);
    Serial.print(F(": "));
    Serial.println(mfrc522.GetStatusCodeName(status));
    return false;
  }

  // Success log
  Serial.print(F("✅ "));
  Serial.print(dataType);
  Serial.print(F(" written to block "));
  Serial.print(blockAddr);
  Serial.print(F(": "));

  // Print human-readable data (trim trailing spaces)
  for (byte i = 0; i < 16; i++) {
    if (data[i] != ' ') Serial.write(data[i]);
  }
  Serial.println();

  return true;
}

// Clear serial buffer
void flushSerial() {
  while (Serial.available()) Serial.read();
}