"""
TikTok Uploader menggunakan Playwright
Upload video ke TikTok dengan reuse cookies/session
VERSI OPTIMIZED - Menggunakan TikTok Creator Center
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Optional, Tuple, List
import random
import aiohttp
import re

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeout

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

# TikTok URLs
TIKTOK_UPLOAD_URL = "https://www.tiktok.com/creator-center/upload"
TIKTOK_STUDIO_URL = "https://www.tiktok.com/tiktokstudio/upload"
TIKTOK_CLASSIC_UPLOAD = "https://www.tiktok.com/upload"
BROWSER_PROFILE_DIR = COOKIES_DIR / "browser_profile"


async def send_telegram_message(message: str):
    """Send text message to all allowed users via Telegram"""
    if not TELEGRAM_BOT_TOKEN or not ALLOWED_USER_IDS:
        return
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            for user_id in ALLOWED_USER_IDS:
                try:
                    data = {'chat_id': str(user_id), 'text': message, 'parse_mode': 'HTML'}
                    await session.post(url, data=data)
                except:
                    pass
    except:
        pass


async def send_debug_screenshot_to_telegram(screenshot_path: Path, caption: str = "Debug Screenshot"):
    """Mengirim screenshot debug ke semua user yang diizinkan via Telegram"""
    logger.info(f"Sending screenshot: {screenshot_path}")
    
    if not TELEGRAM_BOT_TOKEN:
        return
    
    screenshot_path = Path(screenshot_path)
    if not screenshot_path.exists():
        return
    
    if not ALLOWED_USER_IDS:
        return
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            
            for user_id in ALLOWED_USER_IDS:
                try:
                    with open(screenshot_path, 'rb') as f:
                        photo_bytes = f.read()
                    
                    form_data = aiohttp.FormData()
                    form_data.add_field('chat_id', str(user_id))
                    form_data.add_field('caption', f"🔍 {caption}\n📁 {screenshot_path.name}")
                    form_data.add_field('photo', photo_bytes, 
                                      filename=screenshot_path.name,
                                      content_type='image/png')
                    
                    async with session.post(url, data=form_data) as response:
                        if response.status == 200:
                            logger.info(f"Screenshot sent to user {user_id}")
                except Exception as e:
                    logger.error(f"Error sending screenshot to {user_id}: {e}")
    except Exception as e:
        logger.error(f"Error sending debug screenshot: {e}")


class TikTokUploader:
    """TikTok Uploader - Optimized Version"""
    
    def __init__(self, cookies_path: Path = TIKTOK_COOKIES_PATH):
        self.cookies_path = cookies_path
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._playwright = None
    
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
    
    async def _delay(self, min_sec: float = 1.0, max_sec: float = 3.0):
        """Random delay"""
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)
    
    async def _type_like_human(self, text: str, fast: bool = False):
        """Ketik teks dengan kecepatan manusia"""
        for char in text:
            delay = random.randint(30, 80) if fast else random.randint(50, 150)
            await self.page.keyboard.type(char, delay=delay)
            # Kadang pause sebentar
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.2, 0.5))
    
    async def _safe_click(self, element, description: str = "element") -> bool:
        """Click element dengan berbagai metode fallback"""
        if not element:
            return False
        
        try:
            # Scroll ke element dulu
            await element.scroll_into_view_if_needed()
            await self._delay(0.3, 0.6)
            
            # Coba click biasa
            try:
                await element.click(timeout=5000)
                logger.info(f"Clicked {description} (normal click)")
                return True
            except:
                pass
            
            # Coba force click
            try:
                await element.click(force=True, timeout=5000)
                logger.info(f"Clicked {description} (force click)")
                return True
            except:
                pass
            
            # Coba JavaScript click
            try:
                await element.evaluate('el => el.click()')
                logger.info(f"Clicked {description} (JS click)")
                return True
            except:
                pass
            
            # Coba dispatch event
            try:
                await element.evaluate('''el => {
                    el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                }''')
                logger.info(f"Clicked {description} (dispatch event)")
                return True
            except:
                pass
            
            return False
        except Exception as e:
            logger.warning(f"Failed to click {description}: {e}")
            return False
    
    async def _take_screenshot(self, name: str, send_telegram: bool = True):
        """Take screenshot and optionally send to Telegram"""
        try:
            path = LOGS_DIR / f"debug_{name}.png"
            await self.page.screenshot(path=str(path), full_page=False)
            logger.info(f"Screenshot: {path}")
            
            if send_telegram:
                await send_debug_screenshot_to_telegram(path, caption=name)
            
            return path
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return None
    
    async def _init_browser(self, headless: bool = True):
        """Inisialisasi browser"""
        self._playwright = await async_playwright().start()
        
        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Random viewport
        viewport_width = random.randint(1280, 1400)
        viewport_height = random.randint(750, 850)
        
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        ]
        
        self.context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=headless,
            viewport={'width': viewport_width, 'height': viewport_height},
            user_agent=random.choice(user_agents),
            locale='en-US',
            timezone_id='Asia/Jakarta',
            color_scheme='light',
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1366,768',
                '--start-maximized',
            ],
            ignore_default_args=['--enable-automation'],
        )
        
        # Anti-detection script
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [{name: 'Chrome PDF Plugin'}, {name: 'Chrome PDF Viewer'}, {name: 'Native Client'}];
                    plugins.item = (i) => plugins[i];
                    plugins.namedItem = (n) => plugins.find(p => p.name === n);
                    return plugins;
                }
            });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en', 'id'] });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            
            // Remove automation indicators
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        """)
        
        # Load cookies
        try:
            cookies = await self._load_cookies()
            await self.context.add_cookies(cookies)
            logger.info(f"Loaded {len(cookies)} cookies")
        except Exception as e:
            logger.warning(f"Could not load cookies: {e}")
        
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        
        # Set default timeout
        self.page.set_default_timeout(30000)
        
        await self._delay(1, 2)
        logger.info("Browser initialized")
    
    async def _close_browser(self):
        """Tutup browser dengan aman"""
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
            if self._playwright:
                await self._playwright.stop()
        except:
            pass
        
        self.page = None
        self.context = None
        self._playwright = None
        logger.debug("Browser closed")
    
    async def _navigate_to_upload(self) -> bool:
        """Navigate ke halaman upload TikTok"""
        upload_urls = [
            TIKTOK_STUDIO_URL,
            TIKTOK_UPLOAD_URL,
            TIKTOK_CLASSIC_UPLOAD,
        ]
        
        for url in upload_urls:
            try:
                logger.info(f"Trying: {url}")
                await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await self._delay(5, 8)
                
                current_url = self.page.url
                logger.info(f"Current URL: {current_url}")
                
                # Cek apakah redirect ke login
                if "login" in current_url.lower():
                    logger.warning("Redirected to login page - session may be expired")
                    await self._take_screenshot("login_redirect")
                    continue
                
                # Cek apakah ada form upload
                has_upload = await self._check_upload_page()
                if has_upload:
                    logger.info(f"Upload page found at: {url}")
                    return True
                    
            except Exception as e:
                logger.warning(f"Failed to load {url}: {e}")
                continue
        
        return False
    
    async def _check_upload_page(self) -> bool:
        """Cek apakah di halaman upload"""
        indicators = [
            'input[type="file"]',
            '[class*="upload"]',
            '[class*="Upload"]',
            '[data-e2e*="upload"]',
            'button:has-text("Select file")',
            'button:has-text("Select video")',
            'text=Select video',
            'text=Select file',
            'text=Drag and drop',
        ]
        
        for selector in indicators:
            try:
                elem = await self.page.query_selector(selector)
                if elem:
                    logger.debug(f"Found upload indicator: {selector}")
                    return True
            except:
                continue
        
        return False
    
    async def _find_file_input(self) -> Optional[any]:
        """Cari file input element"""
        selectors = [
            'input[type="file"][accept*="video"]',
            'input[type="file"][accept*="mp4"]',
            'input[type="file"]',
            '[data-e2e="upload-input"]',
            'input[accept="video/*"]',
            'input[accept*=".mp4"]',
        ]
        
        # Cek di main page dan semua frames
        frames_to_check = [self.page] + list(self.page.frames)
        
        for frame in frames_to_check:
            try:
                for selector in selectors:
                    try:
                        element = await frame.query_selector(selector)
                        if element:
                            logger.info(f"Found file input: {selector}")
                            return element
                    except:
                        continue
            except:
                continue
        
        return None
    
    async def _wait_for_video_processing(self, timeout: int = 180) -> Tuple[bool, str]:
        """Tunggu video selesai diproses"""
        logger.info("Waiting for video processing...")
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            # Cek error messages
            error_check = await self._check_for_errors()
            if error_check:
                return False, error_check
            
            # Cek apakah video sudah siap (ada preview atau caption editor)
            ready_indicators = [
                # Video preview
                'video',
                '[class*="video-preview"]',
                '[class*="VideoPreview"]',
                # Caption editor
                '[contenteditable="true"]',
                '[class*="caption"]',
                '[class*="Caption"]',
                '[class*="DraftEditor"]',
                # Post button aktif
                'button:has-text("Post"):not([disabled])',
                'button:has-text("Posting"):not([disabled])',
            ]
            
            for selector in ready_indicators:
                try:
                    elem = await self.page.query_selector(selector)
                    if elem and await elem.is_visible():
                        logger.info(f"Video ready indicator found: {selector}")
                        return True, "Video ready"
                except:
                    continue
            
            elapsed = int(asyncio.get_event_loop().time() - start_time)
            if elapsed % 15 == 0:
                logger.info(f"Still processing... ({elapsed}s)")
            
            await asyncio.sleep(2)
        
        return False, "Timeout waiting for video processing"
    
    async def _check_for_errors(self) -> Optional[str]:
        """Cek error messages di halaman"""
        error_selectors = [
            '[class*="error"]',
            '[class*="Error"]',
            '[class*="toast"]',
            '[class*="Toast"]',
            '[class*="alert"]',
            '[class*="Alert"]',
        ]
        
        error_keywords = [
            'error', 'failed', 'gagal', 'tidak dapat', 'cannot', 
            'try again', 'coba lagi', 'something went wrong',
            'kesalahan', 'tidak berhasil', 'rejected', 'ditolak'
        ]
        
        for selector in error_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                for elem in elements:
                    if await elem.is_visible():
                        text = await elem.text_content()
                        if text:
                            text_lower = text.lower()
                            for keyword in error_keywords:
                                if keyword in text_lower:
                                    return text.strip()[:200]
            except:
                continue
        
        return None
    
    async def _input_caption(self, caption: str) -> bool:
        """Input caption ke video"""
        logger.info("Adding caption...")
        
        caption_selectors = [
            '[contenteditable="true"]',
            '[class*="caption"] [contenteditable="true"]',
            '[class*="Caption"] [contenteditable="true"]',
            '[class*="DraftEditor-root"]',
            '[data-contents="true"]',
            '.public-DraftEditor-content',
            'div[class*="notranslate"][contenteditable="true"]',
        ]
        
        for selector in caption_selectors:
            try:
                elem = await self.page.query_selector(selector)
                if elem and await elem.is_visible():
                    await elem.click()
                    await self._delay(0.3, 0.6)
                    
                    # Clear existing text
                    await self.page.keyboard.press('Control+A')
                    await self._delay(0.1, 0.2)
                    
                    # Type caption
                    await self._type_like_human(caption, fast=True)
                    
                    logger.info("Caption added successfully")
                    return True
            except Exception as e:
                logger.debug(f"Caption selector {selector} failed: {e}")
                continue
        
        logger.warning("Could not find caption input")
        return False
    
    async def _close_popups(self):
        """Tutup popup/modal yang mungkin muncul"""
        popup_close_selectors = [
            'button:has-text("Got it")',
            'button:has-text("OK")',
            'button:has-text("Mengerti")',
            'button:has-text("Tutup")',
            'button:has-text("Close")',
            'button:has-text("Enable")',
            'button:has-text("Aktifkan")',
            '[class*="Modal"] button[class*="close"]',
            '[class*="modal"] [aria-label="Close"]',
            '[aria-label="Close"]',
            'button[class*="CloseButton"]',
        ]
        
        for selector in popup_close_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                for elem in elements:
                    if await elem.is_visible():
                        await elem.click(force=True)
                        logger.info(f"Closed popup: {selector}")
                        await self._delay(0.5, 1)
            except:
                continue
        
        # Press Escape sebagai backup
        try:
            await self.page.keyboard.press('Escape')
            await self._delay(0.3, 0.5)
        except:
            pass
    
    async def _find_post_button(self):
        """Cari tombol Post - dengan validasi text yang benar"""
        
        # Pertama, cari dengan selector yang sangat spesifik
        specific_selectors = [
            '[data-e2e="post_video_button"]',
            'button[class*="TUXButton--primary"]:has-text("Post")',
            'button[class*="primary"]:has-text("Post")',
        ]
        
        for selector in specific_selectors:
            try:
                btn = await self.page.query_selector(selector)
                if btn and await btn.is_visible():
                    is_disabled = await btn.is_disabled()
                    if not is_disabled:
                        text = await btn.text_content()
                        logger.info(f"Found specific Post button: '{text}'")
                        return btn
            except:
                continue
        
        # Jika tidak ditemukan, cari semua button dan filter dengan hati-hati
        all_buttons = await self.page.query_selector_all('button')
        
        # Kata-kata yang harus ada di tombol Post
        post_keywords = ['post', 'posting', 'publish', 'upload']
        # Kata-kata yang TIDAK boleh ada (harus di-skip)
        skip_keywords = ['discard', 'cancel', 'batal', 'hapus', 'delete', 'save', 'draft', 'schedule']
        
        candidates = []
        
        for btn in all_buttons:
            try:
                if not await btn.is_visible():
                    continue
                
                is_disabled = await btn.is_disabled()
                if is_disabled:
                    continue
                
                text = await btn.text_content()
                if not text:
                    continue
                
                text_lower = text.strip().lower()
                
                # Skip button yang mengandung kata-kata negatif
                skip = False
                for skip_word in skip_keywords:
                    if skip_word in text_lower:
                        skip = True
                        break
                
                if skip:
                    continue
                
                # Skip sidebar button (Postingan di sidebar)
                if 'postingan' in text_lower:
                    continue
                
                # Cek apakah mengandung kata post keywords
                has_post_keyword = False
                for keyword in post_keywords:
                    if keyword in text_lower:
                        has_post_keyword = True
                        break
                
                if has_post_keyword:
                    box = await btn.bounding_box()
                    if box and box['x'] > 300:  # Harus di area form, bukan sidebar
                        candidates.append((btn, text.strip(), box))
                        logger.info(f"Post candidate: '{text.strip()}' at x={box['x']}")
            except:
                continue
        
        # Pilih candidate terbaik (biasanya yang x-nya paling besar = paling kanan)
        if candidates:
            # Sort by x position descending (paling kanan)
            candidates.sort(key=lambda x: x[2]['x'], reverse=True)
            best = candidates[0]
            logger.info(f"Selected Post button: '{best[1]}' at x={best[2]['x']}")
            return best[0]
        
        return None
    
    async def _wait_for_upload_complete(self, timeout: int = 180) -> Tuple[bool, str]:
        """Tunggu upload selesai setelah klik Post"""
        logger.info("Waiting for upload to complete...")
        start_time = asyncio.get_event_loop().time()
        last_screenshot_time = 0
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            current_url = self.page.url
            elapsed = int(asyncio.get_event_loop().time() - start_time)
            
            # Cek redirect ke content/manage page (sukses)
            success_urls = ['manage', 'profile', '/@', '/content', 'tiktokstudio/content', 'creator-center']
            if any(x in current_url.lower() for x in success_urls):
                logger.info(f"Upload success! Redirected to: {current_url}")
                return True, "Video berhasil diupload ke TikTok!"
            
            # Cek success messages
            success_indicators = [
                'text="Your video is being uploaded"',
                'text="Video posted"',
                'text="Posted"',
                'text="Upload complete"',
                'text="Berhasil diposting"',
                'text="Video telah diposting"',
            ]
            
            for selector in success_indicators:
                try:
                    elem = await self.page.query_selector(selector)
                    if elem and await elem.is_visible():
                        text = await elem.text_content()
                        logger.info(f"Success: {text}")
                        return True, "Video berhasil diupload ke TikTok!"
                except:
                    continue
            
            # Cek error
            error = await self._check_for_errors()
            if error:
                return False, f"Upload error: {error}"
            
            # Log progress
            if elapsed % 20 == 0 and elapsed > 0:
                logger.info(f"Upload in progress... ({elapsed}s)")
            
            # Screenshot setiap 40 detik
            if elapsed - last_screenshot_time >= 40:
                await self._take_screenshot(f"upload_progress_{elapsed}s", send_telegram=False)
                last_screenshot_time = elapsed
            
            await asyncio.sleep(3)
        
        return False, "Upload timeout"
    
    async def upload_video(self, video_path: str, caption: Optional[str] = None) -> Tuple[bool, str]:
        """
        Upload video ke TikTok
        
        Args:
            video_path: Path ke file video
            caption: Caption untuk video
            
        Returns:
            Tuple (success: bool, message: str)
        """
        video_file = Path(video_path)
        
        # Validasi file
        if not video_file.exists():
            return False, f"File tidak ditemukan: {video_path}"
        
        if not video_file.is_file():
            return False, f"Bukan file: {video_path}"
        
        # Cek ukuran file
        file_size_mb = video_file.stat().st_size / (1024 * 1024)
        logger.info(f"Video size: {file_size_mb:.2f} MB")
        
        if file_size_mb > 500:
            return False, "Video terlalu besar (max 500MB)"
        
        caption = caption or TIKTOK_DEFAULT_CAPTION
        
        logger.info(f"="*50)
        logger.info(f"Starting upload: {video_file.name}")
        logger.info(f"Caption: {caption[:50]}...")
        logger.info(f"="*50)
        
        await send_telegram_message(f"🎬 Starting upload:\n📹 {video_file.name}\n💬 {caption[:50]}...")
        
        try:
            # 1. Init browser
            await self._init_browser(headless=HEADLESS_UPLOAD)
            
            # 2. Navigate ke halaman upload
            logger.info("Step 1: Navigating to upload page...")
            if not await self._navigate_to_upload():
                await self._take_screenshot("upload_page_not_found")
                return False, "Tidak dapat mengakses halaman upload. Session mungkin expired - jalankan tiktok_login.py"
            
            await self._take_screenshot("01_upload_page", send_telegram=True)
            await self._delay(2, 3)
            
            # 3. Cari file input
            logger.info("Step 2: Finding file input...")
            file_input = await self._find_file_input()
            
            if not file_input:
                # Coba klik area upload untuk memunculkan input
                upload_area_selectors = [
                    '[class*="upload-card"]',
                    '[class*="UploadCard"]',
                    'button:has-text("Select")',
                    '[class*="upload-btn"]',
                    'div[class*="upload"]',
                ]
                
                for selector in upload_area_selectors:
                    try:
                        elem = await self.page.query_selector(selector)
                        if elem and await elem.is_visible():
                            await elem.click()
                            await self._delay(2, 3)
                            file_input = await self._find_file_input()
                            if file_input:
                                break
                    except:
                        continue
            
            if not file_input:
                await self._take_screenshot("file_input_not_found")
                
                # Save HTML untuk debug
                try:
                    html = await self.page.content()
                    with open(LOGS_DIR / "debug_page.html", "w", encoding="utf-8") as f:
                        f.write(html)
                except:
                    pass
                
                return False, "File input tidak ditemukan. Cek screenshot dan debug_page.html"
            
            # 4. Upload file
            logger.info("Step 3: Uploading video file...")
            await file_input.set_input_files(str(video_file.absolute()))
            
            await self._delay(3, 5)
            await self._take_screenshot("02_file_selected", send_telegram=True)
            
            # 5. Tunggu video diproses
            logger.info("Step 4: Waiting for video processing...")
            success, message = await self._wait_for_video_processing(timeout=180)
            
            if not success:
                await self._take_screenshot("video_processing_failed")
                return False, message
            
            await self._delay(2, 3)
            await self._take_screenshot("03_video_ready", send_telegram=True)
            
            # 6. Close popups
            logger.info("Step 5: Handling popups...")
            await self._close_popups()
            await self._delay(1, 2)
            
            # 7. Input caption
            logger.info("Step 6: Adding caption...")
            await self._input_caption(caption)
            await self._delay(2, 3)
            
            # 8. Close any remaining popups
            await self._close_popups()
            await self._delay(1, 2)
            
            # 9. Screenshot sebelum post
            await self._take_screenshot("04_before_post", send_telegram=True)
            
            # 10. Cari dan klik tombol Post
            logger.info("Step 7: Finding Post button...")
            
            # Delay seperti user yang review
            await self._delay(5, 8)
            
            post_button = await self._find_post_button()
            
            if not post_button:
                await self._take_screenshot("post_button_not_found")
                return False, "Tombol Post tidak ditemukan"
            
            # 11. Klik Post
            logger.info("Step 8: Clicking Post button...")
            clicked = await self._safe_click(post_button, "Post button")
            
            if not clicked:
                # Retry dengan mencari ulang button
                await self._delay(2, 3)
                post_button = await self._find_post_button()
                if post_button:
                    clicked = await self._safe_click(post_button, "Post button (retry)")
            
            await self._delay(3, 5)
            await self._take_screenshot("05_after_post_click", send_telegram=True)
            
            # 12. Tunggu upload selesai
            logger.info("Step 9: Waiting for upload to complete...")
            success, message = await self._wait_for_upload_complete(timeout=180)
            
            await self._take_screenshot("06_final", send_telegram=True)
            
            if success:
                await send_telegram_message(f"✅ Upload berhasil!\n📹 {video_file.name}")
            else:
                await send_telegram_message(f"❌ Upload gagal!\n📹 {video_file.name}\n💬 {message}")
            
            return success, message
            
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            await self._take_screenshot("error")
            return False, f"Upload error: {str(e)}"
        
        finally:
            await self._close_browser()
    
    async def test_connection(self) -> Tuple[bool, str]:
        """Test koneksi dan session"""
        try:
            await self._init_browser(headless=True)
            
            if await self._navigate_to_upload():
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
