#include <Arduino.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <esp_random.h>

#if __has_include("config.local.h")
#include "config.local.h"
#else
#error "Run mqtt/Setup.ps1 to generate config.local.h before compiling."
#endif

// O do 1: OUT/DO -> D27. O do 2: OUT/DO -> D26. Chi dung muc logic 3.3V.
// Co tay = LOW. D4 la tin hieu HIGH, khong dung cap nguon cho module.
constexpr uint8_t SLOT1_PIN = 27;
constexpr uint8_t SLOT2_PIN = 26;
constexpr uint8_t ALWAYS_HIGH_PIN = 4;
constexpr uint32_t RECONNECT_INTERVAL_MS = 5000;
constexpr char FIRMWARE_VERSION[] = "esp32_core-0.2.0";
char telemetryTopic[96], commandTopic[96], ackTopic[96], statusTopic[96];
char bootId[17], mqttClientId[96];
String offlineWill;
Preferences settings;
uint32_t reportIntervalMs = 1000;
uint32_t sampleSeq = 0;
String cachedCommandIds[8], cachedAcks[8];
uint8_t nextAckSlot = 0;

WiFiClient network;
PubSubClient mqtt(network);
WiFiManager wifiManager;
uint32_t lastReportMs = 0;
uint32_t lastReconnectMs = 0;
uint32_t lastWifiAttemptMs = 0;
bool mqttTried = false;
bool wifiWasConnected = false;

