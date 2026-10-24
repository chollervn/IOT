# Phần cứng hiện tại

- Một ESP32-D0WD-V3, nạp qua cổng COM được chọn trong Arduino IDE/CLI.
- Hai module hồng ngoại LM393: OUT ô P1 → D27, OUT ô P2 → D26, chung GND với ESP32.
- Mức tín hiệu hiện tại: LOW = có xe, HIGH = trống. Ngưỡng cảm biến điều chỉnh bằng biến trở trên module.
- GPIO chỉ nhận logic 3.3V. Không đưa OUT 5V trực tiếp vào D27/D26. Cấp module 3V3 nếu module hỗ trợ,
  hoặc dùng chuyển mức phù hợp với đầu ra module.
- D4 giữ HIGH sau setup để duy trì chức năng đã yêu cầu; dùng làm tín hiệu, không dùng làm chân cấp nguồn module.
- Servo SG90 đang tạm bỏ qua; không phát PWM hoặc tự điều khiển thanh chắn.

Khi kiểm thử, che từng cảm biến riêng để đối chiếu P1/P2 trên Monitor và `/parking/slots`.
Hai cảm biến chỉ thể hiện ô có vật/xe; chưa xác định biển số hay phương tiện cụ thể.
