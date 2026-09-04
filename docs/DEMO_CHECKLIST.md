# Cretona — checklist chạy hệ thống để demo

Đọc file này là đủ, không cần mở gì khác.

- Buổi đánh giá quá trình: **2026-09-03**
- Buổi demo cuối kì: **2026-09-05** (thứ Bảy) — vẫn là một buổi demo live,
  **không phải hạn nộp**.
- **Hạn nộp: 2026-09-09.** Sau buổi 09-05 mới soạn source code, báo cáo,
  video demo rồi nộp — không nộp ngay trong ngày 09-05.
- URL tunnel: **đổi mỗi lần khởi động lại `cloudflared`.** Đừng tin con số ghi
  ở đây — lấy URL thật từ cửa sổ cloudflared đang chạy (B3), rồi dùng nó cho
  B4 và cho lệnh kiểm ở PHẦN C.

## Chạy lệnh ở đâu

Terminal dùng là **Windows PowerShell**. Mỗi khối lệnh bên dưới đều ghi rõ thư
mục phải đứng. Chỉ có hai loại:

| Ký hiệu | Thư mục |
|---|---|
| **[GỐC]** | Thư mục clone chứa `gradlew`, `backend` và `app` |
| **[BẤT KỲ]** | Đứng đâu cũng được |

Mở PowerShell rồi vào thư mục gốc:

```powershell
$repoRoot = 'D:\1. UMT\3.5. PLUS26\Cretona'
Set-Location -LiteralPath $repoRoot
```

Trên máy Khoa, chỉ thay giá trị `$repoRoot` bằng đường dẫn clone của Khoa.

Kiểm tra đúng chỗ chưa — phải thấy `gradlew`, `local.properties`, `backend`:

```powershell
ls
```

---

## PHẦN A — ĐÃ XONG (2026-09-02)

Toàn bộ phần A là bằng chứng đã chấp nhận từ 02/09. Không áp migration, tạo lại
worker identity hay đổi credential nếu preflight không chỉ ra lỗi; đi thẳng
xuống PHẦN B.

| Việc | Kết quả |
|---|---|
| Cài app lên emulator | ✅ `com.cretona.app.debug` |
| Đặt mật khẩu DB role `cretona_kaggle_worker` | ✅ `ALTER ROLE` thành công |
| Ghép chuỗi kết nối session pooler | ✅ Kết nối được từ máy local |
| Notebook worker trên tài khoản Kaggle của Bruce | ✅ `bruce335/cretona-wan2-1` |
| Upload bundle `STEPS=25` + sửa hash | ✅ `decc5f5d…` (đã thay bằng bundle audio, xem B6) |
| Nhập 5 Kaggle Secrets | ✅ Cả 5 `Attached` |
| **Chạy 1 job thật** | ✅ **28,5 phút, hoàn tất** |
| **Thumbnail MIG-015** | ✅ **JPEG 40.696 B vào bucket `uploads`** |
| Prompt enhancement dùng Qwen thật | ✅ 20–30 giây |
| Video phát được trong app | ✅ |

### Số liệu job thật (project `46b6d55d…`)

```
provider   : kaggle, 4 giây, 16:9
status     : completed, 100%
video.mp4  : 405.459 B  (bucket videos)
thumbnail  :  40.696 B  (bucket uploads)
ledger     : đúng 1 dòng −1 credit, không hoàn tiền
tổng       : 1711 giây = 28,5 phút (lần đầu, có tải 22,7 GB model)
```

Chi tiết: [MIG015_FIRST_THUMBNAIL_JOB_2026-09-02.md](evidence/MIG015_FIRST_THUMBNAIL_JOB_2026-09-02.md)

### Hai lỗi đã sửa sau job đó

**Thẻ tiến trình đứng giữa chừng.** Polling chỉ phủ 10 phút trong khi job mất
28,5 phút, nên thẻ đóng băng ở 21% rồi hiện *"Generation is still running"*.
Ngân sách polling nâng lên 40 phút, và thẻ có thêm nút **🔄 Refresh** kéo trạng
thái về đồng thời nối lại polling.

**Admin tự hạ quyền / tự khoá được chính mình.** Cả hai giờ bị chặn ở view model
và ẩn nút trên UI — không thể tự khôi phục vì màn admin console gán đúng quyền
vừa mất.

Android: **129 test, 0 fail** (trước là 126).

### Đóng băng cho buổi 05/09

- Giữ `STEPS = 25` và worker SHA-256 `04d3e70b…` — bản có audio. Hai job thật
  đã chạy hết đường ống với bản này ngày 03/09
  ([bằng chứng](evidence/EXP006_FIRST_AUDIO_JOBS_2026-09-03.md)); không đổi
  bundle nữa.
