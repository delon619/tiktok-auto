# ================================================================
# PANDUAN SETUP LENGKAP
# TikTok Auto Upload System (Telegram → TikTok)
# ================================================================

## 📋 DAFTAR ISI
1. Arsitektur Sistem
2. Prerequisite
3. Setup Server Ubuntu VPS
4. Konfigurasi Telegram Bot
5. Login TikTok (Satu Kali)
6. Menjalankan Sistem
7. Monitoring & Maintenance
8. Troubleshooting
9. Best Practices Anti-Ban

---

## 1. 🏗️ ARSITEKTUR SISTEM

```
┌─────────────────┐
│   Telegram      │
│   (kamu kirim   │
│    video)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  Telegram Bot   │────▶│  SQLite Queue   │
│  (telegram_bot) │     │  (database.py)  │
└─────────────────┘     └────────┬────────┘
                                 │
                                 │ FIFO
                                 ▼
┌─────────────────┐     ┌─────────────────┐
│   Scheduler     │────▶│ TikTok Uploader │
│ (06:00,09:00,   │     │ (Playwright)    │
│  12:00)         │     └────────┬────────┘
└─────────────────┘              │
                                 ▼
                        ┌─────────────────┐
                        │     TikTok      │
                        │   (video live)  │
                        └─────────────────┘
```

---

## 2. 📦 PREREQUISITE

### Hardware
- VPS Ubuntu 20.04+ (minimal 2GB RAM, 2 CPU)
- Storage: 20GB+ (untuk video sementara)

### Software
- Python 3.10+
- Chromium (untuk Playwright)
- Akun Telegram
- Akun TikTok

---

## 3. 🖥️ SETUP SERVER UBUNTU VPS

### Opsi A: Jalankan Script Setup Otomatis

```bash
# Download dan jalankan script
chmod +x setup_ubuntu.sh
./setup_ubuntu.sh
```

### Opsi B: Setup Manual

```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Install Python
sudo apt install -y python3 python3-pip python3-venv

# 3. Install dependencies Playwright
sudo apt install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libatspi2.0-0 libgtk-3-0

# 4. Create project directory
mkdir -p ~/tiktok-auto
cd ~/tiktok-auto

# 5. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 6. Install Python packages
pip install python-telegram-bot==20.7 playwright==1.40.0 \
    apscheduler==3.10.4 python-dotenv==1.0.0 aiofiles==23.2.1 pytz==2024.1

# 7. Install Playwright browsers
playwright install chromium
playwright install-deps chromium

# 8. Create folders
mkdir -p videos cookies logs data
```

---

## 4. 🤖 KONFIGURASI TELEGRAM BOT

### Langkah 1: Buat Bot di Telegram
1. Buka Telegram, cari `@BotFather`
2. Kirim `/newbot`
3. Ikuti instruksi, beri nama bot
4. Simpan token yang diberikan (format: `123456789:ABCDEF...`)

### Langkah 2: Dapatkan User ID kamu
1. Buka `@userinfobot` di Telegram
2. Kirim pesan apa saja
3. Bot akan balas dengan User ID kamu

### Langkah 3: Edit file .env
```bash
nano .env
```

```env
# Paste token dari BotFather
TELEGRAM_BOT_TOKEN=123456789:ABCDEFghijklmnop...

# User ID kamu (opsional, untuk keamanan)
ALLOWED_USER_IDS=123456789

# Sisanya bisa default
TIKTOK_DEFAULT_CAPTION=#fyp #viral #foryou
TIMEZONE=Asia/Jakarta
POSTING_SCHEDULE=06:00,09:00,12:00
MAX_RETRY=1
HEADLESS_UPLOAD=true
```

---

## 5. 🔐 LOGIN TIKTOK (SATU KALI)

### ⚠️ PENTING: Login harus dilakukan di mesin dengan GUI

Karena login TikTok memerlukan interaksi browser (captcha, 2FA, dll),
kamu perlu melakukan login di mesin dengan GUI, lalu copy cookies ke VPS.

### Opsi A: Login di Komputer Lokal

```bash
# Di komputer lokal (Windows/Mac/Linux dengan GUI)
cd tiktok-auto
python tiktok_login.py

# Browser akan terbuka
# Login ke TikTok seperti biasa
# Setelah login berhasil, tekan ENTER di terminal
# Cookies akan tersimpan di cookies/tiktok_cookies.json

# Copy file cookies ke VPS
scp cookies/tiktok_cookies.json user@vps-ip:~/tiktok-auto/cookies/
```

### Opsi B: Login via VNC/Remote Desktop

Jika VPS punya GUI atau VNC:
```bash
# Di VPS dengan GUI
python tiktok_login.py
```

### Opsi C: Login via X11 Forwarding (Linux)

```bash
# Di komputer lokal
ssh -X user@vps-ip

# Di VPS
cd ~/tiktok-auto
source venv/bin/activate
python tiktok_login.py
```

### Verifikasi Cookies
```bash
# Cek apakah cookies valid
python tiktok_login.py --verify
```

---

## 6. 🚀 MENJALANKAN SISTEM

### Opsi A: Jalankan Manual (untuk testing)

```bash
cd ~/tiktok-auto
source venv/bin/activate

# Jalankan sistem
python main.py
```

### Opsi B: Jalankan sebagai Service (production)

