/*
  AI Store Robot - minimal motor firmware for Arduino UNO/Nano + L298N driver.
  Talks the line protocol used by robot/robot_control.py (SerialRobot):
    F <ms> | B <ms> | L <ms> | R <ms> | S | GRAB | RELEASE | PING
  Every command is answered with "OK", "PONG" or "ERR <reason>".
*/
#include <Servo.h>

const int ENA = 5, IN1 = 7, IN2 = 8;    // left motor
const int ENB = 6, IN3 = 9, IN4 = 10;   // right motor
const int SERVO_PIN = 3;                // gripper
const int SPEED = 180;                  // 0..255

Servo gripper;
String line;

void motors(int l1, int l2, int r1, int r2) {
  digitalWrite(IN1, l1); digitalWrite(IN2, l2);
  digitalWrite(IN3, r1); digitalWrite(IN4, r2);
  analogWrite(ENA, SPEED); analogWrite(ENB, SPEED);
}
void stopMotors() { analogWrite(ENA, 0); analogWrite(ENB, 0); }

void timedMove(char dir, long ms) {
  switch (dir) {
    case 'F': motors(HIGH, LOW, HIGH, LOW); break;
    case 'B': motors(LOW, HIGH, LOW, HIGH); break;
    case 'L': motors(LOW, HIGH, HIGH, LOW); break;
    case 'R': motors(HIGH, LOW, LOW, HIGH); break;
  }
  delay(ms);
  stopMotors();
}

void setup() {
  pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT); pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
  pinMode(ENA, OUTPUT); pinMode(ENB, OUTPUT);
  gripper.attach(SERVO_PIN);
  gripper.write(90);              // open
  Serial.begin(115200);
  stopMotors();
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      line.trim();
      handle(line);
      line = "";
    } else if (c != '\r') {
      line += c;
    }
  }
}

void handle(const String &cmd) {
  if (cmd == "PING") { Serial.println("PONG"); return; }
  if (cmd == "S") { stopMotors(); Serial.println("OK"); return; }
  if (cmd == "GRAB") { gripper.write(20); delay(400); Serial.println("OK"); return; }
  if (cmd == "RELEASE") { gripper.write(90); delay(400); Serial.println("OK"); return; }
  if (cmd.length() >= 3 && cmd[1] == ' ') {
    char dir = cmd[0];
    long ms = cmd.substring(2).toInt();
    if ((dir == 'F' || dir == 'B' || dir == 'L' || dir == 'R') && ms > 0 && ms < 10000) {
      timedMove(dir, ms);
      Serial.println("OK");
      return;
    }
  }
  Serial.print("ERR unknown command: "); Serial.println(cmd);
}
