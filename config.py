"""
Konfigurasi aplikasi TikTok Auto
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directory
BASE_DIR = Path(__file__).parent.absolute()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_IDS = [
    int(uid.strip()) 
    for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") 
    if uid.strip()
]

# TikTok
TIKTOK_DEFAULT_CAPTION = os.getenv("TIKTOK_DEFAULT_CAPTION", "#fyp #viral #foryou")

# Timezone
TIMEZONE = os.getenv("TIMEZONE", "Asia/Jakarta")

# Posting schedule
POSTING_SCHEDULE = [
    time.strip() 
    for time in os.getenv("POSTING_SCHEDULE", "06:00,09:00,12:00").split(",")
]

# Retry
MAX_RETRY = int(os.getenv("MAX_RETRY", "1"))

# Headless
HEADLESS_UPLOAD = os.getenv("HEADLESS_UPLOAD", "true").lower() == "true"

# Paths
VIDEOS_DIR = BASE_DIR / "videos"
COOKIES_DIR = BASE_DIR / "cookies"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"

# Database
DATABASE_PATH = DATA_DIR / "videos.db"

# Cookie file
TIKTOK_COOKIES_PATH = COOKIES_DIR / "tiktok_cookies.json"

# Create directories if not exist
for directory in [VIDEOS_DIR, COOKIES_DIR, LOGS_DIR, DATA_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Validate required config
def validate_config():
    """Validasi konfigurasi yang wajib ada"""
    errors = []
    
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN tidak ditemukan di .env")
    
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        return False
    return True
