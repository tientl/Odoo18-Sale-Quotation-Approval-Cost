# Sale Approval & Cost - Odoo 18 Community

## 1. Yêu cầu

- Docker, Docker Compose
- Odoo 18 Community
- PostgreSQL 16+

## 2. Cài đặt

```bash
git clone <repo>
cd <repo>

# Module nằm trong ./addons/sale_quotation_approval_cost
docker compose up -d --build
```

Sau khi dịch vụ chạy:

1) Start server http:<YOUR_IP>:1369 hoặc localhost:1369 (Nếu chạy local)
2) Đăng nhập Odoo, bật Developer Mode.
3) Apps > Update Apps List > tìm và Upgrade module **Sale Quotation Approval Cost** 

## 3. Sử dụng
- **Thiết lập vai trò**:
  - Salesperson: người tạo báo giá (trường `user_id`), bật trong Settings > Users nhóm `Sales / User`.
  - Team Leader: user được chọn tại `team_id.user_id` (owner của Sales Team gán cho báo giá).
  - Sales Manager: user có quyền quản trị Sales (Settings > Users, nhóm `Sales / Administrator`).
  - Finance Manager: user thuộc nhóm kế toán quản lý (Settings > Users, nhóm `Accounting / Adviser` hoặc `Invoicing / Administrator`).
- **Quy trình phê duyệt**: từ Draft, bấm `Submit for Approval` (nếu cần duyệt). Team Leader duyệt bước `wait_lead`; nếu quy tắc yêu cầu, chuyển tiếp qua Sales Manager (`wait_manager`) và Finance Manager (`wait_finance`) cho tới `Approved`. Các nút Approve/Reject có popup xác nhận.
- **Chi phí & quy tắc**: mỗi dòng bán hàng có trường `Cost`; tổng `Total Cost` hiển thị trong phần tổng tiền. Quy tắc duyệt tự động: nếu doanh thu ≤ chi phí → cần đủ 3 bước; nếu doanh thu ≤ 150% chi phí → cần Team Leader.
- **Bộ lọc danh sách**:
  - Filter mặc định “My Quotations” động: gồm báo giá của bạn, báo giá chờ bạn duyệt với vai trò Team Leader; nếu bạn là Sales Manager, thêm báo giá `wait_manager`; nếu là Finance Manager, thêm báo giá `wait_finance`.
  - Bộ lọc nhanh: “Team Leader Approvals”, “Manager Approvals” (chỉ hiện với Sales Manager), “Finance Approvals” (chỉ hiện với Finance Manager).
- **Nút & quyền**: chỉ nhân viên Sales được submit; Team Leader của team duyệt bước 1; Sales Manager duyệt bước Manager; Finance Manager duyệt bước Finance.
- **Thông báo OdooBot / Chat**:
  - Khi submit/duyệt, hệ thống tự gửi thông báo (chatter) và tin nhắn chat 1-1 bằng OdooBot tới người duyệt tiếp theo (Team Leader/Sales Manager/Finance) kèm nút “Open Quotation”.
  - Khi báo giá được Approved, salesperson cũng nhận thông báo và chat kèm link mở báo giá.
  - Nếu Discuss chưa cài, chat được bỏ qua; nên giữ app Discuss để xem chat.
