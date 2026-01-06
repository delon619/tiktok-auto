#!/bin/bash
# ================================================================
# SETUP SCRIPT untuk TikTok Auto Upload System
# Jalankan di Ubuntu VPS yang baru
# ================================================================

set -e  # Exit on error

echo "========================================"
echo "🚀 TikTok Auto System - Setup Script"
echo "========================================"

# Update system
echo ""
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Python 3.10+ dan dependencies
echo ""
echo "🐍 Installing Python and dependencies..."
sudo apt install -y python3 python3-pip python3-venv

# Install dependencies untuk Playwright
echo ""
echo "🎭 Installing Playwright dependencies..."
sudo apt install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libgtk-3-0

# Install Xvfb untuk virtual display (opsional, untuk headless)
echo ""
echo "🖥️ Installing Xvfb (virtual display)..."
sudo apt install -y xvfb

# Create project directory
PROJECT_DIR="$HOME/tiktok-auto"
echo ""
echo "📁 Setting up project directory: $PROJECT_DIR"

if [ -d "$PROJECT_DIR" ]; then
    echo "   Directory exists, backing up..."
    mv "$PROJECT_DIR" "${PROJECT_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
fi

mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Create virtual environment
echo ""
echo "🔧 Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Create requirements.txt
echo ""
echo "📄 Creating requirements.txt..."
cat > requirements.txt << 'EOF'
# Telegram Bot
python-telegram-bot==20.7

# Browser Automation
playwright==1.40.0

# Scheduler
apscheduler==3.10.4

# Environment Variables
python-dotenv==1.0.0

# Async Support
aiofiles==23.2.1

# Timezone
pytz==2024.1
EOF

# Install Python packages
echo ""
echo "📦 Installing Python packages..."
pip install -r requirements.txt

# Install Playwright browsers
echo ""
echo "🎭 Installing Playwright browsers..."
playwright install chromium
playwright install-deps chromium

# Create directories
echo ""
echo "📁 Creating project directories..."
mkdir -p videos cookies logs data

# Create .env file template
echo ""
echo "📝 Creating .env template..."
cat > .env << 'EOF'
# Telegram Bot Token (dapatkan dari @BotFather)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Telegram User ID yang diizinkan (opsional, untuk keamanan)
# Pisahkan dengan koma jika lebih dari satu: 123456789,987654321
ALLOWED_USER_IDS=

# Default caption untuk TikTok
TIKTOK_DEFAULT_CAPTION=#fyp #viral #foryou

# Timezone
TIMEZONE=Asia/Jakarta

# Posting schedule (format: HH:MM, pisahkan dengan koma)
POSTING_SCHEDULE=06:00,09:00,12:00

# Max retry untuk upload
MAX_RETRY=1

# Headless mode saat upload (true untuk production)
HEADLESS_UPLOAD=true
EOF

# Create systemd service file
echo ""
echo "🔧 Creating systemd service file..."
sudo tee /etc/systemd/system/tiktok-auto.service > /dev/null << EOF
[Unit]
Description=TikTok Auto Upload System
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/python main.py
Restart=always
RestartSec=10

# Logging
StandardOutput=append:$PROJECT_DIR/logs/service.log
StandardError=append:$PROJECT_DIR/logs/service_error.log

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

echo ""
echo "========================================"
echo "✅ Setup completed!"
echo "========================================"
echo ""
echo "📋 Next steps:"
echo ""
echo "1. Edit .env file dengan token Telegram kamu:"
echo "   nano $PROJECT_DIR/.env"
echo ""
echo "2. Copy semua file Python ke $PROJECT_DIR"
echo ""
echo "3. Login TikTok di mesin dengan GUI, lalu copy cookies ke VPS:"
echo "   # Di mesin lokal (dengan GUI):"
echo "   python tiktok_login.py"
echo "   # Copy file cookies/tiktok_cookies.json ke VPS"
echo ""
echo "4. Jalankan system:"
echo "   cd $PROJECT_DIR"
echo "   source venv/bin/activate"
echo "   python main.py"
echo ""
echo "5. Atau gunakan systemd untuk auto-start:"
echo "   sudo systemctl enable tiktok-auto"
echo "   sudo systemctl start tiktok-auto"
echo "   sudo systemctl status tiktok-auto"
echo ""
echo "========================================"
