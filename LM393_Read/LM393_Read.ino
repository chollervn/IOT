#include <Arduino.h>

// GND cam bien -> GND ESP32; OUT/DO -> GPIO27 qua muc logic 3.3V.
// Chi cap VCC = 3.3V neu module ho tro. Neu OUT = 5V, can chuyen muc.
// Mo Serial Monitor o toc do 115200 baud.
constexpr uint8_t LM393_PIN = 27;
// D4 giu HIGH (~3.3V) sau setup; dung lam tin hieu, khong cap nguon module.
constexpr uint8_t ALWAYS_HIGH_PIN = 4;
// Theo so do thuc te: co tay = 0V (LOW), bo tay = HIGH.
constexpr uint8_t DETECTED_LEVEL = LOW;
constexpr uint32_t REPORT_INTERVAL_MS = 1000;

uint32_t lastReportMs = 0;

void setup() {
  pinMode(ALWAYS_HIGH_PIN, OUTPUT);
  digitalWrite(ALWAYS_HIGH_PIN, HIGH);
  Serial.begin(115200);
  pinMode(LM393_PIN, INPUT_PULLUP);
  lastReportMs = millis();
}

void loop() {
  const uint32_t nowMs = millis();
  if (nowMs - lastReportMs >= REPORT_INTERVAL_MS) {
    lastReportMs = nowMs;
    const int level = digitalRead(LM393_PIN);

    // Thoi gian tinh tu luc ESP32 khoi dong, khong phai gio dong ho.
    Serial.print("Thoi gian: ");
    Serial.print(nowMs / 1000);
    Serial.print(" s | DO=");
    Serial.print(level);
    Serial.print(level == LOW ? " (LOW)" : " (HIGH)");
    Serial.print(" | Ket qua: ");
    Serial.println(level == DETECTED_LEVEL ? "CO VAT CAN" : "KHONG CO VAT CAN");
  }
  delay(1);
}
