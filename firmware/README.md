# Firmware

Theo tên file người dùng yêu cầu, firmware chính được giữ tại
[`esp32_core/esp32_core.ino`](../esp32_core/esp32_core.ino), không tạo bản sao dễ bị lệch phiên bản.
Các sketch `LM393_Read` và `SG90_Continuous_CW` là file thử nghiệm trước đó, không phải firmware đang nạp.

Dependencies: ESP32 Arduino core 3.3.12, PubSubClient 2.8.0, WiFiManager 2.0.17, ArduinoJson 7.4.2.
Preferences và esp_random thuộc ESP32 core. Không commit config.local.h; chạy mqtt/Setup.ps1 để tạo.
