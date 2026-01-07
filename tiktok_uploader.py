"""
TikTok Uploader menggunakan Playwright
Upload video ke TikTok dengan reuse cookies/session
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Optional, Tuple
import random

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config import (
    TIKTOK_COOKIES_PATH, 
    HEADLESS_UPLOAD,
    TIKTOK_DEFAULT_CAPTION,
    COOKIES_DIR
)
from logger_setup import setup_logger

logger = setup_logger("tiktok_uploader")

TIKTOK_UPLOAD_URL = "https://www.tiktok.com/upload"
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
                await page.keyboard.type(char, delay=random.randint(30, 100))
    
    async def _init_browser(self, headless: bool = True):
        """Inisialisasi browser dengan persistent profile (sama seperti login)"""
        self._playwright = await async_playwright().start()
        
        # Gunakan persistent context (sama dengan saat login)
        # Ini akan memakai session yang sudah ada
        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        
        self.context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=headless,
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            locale='id-ID',
            timezone_id='Asia/Jakarta',
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        
        # Anti-detection scripts
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['id-ID', 'id', 'en-US', 'en']
            });
        """)
        
        # Juga load cookies sebagai backup
        try:
            cookies = await self._load_cookies()
            await self.context.add_cookies(cookies)
        except:
            pass
        
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        
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
                return False
            
            # Screenshot untuk debug
            try:
                screenshot_path = COOKIES_DIR / "debug_login_check.png"
                await self.page.screenshot(path=str(screenshot_path))
                logger.info(f"Screenshot saved to {screenshot_path}")
            except:
                pass
            
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
            # Screenshot untuk debug
            try:
                screenshot_path = COOKIES_DIR / "debug_screenshot.png"
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
            
            # Screenshot untuk debug
            try:
                await self.page.screenshot(path=str(COOKIES_DIR / "debug_before_input.png"))
                logger.info("Screenshot saved: debug_before_input.png")
            except:
                pass
            
            # Cek apakah ada iframe yang perlu dimasuki
            file_input = None
            frames_to_check = [self.page] + self.page.frames
            
            # Selector yang lebih lengkap untuk input file
            file_input_selectors = [
                'input[type="file"][accept*="video"]',
                'input[type="file"][accept*="mp4"]',
                'input[type="file"]',
                'input[name*="upload"]',
                'input[name*="file"]',
                '[data-e2e="upload-input"]',
                '[class*="upload"] input[type="file"]',
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
            
            # Screenshot setelah pencarian
            try:
                await self.page.screenshot(path=str(COOKIES_DIR / "debug_after_search.png"))
            except:
                pass
            
            if not file_input:
                # Log HTML untuk debug
                try:
                    html_content = await self.page.content()
                    with open(str(COOKIES_DIR / "debug_page.html"), "w", encoding="utf-8") as f:
                        f.write(html_content)
                    logger.info("Page HTML saved to debug_page.html")
                except:
                    pass
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
            
            while waited < max_wait:
                # Cek apakah ada error (tapi skip beberapa detik pertama)
                if waited > 15:  # Baru cek error setelah 15 detik
                    error_element = await self.page.query_selector('[class*="error"]:not([class*="error-"]), [class*="Error"]:not([class*="Error-"])')
                    if error_element:
                        error_text = await error_element.text_content()
                        if error_text and "error" in error_text.lower():
                            return False, f"Upload error: {error_text}"
                
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
            
            # Tutup modal popup jika ada (copyright check, dll)
            logger.info("Checking for modal popups...")
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
                await self._random_delay(0.3, 0.5)
                await self.page.keyboard.press('Control+A')
                await self._random_delay(0.1, 0.3)
                
                # Ketik caption
                await self.page.keyboard.type(caption, delay=random.randint(20, 50))
                
                logger.info("Caption added")
            else:
                logger.warning("Caption input not found, proceeding without caption")
            
            await self._random_delay(2, 4)
            
            # Klik Post button - harus yang di form, bukan di sidebar
            logger.info("Looking for Post button...")
            
            # Screenshot untuk debug
            await self.page.screenshot(path='debug_looking_post.png')
            
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
                await self.page.screenshot(path='debug_post_button.png')
                return False, "Post button tidak ditemukan"
            
            # Scroll ke button dan klik
            logger.info("Clicking Post button...")
            
            # Scroll ke bawah halaman dulu untuk memastikan button terlihat
            await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await self._random_delay(1, 2)
            
            await post_button.scroll_into_view_if_needed()
            await self._random_delay(0.5, 1)
            
            # Screenshot sebelum klik
            await self.page.screenshot(path='debug_before_post.png')
            
            # Ambil bounding box button
            box = await post_button.bounding_box()
            if box:
                logger.info(f"Button position: x={box['x']}, y={box['y']}, w={box['width']}, h={box['height']}")
            
            # Coba berbagai metode klik
            clicked = False
            
            # Metode 1: Klik dengan mouse di tengah button
            if box and not clicked:
                try:
                    x = box['x'] + box['width'] / 2
                    y = box['y'] + box['height'] / 2
                    await self.page.mouse.click(x, y)
                    clicked = True
                    logger.info(f"Clicked using mouse at ({x}, {y})")
                except Exception as e:
                    logger.warning(f"Mouse click failed: {e}")
            
            # Metode 2: Normal click dengan force
            if not clicked:
                try:
                    await post_button.click(force=True, timeout=5000)
                    clicked = True
                    logger.info("Clicked using force click")
                except Exception as e:
                    logger.warning(f"Force click failed: {e}")
            
            # Metode 3: JavaScript click
            if not clicked:
                try:
                    await post_button.evaluate('el => el.click()')
                    clicked = True
                    logger.info("Clicked using JavaScript")
                except Exception as e:
                    logger.warning(f"JS click failed: {e}")
            
            # Metode 4: dispatchEvent
            if not clicked:
                try:
                    await post_button.evaluate('''el => {
                        el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                    }''')
                    clicked = True
                    logger.info("Clicked using dispatchEvent")
                except Exception as e:
                    logger.warning(f"dispatchEvent failed: {e}")
            
            # Screenshot setelah klik
            await self._random_delay(2, 3)
            await self.page.screenshot(path='debug_after_post.png')
            
            logger.info("Post button clicked, waiting for upload to complete...")
            
            # Tunggu lebih lama untuk proses upload
            await self._random_delay(5, 8)
            
            # Tunggu konfirmasi posting - proses bisa lama
            max_confirm_wait = 120  # 2 menit
            confirm_waited = 0
            
            while confirm_waited < max_confirm_wait:
                # Screenshot setiap 20 detik untuk debug
                if confirm_waited > 0 and confirm_waited % 20 == 0:
                    try:
                        screenshot_path = f'debug_upload_{confirm_waited}s.png'
                        await self.page.screenshot(path=screenshot_path)
                        logger.info(f"Screenshot saved: {screenshot_path}")
                    except:
                        pass
                
                current_url = self.page.url
                logger.debug(f"Current URL: {current_url}")
                
                # Cek apakah sudah redirect ke manage/profile (berarti sudah selesai upload)
                if any(x in current_url.lower() for x in ['manage', 'profile', '/@', '/content']):
                    logger.info(f"Redirected to: {current_url} - Upload successful!")
                    return True, "Video berhasil diupload ke TikTok!"
                
                # Cek success indicator (hanya yang benar-benar menunjukkan posting selesai)
                success_indicators = [
                    'text=Your video is being uploaded to TikTok',
                    'text=Video posted',
                    'text=successfully',
                    'text=Video sedang diproses',
                    'text=Berhasil diposting',
                    'text=Video telah diposting',
                    'text=Posted to TikTok',
                ]
                
                for indicator in success_indicators:
                    try:
                        element = await self.page.query_selector(indicator)
                        if element and await element.is_visible():
                            text = await element.text_content()
                            logger.info(f"Success indicator found: {text}")
                            # Tunggu sebentar lagi untuk memastikan
                            await self._random_delay(3, 5)
                            return True, "Video berhasil diupload ke TikTok!"
                    except:
                        continue
                
                # Cek apakah masih ada progress upload
                progress_selectors = [
                    '[class*="progress"]',
                    '[class*="Progress"]',
                    '[class*="loading"]',
                    '[class*="uploading"]',
                ]
                
                is_still_uploading = False
                for selector in progress_selectors:
                    try:
                        elem = await self.page.query_selector(selector)
                        if elem and await elem.is_visible():
                            is_still_uploading = True
                            if confirm_waited % 10 == 0:
                                logger.info(f"Still uploading... ({confirm_waited}s)")
                            break
                    except:
                        continue
                
                # Cek error
                error_selectors = [
                    'text=failed',
                    'text=error',
                    'text=gagal',
                    'text=tidak dapat',
                    '[class*="error"]:visible',
                ]
                
                for selector in error_selectors:
                    try:
                        elem = await self.page.query_selector(selector)
                        if elem and await elem.is_visible():
                            error_text = await elem.text_content()
                            if error_text and len(error_text) > 3:
                                return False, f"Upload failed: {error_text}"
                    except:
                        continue
                
                await asyncio.sleep(3)
                confirm_waited += 3
            
            # Ambil screenshot terakhir
            try:
                await self.page.screenshot(path='debug_final.png')
                logger.info("Final screenshot saved: debug_final.png")
            except:
                pass
            
            # Cek URL terakhir
            final_url = self.page.url
            if "upload" in final_url.lower():
                return False, f"Upload mungkin gagal - masih di halaman upload. Cek manual di TikTok."
            
            return True, "Video diproses oleh TikTok (cek di profil)"
            
        except Exception as e:
            logger.error(f"Upload failed with exception: {e}")
            
            # Screenshot untuk debug
            if self.page:
                try:
                    await self.page.screenshot(path='debug_error.png')
                except:
                    pass
            
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
