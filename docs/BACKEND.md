# Backend v0.2

Đọc OpenAPI tại `/docs`. Mọi API quản lý cần Bearer JWT, trừ `/health` và `/auth/login`.
Tài khoản admin xem toàn hệ thống; operator xem các thiết bị có `DeviceGrant`. Viewer chỉ dùng `/parking/overview` theo grant và API tài khoản cá nhân, không truy cập API kỹ thuật.
Viewer luôn không được gửi lệnh, kể cả khi vô tình được gán cờ điều khiển.
Operator cần thêm `can_control` để ping, `can_configure` để cấu hình/rule. Chỉ admin quản lý tài khoản,
onboarding, cấp quyền, vị trí và vòng đời. Không có đăng ký công khai tự cấp quyền admin.

## Dashboard cùng origin

`GET /` phục vụ dashboard ParkFlow trong `frontend/`; `/assets/` phục vụ JS/CSS/SVG nội bộ.
Không cần Node.js, CDN hoặc cấu hình CORS để chạy giao diện. `/docs` vẫn dùng Swagger bình thường.
Trang giao diện có CSP, chống nhúng iframe và `nosniff`; trang gốc/phản hồi xác thực dùng `no-store`.

`GET /devices/{id}/permissions` trả quyền hiệu lực **của chính tài khoản đang gọi**:
`can_read`, `can_manage`, `can_control`, `can_configure`. API không tiết lộ grant của người khác;
thiết bị ngoài phạm vi trả 404. Đây là thông tin để giao diện bật/tắt thao tác, mọi API ghi vẫn kiểm tra quyền.

Phản hồi thiết bị thêm `report_interval_ms` và `effective_offline_timeout_s` để giao diện hết hạn
dữ liệu ngay cả giữa hai lần cập nhật. Giao diện truy vấn định kỳ 3 giây và hiển thị giờ UTC+7.
Xem [hướng dẫn frontend](../frontend/README.md).

## Luồng thiết bị

1. `POST /devices` với `code` duy nhất và `name`; trạng thái ban đầu `registered`.
2. `POST /devices/{id}/provision`: tạo tài khoản MQTT riêng và chuyển sang `provisioned`.
   Mật khẩu chỉ trả trong phản hồi này, không trả khi xem thiết bị hoặc audit log.
3. Cấu hình firmware bằng tài khoản đó. Username MQTT cũng là device ID và tên trong topic.
4. `PATCH /devices/{id}` với `{"status":"active"}` để đưa vào sử dụng.
5. `PUT /devices/{id}/grants/{user_id}` để cấp quyền xem/điều khiển/cấu hình.
6. `PATCH /devices/{id}/metadata` để ghi vị trí và lỗi/bảo trì.
7. `PUT /devices/{id}/slot` với `{"slot":"P1"}` hoặc P2 để gán ô. D27/P1, D26/P2 là hợp đồng firmware hiện tại.
8. `revoked` hoặc `decommissioned` gọi broker disableClient, ngắt các kết nối hiện có và chặn kết nối lại.
   API trả lỗi 503 nếu broker không xác nhận, không báo thu hồi thành công giả.

Thiết bị thật `esp32_01` được bootstrap sẵn ở trạng thái active với P1/P2 để giữ nguyên mô hình đã chạy.
Bootstrap không kích hoạt lại thiết bị đã bị thu hồi hoặc đổi mật khẩu của thiết bị đã onboarding.
`POST /devices/{id}/credentials/rotate` tạo mật khẩu mới; phải cập nhật lại trên thiết bị.

Vòng đời: registered → provisioned → active ↔ maintenance; có thể revoked rồi provisioned lại;
decommissioned là trạng thái cuối. Online/offline được tính riêng với trạng thái quản lý.

## Topic và dữ liệu

| Topic | Bên gửi | Nội dung |
|---|---|---|
| `iot/{device_id}/lm393` | ESP32 | Hai cảm biến, uptime, boot ID, seq, firmware/hardware, chu kỳ gửi |
| `iot/{device_id}/commands` | Backend | command_id, action, arguments, deadline, boot đích |
| `iot/{device_id}/ack` | ESP32 | command_id, succeeded/failed, kết quả đã áp dụng |
| `iot/{device_id}/status` | ESP32/broker will | online/offline, boot ID |

Payload telemetry:

```json
{"device_id":"esp32_01","uptime_s":12,"do":0,"detected":true,"do2":1,"detected2":false,
 "boot_id":"0123456789abcdef","seq":3,"firmware":"esp32_core-0.2.0","hardware":"ESP32-D0WD-V3","report_interval_ms":1000}
```

