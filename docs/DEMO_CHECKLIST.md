# Cretona — checklist chạy hệ thống để demo

Đọc file này là đủ, không cần mở gì khác.

- Buổi đánh giá quá trình: **2026-09-03**
- Buổi cuối kì: **2026-09-05** (thứ Bảy)
- URL tunnel hiện tại: `https://firewall-inches-rankings-over.trycloudflare.com`
  **URL này đổi mỗi lần khởi động lại `cloudflared`.**

## Chạy lệnh ở đâu

Terminal dùng là **Windows PowerShell**. Mỗi khối lệnh bên dưới đều ghi rõ thư
mục phải đứng. Chỉ có hai loại:

| Ký hiệu | Thư mục |
|---|---|
| **[GỐC]** | `C:\Users\M15R6\AndroidStudioProjects\Final_Plus\Cretona` |
| **[BẤT KỲ]** | Đứng đâu cũng được |

Mở PowerShell rồi vào thư mục gốc:

```powershell
cd C:\Users\M15R6\AndroidStudioProjects\Final_Plus\Cretona
```

Kiểm tra đúng chỗ chưa — phải thấy `gradlew`, `local.properties`, `backend`:

```powershell
ls
```

---

## PHẦN A — TỐI NAY (2026-09-02)

Backend, cloudflared và Ollama đang chạy sẵn. APK đã khớp URL hiện tại.

### A1. Cài app (1 phút)

