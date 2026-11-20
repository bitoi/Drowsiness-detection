#include <string.h>

// Three LEDs for the classic ESP32 board.
// Green = NORMAL, Yellow = EYES_CLOSED, Red = DROWSY.
#define LED_GREEN   25
#define LED_YELLOW  26
#define LED_RED     27

char inputBuffer[32];
size_t inputIndex = 0;

void setLEDs(bool green, bool yellow, bool red) {
  digitalWrite(LED_GREEN, green ? HIGH : LOW);
  digitalWrite(LED_YELLOW, yellow ? HIGH : LOW);
  digitalWrite(LED_RED, red ? HIGH : LOW);
}

void handleCommand(const char* command) {
  if (strcmp(command, "NORMAL") == 0) {
    setLEDs(true, false, false);
    Serial.println("ACK:NORMAL");
  }
  else if (strcmp(command, "EYES_CLOSED") == 0) {
    setLEDs(false, true, false);
    Serial.println("ACK:EYES_CLOSED");
  }
  else if (strcmp(command, "DROWSY") == 0) {
    setLEDs(false, false, true);
    Serial.println("ACK:DROWSY");
  }
  else if (strcmp(command, "NO_FACE") == 0) {
    setLEDs(false, false, false);
    Serial.println("ACK:NO_FACE");
  }
  else if (command[0] != '\0') {
    Serial.print("ERR:UNKNOWN_COMMAND:");
    Serial.println(command);
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_RED, OUTPUT);

  // Start with all LEDs off.
  setLEDs(false, false, false);
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '\n') {
      inputBuffer[inputIndex] = '\0';
      handleCommand(inputBuffer);
      inputIndex = 0;
    }
    else if (c != '\r') {
      if (inputIndex < sizeof(inputBuffer) - 1) {
        inputBuffer[inputIndex++] = c;
      }
      else {
        // Discard an overlong command and wait for the next line.
        inputIndex = 0;
      }
    }
  }
}
