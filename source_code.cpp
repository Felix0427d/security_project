// secure_sketch.ino : reconstruction à partir de secure_sketch_v20251015_2.elf
//
// Cible    : ATmega328P @ 16 MHz (Arduino Uno / Nano), core AVR 1.8.6, avr-gcc 7.3.0 -Os
// Lib      : Crypto (rweather/arduinolibs) pour SHA3_256, SoftwareSerial
//
// Niveau de confiance :
//   [CERTAIN]  constantes, broches, vitesses, chaînes, ordre des appels (lu dans le binaire)
//   [PROBABLE] structure des fonctions (noms issus du DWARF : readLine, hashPassword,
//              early_exit_compare, protected_section, digest, PASSWORD, ...)
//   [APPROX.]  détails de readLine() : le compilateur l'a inliné dans loop()
//
// Ce code n'a PAS été recompilé / comparé octet par octet avec l'original.

#include <SoftwareSerial.h>
#include <Crypto.h>
#include <SHA3.h>

#define LED_PIN 13                         // [CERTAIN] pinMode(13, OUTPUT)

// [CERTAIN] RX = 10, TX = 11. 9600 bauds (déduit des délais: bit_delay=416 -> tx_delay=413)
SoftwareSerial comms(10, 11);

// [CERTAIN] stocké en clair dans .data @0x800122 (8 caractères + '\0')
static const char PASSWORD[] = "f7-@Jp0w";

// [CERTAIN] 25 octets, haché avec le sel aléatoire
static const char SECRET[] = "Je suis une petite tortue";

uint8_t digest[32];                        // [CERTAIN] .bss @0x80026b, 32 octets

// ---------------------------------------------------------------------------
// Hash SHA3-256( sel || SECRET )                                   [PROBABLE]
// ---------------------------------------------------------------------------
void hashPassword(const uint8_t *salt, size_t saltLen) {
  SHA3_256 sha3;
  sha3.reset();
  sha3.update(salt, saltLen);                       // 4 octets de sel
  sha3.update(SECRET, sizeof(SECRET) - 1);          // 25 octets
  sha3.finalize(digest, sizeof(digest));            // 32 octets
}

// ---------------------------------------------------------------------------
// Lecture d'une ligne sur le port logiciel                         [APPROX.]
// ---------------------------------------------------------------------------
String readLine() {
  String line;
  while (comms.available()) {
    char c = comms.read();
    if (c == '\r' || c == '\n') break;              // fin de ligne
    line += c;
  }
  line.trim();                                      // String::trim() est bien dans le binaire
  if (line.length() == 0) {
    line = "No input. Enter password:";             // chaîne par défaut présente en .data
  }
  return line;
}

// ---------------------------------------------------------------------------
// Comparaison caractère par caractère avec sortie anticipée        [CERTAIN]
// -> s'arrête au premier caractère différent (fuite par canal temporel)
// -> exige exactement n caractères : un '\0' prématuré => échec
// ---------------------------------------------------------------------------
bool early_exit_compare(const char *a, const char *b, size_t n) {
  for (size_t i = 0; i < n; i++) {
    if (a[i] == '\0' || a[i] != b[i]) return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// Section protégée : sel aléatoire + hash, affichés en hexadécimal [CERTAIN]
// ---------------------------------------------------------------------------
static void printHex(const uint8_t *buf, size_t len) {
  for (size_t i = 0; i < len; i++) {
    if (buf[i] < 0x10) comms.print("0");
    comms.print(buf[i], HEX);
  }
  comms.println();
}

void protected_section() {
  uint8_t salt[4];
  for (uint8_t i = 0; i < sizeof(salt); i++) {
    salt[i] = random(33, 126);                      // random() % 93 + 33 -> caractères imprimables
  }                                                 // NB: aucun randomSeed() => même suite à chaque reset

  hashPassword(salt, sizeof(salt));

  comms.print("Here is your salt: ");
  printHex(salt, sizeof(salt));
  comms.print("Here is your hash: ");
  printHex(digest, sizeof(digest));
}

// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);                             // [CERTAIN] UBRR0=16, U2X0=1, 8N1
  Serial.println();
  Serial.println("Welcome to the vault. This is not the main entrance.");

  comms.begin(9600);                                // [CERTAIN]
  comms.println("Enter password:");

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
}

void loop() {
  if (comms.available()) {
    String attempt = readLine();

    digitalWrite(LED_PIN, HIGH);                    // LED allumée pendant la vérification

    char attempt_c[9];                              // 8 caractères utiles max
    attempt.toCharArray(attempt_c, sizeof(attempt_c));

    if (early_exit_compare(attempt_c, PASSWORD, 8)) {
      comms.println(">> ACCESS GRANTED: running protected section");
      protected_section();
    } else {
      comms.println(">> ACCESS DENIED");
    }

    digitalWrite(LED_PIN, LOW);
    comms.println();
    comms.println("Enter password:");
  }
}