**[GỐC]**

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" install -r .\app\build\outputs\apk\debug\app-debug.apk
```

Package id là `com.cretona.app.debug` — chú ý hậu tố `.debug`.

### A2. Upload bundle mới lên Kaggle (5 phút)

1. Vào <https://www.kaggle.com/datasets> → **New Dataset**
2. Upload `_test/cretona-kaggle-worker-STEPS25.zip` (7.222 B) → để **Private**
3. Mở <https://www.kaggle.com/code/bruce335/cretona-wan2-1>
4. **Add Input** → chọn dataset vừa tạo
5. **Xoá input bundle cũ** (bản `ee339afd`)

### A3. Sửa hash trong notebook (2 phút)

Tìm cell có `expected = {`, thay toàn bộ bằng:

```python
expected = {
    "backend/kaggle_worker.py":
        "decc5f5ddddfc0af515ee3cce045e1ce97742af854303afa4c24bba2d97e3823",
    "backend/requirements-kaggle.txt":
        "46263bf0527742dde0d98a5da163afc1646a53b5f6de545ad3e94da43c99c669",
}
```

Notebook sẽ **từ chối bundle cũ** nếu quên bước này — đó là hành vi đúng.

### A4. Bật worker (15 phút chuẩn bị)

Trong notebook: **Settings → Accelerator → GPU T4 x2**, **Internet → On** → **Run All**

Cell cuối phải là `!python backend/kaggle_worker.py` (không có `--once`).

### A5. Nộp 1 job thật (20 phút chờ)

Trên app:

1. Đăng nhập
2. Bấm **Enhance** — nếu ra một đoạn dài, mô tả điện ảnh thì Qwen đang chạy thật.
   Nếu ra câu ngắn cụt thì đang là fallback, xem mục D.
3. Provider **Kaggle · Wan2.1** → **4 giây** → chỉ nhập text, không đính ảnh
4. **Generate**

**Bước này kiểm 3 thứ chưa ai biết:**

| Kiểm cái gì | Đạt là thế nào |
|---|---|
| Tốc độ thật ở 25 steps | Xong trong ~20 phút |
| Chất lượng ở 25 steps | Xem clip, chấp nhận được không |
| Đường thumbnail MIG-015 | Thẻ trong History có ảnh preview |

> **Nếu chất lượng tệ:** sửa `STEPS = 25` về `50` ở `backend/kaggle_worker.py`
> dòng 36, dựng lại bundle, upload lại Kaggle. Clip 4s khi đó mất ~39 phút.
> **Phải quyết tối nay** — sáng thứ Bảy mới phát hiện là hết đường lùi.

---

## PHẦN B — TRƯỚC MỖI BUỔI DEMO (~35 phút)

Làm đúng thứ tự. Bước B6 lâu nhất, làm sớm nhất nếu có thể.

### B1. Ollama — KHÔNG cần bật

Ollama tự khởi động cùng Windows (có `Ollama.lnk` trong Startup folder). Kiểm:

**[BẤT KỲ]**

```powershell
Get-Process ollama -ErrorAction SilentlyContinue
```

Có kết quả là đang chạy. Nếu trống → mở app **Ollama** từ Start Menu.

### B2. Backend (20 giây)

**[GỐC]**

```powershell
.\scripts\run-fastapi.ps1 -SkipPreflight
```

`-SkipPreflight` **bắt buộc**: thiếu nó, profiler ghi đè
`CRETONA_DEFAULT_VIDEO_PROVIDER` trong `.env` mỗi lần khởi động.

### B3. Cloudflared (15 giây)

**Nếu laptop chưa hề tắt từ tối qua và cửa sổ cloudflared vẫn mở → bỏ qua B3,
B4, B5, dùng luôn APK cũ.**

Nếu đã tắt máy:

**[BẤT KỲ]** — mở **cửa sổ PowerShell mới**, vì lệnh này chiếm cửa sổ cho tới
khi tắt.

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

Nó in ra URL dạng `https://xxx-yyy-zzz.trycloudflare.com`. **Chép lại URL đó.**
Để cửa sổ này mở suốt buổi.

### B4. Dán URL mới vào `local.properties` (30 giây)

Mở file `C:\Users\M15R6\AndroidStudioProjects\Final_Plus\Cretona\local.properties`, sửa **dòng 13**.
Giữ nguyên dấu `\` trước mỗi `:`:

```
cretona.api.baseUrl.debug=https\://URL-MOI-O-DAY/api/v1/
```

### B5. Build lại và cài APK (3 phút)

**[GỐC]**

```powershell
.\gradlew :app:assembleDebug
```

Rồi, vẫn **[GỐC]**:

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" install -r .\app\build\outputs\apk\debug\app-debug.apk
```

### B6. Bật worker Kaggle (10–18 phút — LÂU NHẤT)

Mở <https://www.kaggle.com/code/bruce335/cretona-wan2-1> → **Run All**.
Để tab mở suốt buổi.

### B7. Hâm nóng model LLM (25 giây)

**[BẤT KỲ]**

```powershell
curl.exe -s http://127.0.0.1:11434/api/generate -d "{\"model\":\"qwen3.5:2b\",\"prompt\":\"warm\",\"stream\":false,\"options\":{\"num_predict\":8},\"keep_alive\":\"4h\"}"
```

Bỏ bước này thì lần **Enhance** đầu tiên mất hơn 100 giây rồi rơi về fallback.

### B8. Chuẩn bị sẵn 1 video đã xong

Mở History, xác nhận có ít nhất 1 video phát được. Dùng nó ở bước C5 để không
phải chờ 20 phút giữa buổi.

---

## PHẦN C — LÚC DEMO

### Chạy 3 lệnh này TRƯỚC KHI mở app (30 giây)

**1. Backend + tunnel còn sống?**

**[BẤT KỲ]**

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" https://URL-TUNNEL-CUA-BAN/health
```

Phải ra `200`. Ra `000` hoặc `502` → cloudflared chết → quay lại B3.

**2. Model LLM còn nóng?**

**[BẤT KỲ]**

```powershell
curl.exe -s http://127.0.0.1:11434/api/ps
```

Phải thấy `qwen3.5:2b`. Trống → chạy lại B7.

**3. Worker Kaggle còn chạy?**

Nhìn tab Kaggle — cell cuối phải đang chạy (có vòng xoay), không phải đã dừng.

**Cả 3 xanh mới mở app.**

### Kịch bản demo

| # | Việc | Thời gian |
|---|---|---|
| C1 | Nộp 1 job Kaggle 4 giây **ngay đầu buổi** | 1 phút |
| C2 | Đăng ký tài khoản mới tại chỗ | 2 phút |
| C3 | Nhận thưởng sự kiện | 1 phút |
| C4 | Bấm **Enhance** — Qwen thật | ~37 giây |
| C5 | Tạo video provider **Mock** — xem trọn vòng đời job | 1 phút |
| C6 | Mở video đã completed → phát | 2 phút |
| C7 | Save vào máy + Share | 1 phút |
| C8 | Đăng nhập admin → dashboard | 3 phút |
| C9 | Quay lại job C1 xem tiến trình | 1 phút |

**C5 quan trọng hơn vẻ ngoài của nó:** nó cho người xem thấy trọn vẹn một vòng
đời tạo video trong 1 phút, thứ mà đường Kaggle không kịp trong buổi họp. Đây là
provider thật trong hệ thống, không phải mock ghép vào để diễn.

### Sự kiện dùng buổi nào

| Sự kiện | 03/09 | 05/09 (thứ Bảy) |
|---|---|---|
| `NATIONAL_DAY` +20 | **Dùng cái này** | Đã hết hạn 04/09 00:00 |
| `WEEKEND_GIFT` | Không hoạt động | **Dùng cái này** |
| `HOT_HOURS` | Chỉ 20:00–22:00 | Chỉ 20:00–22:00 |

---

## PHẦN D — KHÔNG ĐƯỢC LÀM / KHI HỎNG

### 4 điều không được làm suốt buổi

1. **Không đóng cửa sổ `cloudflared`** → URL đổi, app mất kết nối, phải làm lại
   B3→B5
2. **Không thoát Ollama ở khay hệ thống** → Enhance rơi về fallback
3. **Không để laptop sleep hoặc tắt** → backend chết
4. **Không dùng prompt có hướng hay chuyển động camera** — ví dụ "bay từ trái
   sang phải", "camera xoay quanh", "camera tiến tới". Model bỏ qua cả hai trong
   toàn bộ 4 clip thực nghiệm. Chiếu ra ngược hướng là tự nộp lỗi cho thầy. Chỉ
   tả **chủ thể, bối cảnh, ánh sáng, phong cách**.

### Khi hỏng giữa buổi

| Hiện tượng | Làm gì |
|---|---|
| App báo lỗi mạng | Chạy lệnh C1. Ra `000` → cloudflared chết → B3→B5 |
| Enhance trả câu cụt | Model nguội, chạy B7. Nói thẳng đây là fallback có nhãn |
| Kaggle không cấp GPU | Vẫn demo C2→C8 bình thường. Job nằm chờ worker là hành vi **đúng**, không phải lỗi |
| Job thất bại | Mở màn hình Credits cho xem khoản hoàn trả tự động. Một lần hoàn tiền đúng là bằng chứng tốt về độ tin cậy |
| Backend chết | Chạy lại B2. Job đang chạy vẫn thuộc worker qua lease trong database, không mất |

---

## PHẦN E — SỐ LIỆU ĐÃ ĐO

| Việc | Thời gian | Nguồn |
|---|---|---|
| Backend khởi động | 7–19 giây | Đo 3 lần |
| Mở tunnel + có URL | ~15 giây | Đo |
| `/health` qua tunnel | 2 giây | Đo |
| Build APK debug | 2 phút 10 | Đo |
| Enhance, model đã nóng | 37 giây | Đo |
| Enhance, model nguội | >100 giây | Đo |
| Hâm nóng model | 23 giây | Đo |
| Kaggle xin GPU | 1–3 phút | Ước tính |
| Kaggle `pip install` | 3–5 phút | Ước tính |
| Kaggle nạp model Wan2.1 | 5–10 phút | Ước tính |
| Sinh clip 4 giây @ 25 steps | ~20 phút | **Ngoại suy, chưa đo** |

### Hai thứ chưa ai kiểm chứng

1. **`STEPS = 25` chưa từng chạy trên GPU thật.** Con số 20 phút là ngoại suy từ
   một điểm đo duy nhất. Chất lượng ở 25 bước cũng chưa ai xem.
2. **`usedFallback=false` chưa xác nhận qua API thật.** Mới chỉ chứng minh Ollama
   trả lời đúng trong 37 giây khi gọi trực tiếp.

Bước **A5** tối nay trả lời cả hai.
