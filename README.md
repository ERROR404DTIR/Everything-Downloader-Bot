# 🤖 Everything Downloader Bot — همه‌چیز دانلودر (بله)

یک ربات فارسی برای پیام‌رسان **بله (Bale)** که هر لینکی را با `yt-dlp` دانلود می‌کند و برای کاربر می‌فرستد.

* ساخته‌شده با [balethon](https://github.com/Balethon/Balethon) (کتابخانهٔ ربات بله)
* موتور دانلود: [yt-dlp](https://github.com/yt-dlp/yt-dlp)
* دانلود مستقیم فایل‌ها با `aiohttp` (و `requests` به‌عنوان پشتیبان)
* تنظیمات از طریق فایل سادهٔ `config.json`

---

## ✨ امکانات

| امکان | توضیح |
| --- | --- |
| 🎬 دانلود از سایت‌ها | یوتیوب، اینستاگرام، تیک‌تاک، توییتر/X، آپارات، ساندکلود، ویمیو، توییچ و هر سایتی که yt-dlp پشتیبانی می‌کند |
| 📄 لینک مستقیم فایل | `mp4`، `mkv`، `mp3`، `pdf`، `zip`، `jpg`، `apk` و… با دانلود استریمی |
| 🎚 انتخاب کیفیت | بهترین کیفیت، `1080p`، `720p`، `480p`، `360p` و «فقط صدا (MP3)» |
| 📊 نوار پیشرفت | درصد، حجم، سرعت و زمان باقی‌مانده در حین دانلود |
| 📤 ارسال هوشمند | ویدیو با `sendVideo`، صدا با `sendAudio`، عکس با `sendPhoto` و بقیه با `sendDocument` |
| 📨 دریافت فایل از کاربر | فایلی که برای ربات می‌فرستید با نام اصلی به‌صورت سند برگردانده می‌شود |
| ⚠️ کنترل حجم | سقف حجم قابل تنظیم است (بله حداکثر ۵۰ مگابایت اجازه می‌دهد) |
| 🚦 مدیریت بار | محدودیت دانلود هم‌زمان برای هر کاربر + امکان لغو با دکمه یا `/cancel` |
| 🧹 نظافت خودکار | فایل‌های موقت بعد از ارسال پاک می‌شوند (قابل غیرفعال‌سازی) |

---

## 🚀 نصب و راه‌اندازی

### ۱) پیش‌نیازها

* Python **3.9+**
* `ffmpeg` (اختیاری ولی **به‌شدت توصیه‌شده**): برای ادغام ویدیو+صدا در کیفیت‌های بالا و تبدیل به MP3

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y python3 python3-venv ffmpeg

# macOS
brew install python ffmpeg

# Windows
# ffmpeg را از https://ffmpeg.org/download.html بگیرید و در PATH قرار دهید
```

### ۲) گرفتن توکن ربات

1. در بله به [@botfather](https://ble.ir/botfather) پیام بدهید.
2. با `/newbot` یک ربات بسازید.
3. توکنی مثل `123456789:abcdIuZmK5qNEm2A1BhUaAg7MPJv1O9KCcBQB2ro` می‌گیرید.

### ۳) نصب پروژه

```bash
git clone https://github.com/ERROR404DTIR/Everything-Downloader-Bot.git
cd Everything-Downloader-Bot

python3 -m venv .venv
source .venv/bin/activate        # ویندوز: .venv\Scripts\activate
pip install -r requirements.txt
```

### ۴) وارد کردن توکن در `config.json`

```json
{
  "token": "123456789:abcdIuZmK5qNEm2A1BhUaAg7MPJv1O9KCcBQB2ro"
}
```

تنها کلید **الزامی** همین `token` است؛ بقیهٔ کلیدها اختیاری‌اند و اگر نباشند مقدار پیش‌فرض می‌گیرند.
همین فایل `config.json` در ریشهٔ پروژه به‌صورت آماده قرار دارد؛ فقط جای‌نگهدار را با توکن خودتان عوض کنید.

### ۵) اجرا

```bash
python main.py
```

یا با مسیر دلخواه برای فایل تنظیمات:

```bash
python main.py --config /path/to/config.json
```

برای بررسی درستی تنظیمات بدون اجرای ربات:

```bash
python main.py --check
```

---

## ⚙️ تنظیمات (`config.json`)

| کلید | پیش‌فرض | توضیح |
| --- | --- | --- |
| `token` | — | **الزامی**. توکن ربات از @botfather |
| `base_url` | `https://tapi.bale.ai` | آدرس API بله (اگر از پروکسی/سرور واسط استفاده می‌کنید تغییر دهید) |
| `download_dir` | `downloads` | پوشهٔ موقت دانلودها |
| `max_file_size_mb` | `50` | سقف حجم فایل برای ارسال؛ بیشتر از ۵۰ پذیرفته نمی‌شود |
| `max_concurrent_downloads` | `3` | حداکثر دانلود هم‌زمان برای هر کاربر |
| `allow_playlists` | `false` | اجازهٔ دانلود پلی‌لیست |
| `max_playlist_items` | `10` | حداکثر تعداد آیتم‌های پلی‌لیست |
| `cookies_file` | `null` | مسیر فایل `cookies.txt` برای ویدیوهای نیازمند ورود |
| `ffmpeg_location` | `null` | مسیر ffmpeg اگر در `PATH` نیست |
| `proxy` | `null` | پروکسی برای API بله؛ مثل `http://127.0.0.1:8080` |
| `request_timeout` | `600` | مهلت درخواست‌های API (ثانیه) |
| `log_level` | `INFO` | سطح لاگ |
| `keep_downloaded_files` | `false` | نگه‌داشتن فایل‌ها بعد از ارسال (برای دیباگ) |
| `job_ttl_seconds` | `1800` | مدت اعتبار دکمه‌های انتخاب کیفیت |
| `ytdlp_options` | `{}` | هر گزینهٔ دلخواه yt-dlp به‌صورت JSON (مثل `{"proxy": "socks5://…"}`) |

> 🔐 file `.gitignore` طوری تنظیم شده که فایل‌های موقت و لاگ‌ها در گیت ثبت نشوند؛ توکن هم فقط در `config.json` خودتان است. اگر نمی‌خواهید توکن در گیت برود، فایل را به `config.local.json` منتقل کنید و با `--config config.local.json` اجرا کنید.

---

## 💬 طرز کار ربات

```
کاربر: /start
ربات : سلام 👋 به «همه‌چیز دانلودر» خوش آمدید!
        لطفاً لینک چیزی که می‌خواهید دانلود شود را وارد کنید.

کاربر: https://www.youtube.com/watch?v=…
ربات : 🔍 لینک در حال بررسی است…
        🎬 عنوان ویدیو
        👤 کانال
        ⏱ 3:24
        📦 حجم تقریبی: 24.1 MB
        کیفیت را انتخاب کنید: [بهترین] [1080p] [720p] [480p] [360p] [فقط صدا] [لغو]

کاربر: (انتخاب 720p)
ربات : ▰▰▰▰▰▱▱▱▱▱ 52%  📦 12.3 MB از 24.1 MB  ⚡ 1.2 MB/s  ⏱ 0:09
        ⬇️ فایل دانلود می‌شود و سپس برای کاربر ارسال می‌گردد.
```

* اگر لینک **فقط یک خروجی** داشته باشد (فایل مستقیم، عکس، فایل صوتی) ربات بدون پرسش شروع می‌کند.
* اگر لینک **صفحهٔ HTML** باشد و فایلی برای دانلود نداشته باشد، پیام «پشتیبانی نمی‌شود» می‌گیرید.
* فایلی که خودتان برای ربات بفرستید (تا ۲۰ مگابایت) با نام اصلی به‌صورت سند برمی‌گردد.

### دستورها

| دستور | کار |
| --- | --- |
| `/start` | خوش‌آمدگویی و شروع |
| `/help` | راهنما |
| `/about` | دربارهٔ ربات |
| `/cancel` | لغو کار در حال انجام یا انتخاب کیفیت |
| `/download <لینک>` | شروع دانلود با لینک (اختیاری) |

---

## 🧪 تست‌ها

```bash
pip install pytest pytest-asyncio
python -m pytest -q
```

تست‌ها شامل:

* تست واحد ابزارها و اعتبارسنجی `config.json`
* تست موتور دانلود با **سرور HTTP محلی** (فایل مستقیم، HEAD ناموجود، محدودیت حجم، HTML، ۴۰۴)
* تست هندلرها با کلاینت جعلی (شروع، راهنما، جریان کیفیت، لغو، فایل ورودی)
* تست **end-to-end** با یک سرور شبیه‌ساز API بله: بررسی `base_url`، `getUpdates`، آپلود multipart و ارسال سند

```
74 passed
```

---

## 🐳 اجرا با Docker

```bash
docker build -t everything-downloader-bot .
docker run --rm -v "$PWD/config.json:/app/config.json:ro" \
               -v "$PWD/downloads:/app/downloads" \
               everything-downloader-bot
```

## 🔁 اجرای همیشگی با systemd

```ini
# /etc/systemd/system/everything-downloader-bot.service
[Unit]
Description=Everything Downloader Bot (Bale)
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/Everything-Downloader-Bot
ExecStart=/opt/Everything-Downloader-Bot/.venv/bin/python main.py
Restart=always
RestartSec=5
User=botuser

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now everything-downloader-bot
```

---

## ⚠️ محدودیت‌های بله

| مورد | سقف |
| --- | --- |
| دریافت فایل از سرورهای بله (`getFile`) | ۲۰ مگابایت |
| ارسال فایل توسط ربات (`sendDocument`/`sendVideo`…) | ۵۰ مگابایت |
| ارسال با لینک (URL) | ۲۰ مگابایت برای انواع محتوا، ۵ مگابایت برای تصویر |

ربات قبل و در حین دانلود این محدودیت‌ها را بررسی می‌کند و به‌جای خطای خام، پیام فارسی مناسب نشان می‌دهد.

> 💡 اگر فایل بزرگ‌تری می‌خواهید، کافی است نسخهٔ محلی سرور Bot API بله را بالا بیاورید و `base_url` را در `config.json` به آن تغییر دهید.

---

## 📁 ساختار پروژه

```
Everything-Downloader-Bot/
├── main.py                  # اجراکننده: python main.py
├── config.json              # توکن و تنظیمات (فقط token الزامی است)
├── requirements.txt
├── bot/
│   ├── main.py              # ساخت Client، اجرای ربات، CLI
│   ├── config.py            # بارگذاری و اعتبارسنجی config.json
│   ├── downloader.py        # yt-dlp + aiohttp (تحلیل لینک، دانلود، پیشرفت)
│   ├── handlers.py          # دستورها، لینک‌ها، دکمه‌های کیفیت، فایل‌های ورودی
│   ├── sender.py            # انتخاب متد ارسال و آپلود فایل به بله
│   ├── jobs.py              # مدیریت jobها، لغو و محدودیت هم‌زمانی
│   ├── ui.py                # تمام متن‌ها و کیبوردهای فارسی
│   ├── models.py            # dataclassهای مشترک
│   ├── errors.py            # خطاهای کاربرپسند فارسی
│   ├── utils.py             # استخراج لینک، نام فایل امن، فرمت حجم/زمان
│   └── logger.py
├── tests/
└── .github/workflows/tests.yml
```

---

## 🩺 رفع اشکال

| مشکل | راه‌حل |
| --- | --- |
| `توکن وارد شده معتبر نیست` | توکن باید شکل `123456789:abc…` داشته باشد؛ از @botfather دوباره بگیرید |
| `فایل تنظیمات پیدا نشد` | `config.json` را در ریشهٔ پروژه بسازید یا با `--config` مسیر بدهید |
| کیفیت ۱۰۸۰p خراب/بدون صدا است | `ffmpeg` نصب نیست؛ نصبش کنید یا کیفیت پایین‌تر انتخاب کنید |
| ویدیوی یوتیوب دانلود نمی‌شود | `pip install -U yt-dlp` — یوتیوب تغییر می‌کند و yt-dlp باید به‌روز باشد |
| `ارسال فایل به بله ناموفق بود` | حجم فایل بیش از ۵۰ مگابایت است؛ کیفیت پایین‌تر را امتحان کنید |
| ویدیوی خصوصی/سن‌دار | نیاز به `cookies_file` دارد (فایل `cookies.txt` از مرورگر) |

---

## 📄 لایسنس

MIT — استفاده، تغییر و توزیع آزاد است. لطفاً حقوق سرویس‌های مبدأ و قوانین کپی‌رایت را رعایت کنید.
