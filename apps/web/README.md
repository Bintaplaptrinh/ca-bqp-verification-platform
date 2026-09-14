# Frontend Layer — CA/BQP Verification Platform

Giao diện người dùng Web chuẩn hóa cho **Hệ thống Tra cứu & Xác minh Đối tượng CA/BQP** được xây dựng với React, Vite và Tailwind CSS theo tiêu chuẩn **Mobile-First & Quality-first 2026**.

---

## 1. Cấu trúc thư mục

```
apps/web/
├── package.json                 # Dependencies & Build Scripts
├── README.md                    # Hướng dẫn cài đặt & vận hành
├── vite.config.ts               # Cấu hình Vite & Tailwind
├── src/
│   ├── main.tsx                 # React App Root
│   ├── App.tsx                  # Root Container & View Selector
│   ├── index.css                # Tailwind Global Styling
│   └── components/
│       ├── VerificationModule.jsx    # Component Xác minh chính (Mobile-First Responsive)
│       └── CABQPVerification.jsx    # Giao diện nghiệp vụ mở rộng (Stitch)
```

---

## 2. Hướng dẫn cài đặt & Khởi chạy cục bộ

### Bước 1: Di chuyển vào thư mục web

```bash
cd apps/web
```

### Bước 2: Cài đặt thư viện dependencies

```bash
npm install
```

### Bước 3: Khởi chạy môi trường phát triển (Development Server)

```bash
npm run dev
```

Sau khi khởi chạy, ứng dụng sẽ hoạt động tại:
- **Địa chỉ Local**: `http://localhost:3000` (hoặc `http://localhost:5173` tùy cấu hình)
- Tự động kết nối với API Backend tại: `http://localhost:8000/api/v1/verification/cases`

### Cấu hình biến môi trường kết nối Backend (.env)

Tạo file `.env` nếu cần đổi cổng hoặc địa chỉ Backend:
```env
VITE_API_BASE_URL=http://localhost:8000
```

> **Cơ chế Dự phòng Thông minh (Resilient Fallback):** Nếu Backend chưa được bật, ứng dụng tự động kích hoạt Động cơ Quy tắc Nội bộ 2026 trên trình duyệt, vẫn trả về kết quả đối soát chính xác theo các Invariant 2026 mà không làm gián đoạn trải nghiệm người dùng.

---

## 3. Các đặc tính Responsive & Mobile-First trong `VerificationModule.jsx`

Component `VerificationModule.jsx` được thiết kế theo tư duy **Mobile-first** triệt để:

1. **Hệ thống Grid & Flexbox thích ứng linh hoạt**:
   - Chuyển đổi từ `flex-col` trên điện thoại sang `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3` hoặc `grid-cols-12` trên desktop.
   - Khoảng đệm (padding) tự động co giãn: `p-4 sm:p-6 lg:p-8`.
2. **Thanh điều hướng tối ưu hóa cho màn hình cảm ứng**:
   - Menu trượt (Hamburger Drawer) tự động thu gọn trên thiết bị di động.
   - Nút bấm và vùng chạm (touch targets) đạt tối thiểu 44px (`h-11` đến `h-12`).
3. **Bảng dữ liệu chuyển hóa thông minh (Table-to-Card Transformation)**:
   - Danh mục bằng chứng đối soát (`Evidence Matrix`) hiển thị dưới dạng bảng chi tiết trên màn hình máy tính (`hidden sm:block table`).
   - Tự động chuyển thành các thẻ tóm tắt dạng danh sách (`sm:hidden cards`) trên màn hình điện thoại để chống tràn ngang (no horizontal overflow).
4. **Tích hợp Axios & Quản lý trạng thái bằng React Hooks**:
   - Sử dụng `useState`, `useEffect` để quản lý các trạng thái: Nhập liệu, Tải tệp, Quét OCR, Loading Stepper 4 bước, và Hiển thị Kết quả Phân loại.
   - Hiển thị rõ ràng 3 phân nhóm: **Chế độ an sinh xã hội**, **Tổ chức quản lý (BCA / BQP / Dân sự)**, và **Bằng chứng đối soát (Evidence)**.
