"""
TikTok Uploader menggunakan Playwright
Upload video ke TikTok dengan reuse cookies/session
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Optional, Tuple, List
import random
import aiohttp

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config import (
    TIKTOK_COOKIES_PATH, 
    HEADLESS_UPLOAD,
    TIKTOK_DEFAULT_CAPTION,
    COOKIES_DIR,
    LOGS_DIR,
    TELEGRAM_BOT_TOKEN,
    ALLOWED_USER_IDS
)
from logger_setup import setup_logger

logger = setup_logger("tiktok_uploader")

TIKTOK_UPLOAD_URL = "https://www.tiktok.com/upload"


async def send_debug_screenshot_to_telegram(screenshot_path: Path, caption: str = "Debug Screenshot"):
    """
    Mengirim screenshot debug ke semua user yang diizinkan via Telegram
    
    Args:
        screenshot_path: Path ke file screenshot
        caption: Caption untuk screenshot
    """
    logger.info(f"Attempting to send screenshot: {screenshot_path}")
    
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN tidak dikonfigurasi, skip kirim screenshot")
        return
    
    # Konversi ke Path jika belum
    screenshot_path = Path(screenshot_path)
    
    if not screenshot_path.exists():
        logger.warning(f"Screenshot tidak ditemukan: {screenshot_path}")
        return
    
    if not ALLOWED_USER_IDS:
        logger.warning("ALLOWED_USER_IDS kosong, skip kirim screenshot")
        return
    
    logger.info(f"Sending screenshot to {len(ALLOWED_USER_IDS)} user(s): {ALLOWED_USER_IDS}")
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            
            for user_id in ALLOWED_USER_IDS:
                try:
                    # Read file as bytes first
                    with open(screenshot_path, 'rb') as f:
                        photo_bytes = f.read()
                    
                    # Create form data with bytes
                    form_data = aiohttp.FormData()
                    form_data.add_field('chat_id', str(user_id))
                    form_data.add_field('caption', f"🔍 {caption}\n📁 {screenshot_path.name}")
                    form_data.add_field('photo', photo_bytes, 
                                      filename=screenshot_path.name,
                                      content_type='image/png')
                    
                    async with session.post(url, data=form_data) as response:
                        resp_text = await response.text()
                        if response.status == 200:
                            logger.info(f"Screenshot sent to user {user_id}")
                        else:
                            logger.warning(f"Failed to send screenshot to {user_id}: status={response.status}, response={resp_text}")
                except Exception as e:
                    logger.error(f"Error sending screenshot to user {user_id}: {type(e).__name__}: {e}")
                    
    except Exception as e:
        logger.error(f"Error sending debug screenshot: {type(e).__name__}: {e}")
BROWSER_PROFILE_DIR = COOKIES_DIR / "browser_profile"


class TikTokUploader:
    """
    TikTok Uploader class
    Menggunakan Playwright untuk upload video via browser automation
    """
    
    def __init__(self, cookies_path: Path = TIKTOK_COOKIES_PATH):
        self.cookies_path = cookies_path
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
    
    async def _load_cookies(self) -> list:
        """Load cookies dari file"""
        if not self.cookies_path.exists():
            raise FileNotFoundError(
                f"Cookies file tidak ditemukan: {self.cookies_path}\n"
                "Jalankan tiktok_login.py terlebih dahulu untuk login manual."
            )
        
        with open(self.cookies_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        
        logger.debug(f"Loaded {len(cookies)} cookies")
        return cookies
    
    async def _random_delay(self, min_sec: float = 0.5, max_sec: float = 2.0):
        """Random delay untuk meniru perilaku manusia"""
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)
    
    async def _human_type(self, page: Page, selector: str, text: str):
        """Ketik teks dengan delay seperti manusia"""
        element = await page.wait_for_selector(selector, timeout=10000)
        if element:
            await element.click()
            await self._random_delay(0.3, 0.7)
            
            # Ketik karakter per karakter dengan delay random
            for char in text:
                await page.keyboard.type(char, delay=random.randint(50, 150))
    
    async def _human_mouse_move(self, page: Page, x: int, y: int):
        """Gerakkan mouse secara natural seperti manusia"""
        # Get current mouse position (approximate)
        current_x = random.randint(100, 500)
        current_y = random.randint(100, 300)
        
        # Move in small steps with random delays
        steps = random.randint(5, 15)
        for i in range(steps):
            # Calculate intermediate position with some randomness
            progress = (i + 1) / steps
            intermediate_x = current_x + (x - current_x) * progress + random.randint(-10, 10)
            intermediate_y = current_y + (y - current_y) * progress + random.randint(-10, 10)
            
            await page.mouse.move(intermediate_x, intermediate_y)
            await asyncio.sleep(random.uniform(0.01, 0.05))
        
        # Final position
        await page.mouse.move(x, y)
    
    async def _human_scroll(self, page: Page):
        """Scroll halaman seperti manusia - random scroll up/down"""
        scroll_amount = random.randint(100, 300)
        direction = random.choice([1, -1])
        
        await page.mouse.wheel(0, scroll_amount * direction)
        await self._random_delay(0.3, 0.8)
    
    async def _init_browser(self, headless: bool = True):
        """Inisialisasi browser dengan persistent profile (sama seperti login)"""
        self._playwright = await async_playwright().start()
        
        # Gunakan persistent context (sama dengan saat login)
        # Ini akan memakai session yang sudah ada
        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Random viewport untuk menghindari fingerprinting
        viewport_width = random.randint(1250, 1350)
        viewport_height = random.randint(700, 800)
        
        # User agents yang lebih baru dan beragam
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        ]
        
        self.context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=headless,
            viewport={'width': viewport_width, 'height': viewport_height},
            user_agent=random.choice(user_agents),
            locale='id-ID',
            timezone_id='Asia/Jakarta',
            color_scheme='light',
            has_touch=False,
            is_mobile=False,
            java_script_enabled=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--window-size=1280,720',
                '--start-maximized',
                '--disable-extensions',
                '--disable-plugins-discovery',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
            ],
            ignore_default_args=['--enable-automation'],
        )
        
        # Advanced anti-detection scripts
        await self.context.add_init_script("""
            // Remove webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Mock chrome object
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // Mock plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                        {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                        {name: 'Native Client', filename: 'internal-nacl-plugin'}
                    ];
                    plugins.item = (index) => plugins[index];
                    plugins.namedItem = (name) => plugins.find(p => p.name === name);
                    plugins.refresh = () => {};
                    return plugins;
                }
            });
            
            // Mock languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['id-ID', 'id', 'en-US', 'en']
            });
            
            // Mock permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Mock WebGL
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter.apply(this, arguments);
            };
            
            // Remove automation indicators
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
            
            // Mock connection
            Object.defineProperty(navigator, 'connection', {
                get: () => ({
                    effectiveType: '4g',
                    rtt: 50,
                    downlink: 10,
                    saveData: false
                })
            });
            
            // Mock hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });
            
            // Mock device memory
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
        """)
        
        # Juga load cookies sebagai backup
        try:
            cookies = await self._load_cookies()
            await self.context.add_cookies(cookies)
        except:
            pass
        
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        
        # Simulate some initial human behavior
        await self._random_delay(1, 2)
        
        logger.info("Browser initialized with persistent profile")
    
    async def _close_browser(self):
        """Tutup browser"""
        try:
            if self.page:
                await self.page.close()
        except:
            pass
        try:
            if self.context:
                await self.context.close()
        except:
            pass
        try:
            if self.browser:
                await self.browser.close()
        except:
            pass
        try:
            if hasattr(self, '_playwright') and self._playwright:
                await self._playwright.stop()
        except:
            pass
        
        self.page = None
        self.context = None
        self.browser = None
        
        logger.debug("Browser closed")
    
    async def _check_login_status(self) -> bool:
        """Cek apakah masih login"""
        try:
            await self.page.goto(TIKTOK_UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
            await self._random_delay(7, 10)  # Tunggu lebih lama untuk load penuh
            
            current_url = self.page.url
            logger.info(f"Current URL: {current_url}")
            
            # Jika redirect ke login, berarti session expired
            if "login" in current_url.lower():
                logger.warning("Session expired - redirect to login page")
                # Screenshot saat session expired
                try:
                    login_path = LOGS_DIR / "debug_session_expired.png"
                    await self.page.screenshot(path=str(login_path))
                    await send_debug_screenshot_to_telegram(
                        login_path,
                        caption="⚠️ Session Expired - Perlu login ulang"
                    )
                except Exception as e:
                    logger.error(f"Failed to send session expired screenshot: {e}")
                return False
            
            # Screenshot untuk debug (simpan ke logs folder untuk persistence)
            try:
                screenshot_path = LOGS_DIR / "debug_login_check.png"
                await self.page.screenshot(path=str(screenshot_path))
                logger.info(f"Screenshot saved to {screenshot_path}")
                # Kirim ke Telegram
                await send_debug_screenshot_to_telegram(
                    screenshot_path,
                    caption="🔐 Login Check - Halaman setelah buka TikTok Upload"
                )
            except Exception as e:
                logger.error(f"Failed to save/send login check screenshot: {e}")
            
            # Cek berbagai kemungkinan elemen upload
            selectors_to_try = [
                'input[type="file"]',
                '[class*="upload"]',
                '[class*="Upload"]',
                'iframe[src*="upload"]',
                '[data-e2e*="upload"]',
                'button[class*="upload"]',
                '[class*="creator"]',
                '[class*="studio"]',
            ]
            
            for selector in selectors_to_try:
                try:
                    elem = await self.page.query_selector(selector)
                    if elem:
                        logger.info(f"Found element: {selector}")
                        return True
                except:
                    pass
            
            # Jika URL mengandung upload/studio/creator, anggap valid
            if any(x in current_url.lower() for x in ['upload', 'studio', 'creator']):
                logger.info("URL indicates upload page - assuming logged in")
                return True
            
            logger.warning("Upload elements not found")
            # Screenshot untuk debug (simpan ke logs folder)
            try:
                screenshot_path = LOGS_DIR / "debug_screenshot.png"
                await self.page.screenshot(path=str(screenshot_path))
                logger.info(f"Screenshot saved to {screenshot_path}")
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking login status: {e}")
            return False
    
    async def upload_video(
        self, 
        video_path: str, 
        caption: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Upload video ke TikTok
        
        Args:
            video_path: Path ke file video
            caption: Caption untuk video (opsional)
            
        Returns:
            Tuple (success: bool, message: str)
        """
        video_file = Path(video_path)
        
        # Validasi file
        if not video_file.exists():
            return False, f"File tidak ditemukan: {video_path}"
        
        if not video_file.is_file():
            return False, f"Bukan file: {video_path}"
        
        caption = caption or TIKTOK_DEFAULT_CAPTION
        
        logger.info(f"Starting upload: {video_file.name}")
        logger.info(f"Caption: {caption[:50]}...")
        
        try:
            # Init browser
            await self._init_browser(headless=HEADLESS_UPLOAD)
            
            # Cek login
            if not await self._check_login_status():
                return False, "Session expired - perlu login ulang (jalankan tiktok_login.py)"
            
            # Navigate ke upload page (mungkin sudah di sana)
            if "upload" not in self.page.url.lower() and "studio" not in self.page.url.lower():
                await self.page.goto(TIKTOK_UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
            
            await self._random_delay(3, 5)
            
            # Tunggu file input muncul
            logger.info("Waiting for upload input...")
            
            # Screenshot untuk debug (simpan ke logs folder)
            try:
                await self.page.screenshot(path=str(LOGS_DIR / "debug_before_input.png"))
                logger.info(f"Screenshot saved: {LOGS_DIR / 'debug_before_input.png'}")
            except:
                pass
            
            # Cek apakah ada iframe yang perlu dimasuki
            file_input = None
            frames_to_check = [self.page] + self.page.frames
            
            # Selector yang lebih lengkap untuk input file - TikTok sering berubah
            file_input_selectors = [
                'input[type="file"][accept*="video"]',
                'input[type="file"][accept*="mp4"]',
                'input[type="file"]',
                'input[name*="upload"]',
                'input[name*="file"]',
                '[data-e2e="upload-input"]',
                '[class*="upload"] input[type="file"]',
                # Selector tambahan untuk TikTok Studio
                'input[accept="video/*"]',
                'input[accept=".mp4,.mov,.avi,.webm"]',
                '#upload-input',
                '.upload-input',
                '[class*="file-select"] input',
                '[class*="FileSelect"] input',
                '[class*="uploader"] input[type="file"]',
                '[class*="Uploader"] input[type="file"]',
            ]
            
            # Coba cari di semua frame
            for frame in frames_to_check:
                try:
                    for selector in file_input_selectors:
                        try:
                            file_input = await frame.query_selector(selector)
                            if file_input:
                                logger.info(f"Found file input with: {selector}")
                                break
                        except:
                            continue
                    if file_input:
                        break
                except:
                    continue
            
            # Jika masih tidak ditemukan, tunggu lebih lama dan coba lagi
            if not file_input:
                logger.info("File input not found, waiting longer...")
                await self._random_delay(5, 8)
                
                # Refresh halaman dan coba lagi
                await self.page.reload(wait_until="domcontentloaded")
                await self._random_delay(5, 8)
                
                frames_to_check = [self.page] + self.page.frames
                for frame in frames_to_check:
                    try:
                        for selector in file_input_selectors:
                            try:
                                file_input = await frame.query_selector(selector)
                                if file_input:
                                    logger.info(f"Found file input after reload: {selector}")
                                    break
                            except:
                                continue
                        if file_input:
                            break
                    except:
                        continue
            
            # Coba klik area upload dulu untuk memunculkan input
            if not file_input:
                logger.info("Trying to click upload area...")
                upload_area_selectors = [
                    '[class*="upload-card"]',
                    '[class*="UploadCard"]',
                    '[class*="upload-btn"]',
                    '[class*="UploadBtn"]',
                    'div[class*="upload"]',
                    '[data-e2e="upload-card"]',
                    'button:has-text("Select video")',
                    'button:has-text("Pilih video")',
                ]
                
                for selector in upload_area_selectors:
                    try:
                        upload_btn = await self.page.query_selector(selector)
                        if upload_btn and await upload_btn.is_visible():
                            await upload_btn.click()
                            logger.info(f"Clicked upload area: {selector}")
                            await self._random_delay(2, 3)
                            
                            # Coba cari file input lagi
                            for fs in file_input_selectors:
                                file_input = await self.page.query_selector(fs)
                                if file_input:
                                    break
                            if file_input:
                                break
                    except:
                        continue
            
            # Screenshot setelah pencarian (simpan ke logs folder dan kirim ke Telegram)
            try:
                after_search_path = LOGS_DIR / "debug_after_search.png"
                await self.page.screenshot(path=str(after_search_path))
                await send_debug_screenshot_to_telegram(
                    after_search_path,
                    caption="🔍 After Search - Mencari upload input"
                )
            except:
                pass
            
            if not file_input:
                # Log HTML untuk debug
                try:
                    html_content = await self.page.content()
                    with open(str(COOKIES_DIR / "debug_page.html"), "w", encoding="utf-8") as f:
                        f.write(html_content)
                    logger.info("Page HTML saved to debug_page.html")
                    
                    # Kirim screenshot error ke Telegram
                    error_input_path = LOGS_DIR / "debug_input_not_found.png"
                    await self.page.screenshot(path=str(error_input_path))
                    logger.info(f"Error screenshot saved to {error_input_path}")
                    await send_debug_screenshot_to_telegram(
                        error_input_path,
                        caption="❌ Upload Input Not Found - File input tidak ditemukan di halaman"
                    )
                except Exception as e:
                    logger.error(f"Failed to save/send input not found screenshot: {e}")
                return False, "Upload input tidak ditemukan - cek debug_page.html dan screenshot"
            
            # Upload file langsung (tanpa harus visible)
            logger.info("Uploading video file...")
            await file_input.set_input_files(str(video_file.absolute()))
            
            # Tunggu upload progress - beri waktu lebih lama
            logger.info("Waiting for upload to complete...")
            await self._random_delay(8, 12)  # Tunggu lebih lama
            
            # Tunggu sampai video selesai diupload (progress bar hilang atau muncul preview)
            max_wait = 180  # 3 menit max untuk upload
            waited = 0
            
            # Kata kunci error
            error_keywords = [
                'error', 'gagal', 'failed', 'kesalahan', 'terjadi kesalahan',
                'tidak dapat', 'cannot', 'tidak berhasil', 'coba lagi',
                'try again', 'something went wrong', 'menggantinya dengan video lain'
            ]
            
            while waited < max_wait:
                # Cek apakah ada error (tapi skip beberapa detik pertama)
                if waited > 10:  # Baru cek error setelah 10 detik
                    # Cek error elements
                    error_selectors = [
                        '[class*="error"]',
                        '[class*="Error"]',
                        '[class*="toast"]',
                        '[class*="Toast"]',
                        '[class*="notice"]',
                        '[class*="alert"]',
                    ]
                    for selector in error_selectors:
                        try:
                            error_element = await self.page.query_selector(selector)
                            if error_element and await error_element.is_visible():
                                error_text = await error_element.text_content()
                                if error_text:
                                    error_text_lower = error_text.lower()
                                    for keyword in error_keywords:
                                        if keyword in error_text_lower:
                                            logger.error(f"Upload error detected: {error_text}")
                                            # Screenshot error
                                            try:
                                                error_path = LOGS_DIR / 'debug_upload_error.png'
                                                await self.page.screenshot(path=str(error_path))
                                                await send_debug_screenshot_to_telegram(
                                                    error_path,
                                                    caption=f"❌ Upload Error: {error_text[:100]}"
                                                )
                                            except:
                                                pass
                                            return False, f"Upload error: {error_text}"
                        except:
                            continue
                
                # Cek apakah upload selesai (muncul caption editor atau post button)
                caption_editor = await self.page.query_selector(
                    '[class*="caption"], [class*="DraftEditor"], [contenteditable="true"]'
                )
                post_button = await self.page.query_selector(
                    'button:has-text("Post"), button:has-text("Upload"), [class*="post-button"]'
                )
                
                if caption_editor or post_button:
                    logger.info("Video uploaded, proceeding to caption...")
                    break
                
                await asyncio.sleep(2)
                waited += 2
                
                if waited % 20 == 0:
                    logger.info(f"Still uploading... ({waited}s)")
            
            if waited >= max_wait:
                return False, "Upload timeout - video terlalu besar atau koneksi lambat"
            
            await self._random_delay(2, 3)
            
            # Handle popup "Aktifkan pemeriksaan konten otomatis?" - klik Aktifkan
            logger.info("Checking for content check popup...")
            try:
                # Cari popup pemeriksaan konten
                aktifkan_selectors = [
                    'button:has-text("Aktifkan")',
                    'button:has-text("Enable")',
                    'button:has-text("Turn on")',
                    '[class*="Modal"] button[class*="primary"]',
                    '[class*="Dialog"] button[class*="primary"]',
                ]
                
                for selector in aktifkan_selectors:
                    try:
                        aktifkan_btn = await self.page.query_selector(selector)
                        if aktifkan_btn and await aktifkan_btn.is_visible():
                            # Verifikasi ini adalah popup yang benar
                            text = await aktifkan_btn.text_content()
                            if text and ('aktifkan' in text.lower() or 'enable' in text.lower() or 'turn on' in text.lower()):
                                await self._random_delay(0.5, 1)
                                await aktifkan_btn.click()
                                logger.info(f"Clicked 'Aktifkan' button for content check")
                                await self._random_delay(2, 3)
                                break
                    except:
                        continue
            except Exception as e:
                logger.debug(f"No content check popup or error: {e}")
            
            # Tutup modal popup lain jika ada (copyright check, dll)
            logger.info("Checking for other modal popups...")
            try:
                modal_close_selectors = [
                    '[class*="Modal"] button[class*="close"]',
                    '[class*="Modal"] [aria-label="Close"]',
                    '[class*="TUXModal"] button',
                    'button:has-text("Got it")',
                    'button:has-text("OK")',
                    'button:has-text("Mengerti")',
                    'button:has-text("Tutup")',
                    '[class*="modal"] button:has-text("OK")',
                    'div[class*="overlay"] button',
                ]
                
                for selector in modal_close_selectors:
                    try:
                        modal_btn = await self.page.query_selector(selector)
                        if modal_btn and await modal_btn.is_visible():
                            await modal_btn.click(force=True)
                            logger.info(f"Closed modal with: {selector}")
                            await self._random_delay(1, 2)
                            break
                    except:
                        continue
                
                # Tekan Escape untuk tutup modal
                await self.page.keyboard.press('Escape')
                await self._random_delay(0.5, 1)
            except:
                pass
            
            # Input caption
            logger.info("Adding caption...")
            
            # Cari caption input
            caption_selectors = [
                '[class*="caption"] [contenteditable="true"]',
                '[class*="DraftEditor-root"]',
                '[data-contents="true"]',
                '.public-DraftEditor-content',
                '[contenteditable="true"]'
            ]
            
            caption_input = None
            for selector in caption_selectors:
                caption_input = await self.page.query_selector(selector)
                if caption_input:
                    break
            
            if caption_input:
                # Clear existing caption dan ketik baru
                await caption_input.click()
                await self._random_delay(0.5, 1.0)
                
                # Random scroll sedikit sebelum mulai ketik (human behavior)
                await self._human_scroll(self.page)
                await self._random_delay(0.3, 0.7)
                
                await self.page.keyboard.press('Control+A')
                await self._random_delay(0.2, 0.4)
                
                # Ketik caption dengan delay yang lebih natural (seperti mengetik normal)
                for char in caption:
                    await self.page.keyboard.type(char, delay=random.randint(50, 120))
                    # Kadang pause sebentar seperti berpikir
                    if random.random() < 0.1:  # 10% chance
                        await self._random_delay(0.3, 0.8)
                
                logger.info("Caption added")
            else:
                logger.warning("Caption input not found, proceeding without caption")
            
            # Delay lebih lama setelah input caption (seperti user review sebelum post)
            logger.info("Waiting after caption input (simulating user review)...")
            await self._random_delay(8, 12)
            
            # Scroll halaman sedikit seperti user yang review
            await self._human_scroll(self.page)
            await self._random_delay(2, 4)
            
            # Klik Post button - harus yang di form, bukan di sidebar
            logger.info("Looking for Post button...")
            
            # Screenshot untuk debug (simpan ke logs folder)
            await self.page.screenshot(path=str(LOGS_DIR / 'debug_looking_post.png'))
            
            # Selector lebih spesifik untuk tombol Post di form (bukan sidebar)
            # Tombol Post biasanya di kanan/bawah form dengan warna primary
            post_selectors = [
                # Tombol dengan class primary/main yang mengandung Post
                'button[class*="primary"]:has-text("Post")',
                'button[class*="Primary"]:has-text("Post")',
                'button[class*="TUXButton--primary"]:has-text("Post")',
                # Tombol di area form
                'form button:has-text("Post")',
                'div[class*="form"] button:has-text("Post")',
                # Data attribute
                '[data-e2e="post_video_button"]',
                '[data-e2e*="post"]',
                # Tombol submit
                'button[type="submit"]',
            ]
            
            post_button = None
            for selector in post_selectors:
                try:
                    buttons = await self.page.query_selector_all(selector)
                    for btn in buttons:
                        try:
                            if await btn.is_visible():
                                box = await btn.bounding_box()
                                # Tombol Post utama biasanya di kanan halaman (x > 500)
                                if box and box['x'] > 400:
                                    text = await btn.text_content()
                                    logger.info(f"Found POST button: '{text}' at x={box['x']}")
                                    post_button = btn
                                    break
                        except:
                            continue
                    if post_button:
                        break
                except:
                    continue
            
            # Fallback: cari semua button dan pilih yang di kanan dengan text Post
            if not post_button:
                logger.info("Searching all buttons for Post...")
                all_buttons = await self.page.query_selector_all('button')
                candidates = []
                for btn in all_buttons:
                    try:
                        text = await btn.text_content()
                        if text and 'post' in text.lower():
                            box = await btn.bounding_box()
                            if box:
                                logger.info(f"Button '{text}' at x={box['x']}, y={box['y']}")
                                # Skip sidebar button (Postingan at x < 100)
                                if 'postingan' not in text.lower() and not await btn.is_disabled():
                                    candidates.append((btn, text, box))
                    except:
                        continue
                
                # Pilih button "Posting" yang bukan di sidebar
                for btn, text, box in candidates:
                    if 'posting' in text.lower():
                        post_button = btn
                        logger.info(f"Selected button: '{text}'")
                        break
                
                # Fallback ke candidate pertama
                if not post_button and candidates:
                    post_button, text, box = candidates[0]
                    logger.info(f"Selected first candidate: '{text}'")
            
            if not post_button:
                await self.page.screenshot(path=str(LOGS_DIR / 'debug_post_button.png'))
                return False, "Post button tidak ditemukan"
            
            # ============================================
            # DELAY PANJANG SEBELUM KLIK POST
            # Simulasi user yang review konten sebelum post
            # ============================================
            logger.info("Waiting before clicking Post (simulating user review)...")
            
            # Delay 10-15 detik seperti user yang membaca/review
            await self._random_delay(10, 15)
            
            # Scroll ke button dan klik
            logger.info("Preparing to click Post button...")
            
            # Tutup semua modal/popup yang mungkin menghalangi SEBELUM klik Post
            try:
                # Tekan Escape beberapa kali untuk tutup modal
                for _ in range(3):
                    await self.page.keyboard.press('Escape')
                    await self._random_delay(0.3, 0.5)
                
                # Coba tutup modal dengan berbagai selector
                modal_close_selectors = [
                    '[class*="TUXModal"] button',
                    '[class*="Modal"] button[class*="close"]',
                    '[class*="modal"] [aria-label="Close"]',
                    'button:has-text("Got it")',
                    'button:has-text("OK")',
                    'button:has-text("Mengerti")',
                    'button:has-text("Tutup")',
                    '[class*="overlay"] button',
                ]
                
                for selector in modal_close_selectors:
                    try:
                        modal_btns = await self.page.query_selector_all(selector)
                        for btn in modal_btns:
                            if await btn.is_visible():
                                await btn.click(force=True)
                                logger.info(f"Closed modal: {selector}")
                                await self._random_delay(0.5, 1)
                    except:
                        continue
            except:
                pass
            
            await self._random_delay(1, 2)
            
            # Scroll ke bawah halaman dulu untuk memastikan form terlihat
            await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await self._random_delay(1, 2)
            
            # Human behavior: scroll sedikit dan gerak mouse sebelum klik
            await self._human_scroll(self.page)
            await self._random_delay(0.5, 1.5)
            
            # Scroll ke Post button dengan benar
            await post_button.scroll_into_view_if_needed()
            await self._random_delay(1.5, 3)
            
            # Ambil bounding box SETELAH scroll (posisi mungkin berubah)
            box = await post_button.bounding_box()
            if box:
                logger.info(f"Button position: x={box['x']}, y={box['y']}, w={box['width']}, h={box['height']}")
                
                # Human behavior: move mouse to button area naturally
                target_x = box['x'] + box['width'] / 2
                target_y = box['y'] + box['height'] / 2
                await self._human_mouse_move(self.page, int(target_x), int(target_y))
                await self._random_delay(0.5, 1.0)
            
            # Screenshot sebelum klik (simpan ke logs folder dan kirim ke Telegram)
            before_post_path = LOGS_DIR / 'debug_before_post.png'
            await self.page.screenshot(path=str(before_post_path))
            await send_debug_screenshot_to_telegram(
                before_post_path, 
                caption="📸 Before Post Click - Halaman sebelum klik tombol Post"
            )
            
            # Delay sebelum klik seperti user mereview
            await self._random_delay(1, 2)
            
            # Coba berbagai metode klik - mulai dari yang paling natural
            clicked = False
            
            # Metode 1: Mouse click yang natural (paling human-like)
            if box:
                try:
                    x = box['x'] + box['width'] / 2 + random.randint(-3, 3)  # Sedikit offset random
                    y = box['y'] + box['height'] / 2 + random.randint(-3, 3)
                    await self.page.mouse.click(x, y)
                    clicked = True
                    logger.info(f"Clicked using natural mouse at ({x:.0f}, {y:.0f})")
                except Exception as e:
                    logger.warning(f"Natural mouse click failed: {e}")
            
            # Metode 2: Element click (jika mouse click gagal)
            if not clicked:
                try:
                    await post_button.click(timeout=5000)
                    clicked = True
                    logger.info("Clicked using element click")
                except Exception as e:
                    logger.warning(f"Element click failed: {e}")
            
            # Metode 3: JavaScript click (fallback)
            if not clicked:
                try:
                    await post_button.evaluate('el => el.click()')
                    clicked = True
                    logger.info("Clicked using JavaScript")
                except Exception as e:
                    logger.warning(f"JS click failed: {e}")
            
            # Metode 4: dispatchEvent dengan MouseEvent
            if not clicked:
                try:
                    await post_button.evaluate('''el => {
                        el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                    }''')
                    clicked = True
                    logger.info("Clicked using dispatchEvent")
                except Exception as e:
                    logger.warning(f"dispatchEvent failed: {e}")
            
            # Metode 5: Force click (last resort)
            if not clicked:
                try:
                    await post_button.click(force=True, timeout=5000)
                    clicked = True
                    logger.info("Clicked using force click")
                except Exception as e:
                    logger.warning(f"Force click failed: {e}")
            
            # Screenshot setelah klik (simpan ke logs folder dan kirim ke Telegram)
            await self._random_delay(3, 5)  # Delay lebih lama setelah klik
            after_post_path = LOGS_DIR / 'debug_after_post.png'
            await self.page.screenshot(path=str(after_post_path))
            await send_debug_screenshot_to_telegram(
                after_post_path, 
                caption="📸 After Post Click - Halaman setelah klik tombol Post"
            )
            
            logger.info("Post button clicked, waiting for upload to complete...")
            
            # Tunggu lebih lama untuk proses upload
            await self._random_delay(5, 8)
            
            # Tunggu konfirmasi posting - proses bisa lama
            max_confirm_wait = 120  # 2 menit
            confirm_waited = 0
            
            while confirm_waited < max_confirm_wait:
                # Screenshot setiap 30 detik untuk debug (simpan ke logs folder)
                if confirm_waited > 0 and confirm_waited % 30 == 0:
                    try:
                        screenshot_path = LOGS_DIR / f'debug_upload_{confirm_waited}s.png'
                        await self.page.screenshot(path=str(screenshot_path))
                        logger.info(f"Screenshot saved: {screenshot_path}")
                    except:
                        pass
                
                current_url = self.page.url
                
                # Cek apakah sudah redirect ke manage/profile/content (berarti sudah selesai upload)
                if any(x in current_url.lower() for x in ['manage', 'profile', '/@', '/content', 'tiktokstudio/content']):
                    logger.info(f"Redirected to: {current_url} - Upload successful!")
                    return True, "Video berhasil diupload ke TikTok!"
                
                # Cek success indicator dengan selector yang lebih baik
                success_selectors = [
                    # Pesan sukses dalam berbagai bahasa
                    'text="Your video is being uploaded"',
                    'text="Video posted"', 
                    'text="Posted"',
                    'text="Video sedang diproses"',
                    'text="Berhasil diposting"',
                    'text="Video telah diposting"',
                    'text="Upload selesai"',
                    # Toast/notification sukses
                    '[class*="toast"]:has-text("success")',
                    '[class*="Toast"]:has-text("berhasil")',
                    '[class*="notification"]:has-text("posted")',
                ]
                
                for selector in success_selectors:
                    try:
                        element = await self.page.query_selector(selector)
                        if element:
                            is_visible = await element.is_visible()
                            if is_visible:
                                text = await element.text_content()
                                logger.info(f"Success indicator found: {text}")
                                await self._random_delay(2, 3)
                                return True, "Video berhasil diupload ke TikTok!"
                    except:
                        continue
                
                # Cek apakah tombol Post masih ada dan enabled (berarti belum diklik/submit)
                try:
                    post_btn = await self.page.query_selector('button:has-text("Posting"), button:has-text("Post")')
                    if post_btn:
                        is_disabled = await post_btn.is_disabled()
                        # Jika button masih enabled setelah 30 detik, mungkin klik gagal
                        if not is_disabled and confirm_waited >= 30:
                            logger.warning("Post button still enabled - clicking again...")
                            await post_btn.click(force=True)
                            await self._random_delay(3, 5)
                except:
                    pass
                
                # Log progress setiap 30 detik
                if confirm_waited % 30 == 0:
                    logger.info(f"Still uploading... ({confirm_waited}s)")
                
                # Cek error messages - termasuk pesan error TikTok dalam bahasa Indonesia
                error_selectors = [
                    '[class*="error"]',
                    '[class*="Error"]', 
                    '[class*="toast"]',
                    '[class*="Toast"]',
                    '[class*="alert"]',
                    '[class*="Alert"]',
                    '[class*="notice"]',
                    '[class*="Notice"]',
                    'text="failed"',
                    'text="gagal"',
                    'text="tidak dapat"',
                    'text="terjadi kesalahan"',
                    'text="kesalahan"',
                ]
                
                # Kata-kata kunci error dalam berbagai bahasa
                error_keywords = [
                    'error', 'gagal', 'failed', 'kesalahan', 'terjadi kesalahan',
                    'tidak dapat', 'cannot', 'tidak berhasil', 'coba lagi',
                    'try again', 'something went wrong'
                ]
                
                for selector in error_selectors:
                    try:
                        elem = await self.page.query_selector(selector)
                        if elem and await elem.is_visible():
                            error_text = await elem.text_content()
                            if error_text and len(error_text.strip()) > 5:
                                error_text_lower = error_text.lower()
                                # Cek apakah mengandung kata kunci error
                                for keyword in error_keywords:
                                    if keyword in error_text_lower:
                                        logger.error(f"Error detected: {error_text}")
                                        # Screenshot error
                                        try:
                                            error_path = LOGS_DIR / 'debug_tiktok_error.png'
                                            await self.page.screenshot(path=str(error_path))
                                            await send_debug_screenshot_to_telegram(
                                                error_path,
                                                caption=f"❌ TikTok Error: {error_text[:100]}"
                                            )
                                        except:
                                            pass
                                        return False, f"TikTok error: {error_text}"
                    except:
                        continue
                
                await asyncio.sleep(3)
                confirm_waited += 3
            
            # Ambil screenshot terakhir (simpan ke logs folder dan kirim ke Telegram)
            try:
                screenshot_path = LOGS_DIR / 'debug_final.png'
                await self.page.screenshot(path=str(screenshot_path))
                logger.info(f"Final screenshot saved: {screenshot_path}")
                # Kirim ke Telegram
                await send_debug_screenshot_to_telegram(
                    screenshot_path, 
                    caption="🏁 Final State - Setelah menunggu konfirmasi upload"
                )
            except Exception as e:
                logger.warning(f"Failed to save/send final screenshot: {e}")
            
            # Cek URL terakhir
            final_url = self.page.url
            if "upload" in final_url.lower():
                return False, f"Upload mungkin gagal - masih di halaman upload. Cek manual di TikTok."
            
            return True, "Video diproses oleh TikTok (cek di profil)"
            
        except Exception as e:
            logger.error(f"Upload failed with exception: {e}")
            
            # Screenshot untuk debug (simpan ke logs folder dan kirim ke Telegram)
            if self.page:
                try:
                    error_screenshot_path = LOGS_DIR / 'debug_error.png'
                    await self.page.screenshot(path=str(error_screenshot_path))
                    logger.info(f"Error screenshot saved: {error_screenshot_path}")
                    # Kirim ke Telegram
                    await send_debug_screenshot_to_telegram(
                        error_screenshot_path, 
                        caption=f"❌ Error State - {str(e)[:100]}"
                    )
                except Exception as e2:
                    logger.warning(f"Failed to save/send error screenshot: {e2}")
            
            return False, f"Upload error: {str(e)}"
        
        finally:
            await self._close_browser()
    
    async def test_connection(self) -> Tuple[bool, str]:
        """Test koneksi dan session"""
        try:
            await self._init_browser(headless=True)
            
            if await self._check_login_status():
                return True, "Koneksi OK - Session valid"
            else:
                return False, "Session expired atau invalid"
                
        except FileNotFoundError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"
        finally:
            await self._close_browser()


async def upload_single_video(video_path: str, caption: Optional[str] = None) -> Tuple[bool, str]:
    """
    Fungsi helper untuk upload single video
    
    Args:
        video_path: Path ke file video
        caption: Caption untuk video
        
    Returns:
        Tuple (success, message)
    """
    uploader = TikTokUploader()
    return await uploader.upload_video(video_path, caption)


if __name__ == "__main__":
    """Test upload"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python tiktok_uploader.py <video_path> [caption]")
        print("Example: python tiktok_uploader.py test_video.mp4 'Test caption #fyp'")
        sys.exit(1)
    
    video_path = sys.argv[1]
    caption = sys.argv[2] if len(sys.argv) > 2 else None
    
    async def main():
        success, message = await upload_single_video(video_path, caption)
        print(f"\n{'✅' if success else '❌'} {message}")
        return 0 if success else 1
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
