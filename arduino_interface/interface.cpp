#include <SoftwareSerial.h>

// Arduino interface
// RX = 10 : reçoit le TX de l'Arduino cible
// TX = 11 : envoie vers le RX de l'Arduino cible
SoftwareSerial ttlSerial(10, 11);

void setup() {
  // USB <-> PC
  Serial.begin(9600);

  // Communication avec l'Arduino cible
  ttlSerial.begin(9600);

  Serial.println("TTL bridge ready");
}

void loop() {
  // PC -> Arduino cible
  while (Serial.available()) {
    char c = Serial.read();
    ttlSerial.write(c);
  }

  // Arduino cible -> PC
  while (ttlSerial.available()) {
    char c = ttlSerial.read();
    Serial.write(c);
  }
}
