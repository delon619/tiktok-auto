# Struktur Project TikTok Auto

```
tiktok-auto/
├── .env                    # Environment variables (JANGAN commit ke git)
├── .env.example            # Template environment variables
├── requirements.txt        # Python dependencies
├── config.py               # Konfigurasi aplikasi
├── database.py             # Database handler (SQLite)
├── telegram_bot.py         # Telegram bot untuk terima video
├── tiktok_uploader.py      # Upload video ke TikTok via Playwright
├── tiktok_login.py         # Script login manual TikTok (jalankan sekali)
├── scheduler.py            # Scheduler untuk posting otomatis
├── main.py                 # Entry point - jalankan bot + scheduler
├── logs/                   # Folder log
│   └── app.log
├── videos/                 # Folder penyimpanan video
├── cookies/                # Folder penyimpanan cookies TikTok
│   └── tiktok_cookies.json
└── data/
    └── videos.db           # SQLite database
```