`do/detected` là P1; `do2/detected2` là P2. LOW=occupied. Backend kiểm tra topic/ID, kiểu và miền giá trị,
quan hệ DO/occupied. Thiết bị chưa được đăng ký/cấp quyền hoặc revoked bị từ chối. `simulator` có topic
và tài khoản riêng, chỉ admin xem; không cập nhật trạng thái bãi xe thật.

Một boot có seq tăng dần. Bản tin trùng, seq cũ hoặc boot đã được thay thế bị bỏ qua.
Firmware mới gửi đủ boot/seq; bản tin cũ không có cả hai trường vẫn được chấp nhận để tương thích.
Telemetry publish QoS 0, không retain; trạng thái mới nhất gửi theo chu kỳ, không có bộ đệm gửi bù.
Backend ghi timestamp nhận UTC. Uptime là giây từ khi thiết bị khởi động, không phải giờ đồng hồ.

## Cấu hình từ xa và xác nhận

```http
POST /devices/{id}/commands
Authorization: Bearer <token>
Content-Type: application/json

{"action":"configure","report_interval_ms":2000,"idempotency_key":"demo-config-01"}
```

HTTP 202 chỉ có nghĩa tạo yêu cầu, chưa có nghĩa ESP32 đã thực hiện. Theo dõi `GET /commands/{id}`.
Trạng thái: queued → sent → acknowledged/failed/timed_out/cancelled. Backend publish QoS 1,
thử tối đa ba lần, cách nhau hai giây, dùng lại command_id. ESP32 nhớ tám ACK gần nhất trong RAM;
hai lệnh hiện có đều idempotent. Cấu hình được lưu vào NVS và giữ sau khi khởi động lại.
Deadline theo boot ID/uptime giúp từ chối lệnh thuộc boot cũ hoặc đến quá hạn, không phụ thuộc Internet/NTP.

`{"action":"ping"}` kiểm tra phản hồi. Không có lệnh servo trong phiên bản này.
GET `/devices/{id}/configuration` cho biết chu kỳ đã ghi nhận và yêu cầu đang chờ.

## Cảnh báo và lịch sử

- GET/PUT `/devices/{id}/rules`: bật/tắt cảnh báo offline/bãi đầy, ngưỡng offline 5–120 giây.
- Ngưỡng thực tế lấy max(ngưỡng cấu hình, ba chu kỳ gửi) để tránh báo mất kết nối sai khi tăng chu kỳ.
- Một cảnh báo đang diễn ra không bị tạo lại mỗi giây. Hết điều kiện thì ghi resolved_at.
- Xác nhận cảnh báo (`POST /alerts/{id}/acknowledge`) là thao tác người dùng, tách khỏi việc điều kiện đã hết.
- `/parking/events` ghi initial/occupied/available/unknown/after_gap. Đây là thay đổi trạng thái ô,
  không phải nhận diện xe hoặc chứng minh chính xác lượt ra/vào qua cổng.
- Khi mất kết nối hoặc dữ liệu quá cũ, `/parking/slots` và `/dashboard` dùng unknown, không tính là trống.

## Truy vấn

- `/telemetry/latest?device_id=esp32_01`
- `/telemetry?device_id=esp32_01&limit=50&before_id=123&from_at=...&to_at=...`
- `/telemetry/statistics`: đếm mẫu theo giờ UTC và ô; phần trăm là phần trăm **số mẫu**, không phải thời gian đỗ.
- `/telemetry/export.csv`: tối đa 10000 dòng mỗi lần, thu hẹp khoảng thời gian để xuất tiếp.

from_at/to_at dùng ISO 8601 kèm múi giờ, ví dụ `2026-10-24T08:00:00+07:00`; client phải URL-encode dấu +.
Dữ liệu nhạy cảm: tên tài khoản, mật khẩu băm, quyền thiết bị. Không thu biển số/ảnh/vị trí GPS cá nhân.
Không commit `.env`, `config.local.h`, `mqtt/runtime`, database hoặc bản sao lưu. Triển khai local chưa có TLS/HTTPS.

## Chính sách dữ liệu mới

Xem [STORAGE.md](STORAGE.md). `live_telemetry` lưu trạng thái hiện tại độc lập với lịch sử.
`/telemetry/latest` lấy trạng thái này; lịch sử/CSV chỉ chứa mẫu thay đổi hoặc checkpoint 60 giây, giữ 3 ngày.
`/parking/utilization` trả thời gian quan sát theo giờ (có xe/trống/chưa xác định), làm tròn bộ lọc ra toàn bộ giờ giao nhau.
`/telemetry/statistics` cũ vẫn đếm mẫu được lưu và không dùng làm tỷ lệ thời gian.
`/storage/policy` dành cho admin. Viewer bị từ chối các API thiết bị, telemetry, cấu hình, lệnh và cảnh báo kỹ thuật bằng 403.