```bash
# Enable dan start service
sudo systemctl enable tiktok-auto
sudo systemctl start tiktok-auto

# Cek status
sudo systemctl status tiktok-auto

# Lihat logs
sudo journalctl -u tiktok-auto -f
```

### Opsi C: Jalankan dengan Screen/Tmux

```bash
# Install screen
sudo apt install screen

# Buat session baru
screen -S tiktok

# Jalankan
cd ~/tiktok-auto
source venv/bin/activate
python main.py

# Detach: tekan Ctrl+A, lalu D
# Reattach: screen -r tiktok
```

---

## 7. 📊 MONITORING & MAINTENANCE

### Cek Status via Telegram Bot
- `/status` - Lihat statistik queue
- `/queue` - Lihat daftar video pending

### Cek Logs
```bash
# Lihat log aplikasi
tail -f ~/tiktok-auto/logs/app.log

# Lihat log service
sudo journalctl -u tiktok-auto -f
```

### Cek Database
```bash
cd ~/tiktok-auto
source venv/bin/activate

# Lihat status queue
python scheduler.py --status
```

### Manual Upload (testing)
```bash
# Upload video sekarang juga
python scheduler.py --run-now
```

---

## 8. 🔧 TROUBLESHOOTING

### Error: "Cookies file tidak ditemukan"
- Jalankan `python tiktok_login.py` untuk login
- Pastikan file `cookies/tiktok_cookies.json` ada

### Error: "Session expired"
- Cookies sudah kadaluarsa
- Jalankan `python tiktok_login.py` lagi
- TikTok mungkin mendeteksi aktivitas mencurigakan

### Error: "TELEGRAM_BOT_TOKEN tidak ditemukan"
- Cek file `.env`
- Pastikan format token benar

### Upload Timeout
- Video terlalu besar
- Koneksi lambat
- Coba kurangi ukuran video sebelum kirim

### Video Gagal Upload (Status Failed)
```bash
# Cek error di database
python -c "
from database import db
videos = db.get_all_pending()
for v in videos:
    if v['error_message']:
        print(f\"ID {v['id']}: {v['error_message']}\")
"
```

---

## 9. 🛡️ BEST PRACTICES ANTI-BAN

### 1. Jangan Login Terlalu Sering
- Login manual SEKALI, simpan cookies
- Gunakan cookies yang sama selama mungkin
- Hanya login ulang jika cookies expired

### 2. Human-like Behavior
- Sistem sudah menggunakan random delay
- Tidak ada spam upload (3x sehari cukup)
- Caption bervariasi

### 3. IP yang Konsisten
- Gunakan VPS dengan IP tetap
- Jangan ganti-ganti server
- IP Indonesia lebih aman untuk akun ID

### 4. Jangan Modifikasi Script Terlalu Agresif
- Jangan ubah delay menjadi terlalu cepat
- Jangan tambah jadwal posting terlalu banyak

### 5. Refresh Cookies Periodik
- Setiap 2-4 minggu, login ulang untuk refresh
- Set reminder untuk cek cookies

### 6. Gunakan Akun dengan History
- Jangan gunakan akun baru
- Akun yang sudah ada aktivitas lebih aman

### 7. Hindari VPN/Proxy
- Gunakan IP langsung VPS
- VPN bisa trigger security check

---

## 📁 STRUKTUR FOLDER FINAL

```
~/tiktok-auto/
├── .env                    # Environment variables
├── config.py               # Konfigurasi
├── database.py             # Database handler
├── logger_setup.py         # Logging setup
├── main.py                 # Entry point utama
├── requirements.txt        # Python dependencies
├── scheduler.py            # Scheduler posting
├── setup_ubuntu.sh         # Script setup
├── telegram_bot.py         # Telegram bot
├── tiktok_login.py         # Script login manual
├── tiktok_uploader.py      # TikTok uploader
├── cookies/
│   └── tiktok_cookies.json # Cookies TikTok
├── data/
│   └── videos.db           # SQLite database
├── logs/
│   └── app.log             # Application logs
└── videos/                 # Video storage
```

---

## 🎯 QUICK START CHECKLIST

- [ ] VPS Ubuntu ready
- [ ] Jalankan `setup_ubuntu.sh`
- [ ] Buat bot Telegram via @BotFather
- [ ] Edit `.env` dengan token Telegram
- [ ] Copy semua file Python ke VPS
- [ ] Login TikTok di mesin dengan GUI
- [ ] Copy `tiktok_cookies.json` ke VPS
- [ ] Jalankan `python main.py`
- [ ] Kirim video via Telegram untuk test
- [ ] Setup systemd untuk auto-start

---

## ❓ FAQ

**Q: Berapa lama cookies TikTok valid?**
A: Bervariasi, biasanya 2-4 minggu. Cek dengan `--verify` periodik.

**Q: Bisa multiple akun TikTok?**
A: Sistem ini untuk 1 akun. Untuk multiple, perlu modifikasi.

**Q: Video berapa besar yang bisa diupload?**
A: Tergantung limit Telegram (50MB untuk bot). TikTok hingga 287MB.

**Q: Kenapa harus login di mesin dengan GUI?**
A: TikTok punya captcha dan security check yang butuh interaksi visual.

**Q: Apakah aman?**
A: Gunakan dengan bijak. TikTok bisa mendeteksi automation.

---

Selamat menggunakan! 🎉
