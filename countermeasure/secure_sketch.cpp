// Demonstration firmware with UART attempt limiting and fixed-length comparison.
// Physical protection of the power-measurement path must be implemented in hardware.

#include <Arduino.h>
#include <EEPROM.h>
#include <SoftwareSerial.h>
#include <Crypto.h>
#include <SHA3.h>

constexpr uint8_t LED_PIN = 13;
constexpr uint8_t UART_RX_PIN = 10;
constexpr uint8_t UART_TX_PIN = 11;
constexpr uint32_t UART_BAUD = 9600;

constexpr char PASSWORD[] = "f7-@Jp0w";
constexpr size_t PASSWORD_LENGTH = sizeof(PASSWORD) - 1;
constexpr char SECRET[] = "Je suis une petite tortue";

constexpr uint8_t MAX_FAILED_ATTEMPTS = 5;
constexpr uint32_t LOCKOUT_BASE_MS = 30000UL;
constexpr uint8_t MAX_LOCKOUT_LEVEL = 4;

constexpr uint8_t EEPROM_SLOT_COUNT = 64;
constexpr uint8_t EEPROM_RECORD_SIZE = 3;
constexpr uint8_t EEPROM_CHECK_VALUE = 0xA7;

SoftwareSerial comms(UART_RX_PIN, UART_TX_PIN);
uint8_t digest[32];
char inputLine[PASSWORD_LENGTH] = {};
uint8_t inputLength = 0;
bool inputTooLong = false;

uint8_t failedAttempts = 0;
uint8_t lockoutLevel = 0;
uint8_t recordSequence = 0;
uint8_t recordSlot = EEPROM_SLOT_COUNT - 1;
bool lockedOut = false;
uint32_t lockoutStartedAt = 0;
uint32_t lockoutDuration = 0;

uint8_t encodeAttemptState() {
  return static_cast<uint8_t>((lockoutLevel << 3) | failedAttempts);
}

void loadAttemptState() {
  bool foundRecord = false;
  uint8_t newestSequence = 0;

  for (uint8_t slot = 0; slot < EEPROM_SLOT_COUNT; ++slot) {
    const int address = slot * EEPROM_RECORD_SIZE;
    const uint8_t sequence = EEPROM.read(address);
    const uint8_t state = EEPROM.read(address + 1);
    const uint8_t check = EEPROM.read(address + 2);

    if (static_cast<uint8_t>(sequence ^ state ^ EEPROM_CHECK_VALUE) != check ||
        (state & 0xC0) != 0) {
      continue;
    }

    const uint8_t failures = state & 0x07;
    const uint8_t level = (state >> 3) & 0x07;
    if (failures > MAX_FAILED_ATTEMPTS || level > MAX_LOCKOUT_LEVEL) {
      continue;
    }

    if (!foundRecord ||
        static_cast<int8_t>(sequence - newestSequence) > 0) {
      foundRecord = true;
      newestSequence = sequence;
      recordSequence = sequence;
      recordSlot = slot;
      failedAttempts = failures;
      lockoutLevel = level;
    }
  }

  if (!foundRecord) {
    failedAttempts = 0;
    lockoutLevel = 0;
    recordSequence = 0xFF;
    recordSlot = EEPROM_SLOT_COUNT - 1;
  }
}

void saveAttemptState() {
  recordSequence = static_cast<uint8_t>(recordSequence + 1);
  recordSlot = static_cast<uint8_t>((recordSlot + 1) % EEPROM_SLOT_COUNT);

  const int address = recordSlot * EEPROM_RECORD_SIZE;
  const uint8_t state = encodeAttemptState();
  const uint8_t check =
      static_cast<uint8_t>(recordSequence ^ state ^ EEPROM_CHECK_VALUE);

  EEPROM.update(address + 2, static_cast<uint8_t>(check ^ 0xFF));
  EEPROM.update(address, recordSequence);
  EEPROM.update(address + 1, state);
  EEPROM.update(address + 2, check);
}