void handleCommand(char* topic, byte* payload, unsigned int length) {
  if (strcmp(topic, commandTopic) != 0 || length > 700) return;
  JsonDocument command;
  if (deserializeJson(command, payload, length)) return;
  const String id = command["command_id"] | "";
  const String action = command["action"] | "";
  const String targetBoot = command["boot_id"] | "";
  if (id.length() != 32) return;
  for (size_t index = 0; index < id.length(); index++) {
    const char ch = id[index];
    if (!((ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f'))) return;
  }
  for (uint8_t index = 0; index < 8; index++) {
    if (cachedCommandIds[index] == id) {
      mqtt.publish(ackTopic, cachedAcks[index].c_str(), false);
      return;
    }
  }
  bool success = false;
  const char* error = "Unsupported command";
  if (targetBoot != bootId || !command["uptime_deadline_s"].is<uint32_t>()) {
    error = "Command targets another boot or has no deadline";
  } else if (millis() / 1000 > command["uptime_deadline_s"].as<uint32_t>()) {
    error = "Command expired";
  } else if (action == "ping") {
    success = true;
  } else if (action == "configure") {
    if (!command["arguments"]["report_interval_ms"].is<uint32_t>()) {
      error = "Invalid report interval";
    } else {
      const uint32_t requested = command["arguments"]["report_interval_ms"].as<uint32_t>();
      if (requested < 500 || requested > 10000) {
        error = "Report interval must be 500..10000 ms";
      } else if (requested == reportIntervalMs || settings.putUInt("report_ms", requested) == sizeof(uint32_t)) {
        reportIntervalMs = requested;
        success = true;
      } else {
        error = "Could not save configuration";
      }
    }
  }
  JsonDocument ack;
  ack["device_id"] = MQTT_USERNAME;
  ack["command_id"] = id;
  ack["status"] = success ? "succeeded" : "failed";
  ack["result"]["report_interval_ms"] = reportIntervalMs;
  ack["result"]["uptime_s"] = millis() / 1000;
  if (!success) ack["error"] = error;
  String encoded;
  serializeJson(ack, encoded);
  cachedCommandIds[nextAckSlot] = id;
  cachedAcks[nextAckSlot] = encoded;
  nextAckSlot = (nextAckSlot + 1) % 8;
  mqtt.publish(ackTopic, encoded.c_str(), false);
  Serial.print("Lenh ");
  Serial.print(action);
  Serial.print(success ? " OK | Chu ky gui: " : " THAT BAI | Chu ky gui: ");
  Serial.print(reportIntervalMs);
  Serial.println(" ms");
}

void startWifiPortal() {
  Serial.print("Cau hinh Wi-Fi: ket noi mang ");
  Serial.println(SETUP_AP_NAME);
  Serial.print("Mat khau mang cau hinh: ");
  Serial.println(SETUP_AP_PASSWORD);
  Serial.println("Mo http://192.168.4.1 va chon Wi-Fi 2.4 GHz cung LAN voi may tinh.");
  wifiManager.startConfigPortal(SETUP_AP_NAME, SETUP_AP_PASSWORD);
}

void setup() {
  pinMode(ALWAYS_HIGH_PIN, OUTPUT);
  digitalWrite(ALWAYS_HIGH_PIN, HIGH);
  pinMode(SLOT1_PIN, INPUT_PULLUP);
  pinMode(SLOT2_PIN, INPUT_PULLUP);
  Serial.begin(115200);

  settings.begin("iot-settings", false);
  reportIntervalMs = settings.getUInt("report_ms", 1000);
  if (reportIntervalMs < 500 || reportIntervalMs > 10000) reportIntervalMs = 1000;
  snprintf(bootId, sizeof(bootId), "%08lx%08lx", static_cast<unsigned long>(esp_random()), static_cast<unsigned long>(esp_random()));
  snprintf(mqttClientId, sizeof(mqttClientId), "%s-%06lx", MQTT_USERNAME,
           static_cast<unsigned long>(ESP.getEfuseMac() & 0xFFFFFF));
  snprintf(telemetryTopic, sizeof(telemetryTopic), "iot/%s/lm393", MQTT_USERNAME);
  snprintf(commandTopic, sizeof(commandTopic), "iot/%s/commands", MQTT_USERNAME);
  snprintf(ackTopic, sizeof(ackTopic), "iot/%s/ack", MQTT_USERNAME);
  snprintf(statusTopic, sizeof(statusTopic), "iot/%s/status", MQTT_USERNAME);
  JsonDocument will;
  will["device_id"] = MQTT_USERNAME;
  will["state"] = "offline";
  will["boot_id"] = bootId;
  serializeJson(will, offlineWill);

  network.setConnectionTimeout(300);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setKeepAlive(15);
  mqtt.setSocketTimeout(1);
  mqtt.setBufferSize(768);
  mqtt.setCallback(handleCommand);

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  wifiManager.setDebugOutput(false);
  wifiManager.setConfigPortalBlocking(false);
  wifiManager.setConnectTimeout(10);
  wifiManager.setConfigPortalTimeout(0);
  wifiManager.setHostname("esp32-iot-01");
  if (!wifiManager.getWiFiIsSaved()) {
    startWifiPortal();
  } else {
    WiFi.begin();
  }
  Serial.println("Serial 115200. Go w va Enter de mo lai trang cau hinh Wi-Fi.");
}

void loop() {
  wifiManager.process();
  if (Serial.available() && Serial.read() == 'w') startWifiPortal();

  uint32_t nowMs = millis();
  const bool wifiConnected = WiFi.status() == WL_CONNECTED;
  if (wifiConnected && !wifiWasConnected) {
    Serial.print("Wi-Fi OK | IP ESP32: ");
    Serial.println(WiFi.localIP());
    Serial.print("MQTT broker: ");
    Serial.println(MQTT_HOST);
    mqttTried = false;
  }
  if (!wifiConnected && wifiWasConnected) mqtt.disconnect();
  wifiWasConnected = wifiConnected;

  if (!wifiConnected && !wifiManager.getConfigPortalActive() &&
      nowMs - lastWifiAttemptMs >= 15000) {
    lastWifiAttemptMs = nowMs;
    WiFi.reconnect();
  }
  if (wifiConnected && !mqtt.connected() &&
      (!mqttTried || nowMs - lastReconnectMs >= RECONNECT_INTERVAL_MS)) {
    mqttTried = true;
    lastReconnectMs = nowMs;
    if (mqtt.connect(mqttClientId, MQTT_USERNAME, MQTT_PASSWORD, statusTopic, 1, true, offlineWill.c_str(), true)) {
      mqtt.subscribe(commandTopic, 1);
      JsonDocument online;
      online["device_id"] = MQTT_USERNAME;
      online["state"] = "online";
      online["boot_id"] = bootId;
      String onlinePayload;
      serializeJson(online, onlinePayload);
      mqtt.publish(statusTopic, onlinePayload.c_str(), true);
      Serial.println("MQTT OK");
    } else {
      Serial.print("MQTT chua ket noi | ma loi: ");
      Serial.println(mqtt.state());
    }
  }
  if (wifiConnected && mqtt.connected()) mqtt.loop();

  nowMs = millis();
  if (nowMs - lastReportMs >= reportIntervalMs) {
    lastReportMs = nowMs;
    const int level1 = digitalRead(SLOT1_PIN);
    const int level2 = digitalRead(SLOT2_PIN);
    char payload[512];
    JsonDocument reading;
    reading["device_id"] = MQTT_USERNAME;
    reading["uptime_s"] = nowMs / 1000;
    reading["do"] = level1;
    reading["detected"] = level1 == LOW;
    reading["do2"] = level2;
    reading["detected2"] = level2 == LOW;
    reading["boot_id"] = bootId;
    reading["seq"] = sampleSeq++;
    reading["firmware"] = FIRMWARE_VERSION;
    reading["hardware"] = ESP.getChipModel();
    reading["report_interval_ms"] = reportIntervalMs;
    serializeJson(reading, payload, sizeof(payload));
    // Khong retain: tranh coi gia tri cu la phep do moi sau khi ket noi lai.
    const bool sent = wifiConnected && mqtt.connected() && mqtt.publish(telemetryTopic, payload, false);
    Serial.print("Thoi gian: ");
    Serial.print(nowMs / 1000);
    Serial.print(" s | P1(D27)=");
    Serial.print(level1);
    Serial.print(level1 == LOW ? " CO XE" : " TRONG");
    Serial.print(" | P2(D26)=");
    Serial.print(level2);
    Serial.print(level2 == LOW ? " CO XE" : " TRONG");
    Serial.print(wifiConnected ? " | Wi-Fi=OK" : " | Wi-Fi=CHO");
    Serial.println(sent ? " | MQTT=DA GUI" : " | MQTT=CHUA GUI");
  }
  delay(1);
}