- Không chuyển sang Wan2.2. EXP-007 chưa từng chạy trên GPU thật.
- Clip có audio nặng 2,9–5,1 MB thay vì ~0,4 MB. Qua tunnel Cloudflare thì
  video sẽ mất thêm vài giây mới bắt đầu phát — đó là hành vi đã biết, không
  phải lỗi.
- Chất lượng 25 bước chưa được chấm đối chiếu với 50 bước; mô tả đúng là
  **demo-adequate, quality unverified**.

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

**[BẤT KỲ]** — mở **cửa sổ PowerShell mới của chính bạn** rồi gõ tay:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

Nó in ra URL dạng `https://xxx-yyy-zzz.trycloudflare.com`. **Chép lại URL đó.**
Để cửa sổ này mở suốt buổi.

> **Phải tự gõ trong cửa sổ của bạn.** Đừng để script hay công cụ nào bật hộ:
> tiến trình con sinh ra từ một phiên khác sẽ bị dọn theo khi phiên đó kết
> thúc, và tunnel chết lặng lẽ. Đã xảy ra ngày 03/09 — app báo *"The server
> could not complete the request"* trong khi backend vẫn trả `200`.

> **Tunnel chết KHÔNG giết job đang sinh video.** Worker Kaggle nói chuyện
> thẳng với Supabase, không đi qua tunnel. Mất kết nối giữa buổi thì cứ dựng
> lại B3→B5, video vẫn đang được tạo.

### B4. Dán URL mới vào `local.properties` (30 giây)

Mở file `local.properties` ngay trong **[GỐC]**, tìm khóa
`cretona.api.baseUrl.debug` (không dựa vào số dòng) và thay URL. Giữ nguyên dấu
`\` trước mỗi `:`:

```
cretona.api.baseUrl.debug=https\://URL-MOI-O-DAY/api/v1/
```

### B4b. Bật emulator (1 phút)

Bỏ qua nếu demo bằng **điện thoại thật** — chỉ cần cắm USB và bật USB debugging.

**[BẤT KỲ]** — mở **cửa sổ PowerShell mới**:

```powershell
Start-Process "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe" -ArgumentList '-avd','Pixel_10_Pro'
```

Chờ tới lúc sẵn sàng rồi mới sang B5:

```powershell
$adb="$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"; $t0=Get-Date; for($i=0;$i -lt 90;$i++){ if("$(& $adb shell getprop sys.boot_completed 2>$null)".Trim() -eq '1'){ "EMULATOR SAN SANG sau $([int]((Get-Date)-$t0).TotalSeconds)s"; break }; Start-Sleep -Seconds 5 }
```

Boot thường mất ~30 giây. Chưa thấy `EMULATOR SAN SANG` thì đừng chạy B5, vì
`adb install` sẽ báo không tìm thấy thiết bị.

Nếu emulator dở chứng (treo, Google Play Services crash), cold boot:

```powershell
Start-Process "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe" -ArgumentList '-avd','Pixel_10_Pro','-no-snapshot-load'
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