void hashSecret(const uint8_t *salt, size_t saltLength) {
  SHA3_256 sha3;
  sha3.reset();
  sha3.update(salt, saltLength);
  sha3.update(SECRET, sizeof(SECRET) - 1);
  sha3.finalize(digest, sizeof(digest));
}

void printHex(const uint8_t *buffer, size_t length) {
  for (size_t i = 0; i < length; ++i) {
    if (buffer[i] < 0x10) {
      comms.print('0');
    }
    comms.print(buffer[i], HEX);
  }
  comms.println();
}

void runProtectedSection() {
  uint8_t salt[4];
  for (uint8_t i = 0; i < sizeof(salt); ++i) {
    salt[i] = static_cast<uint8_t>(random(33, 126));
  }

  hashSecret(salt, sizeof(salt));
  comms.print("Here is your salt: ");
  printHex(salt, sizeof(salt));
  comms.print("Here is your hash: ");
  printHex(digest, sizeof(digest));
}

bool passwordMatches(const char *candidate, uint8_t length, bool tooLong) {
  volatile uint8_t difference =
      static_cast<uint8_t>((length == PASSWORD_LENGTH && !tooLong) ? 0 : 1);

  for (uint8_t i = 0; i < PASSWORD_LENGTH; ++i) {
    difference |= static_cast<uint8_t>(candidate[i] ^ PASSWORD[i]);
  }

  return difference == 0;
}

uint32_t cooldownForLevel(uint8_t level) {
  return LOCKOUT_BASE_MS << level;
}

void beginLockout() {
  lockedOut = true;
  lockoutStartedAt = millis();
  lockoutDuration = cooldownForLevel(lockoutLevel);
  comms.println("Too many failed attempts. UART temporarily locked.");
}

void finishLockoutIfExpired() {
  if (!lockedOut || millis() - lockoutStartedAt < lockoutDuration) {
    return;
  }

  lockedOut = false;
  failedAttempts = 0;
  if (lockoutLevel < MAX_LOCKOUT_LEVEL) {
    ++lockoutLevel;
  }
  saveAttemptState();
  comms.println("UART unlocked. Enter password:");
}

void clearInputLine() {
  for (uint8_t i = 0; i < PASSWORD_LENGTH; ++i) {
    inputLine[i] = '\0';
  }
  inputLength = 0;
  inputTooLong = false;
}

void processAttempt() {
  if (lockedOut) {
    clearInputLine();
    return;
  }

  digitalWrite(LED_PIN, HIGH);
  const bool accepted = passwordMatches(inputLine, inputLength, inputTooLong);
  digitalWrite(LED_PIN, LOW);
  clearInputLine();

  if (!accepted) {
    if (failedAttempts < MAX_FAILED_ATTEMPTS) {
      ++failedAttempts;
    }
    saveAttemptState();

    comms.println(">> ACCESS DENIED");
    if (failedAttempts >= MAX_FAILED_ATTEMPTS) {
      beginLockout();
    } else {
      comms.print("Attempts remaining: ");
      comms.println(MAX_FAILED_ATTEMPTS - failedAttempts);
      comms.println("Enter password:");
    }
    return;
  }

  failedAttempts = 0;
  lockoutLevel = 0;
  saveAttemptState();
  comms.println(">> ACCESS GRANTED: running protected section");
  runProtectedSection();
  comms.println();
  comms.println("Enter password:");
}

void readUartLine() {
  while (comms.available() > 0 && !lockedOut) {
    const char character = static_cast<char>(comms.read());

    if (character == '\r') {
      continue;
    }
    if (character == '\n') {
      processAttempt();
      continue;
    }

    if (inputLength < PASSWORD_LENGTH) {
      inputLine[inputLength++] = character;
    } else {
      inputTooLong = true;
    }
  }
}

void setup() {
  comms.begin(UART_BAUD);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  loadAttemptState();
  if (failedAttempts >= MAX_FAILED_ATTEMPTS) {
    beginLockout();
  } else {
    comms.println("Enter password:");
  }
}

void loop() {
  finishLockoutIfExpired();

  if (lockedOut) {
    while (comms.available() > 0) {
      comms.read();
    }
    return;
  }

  readUartLine();
}
