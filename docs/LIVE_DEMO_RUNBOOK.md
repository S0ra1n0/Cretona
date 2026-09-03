# Cretona — live demonstration runbook

**Chuẩn nghiệm thu của dự án này là hệ thống chạy live trước mặt người xem.**
Không phải test xanh ở nhà rồi chụp ảnh nộp. Test suite và screenshot là bằng
chứng bổ trợ; chúng trả lời "đã từng chạy", không trả lời "mở lên có dùng được
không". Tài liệu này là kịch bản để câu thứ hai được trả lời trực tiếp.

- Buổi đánh giá quá trình: **2026-09-03**
- Buổi demo cuối kì: **2026-09-05** (thứ Bảy) — vẫn là một buổi demo live,
  **không phải hạn nộp**.
- **Hạn nộp: 2026-09-09.** Sau buổi 09-05 mới soạn source code, báo cáo,
  video demo rồi nộp — không nộp ngay trong ngày 09-05.

---

## 1. Ràng buộc phải nói thẳng

Một job Wan2.1 mất **khoảng 49 phút** trên Kaggle 2×T4 (65 frame, 4 giây; bản 3
giây/49 frame ngắn hơn nhưng vẫn hàng chục phút). **Không thể sinh xong một
video trong một buổi demo 10–15 phút.** Bất kỳ kịch bản nào hứa điều đó sẽ hỏng
trước mặt giám khảo.

Cách trung thực để vẫn demo live:

1. **Bật worker Kaggle trước giờ demo.**
2. **Nộp một job thật ngay đầu buổi** — người xem thấy job vào hàng đợi, thấy
   `pending → generating`, thấy phần trăm tiến trình nhích lên do worker thật
   ghi vào database thật.
3. **Demo toàn bộ phần còn lại của hệ thống trong lúc job chạy** — đăng ký, đăng
   nhập, credits, sự kiện, admin, lịch sử.
4. **Phát một video đã sinh xong từ trước** để chứng minh khâu phát. Nói rõ đây
   là job của lần chạy trước, không giả vờ nó vừa sinh xong.
5. **Quay lại job đầu buổi ở cuối buổi.** Nếu buổi đủ dài thì nó đã xong; nếu
   chưa, tiến trình đang nhích vẫn là bằng chứng sống.

Điểm mấu chốt: **mọi thứ người xem thấy đều là hệ thống thật đang chạy**, chỉ có
độ dài sinh video là không nén được. Nói ra ràng buộc đó là trung thực, giấu nó
mới là gian.

---

## 2. Thứ tự bật hệ thống

Chạy từ gốc repo. Một lệnh một dòng — terminal là Windows PowerShell 5.1, `&&`
là lỗi cú pháp ở đó.

```powershell
.\scripts\run-fastapi.ps1 -SkipPreflight
```

`-SkipPreflight` **không phải tùy chọn**: thiếu nó, profiler ghi đè
`CRETONA_DEFAULT_VIDEO_PROVIDER` trong `.env` mỗi lần khởi động.

Kiểm tra backend sống:

```powershell
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/health
```

Phải trả `200`. Emulator dùng `10.0.2.2:8000` để trỏ về máy host; máy thật thì
dùng IP LAN.

Ứng dụng cài trên emulator có id **`com.cretona.app.debug`** — chú ý hậu tố,
`com.cretona.app` sẽ báo `No activities found`.

Worker Kaggle: mở notebook riêng, verify hash bundle
`cretona-kaggle-worker-a7330d06.zip`, rồi chạy **không** `--once` để nó phục vụ
cả hàng đợi:

```bash
!python backend/kaggle_worker.py
```

---

## 3. Kịch bản demo

Thứ tự này để phần rủi ro nhất xảy ra sớm, khi còn thời gian xử lý.

| # | Bước | Chứng minh điều gì |
|---|---|---|
| 1 | Nộp một job `kaggle` thật, text-only, 3–4 giây | Hàng đợi thật, worker thật claim |
| 2 | Đăng ký một tài khoản mới ngay tại chỗ | Supabase Auth thật, trigger tạo profile, số dư khởi tạo |
| 3 | Nhận thưởng sự kiện | Ledger credits thật, ràng buộc thời gian thật |
| 4 | Tạo một video bằng provider `fake` | Vòng đời job hoàn chỉnh trong vài giây, không phải chờ GPU |
| 5 | Mở một project đã hoàn thành từ trước, phát video | Signed URL thật, Media3 phát thật |
| 6 | Lưu về máy và chia sẻ | FR-MEDIA-001/002 |
| 7 | Đăng nhập admin, xem dashboard | RBAC thật, số liệu thật |
| 8 | Quay lại job bước 1 | Tiến trình đã nhích, hoặc đã xong |

Bước 4 quan trọng hơn vẻ ngoài của nó: nó cho người xem thấy **trọn vẹn** một
vòng đời tạo video trong vài giây, điều mà đường Kaggle không làm kịp trong buổi
họp. Đây là provider thật trong hệ thống, không phải mock ghép vào để diễn.

### Prompt dùng khi demo

Bốn clip thực nghiệm đều **bỏ qua hướng và chuyển động camera**. Viết "bay từ
trái sang phải" rồi chiếu clip bay ngược lại là tự nộp lỗi cho giám khảo. Chỉ tả
chủ thể, bối cảnh, ánh sáng, phong cách.

### Sự kiện nào còn sống ngày nào

| Sự kiện | 09-03 | 09-05 (thứ Bảy) |
|---|---|---|
| `NATIONAL_DAY` +20 | **Còn** — hết hạn 09-04 00:00+07 | Hết hạn |
| `WEEKEND_GIFT` | Không | **Còn** |
| `HOT_HOURS` 20:00–22:00 | Chỉ trong khung giờ | Chỉ trong khung giờ |

Buổi 09-03 demo `NATIONAL_DAY`; buổi 09-05 demo `WEEKEND_GIFT`. Đừng chuẩn bị
một kịch bản dùng chung cho cả hai buổi.

---

## 4. Trước mỗi buổi, kiểm 6 mục

1. Backend `200` trên `/health`.
2. Emulator chạy, app `com.cretona.app.debug` đã cài.
3. Worker Kaggle đang chạy, đã verify hash bundle.
4. Có ít nhất một project **đã completed** với video phát được, để dùng ở bước 5.
5. Tài khoản admin đăng nhập được.
6. Sự kiện định demo đang thực sự còn hiệu lực hôm đó.

Mục 4 là lưới an toàn: nếu GPU Kaggle không cấp phát hôm đó, bước 5 vẫn chứng
minh được hệ thống sinh ra video thật.

---

## 5. Khi có sự cố

- **Kaggle không cấp GPU:** vẫn demo đủ bước 2–7. Nói rõ hàng đợi đang chờ
  worker, đó là hành vi đúng của hệ thống, không phải lỗi.
- **Job thất bại:** mở màn hình credits cho người xem thấy khoản hoàn trả tự
  động. Một lần hoàn tiền đúng là bằng chứng tốt về độ tin cậy, không phải điều
  cần che.
- **Backend chết giữa chừng:** khởi động lại bằng lệnh ở mục 2; job đang chạy
  vẫn thuộc về worker qua lease trong database, không mất.

---

## 6. Ranh giới bằng chứng

Tài liệu này mô tả cách trình diễn, không phải bằng chứng đã trình diễn. Sau mỗi
buổi, ghi lại đã chạy live những bước nào, bước nào không và vì sao, vào một bản
ghi mới trong `docs/evidence/`. Không sửa ngược các bản ghi cũ.