**Ở đâu:** mở notebook riêng
[`bruce335/cretona-wan2-1`](https://www.kaggle.com/code/bruce335/cretona-wan2-1/edit).
Notebook này vẫn giữ các cell EXP-005 cũ làm lịch sử thử nghiệm.

Kiểm 2 thứ trước khi chạy, ở panel phải → **Settings**:

- **Accelerator** = `GPU T4 x2`
- **Internet** = `On`

Cuộn xuống **cell code cuối cùng**, bắt đầu bằng
`from kaggle_secrets import UserSecretsClient` và kết thúc bằng
`!python backend/kaggle_worker.py`. **Chỉ bấm nút chạy của cell cuối; tuyệt đối
không bấm Run All**, vì Run All sẽ chạy lại toàn bộ EXP-005. Để tab mở suốt
buổi; cell cuối phải tiếp tục chạy để phục vụ hàng đợi.

> **Dataset phải có `cretona-kaggle-worker-AUDIO.zip`.** Cell lọc ứng viên
> theo hash, nên nếu chỉ attach bundle silent cũ thì nó dừng với
> `matchingCount: 0` — đó là hành vi đúng. File nằm ở
> **[GỐC]**`\_test\cretona-kaggle-worker-AUDIO.zip`.
>
> Cell phải hiển thị `audio: 1`, rồi `OK backend/kaggle_worker.py` và
> `OK backend/requirements-kaggle.txt`. Hash worker trong cell phải bắt đầu bằng
> `04d3e70b`. Nếu khác hoặc cell kết thúc ngay, dừng; không sửa hash để ép chạy
> một bundle khác.

### B7. Hâm nóng model LLM (25 giây)

**[BẤT KỲ]**

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:11434/api/generate -Method Post -ContentType 'application/json' -Body (@{ model='qwen3.5:2b'; prompt='warm'; stream=$false; keep_alive='4h'; options=@{ num_predict=8 } } | ConvertTo-Json) -TimeoutSec 180 | Out-Null; (Invoke-RestMethod http://127.0.0.1:11434/api/ps).models.name
```

In ra `qwen3.5:2b` là xong. Đây là model **máy này** thực sự chạy:
`backend/.env` đặt `CRETONA_OLLAMA_MODEL=qwen3.5:2b`, đè lên giá trị mặc định
`qwen3:4b-instruct-2507-q4_K_M` trong `config.py`. Đừng warm model mặc định đó
— máy này chưa pull nó về, Ollama sẽ trả `model not found`.

Trước khi khởi động B2, `backend/.env` phải đặt
`CRETONA_PROMPT_LLM_PROVIDER=ollama`; nếu là `deterministic`, Enhance đang dùng
fallback có nhãn chứ không phải LLM thật.

> **Đừng dùng `curl.exe` cho lệnh này.** Windows PowerShell 5.1 không gửi được
> JSON qua `curl.exe`: viết `\"` thì nó gửi luôn cả dấu `\`, viết nháy đơn thì
> nó nuốt mất nháy kép bên trong. Cả hai cách đều bị Ollama trả
> `invalid character ... looking for beginning of object key string`.
> `Invoke-RestMethod` truyền chuỗi thẳng vào .NET nên không dính.

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
try { (Invoke-WebRequest https://URL-TUNNEL-CUA-BAN/health -TimeoutSec 12 -UseBasicParsing).StatusCode } catch { "CHET: $($_.Exception.Message)" }
```

Phải ra `200`. Ra `530`, `502` hoặc không phân giải được tên miền →
cloudflared chết → quay lại B3, lấy URL mới, rồi B4 → B5.

**2. Model LLM còn nóng?**

**[BẤT KỲ]**

```powershell
(Invoke-RestMethod http://127.0.0.1:11434/api/ps).models.name
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

### Demo image-to-video (I2V)

**Kaggle · Wan2.1 KHÔNG nhận ảnh.** Wan2.1 T2V 1.3B là text-only. Đính ảnh rồi
chọn Kaggle sẽ bị backend từ chối với `PROVIDER_ERROR` — đó là hành vi **đúng**
theo `SRS.md` FR-GEN-006, không phải lỗi.

Provider nào nhận ảnh:

| Engine Tier | Nhận ảnh | Ghi chú |
|---|---|---|
| 🎭 Demo Sample (`fake`) | ❌ | Clip test dựng sẵn |
| 🖼️ AI image + motion (`cloud`) | ✅ | Gọi `text.pollinations.ai`, miễn phí, **cần mạng** |
| 💻 Local (`local`) | ✅ | ffmpeg trên máy, **không cần mạng, không cần key** |
| 🎬 Kaggle · Wan2.1 | ❌ | Text-only |

**Demo I2V nên dùng `Local`** — không phụ thuộc dịch vụ ngoài, dùng thẳng ảnh
bạn upload làm khung nền, chạy trong vài giây.

**Nói thật khi trình bày:** `cloud` và `local` lấy **một ảnh tĩnh rồi áp chuyển
động camera bằng ffmpeg**. Đó không phải mô hình sinh video theo thời gian như
Wan2.1. Trình bày chúng như "AI video generation" cùng hạng với Wan2.1 là chỗ
giám khảo bắt lỗi được. Cách nói đúng: *ba tier khác nhau, chỉ Kaggle chạy mô
hình temporal thật.*

Nếu thầy hỏi "sao ảnh không ra video AI thật": vì mô hình temporal miễn phí duy
nhất chạy được trên Kaggle là Wan2.1 T2V, và nó text-only. Đây là quyết định có
ghi trong `DECISIONS.md`, không phải thiếu sót.

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
| Job 4 giây @ 25 steps, cold + tải model | 28,5 phút | Đo 2026-09-02 |
| Job Kaggle live khác @ 25 steps | 25,9 phút end to end | Đo 2026-09-03 |

### Ranh giới chưa được nghiệm thu

1. Thời gian warm-cache chưa được đo riêng; 25,9 phút là end-to-end, không phải
   benchmark warm được cô lập.
2. Chất lượng 25 bước chưa được chấm số so với 50 bước.
3. Audio chỉ qua EXP-006 cô lập; chưa có worker-to-Android E2E.
4. Wan2.2 image-to-video EXP-007 chưa chạy trên Kaggle GPU.

Các mục này không phải release gate. Trong buổi demo chỉ cần kiểm API Enhance
trả `usedFallback=false` để chứng minh Qwen đang được gọi qua FastAPI.
