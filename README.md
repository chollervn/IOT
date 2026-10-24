# Bãi đỗ xe IoT — ESP32, MQTT và FastAPI

Nguyên mẫu một bãi xe với hai ô đỗ: **P1 dùng D27, P2 dùng D26**. Hai cảm biến LM393 gửi trạng thái
qua Wi-Fi/MQTT; backend lưu lịch sử, quản lý tài khoản/thiết bị, phân quyền và sinh cảnh báo.
Servo SG90 và giao diện frontend hiện chưa tích hợp; người dùng đã yêu cầu tạm bỏ qua thanh chắn.

```text
LM393 P1/P2 → ESP32 ↔ Mosquitto ↔ FastAPI → SQLite
                                  ↓
                           Monitor / Swagger API
```

## Chạy trên Windows

Cần Python, Arduino IDE có ESP32 core, Wi-Fi 2.4 GHz cho ESP32; máy tính và ESP32 truy cập được cùng LAN.

```powershell
python -m venv backend\.venv
.\mqtt\Setup.ps1
.\mqtt\Start-IOT.ps1
```

Nếu PowerShell chặn script, dùng `powershell -ExecutionPolicy Bypass -File .\mqtt\Setup.ps1`.
Broker mặc định dùng cổng **1884**, tránh dịch vụ đang dùng 1883 trên máy phát triển.
Chạy `mqtt/Enable-Firewall.cmd` một lần với quyền Administrator để cho phép MQTT từ mạng LAN.

Mở **http://127.0.0.1:8000/docs**. Tài khoản quản trị được tạo với mật khẩu ngẫu nhiên ở
`mqtt/runtime/THONG_TIN_DANG_NHAP.txt`. Không có mật khẩu thật nào được lưu trong repo.

## Nạp ESP32

```powershell
.\mqtt\Upload-ESP32.ps1 -Port COM5
```

Thay COM5 bằng cổng thực tế. Mã nguồn chính nằm ở **`esp32_core/esp32_core.ino`**.
Setup tạo `config.local.h` với địa chỉ và tài khoản MQTT. Lần đầu, kết nối Wi-Fi `ESP32-IOT-Setup`
bằng điện thoại, dùng mật khẩu cấu hình trong file thông tin ở trên và mở **http://192.168.4.1**.
Nhập Wi-Fi 2.4 GHz cùng mạng với máy tính. Mở `mqtt/Monitor.cmd` để xem trạng thái hai ô.

## Chức năng backend

- Tạo tài khoản, đăng nhập/đăng xuất, đổi mật khẩu, khóa tài khoản; vai trò admin/operator/viewer.
- Cấp quyền theo từng thiết bị; người không được cấp quyền không xem được dữ liệu của thiết bị đó.
- Onboarding với mật khẩu MQTT riêng; quản lý vị trí, firmware/hardware, bảo trì và vòng đời thiết bị.
- Thu hồi/decommission được áp dụng lên broker bằng Mosquitto Dynamic Security.
- Telemetry theo thời gian, phát hiện bản tin trùng bằng boot ID/sequence, lịch sử từng ô và sự kiện đổi trạng thái.
- Online/offline, cảnh báo mất kết nối/bãi đầy, xác nhận và lưu lịch sử cảnh báo.
- Lệnh `ping` và đổi chu kỳ gửi từ 500–10000 ms, có retry, timeout, idempotency key và ACK từ ESP32.
- Lọc theo thời gian, thống kê số mẫu theo giờ và xuất CSV. Không suy diễn biển số, lượt xe hoặc phí gửi xe.

## Kiểm tra

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.\backend\.venv\Scripts\python.exe -m pytest -q
.\backend\.venv\Scripts\python.exe mqtt\check_setup.py
```

## Tài liệu

- [Backend và API](docs/BACKEND.md)
- [Đối chiếu yêu cầu đồ án](docs/REQUIREMENTS.md)
- [Đấu nối phần cứng](hardware/README.md)
- [Database](database/README.md)
- [MQTT và triển khai local](mqtt/README.md)

Mô hình hiện chạy trong LAN, MQTT TCP chưa có TLS, API chỉ lắng nghe localhost. Cần cấu hình HTTPS/TLS
và triển khai phù hợp trước khi đưa lên Internet. Khóa/mật khẩu, database, bản sao lưu, log và công cụ
đã tải về đều bị loại khỏi Git bằng `.gitignore`.

Thư viện sử dụng: [ESP32 Arduino](https://github.com/espressif/arduino-esp32),
[PubSubClient](https://github.com/knolleary/pubsubclient), [WiFiManager](https://github.com/tzapu/WiFiManager),
[ArduinoJson](https://arduinojson.org/), [Mosquitto](https://mosquitto.org/),
[Paho MQTT](https://eclipse.dev/paho/), [FastAPI](https://fastapi.tiangolo.com/),
[SQLAlchemy](https://www.sqlalchemy.org/). Code và tài liệu được hỗ trợ bằng AI; nhóm cần hiểu, kiểm thử
và giải thích được các phần sử dụng khi bảo vệ đồ án.
