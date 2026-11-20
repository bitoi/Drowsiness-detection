#include <string.h>

// Example pin assignment for the classic ESP32 module shown in the photo.
#define LED_GREEN   25
#define LED_YELLOW  26
#define LED_RED     27
#define MOTOR_PIN   32   // Connect to the vibration module's IN pin

// Most simple driver modules are active-HIGH.
// If your module behaves in reverse, change HIGH to LOW here.
const int MOTOR_ON_LEVEL = HIGH;
const int MOTOR_OFF_LEVEL = (MOTOR_ON_LEVEL == HIGH) ? LOW : HIGH;

char inputBuffer[32];
size_t inputIndex = 0;

void setOutputs(bool green, bool yellow, bool red, bool motorOn) {
  digitalWrite(LED_GREEN, green ? HIGH : LOW);
  digitalWrite(LED_YELLOW, yellow ? HIGH : LOW);
  digitalWrite(LED_RED, red ? HIGH : LOW);
  digitalWrite(MOTOR_PIN, motorOn ? MOTOR_ON_LEVEL : MOTOR_OFF_LEVEL);
}

void handleCommand(const char* command) {
  if (strcmp(command, "NORMAL") == 0) {
    setOutputs(true, false, false, false);
    Serial.println("ACK:NORMAL");
  }
  else if (strcmp(command, "EYES_CLOSED") == 0) {
    setOutputs(false, true, false, false);
    Serial.println("ACK:EYES_CLOSED");
  }
  else if (strcmp(command, "DROWSY") == 0) {
    // Red LED and vibration motor are active while DROWSY is detected.
    setOutputs(false, false, true, true);
    Serial.println("ACK:DROWSY");
  }
  else if (strcmp(command, "NO_FACE") == 0) {
    setOutputs(false, false, false, false);
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
  pinMode(MOTOR_PIN, OUTPUT);

  setOutputs(false, false, false, false);
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
        // Discard an overlong command and start receiving a new one.
        inputIndex = 0;
      }
    }
  }
}
