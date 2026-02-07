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
        
        # Bersihkan lock file jika browser sebelumnya crash
        lock_files = [
            BROWSER_PROFILE_DIR / "Default" / "LOCK",
            BROWSER_PROFILE_DIR / "SingletonLock",
            BROWSER_PROFILE_DIR / "SingletonSocket",
            BROWSER_PROFILE_DIR / "SingletonCookie",
        ]
        for lock_file in lock_files:
            try:
                if lock_file.exists():
                    lock_file.unlink()
                    logger.debug(f"Removed stale lock: {lock_file}")
            except Exception as e:
                logger.debug(f"Could not remove lock {lock_file}: {e}")
        
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
            # Jangan close page terpisah pada persistent context
            # karena bisa menyebabkan race condition
            if self.context:
                await self.context.close()
        except Exception as e:
            logger.debug(f"Error closing context: {e}")
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.debug(f"Error stopping playwright: {e}")
        
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
                
                # Navigate dan tunggu sampai halaman stabil
                response = await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await self._delay(3, 5)
                
                # Tunggu sampai tidak ada redirect lagi
                for _ in range(3):
                    old_url = self.page.url
                    await asyncio.sleep(2)
                    if self.page.url == old_url:
                        break
                
                current_url = self.page.url
                logger.info(f"Current URL: {current_url}")
                
                # Cek apakah redirect ke login
                if "login" in current_url.lower():
                    logger.warning("Redirected to login page - session may be expired")
                    await self._take_screenshot("login_redirect")
                    
                    # Coba refresh cookies dan retry URL ini sekali
                    try:
                        cookies = await self._load_cookies()
                        await self.context.add_cookies(cookies)
                        logger.info("Re-loaded cookies, retrying...")
                        await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        await self._delay(5, 8)
                        
                        if "login" not in self.page.url.lower():
                            current_url = self.page.url
                            logger.info(f"Cookie refresh worked! URL: {current_url}")
                        else:
                            continue
                    except:
                        continue
                
                # Tutup popup yang mungkin muncul
                await self._close_popups()
                await self._delay(1, 2)
                
                # Cek apakah ada form upload
                has_upload = await self._check_upload_page()
                if has_upload:
                    logger.info(f"Upload page found at: {url}")
                    return True
                
                # Jika URL mengandung upload/studio tapi belum detect form, 
                # tunggu lebih lama karena halaman mungkin masih loading
                if any(x in current_url.lower() for x in ['upload', 'studio']):
                    logger.info("URL looks correct, waiting longer for page to load...")
                    await self._delay(5, 8)
                    has_upload = await self._check_upload_page()
                    if has_upload:
                        logger.info(f"Upload page found after extra wait at: {current_url}")
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
                # Ignore transient errors di awal upload
                elapsed_err = int(asyncio.get_event_loop().time() - start_time)
                if elapsed_err > 30:
                    return False, error_check
                else:
                    logger.debug(f"Ignoring early error: {error_check}")
            
            # Cek apakah video sudah siap - gunakan kombinasi indikator
            # Caption editor (contenteditable) + Post button = paling reliable
            caption_editor_found = False
            post_button_found = False
            
            # Cek caption editor
            caption_selectors = [
                '[contenteditable="true"]',
                '[class*="DraftEditor"]',
                '[data-contents="true"]',
                '.public-DraftEditor-content',
                'div[class*="notranslate"][contenteditable="true"]',
            ]
            for selector in caption_selectors:
                try:
                    elem = await self.page.query_selector(selector)
                    if elem and await elem.is_visible():
                        caption_editor_found = True
                        break
                except:
                    continue
            
            # Cek post button
            post_selectors = [
                'button:has-text("Post"):not([disabled])',
                'button:has-text("Posting"):not([disabled])',
                '[data-e2e="post_video_button"]',
            ]
            for selector in post_selectors:
                try:
                    elem = await self.page.query_selector(selector)
                    if elem and await elem.is_visible():
                        post_button_found = True
                        break
                except:
                    continue
            
            # Video ready jika caption editor OR post button ditemukan
            if caption_editor_found:
                logger.info("Video ready: caption editor found")
                return True, "Video ready"
            
            if post_button_found:
                logger.info("Video ready: Post button found")
                return True, "Video ready"
            
            # Cek juga video preview yang lebih spesifik
            preview_selectors = [
                'video[src*="blob:"]',
                'video[src*="tiktok"]',
                '[class*="video-preview"] video',
                '[class*="VideoPreview"] video',
                '[class*="upload"] video[src]',
            ]
            for selector in preview_selectors:
                try:
                    elem = await self.page.query_selector(selector)
                    if elem and await elem.is_visible():
                        logger.info(f"Video preview found: {selector}")
                        # Tunggu 3 detik lagi agar caption editor juga muncul
                        await asyncio.sleep(3)
                        return True, "Video ready"
                except:
                    continue
            
            elapsed = int(asyncio.get_event_loop().time() - start_time)
            if elapsed % 15 == 0 and elapsed > 0:
                logger.info(f"Still processing... ({elapsed}s)")
                await self._take_screenshot(f"processing_{elapsed}s", send_telegram=False)
            
            await asyncio.sleep(2)
        
        await self._take_screenshot("video_processing_timeout", send_telegram=True)
        return False, "Timeout waiting for video processing"
    
    async def _wait_for_content_checks(self, timeout: int = 120) -> bool:
        """
        Tunggu sampai Content checks selesai (Music copyright check & Content check lite)
        TikTok WAJIB menyelesaikan checks sebelum Post bisa berhasil.
        Jika Post sebelum checks selesai → "Something went wrong"
        """
        logger.info("Waiting for content checks to complete...")
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                # Scroll ke bawah agar area Checks terlihat
                await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(0.5)
                
                # Method 1: Cari text "No issues found" via page content
                page_text = await self.page.evaluate('() => document.body.innerText')
                
                # Hitung berapa kali "No issues found" muncul
                no_issues_count = page_text.lower().count('no issues found')
                if no_issues_count >= 2:
                    logger.info(f"Content checks completed: Found {no_issues_count}x 'No issues found' in page text")
                    return True
                
                # Method 2: Cek jika ada "No issues found." elements visible
                no_issues_elements = await self.page.query_selector_all('text=/No issues found/')
                visible_count = 0
                for elem in no_issues_elements:
                    try:
                        if await elem.is_visible():
                            visible_count += 1
                    except:
                        continue
                
                if visible_count >= 2:
                    logger.info(f"Content checks completed: {visible_count} visible 'No issues found' elements")
                    return True
                
                # Method 3: Cek apakah ada teks spesifik dari kedua checks
                has_music_check = 'music copyright check' in page_text.lower()
                has_content_check = 'content check' in page_text.lower()
                has_no_issues = no_issues_count >= 1
                
                if has_music_check and has_content_check and has_no_issues:
                    # Setidaknya satu check selesai, tunggu sedikit lagi untuk yang kedua
                    await asyncio.sleep(5)
                    page_text2 = await self.page.evaluate('() => document.body.innerText')
                    if page_text2.lower().count('no issues found') >= 2:
                        logger.info("Content checks completed after extra wait")
                        return True
                
            except Exception as e:
                logger.debug(f"Check iteration error: {e}")
            
            elapsed = int(asyncio.get_event_loop().time() - start_time)
            if elapsed % 15 == 0 and elapsed > 0:
                logger.info(f"Still waiting for content checks... ({elapsed}s) [found {no_issues_count if 'no_issues_count' in dir() else '?'} 'No issues found']")
                await self._take_screenshot(f"content_check_{elapsed}s", send_telegram=False)
            
            await asyncio.sleep(3)
        
        # Timeout - cek sekali lagi
        try:
            final_text = await self.page.evaluate('() => document.body.innerText')
            final_count = final_text.lower().count('no issues found')
            if final_count >= 1:
                logger.warning(f"Content checks timeout but found {final_count} 'No issues found', proceeding...")
                return True
        except:
            pass
        
        logger.warning("Content checks did not complete in time")
        await self._take_screenshot("content_checks_timeout", send_telegram=True)
        return False
    
    async def _simulate_human_behavior(self):
        """Simulasi perilaku manusia: scroll, mouse move, dll"""
        try:
            # Random scroll
            await self.page.evaluate('''() => {
                window.scrollBy(0, Math.random() * 100 + 50);
            }''')
            await self._delay(0.5, 1)
            
            # Scroll back
            await self.page.evaluate('''() => {
                window.scrollBy(0, -(Math.random() * 50 + 25));
            }''')
            await self._delay(0.3, 0.6)
            
            # Random mouse movement (viewport_size is a property, NOT a coroutine)
            viewport = self.page.viewport_size
            if viewport:
                for _ in range(random.randint(2, 4)):
                    x = random.randint(100, min(viewport['width'] - 100, 1200))
                    y = random.randint(100, min(viewport['height'] - 100, 700))
                    await self.page.mouse.move(x, y)
                    await self._delay(0.1, 0.3)
            
            logger.debug("Human behavior simulation completed")
        except Exception as e:
            logger.debug(f"Human behavior simulation error: {e}")
    
    async def _check_for_errors(self) -> Optional[str]:
        """Cek error messages di halaman"""
        # Cari elemen yang kemungkinan besar berisi pesan error
        error_selectors = [
            '[role="alert"]',
            '[class*="toast"][class*="error"]',
            '[class*="Toast"][class*="error"]',
            '[class*="error-message"]',
            '[class*="ErrorMessage"]',
            '[class*="snackbar"][class*="error"]',
        ]
        
        error_keywords = [
            'something went wrong', 'failed', 'gagal', 'tidak dapat', 'cannot', 
            'try again', 'coba lagi', 'kesalahan', 'rejected', 'ditolak',
            'video cannot be uploaded', 'upload failed', 'network error',
        ]
        
        for selector in error_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                for elem in elements:
                    try:
                        if not await elem.is_visible():
                            continue
                        text = await elem.text_content()
                        if text:
                            text_lower = text.lower().strip()
                            # Skip teks yang terlalu pendek atau terlalu panjang (bukan error message)
                            if len(text_lower) < 5 or len(text_lower) > 500:
                                continue
                            for keyword in error_keywords:
                                if keyword in text_lower:
                                    return text.strip()[:200]
                    except:
                        continue
            except:
                continue
        
        return None
    
    async def _detect_something_went_wrong(self) -> bool:
        """
        Deteksi apakah ada toast/notifikasi 'Something went wrong' di halaman.
        Returns True jika error terdeteksi.
        """
        try:
            # Method 1: Cari lewat page text (paling reliable)
            page_text = await self.page.evaluate('() => document.body.innerText.substring(0, 5000)')
            error_phrases = [
                'something went wrong',
                'replace it with a different video',
                'video cannot be uploaded',
            ]
            for phrase in error_phrases:
                if phrase in page_text.lower():
                    return True
            
            # Method 2: Cari lewat selectors
            toast_selectors = [
                '[class*="toast"]',
                '[class*="Toast"]',
                '[class*="Snackbar"]',
                '[class*="snackbar"]',
                '[class*="notification"]',
                '[class*="Notification"]',
                '[role="alert"]',
                '[class*="TUXSnackbar"]',
            ]
            
            for selector in toast_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    for elem in elements:
                        if await elem.is_visible():
                            text = await elem.text_content()
                            if text and 'something went wrong' in text.lower():
                                return True
                except:
                    continue
                    
        except:
            pass
        
        return False
    
    async def _dismiss_error_toast(self) -> bool:
        """
        Dismiss/tutup toast error yang muncul.
        Returns True jika berhasil dismiss.
        """
        try:
            # Toast TikTok biasanya otomatis hilang dalam ~5 detik
            # Tapi kita coba dismiss lebih cepat
            
            # Coba klik tombol close/dismiss
            dismiss_selectors = [
                '[class*="toast"] button',
                '[class*="Toast"] button',
                '[class*="Snackbar"] button',
                '[class*="TUXSnackbar"] button',
                '[role="alert"] button',
                'button[aria-label="Close"]',
                'button[aria-label="Dismiss"]',
            ]
            
            for selector in dismiss_selectors:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn and await btn.is_visible():
                        await btn.click(force=True)
                        logger.info(f"Dismissed toast with: {selector}")
                        await self._delay(1, 2)
                        return True
                except:
                    continue
            
            # Klik di area kosong untuk dismiss
            await self.page.mouse.click(700, 400)
            await self._delay(1, 2)
            
            # Tekan Escape
            await self.page.keyboard.press('Escape')
            await self._delay(1, 2)
            
            return True
        except:
            return False
    
    async def _handle_upload_error(self) -> bool:
        """
        Handle error seperti 'Something went wrong' dengan dismiss dan retry.
        Returns True jika error ditemukan dan di-handle.
        """
        if await self._detect_something_went_wrong():
            logger.warning("Detected 'Something went wrong' error!")
            await self._take_screenshot("error_something_went_wrong")
            await self._dismiss_error_toast()
            return True
        
        return False
    
    async def _handle_continue_to_post_popup(self) -> bool:
        """
        Handle popup 'Continue to post?' yang muncul saat video masih dicek
        Klik 'Post now' untuk lanjut posting
        Returns True jika popup ditemukan dan di-handle
        """
        try:
            # Cek apakah ada popup "Continue to post?"
            popup_texts = ['continue to post', 'post now', 'still checking']
            
            # Cari dialog/modal
            dialogs = await self.page.query_selector_all('[role="dialog"], [class*="modal"], [class*="Modal"], [class*="popup"], [class*="Popup"], [class*="dialog"], [class*="Dialog"]')
            
            for dialog in dialogs:
                try:
                    if not await dialog.is_visible():
                        continue
                    text = await dialog.text_content()
                    if not text:
                        continue
                    text_lower = text.lower()
                    
                    if any(pt in text_lower for pt in popup_texts):
                        logger.info("Found 'Continue to post?' popup")
                        
                        # Cari tombol "Post now"
                        post_now_selectors = [
                            'button:has-text("Post now")',
                            'button:has-text("Post Now")',
                            'button:has-text("Posting")',
                            '[class*="primary"]:has-text("Post")',
                            '[class*="confirm"]:has-text("Post")',
                        ]
                        
                        for selector in post_now_selectors:
                            try:
                                btn = await self.page.query_selector(selector)
                                if btn and await btn.is_visible():
                                    await btn.click()
                                    logger.info(f"Clicked 'Post now' button")
                                    await self._delay(2, 3)
                                    return True
                            except:
                                continue
                        
                        # Fallback: cari button dengan warna pink/merah (primary button)
                        buttons = await dialog.query_selector_all('button')
                        for btn in buttons:
                            try:
                                btn_text = await btn.text_content()
                                if btn_text and 'post' in btn_text.lower() and 'cancel' not in btn_text.lower():
                                    await btn.click()
                                    logger.info(f"Clicked button: {btn_text}")
                                    await self._delay(2, 3)
                                    return True
                            except:
                                continue
                except:
                    continue
        except Exception as e:
            logger.error(f"Error in _handle_continue_to_post_popup: {e}")
        
        return False
    
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
                    # Klik untuk focus
                    await elem.click()
                    await self._delay(0.5, 1)
                    
                    # Clear existing text dengan multiple method
                    # Method 1: Ctrl+A lalu Delete
                    await self.page.keyboard.press('Control+A')
                    await self._delay(0.2, 0.4)
                    await self.page.keyboard.press('Backspace')
                    await self._delay(0.3, 0.5)
                    
                    # Method 2: Pastikan benar-benar kosong
                    await self.page.keyboard.press('Control+A')
                    await self._delay(0.1, 0.2)
                    await self.page.keyboard.press('Delete')
                    await self._delay(0.3, 0.5)
                    
                    # Type caption - gunakan keyboard.type yang lebih reliable
                    # Split caption jika panjang untuk menghindari timeout
                    if len(caption) > 100:
                        # Untuk caption panjang, ketik langsung (lebih cepat)
                        await self.page.keyboard.type(caption, delay=50)
                    else:
                        await self._type_like_human(caption, fast=True)
                    
                    await self._delay(0.5, 1)
                    
                    # Verifikasi caption diinput
                    try:
                        text_content = await elem.text_content()
                        if text_content and len(text_content.strip()) > 0:
                            logger.info(f"Caption added successfully: {text_content[:50]}...")
                            return True
                        else:
                            # Coba lagi dengan metode fill
                            logger.warning("Caption appears empty, retrying with fill...")
                            await elem.click()
                            await self._delay(0.3, 0.5)
                            await elem.fill(caption)
                            await self._delay(0.5, 1)
                            return True
                    except:
                        # Anggap berhasil jika tidak bisa verifikasi
                        logger.info("Caption input completed (cannot verify)")
                        return True
            except Exception as e:
                logger.debug(f"Caption selector {selector} failed: {e}")
                continue
        
        # Fallback: coba input via JavaScript
        try:
            logger.warning("Trying JavaScript caption input as fallback...")
            result = await self.page.evaluate(f'''
                () => {{
                    const editors = document.querySelectorAll('[contenteditable="true"]');
                    for (const editor of editors) {{
                        if (editor.offsetParent !== null) {{  // visible check
                            editor.focus();
                            editor.textContent = '';
                            editor.textContent = {json.dumps(caption)};
                            editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            return true;
                        }}
                    }}
                    return false;
                }}
            ''')
            if result:
                logger.info("Caption added via JavaScript fallback")
                return True
        except Exception as e:
            logger.debug(f"JS caption fallback failed: {e}")
        
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
        
        # URL patterns yang menandakan SUKSES (sudah di-redirect ke halaman content)
        success_patterns = [
            'tiktokstudio/content',
            'creator-center/content',
            '/manage',
            '/profile',
            '/@',
        ]
        # URL patterns halaman upload (BUKAN sukses)
        upload_patterns = ['/upload', 'studio/upload', 'creator-center/upload']
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            current_url = self.page.url
            current_url_lower = current_url.lower()
            elapsed = int(asyncio.get_event_loop().time() - start_time)
            
            # Cek apakah URL sekarang adalah halaman sukses
            is_upload_page = any(u in current_url_lower for u in upload_patterns)
            is_success_page = any(p in current_url_lower for p in success_patterns)
            
            if is_success_page and not is_upload_page:
                logger.info(f"Upload success! URL: {current_url}")
                return True, "Video berhasil diupload ke TikTok!"
            
            # Jika redirect ke login → session expired
            if 'login' in current_url_lower and '/upload' not in current_url_lower:
                return False, "Session expired - redirect ke login"
            
            # Cek success messages di halaman
            success_texts = [
                'Your video is being uploaded',
                'Video posted',
                'Upload complete',
                'Berhasil diposting',
                'Video telah diposting',
                'Your video has been posted',
                'Successfully posted',
                'Your video is now live',
                'Manage your posts',
                'Your videos',
            ]
            
            for text in success_texts:
                try:
                    elem = await self.page.query_selector(f'text="{text}"')
                    if elem and await elem.is_visible():
                        found_text = await elem.text_content()
                        logger.info(f"Success indicator found: {found_text}")
                        return True, "Video berhasil diupload ke TikTok!"
                except:
                    continue
            
            # Cek lewat body text
            try:
                page_text = await self.page.evaluate('() => document.body.innerText.substring(0, 3000)')
                page_text_lower = page_text.lower()
                for text in ['your video is being uploaded', 'manage your posts', 'your video has been posted', 'your videos']:
                    if text in page_text_lower and not is_upload_page:
                        logger.info(f"Success text found in page body: {text}")
                        return True, "Video berhasil diupload ke TikTok!"
            except:
                pass
            
            # Cek apakah ada popup "Continue to post?"
            popup_handled = await self._handle_continue_to_post_popup()
            if popup_handled:
                logger.info("Handled popup during wait")
                await self._delay(3, 5)
            
            # Cek error
            error = await self._check_for_errors()
            if error:
                logger.warning(f"Error detected during upload wait: {error}")
                if elapsed > 30:
                    return False, f"Upload error: {error}"
            
            # Log progress
            if elapsed % 20 == 0 and elapsed > 0:
                logger.info(f"Upload in progress... ({elapsed}s) URL: {current_url}")
            
            # Screenshot setiap 40 detik
            if elapsed - last_screenshot_time >= 40:
                await self._take_screenshot(f"upload_progress_{elapsed}s", send_telegram=False)
                last_screenshot_time = elapsed
            
            await asyncio.sleep(3)
        
        # Timeout - final check: mungkin sudah sukses tapi text belum terdeteksi
        current_url_lower = self.page.url.lower()
        is_upload_page = any(u in current_url_lower for u in upload_patterns)
        is_success_page = any(p in current_url_lower for p in success_patterns)
        if is_success_page and not is_upload_page:
            logger.info(f"Upload success detected at timeout! URL: {self.page.url}")
            return True, "Video berhasil diupload ke TikTok!"
        
        await self._take_screenshot("upload_timeout", send_telegram=True)
        return False, "Upload timeout - cek screenshot untuk status terakhir"
    
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
            
            # 9. PENTING: Tunggu content checks selesai (Music copyright & Content check)
            # Ini KRUSIAL - jika Post sebelum checks selesai → "Something went wrong"
            logger.info("Step 7: Waiting for content checks...")
            checks_ok = await self._wait_for_content_checks(timeout=120)
            
            if not checks_ok:
                logger.warning("Content checks did not complete - upload may fail")
                await self._take_screenshot("content_checks_incomplete")
                # Tetap lanjut, tapi catat bahwa mungkin gagal
            
            await self._delay(3, 5)
            
            # 10. Simulasi human behavior
            logger.info("Simulating human behavior...")
            await self._simulate_human_behavior()
            await self._delay(2, 3)
            
            # 11. Screenshot sebelum post
            await self._take_screenshot("04_before_post", send_telegram=True)
            
            # 12. POST dengan retry loop
            # TikTok sering menampilkan "Something went wrong" yang bisa di-retry
            max_post_attempts = 3
            post_success = False
            
            for post_attempt in range(max_post_attempts):
                if post_attempt > 0:
                    logger.info(f"=== Post retry attempt {post_attempt + 1}/{max_post_attempts} ===")
                    await send_telegram_message(f"🔄 Retry Post ({post_attempt + 1}/{max_post_attempts})...")
                
                # Scroll ke bawah untuk lihat Post button
                logger.info("Step 8: Finding Post button...")
                await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await self._delay(2, 3)
                
                post_button = await self._find_post_button()
                
                if not post_button:
                    logger.warning("Post button not found, waiting and retrying...")
                    await self._delay(8, 12)
                    post_button = await self._find_post_button()
                
                if not post_button:
                    # Coba cek apakah button disabled
                    disabled_btn = await self.page.query_selector('button:has-text("Post")[disabled]')
                    if disabled_btn:
                        logger.warning("Post button is disabled, waiting for it to enable...")
                        # Tunggu sampai button enabled
                        for _ in range(15):
                            await asyncio.sleep(3)
                            post_button = await self._find_post_button()
                            if post_button:
                                break
                    
                    if not post_button:
                        await self._take_screenshot("post_button_not_found")
                        return False, "Tombol Post tidak ditemukan"
                
                # Klik Post
                logger.info("Step 9: Clicking Post button...")
                await self._delay(1, 2)
                clicked = await self._safe_click(post_button, "Post button")
                
                if not clicked:
                    await self._delay(2, 3)
                    post_button = await self._find_post_button()
                    if post_button:
                        clicked = await self._safe_click(post_button, "Post button (force retry)")
                
                if not clicked:
                    await self._take_screenshot("post_click_failed")
                    return False, "Gagal klik tombol Post"
                
                # Tunggu sebentar untuk cek reaksi halaman
                await self._delay(5, 8)
                
                # Handle popup "Continue to post?"
                popup_handled = await self._handle_continue_to_post_popup()
                if popup_handled:
                    logger.info("Handled 'Continue to post?' popup")
                    await self._delay(3, 5)
                
                # Cek apakah muncul error "Something went wrong"
                await self._delay(3, 5)
                error_detected = await self._detect_something_went_wrong()
                
                if error_detected:
                    logger.warning(f"'Something went wrong' detected on attempt {post_attempt + 1}")
                    await self._take_screenshot(f"error_attempt_{post_attempt + 1}")
                    await self._dismiss_error_toast()
                    
                    if post_attempt < max_post_attempts - 1:
                        # Tunggu sebelum retry - semakin lama tiap retry
                        wait_time = 15 * (post_attempt + 1)  # 15s, 30s
                        logger.info(f"Waiting {wait_time}s before retry...")
                        await self._delay(wait_time, wait_time + 5)
                        
                        # Tunggu content checks lagi sebelum retry
                        logger.info("Re-checking content checks before retry...")
                        await self._wait_for_content_checks(timeout=60)
                        await self._delay(3, 5)
                        await self._simulate_human_behavior()
                        await self._delay(2, 3)
                        continue
                    else:
                        # Semua attempt gagal
                        await self._take_screenshot("all_post_attempts_failed")
                        return False, "Upload gagal: 'Something went wrong' setelah 3x retry. Video mungkin bermasalah."
                else:
                    # Tidak ada error → Post berhasil diklik
                    post_success = True
                    break
            
            await self._take_screenshot("05_after_post_click", send_telegram=True)
            
            # 14. Tunggu upload selesai
            logger.info("Step 10: Waiting for upload to complete...")
            success, message = await self._wait_for_upload_complete(timeout=180)
            
            await self._take_screenshot("06_final", send_telegram=True)
            
            if success:
                await send_telegram_message(f"✅ Upload berhasil!\n📹 {video_file.name}")
            else:
                await send_telegram_message(f"❌ Upload gagal!\n📹 {video_file.name}\n💬 {message}")
            
            return success, message
            
        except PlaywrightTimeout as e:
            logger.error(f"Upload timeout: {e}")
            try:
                await self._take_screenshot("timeout_error")
                await send_telegram_message(f"⏰ Upload timeout!\n📹 {video_file.name}")
            except:
                pass
            return False, f"Upload timeout: browser operation timed out"
            
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            try:
                await self._take_screenshot("error")
                await send_telegram_message(f"❌ Upload error!\n📹 {video_file.name}\n💬 {str(e)[:100]}")
            except:
                pass
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
