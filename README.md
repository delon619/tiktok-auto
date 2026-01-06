# TikTok Auto Upload System

Sistem otomasi untuk upload video dari Telegram ke TikTok secara otomatis.

## 🎯 Fitur

- ✅ Telegram Bot untuk menerima video
- ✅ Queue database (SQLite) dengan FIFO
- ✅ Scheduler otomatis (06:00, 09:00, 12:00)
- ✅ Browser automation dengan Playwright
- ✅ Reuse cookies/session (login sekali)
- ✅ Error handling dengan retry
- ✅ Logging lengkap

## 🚀 Quick Start

### 1. Setup Environment

```bash
# Clone/copy project
cd tiktok-auto

# Install dependencies
pip install -r requirements.txt
playwright install chromium
```

### 2. Konfigurasi

```bash
# Copy template .env
cp .env.example .env

# Edit dengan token Telegram kamu
nano .env
```

### 3. Login TikTok (sekali)

```bash
python tiktok_login.py
# Login di browser yang terbuka, lalu tekan ENTER
```

### 4. Jalankan Sistem

```bash
python main.py
```

## 📖 Dokumentasi Lengkap

Lihat [SETUP_GUIDE.md](SETUP_GUIDE.md) untuk panduan lengkap.

## 📁 Struktur Project

```
tiktok-auto/
├── main.py              # Entry point
├── telegram_bot.py      # Telegram bot
├── tiktok_uploader.py   # TikTok uploader
├── tiktok_login.py      # Script login
├── scheduler.py         # Scheduler
├── database.py          # Database
├── config.py            # Konfigurasi
├── utils.py             # Utilities
├── cookies/             # Cookies TikTok
├── videos/              # Video storage
├── logs/                # Logs
└── data/                # Database
```

## 🔧 Commands

### Telegram Bot
- `/start` - Mulai bot
- `/status` - Statistik queue
- `/queue` - Lihat antrian
- `/help` - Bantuan

### CLI
```bash
# Status sistem
python utils.py --status

# Test koneksi TikTok
python utils.py --test-tiktok

# Reset video failed
python utils.py --reset-failed

# Manual posting
python scheduler.py --run-now
```

## ⚠️ Disclaimer

Gunakan dengan bijak. TikTok dapat mendeteksi aktivitas automation dan mungkin membatasi akun.
