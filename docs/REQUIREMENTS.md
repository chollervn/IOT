# Đối chiếu yêu cầu đồ án IoT

Đối chiếu theo đề bài học phần do nhóm cung cấp, các mục 4.2–4.6, 6–8. Phạm vi đợt này là backend
cho một bãi xe hai ô; người dùng yêu cầu tạm bỏ servo SG90.

| Nhóm tiêu chí | Phần triển khai | Phần còn lại |
|---|---|---|
| Người dùng | Tạo tài khoản, đăng nhập/đăng xuất, đổi mật khẩu, khóa tài khoản, ba vai trò | Giao diện người dùng |
| Phạm vi quyền | DeviceGrant, kiểm tra backend cho thiết bị/telemetry/cảnh báo/lệnh/CSV | Demo giao diện theo vai trò |
| Vòng đời thiết bị | Onboarding, mật khẩu MQTT riêng, gán user/vị trí/ô, active/maintenance/revoked/decommissioned | Giao diện quản trị |
| Kết nối thật | Hai LM393 ở D27/D26, Wi-Fi/MQTT, reconnect, heartbeat qua telemetry và LWT | Đo độ ổn định dài hạn |
| Dữ liệu | Timestamp UTC, boot/seq, kiểm tra hợp lệ, lịch sử, bộ lọc thời gian, thống kê mẫu, CSV | Biểu đồ frontend |
| Giám sát | Dashboard API, online/offline, unknown khi không có dữ liệu mới | Dashboard web/mobile |
| Cảnh báo | Offline, bãi đầy, timeout lệnh, lịch sử và xác nhận | Giao diện xử lý cảnh báo |
| Cấu hình/ACK | Ping, đổi chu kỳ gửi, retry/timeout, lịch sử lệnh, xác nhận từ ESP32 | Điều khiển servo được tạm hoãn |
| Bảo mật | Hash mật khẩu người dùng, JWT, scope, MQTT ACL riêng, thu hồi trên broker, audit log, secret ngoài Git | TLS/HTTPS và kiểm tra khi triển khai Internet |
| Sản phẩm nộp | Source, schema, tài liệu API/topic, test tự động, script chạy local | ERD/sơ đồ thiết kế, frontend, báo cáo/slide, bằng chứng demo theo nhóm |

Không coi việc có backend là hoàn thành toàn bộ đồ án. Chưa triển khai OTA, AI, nhận diện biển số,
tính phí hay cổng tự động. Hai cảm biến cùng một loại không được mô tả là hai loại cảm biến khác nhau.
