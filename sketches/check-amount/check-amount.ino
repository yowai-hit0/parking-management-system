#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN         9
#define SS_PIN          10
MFRC522 mfrc522(SS_PIN, RST_PIN);

void setup() {
  Serial.begin(9600);
  SPI.begin();
  mfrc522.PCD_Init();
  Serial.println("Place your card on the reader...");
}

void loop() {
  if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) {
    return;
  }

  Serial.print("Card UID: ");
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    Serial.print(mfrc522.uid.uidByte[i] < 0x10 ? " 0" : " ");
    Serial.print(mfrc522.uid.uidByte[i], HEX);
  }
  Serial.println();

  byte block[18];

  if (readBlock(2, block)) {
    Serial.print("Plate Number: ");
    for (int i = 0; i < 16; i++) {
      if (block[i] == 0x00) break;
      Serial.write(block[i]);
    }
    Serial.println();
  } else {
    Serial.println("Failed to read plate.");
  }

  if (readBlock(4, block)) {
    int balance;
    memcpy(&balance, block, sizeof(int));
    Serial.print("Balance: ");
    Serial.println(balance);
  } else {
    Serial.println("Failed to read balance.");
  }

  delay(2000);
  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
}

bool readBlock(byte blockAddr, byte* buffer) {
  MFRC522::MIFARE_Key key;
  for (byte i = 0; i < 6; i++) key.keyByte[i] = 0xFF;

  byte status = mfrc522.PCD_Authenticate(
    MFRC522::PICC_CMD_MF_AUTH_KEY_A,
    blockAddr,
    &key,
    &(mfrc522.uid)
  );
  if (status != MFRC522::STATUS_OK) {
    Serial.print("Auth failed: ");
    Serial.println(mfrc522.GetStatusCodeName(status));
    return false;
  }
  byte bufferSize = 18;
  status = mfrc522.MIFARE_Read(blockAddr, buffer, &bufferSize);
  if (status != MFRC522::STATUS_OK) {
    Serial.print("Read failed: ");
    Serial.println(mfrc522.GetStatusCodeName(status));
    return false;
  }

  return true;
}
