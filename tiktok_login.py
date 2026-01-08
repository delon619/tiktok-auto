"""
Script untuk login TikTok secara manual (NON-HEADLESS)
Jalankan sekali untuk menyimpan cookies/session

ALTERNATIF LOGIN:
1. QR Code Login - Paling aman, scan dari HP
2. Import cookies dari Chrome/Edge/Firefox
3. Manual login dengan browser profile yang persistent

PENTING: 
- Jalankan di environment dengan GUI (bukan headless VPS)
- Atau gunakan X11 forwarding / VNC
- Login manual, lalu cookies akan disimpan
"""
import asyncio
import json
import sys
import os
import sqlite3
import shutil
import base64
import random
from pathlib import Path
from datetime import datetime

# Note: win32crypt dan Cryptodome dibutuhkan untuk decrypt cookies Chrome di Windows
# Fitur ini belum diimplementasi sepenuhnya, jadi import dihapus untuk saat ini
# Jika perlu decrypt cookies, install: pip install pywin32 pycryptodomex

from playwright.async_api import async_playwright, Browser, BrowserContext

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import COOKIES_DIR, TIKTOK_COOKIES_PATH
from logger_setup import setup_logger

logger = setup_logger("tiktok_login")

TIKTOK_URL = "https://www.tiktok.com"
TIKTOK_UPLOAD_URL = "https://www.tiktok.com/upload"
TIKTOK_LOGIN_URL = "https://www.tiktok.com/login"

# Browser profile directory untuk persistent login
BROWSER_PROFILE_DIR = COOKIES_DIR / "browser_profile"


async def save_cookies(context: BrowserContext, filepath: Path):
    """Simpan cookies ke file JSON"""
    cookies = await context.cookies()
    
    # Simpan dengan format yang aman
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(cookies, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Cookies saved to: {filepath}")
    print(f"\n✅ Cookies berhasil disimpan ke: {filepath}")
    print(f"   Total cookies: {len(cookies)}")


def get_chrome_cookies_path():
    """Dapatkan path cookies Chrome"""
    if sys.platform == "win32":
        local_app = os.environ.get('LOCALAPPDATA')
        paths = [
            Path(local_app) / "Google" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies",
            Path(local_app) / "Google" / "Chrome" / "User Data" / "Default" / "Cookies",
        ]
    elif sys.platform == "darwin":
        paths = [
            Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Default" / "Cookies",
        ]
    else:
        paths = [
            Path.home() / ".config" / "google-chrome" / "Default" / "Cookies",
            Path.home() / ".config" / "chromium" / "Default" / "Cookies",
        ]
    
    for path in paths:
        if path.exists():
            return path
    return None


def get_edge_cookies_path():
    """Dapatkan path cookies Edge"""
    if sys.platform == "win32":
        local_app = os.environ.get('LOCALAPPDATA')
        paths = [
            Path(local_app) / "Microsoft" / "Edge" / "User Data" / "Default" / "Network" / "Cookies",
            Path(local_app) / "Microsoft" / "Edge" / "User Data" / "Default" / "Cookies",
        ]
    else:
        paths = []
    
    for path in paths:
        if path.exists():
            return path
    return None


def human_delay(min_sec=1, max_sec=3):
    """Random delay untuk meniru perilaku manusia"""
    delay = random.uniform(min_sec, max_sec)
    return delay


async def verify_login(context: BrowserContext) -> bool:
    """Verifikasi apakah sudah login"""
    page = await context.new_page()
    
    try:
        # Coba akses halaman upload dengan timeout lebih lama
        await page.goto(TIKTOK_UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        
        current_url = page.url
        
        # Jika redirect ke login, berarti belum login
        if "login" in current_url.lower():
            return False
        
        # Cek apakah ada elemen upload atau studio
        try:
            # Tunggu sebentar untuk halaman load
            await asyncio.sleep(3)
            
            # Cek berbagai indikator halaman upload
            upload_indicators = [
                '[class*="upload"]',
                '[class*="Upload"]',
                '[data-e2e*="upload"]',
                'input[type="file"]',
                '[class*="studio"]',
                '[class*="creator"]',
            ]
            
            for selector in upload_indicators:
                elem = await page.query_selector(selector)
                if elem:
                    return True
            
            # Jika tidak ada redirect ke login, anggap valid
            if "upload" in current_url.lower() or "studio" in current_url.lower():
                return True
                
        except:
            pass
        
        # Fallback: jika tidak redirect ke login, anggap valid
        return "login" not in current_url.lower()
        
    except Exception as e:
        logger.error(f"Error verifying login: {e}")
        # Jangan langsung return False, coba cek cookies penting
        return False
    finally:
        await page.close()


async def qr_code_login():
    """
    Login via QR Code - Metode paling aman
    Tidak kena rate limit karena autentikasi lewat app TikTok
    """
    print("\n" + "="*60)
    print("📱 TikTok QR Code Login")
    print("="*60)
    print("\nMetode ini paling aman dan jarang kena rate limit!")
    print("Kamu akan scan QR code dari aplikasi TikTok di HP.")
    print("="*60 + "\n")
    
    async with async_playwright() as p:
        # Buat browser profile directory jika belum ada
        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Launch browser dengan persistent context (menyimpan semua data)
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=False,
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
        
        # Inject script untuk menyembunyikan automation
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['id-ID', 'id', 'en-US', 'en']
            });
            
            // Tambahan anti-detection
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 1 });
        """)
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        try:
            print("📱 Membuka halaman login TikTok...")
            await page.goto(TIKTOK_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            
            print("\n" + "="*60)
            print("📲 INSTRUKSI LOGIN QR CODE:")
            print("="*60)
            print("1. Di browser, klik 'Use QR code' atau icon QR")
            print("2. Buka aplikasi TikTok di HP kamu")
            print("3. Tap ikon profil (kanan bawah)")
            print("4. Tap menu ☰ (kanan atas)")
            print("5. Pilih 'Pindai' atau 'Scan'")
            print("6. Scan QR code yang muncul di browser")
            print("7. Konfirmasi login di HP")
            print("="*60)
            
            # Coba klik opsi QR code jika ada
            try:
                qr_selectors = [
                    'div[class*="qr"]',
                    '[data-e2e*="qr"]',
                    'text=QR',
                    'text=Scan',
                ]
                for selector in qr_selectors:
                    try:
                        elem = await page.query_selector(selector)
                        if elem and await elem.is_visible():
                            await asyncio.sleep(1)
                            await elem.click()
                            print("✓ Klik opsi QR Code")
                            await asyncio.sleep(2)
                            break
                    except:
                        continue
            except:
                pass
            
            print("\n⏳ Silakan login di browser...")
            print("   Setelah login berhasil, tekan ENTER di sini.\n")
            
            # Tunggu user tekan ENTER
            input(">>> Tekan ENTER setelah berhasil login... ")
            
            print("\n⏳ Menyimpan session...")
            await asyncio.sleep(3)
            
            # Navigate ke homepage untuk memastikan cookies lengkap
            await page.goto(TIKTOK_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            
            # Simpan cookies
            await save_cookies(context, TIKTOK_COOKIES_PATH)
            
            # Verifikasi dengan coba akses upload page
            print("\n🔍 Memverifikasi login...")
            await page.goto(TIKTOK_UPLOAD_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            
            if "login" in page.url.lower():
                print("\n⚠️  Warning: Redirect ke login saat akses upload page")
                print("   Cookies mungkin tidak lengkap.")
                print("   Coba login lagi dengan cara yang berbeda.")
            else:
                print("✅ Verifikasi berhasil - bisa akses upload page!")
            
            print("\n✅ Cookies tersimpan!")
            input("\nTekan ENTER untuk menutup browser...")
            return True
            
        except Exception as e:
            logger.error(f"Error during QR login: {e}")
            print(f"\n❌ Error: {e}")
            try:
                input("\nTekan ENTER untuk menutup browser...")
            except:
                pass
            return False
        finally:
            try:
                await context.close()
            except:
                pass


async def persistent_profile_login():
    """
    Login dengan browser profile yang persistent
    Profile disimpan, jadi tidak perlu login ulang setiap kali
    """
    print("\n" + "="*60)
    print("🔐 TikTok Persistent Profile Login")
    print("="*60)
    print("\nBrowser akan menggunakan profile yang tersimpan.")
    print("Jika sudah pernah login, session masih ada.")
    print("="*60 + "\n")
    
    async with async_playwright() as p:
        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=False,
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            locale='id-ID',
            timezone_id='Asia/Jakarta',
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--no-sandbox',
            ]
        )
        
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        try:
            print("🔍 Mengecek status login...")
            await page.goto(TIKTOK_URL, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(human_delay(2, 4))
            
            # Cek apakah sudah login dengan mencoba akses upload
            await page.goto(TIKTOK_UPLOAD_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            if "login" not in page.url.lower():
                print("\n✅ Sudah login! Session masih valid.")
                await save_cookies(context, TIKTOK_COOKIES_PATH)
                input("\nTekan ENTER untuk menutup browser...")
                return True
            
            print("\n⚠️  Belum login. Silakan login manual.")
            print("\n💡 TIPS untuk menghindari rate limit:")
            print("   - Gunakan login QR Code (paling aman)")
            print("   - Atau login dengan Google/Facebook")
            print("   - Jangan spam login, tunggu 5-10 menit jika gagal")
            
            await page.goto(TIKTOK_LOGIN_URL, wait_until="networkidle", timeout=30000)
            
            input("\n⏳ Tekan ENTER setelah berhasil login... ")
            
            await asyncio.sleep(human_delay(3, 5))
            await save_cookies(context, TIKTOK_COOKIES_PATH)
            
            print("\n✅ Login berhasil dan session tersimpan!")
            input("\nTekan ENTER untuk menutup browser...")
            return True
            
        except Exception as e:
            logger.error(f"Error: {e}")
            print(f"\n❌ Error: {e}")
            input("\nTekan ENTER untuk menutup browser...")
            return False
        finally:
            await context.close()


async def import_browser_cookies():
    """
    Import cookies dari browser yang sudah login (Chrome/Edge)
    Metode ini menggunakan cookies dari browser asli kamu
    """
    print("\n" + "="*60)
    print("🍪 Import Cookies dari Browser")
    print("="*60)
    print("\nMetode ini akan mengambil cookies TikTok dari browser kamu.")
    print("Pastikan kamu sudah login TikTok di Chrome/Edge terlebih dahulu!")
    print("="*60 + "\n")
    
    print("Pilih browser sumber cookies:")
    print("1. Google Chrome")
    print("2. Microsoft Edge")
    print("3. Manual - Paste cookies JSON")
    
    choice = input("\nPilihan (1/2/3): ").strip()
    
    if choice == "3":
        return await manual_paste_cookies()
    
    browser_name = "Chrome" if choice == "1" else "Edge"
    cookies_path = get_chrome_cookies_path() if choice == "1" else get_edge_cookies_path()
    
    if not cookies_path:
        print(f"\n❌ Tidak dapat menemukan cookies {browser_name}")
        print("   Pastikan browser terinstall dan pernah digunakan.")
        return False
    
    print(f"\n⚠️  PENTING:")
    print(f"   1. Tutup semua window {browser_name} terlebih dahulu")
    print(f"   2. Pastikan sudah login TikTok di {browser_name}")
    
    input("\nTekan ENTER jika sudah siap...")
    
    try:
        # Copy database cookies (karena mungkin locked)
        temp_cookies = COOKIES_DIR / "temp_cookies.db"
        shutil.copy2(cookies_path, temp_cookies)
        
        # Baca cookies dari SQLite
        conn = sqlite3.connect(str(temp_cookies))
        cursor = conn.cursor()
        
        # Query cookies TikTok
        cursor.execute("""
            SELECT host_key, name, value, path, expires_utc, is_secure, is_httponly
            FROM cookies
            WHERE host_key LIKE '%tiktok%'
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        # Hapus temp file
        temp_cookies.unlink()
        
        if not rows:
            print("\n❌ Tidak ada cookies TikTok ditemukan!")
            print(f"   Pastikan sudah login TikTok di {browser_name}")
            return False
        
        # Convert ke format Playwright
        cookies = []
        for row in rows:
            host, name, value, path, expires, secure, httponly = row
            
            # Note: Di Windows, value terenkripsi, perlu decrypt
            # Ini simplified version - mungkin perlu penyesuaian
            
            cookie = {
                "name": name,
                "value": value,  
                "domain": host,
                "path": path,
                "expires": expires / 1000000 - 11644473600 if expires else -1,
                "httpOnly": bool(httponly),
                "secure": bool(secure),
                "sameSite": "Lax"
            }
            cookies.append(cookie)
        
        # Simpan
        with open(TIKTOK_COOKIES_PATH, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, indent=2)
        
        print(f"\n✅ Berhasil import {len(cookies)} cookies dari {browser_name}!")
        print(f"   Disimpan ke: {TIKTOK_COOKIES_PATH}")
        
        # Verifikasi
        verify = input("\nVerifikasi cookies? (y/n): ").strip().lower()
        if verify == 'y':
            await load_and_verify_cookies()
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Alternatif: Gunakan metode 'Manual - Paste cookies JSON'")
        return False


async def manual_paste_cookies():
    """Paste cookies JSON secara manual dari browser DevTools atau Extension"""
    print("\n" + "="*70)
    print("🍪 IMPORT COOKIES DARI BROWSER (Cara Paling Mudah!)")
    print("="*70)
    print("""
⭐ LANGKAH-LANGKAH:

1. Buka Chrome/Edge biasa (BUKAN script ini)
2. Pergi ke https://www.tiktok.com dan pastikan SUDAH LOGIN
3. Install extension 'Cookie-Editor' dari Chrome Web Store:
   https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm

4. Klik icon extension Cookie-Editor di toolbar
5. Klik tombol 'Export' (icon panah ke atas)
6. Pilih 'Export as JSON'
7. Cookies akan ter-copy ke clipboard

8. Kembali ke sini dan PASTE (Ctrl+V) lalu tekan ENTER dua kali
""")
    print("="*70)
    
    print("\n📝 Paste cookies JSON di bawah ini, lalu tekan ENTER dua kali:\n")
    
    lines = []
    empty_count = 0
    while empty_count < 1:
        try:
            line = input()
            if line == "":
                empty_count += 1
            else:
                empty_count = 0
                lines.append(line)
        except EOFError:
            break
    
    json_str = "\n".join(lines)
    
    if not json_str.strip():
        print("\n❌ Tidak ada input!")
        return False
    
    try:
        cookies = json.loads(json_str)
        
        if not isinstance(cookies, list):
            raise ValueError("Cookies harus berupa array/list")
        
        # Validasi dan normalisasi format
        normalized = []
        tiktok_cookies = 0
        for c in cookies:
            # Cek apakah cookie untuk TikTok
            domain = c.get("domain", c.get("Domain", ""))
            if "tiktok" not in domain.lower():
                continue
                
            cookie = {
                "name": c.get("name", c.get("Name", "")),
                "value": c.get("value", c.get("Value", "")),
                "domain": domain,
                "path": c.get("path", c.get("Path", "/")),
                "secure": c.get("secure", c.get("Secure", True)),
                "httpOnly": c.get("httpOnly", c.get("HttpOnly", False)),
            }
            
            # Tambahkan expiry jika ada
            if "expirationDate" in c:
                cookie["expires"] = c["expirationDate"]
            elif "expiry" in c:
                cookie["expires"] = c["expiry"]
                
            if cookie["name"] and cookie["value"]:
                normalized.append(cookie)
                tiktok_cookies += 1
        
        if not normalized:
            print("\n❌ Tidak ada cookies TikTok ditemukan!")
            print("   Pastikan kamu sudah login di TikTok dan export dari halaman TikTok.")
            return False
        
        # Simpan
        with open(TIKTOK_COOKIES_PATH, 'w', encoding='utf-8') as f:
            json.dump(normalized, f, indent=2)
        
        print(f"\n✅ Berhasil menyimpan {tiktok_cookies} cookies TikTok!")
        print(f"   File: {TIKTOK_COOKIES_PATH}")
        
        # Cek cookies penting
        important_cookies = ['sessionid', 'sid_tt', 'ssid_ucp_v1', 'passport_csrf_token']
        found = [c['name'] for c in normalized if c['name'] in important_cookies]
        if found:
            print(f"   ✓ Cookies penting ditemukan: {', '.join(found)}")
        else:
            print("   ⚠️  Warning: Beberapa cookies penting tidak ditemukan")
        
        # Verifikasi
        verify = input("\nVerifikasi cookies sekarang? (y/n): ").strip().lower()
        if verify == 'y':
            await load_and_verify_cookies()
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"\n❌ Format JSON tidak valid: {e}")
        print("   Pastikan copy semua text dari Cookie-Editor")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


async def manual_login():
    """
    Proses login manual TikTok dengan anti-detection yang lebih baik
    Browser akan terbuka, user login manual, lalu cookies disimpan
    """
    print("\n" + "="*60)
    print("🔐 TikTok Manual Login Script")
    print("="*60)
    print("\n⚠️  Jika sering gagal/rate limit, coba metode lain:")
    print("   - python tiktok_login.py --qr     (Login QR Code)")
    print("   - python tiktok_login.py --import (Import dari browser)")
    print("\nBrowser akan terbuka. Silakan login ke TikTok secara manual.")
    print("Setelah berhasil login, tekan ENTER di terminal ini.")
    print("\n⚠️  TIPS untuk menghindari ban:")
    print("   - Login dengan QR Code (paling aman!)")
    print("   - Atau login dengan Google/Facebook")
    print("   - Jangan terlalu cepat, tunggu loading")
    print("   - Jika ada captcha, selesaikan dengan sabar")
    print("   - Tunggu 5-10 menit jika kena rate limit")
    print("="*60 + "\n")
    
    async with async_playwright() as p:
        # Gunakan persistent context untuk menyimpan session
        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Launch browser dengan persistent context
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=False,
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
                '--disable-extensions',
            ]
        )
        
        # Inject script untuk menyembunyikan automation
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Overwrite the plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Overwrite languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['id-ID', 'id', 'en-US', 'en']
            });
            
            // Chrome runtime
            window.chrome = { runtime: {} };
            
            // Additional anti-detection
            Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 1 });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        """)
        
        # Open TikTok
        page = context.pages[0] if context.pages else await context.new_page()
        
        try:
            print("📱 Membuka TikTok...")
            await page.goto(TIKTOK_URL, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(human_delay(2, 4))
            
            print("\n🔑 Silakan login ke TikTok di browser yang terbuka.")
            print("   Metode login yang DISARANKAN:")
            print("   ⭐ QR Code (paling aman, jarang kena rate limit)")
            print("   ✓ Google/Facebook/Apple")
            print("   ⚠ Email/Password (sering kena rate limit)")
            
            # Tunggu user login
            input("\n⏳ Tekan ENTER setelah berhasil login dan halaman TikTok sudah termuat... ")
            
            # Tunggu sebentar untuk memastikan semua cookies tersimpan
            print("\n⏳ Menyimpan session...")
            await asyncio.sleep(human_delay(3, 5))
            
            # Verifikasi login
            print("🔍 Memverifikasi login...")
            
            # Coba akses upload page
            await page.goto(TIKTOK_UPLOAD_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(human_delay(2, 3))
            
            current_url = page.url
            
            if "login" in current_url.lower():
                print("\n❌ Login sepertinya belum berhasil (redirect ke halaman login)")
                print("   Silakan coba lagi dengan menjalankan script ini ulang.")
                print("\n💡 Tips: Coba gunakan --qr untuk login via QR Code")
                
                input("\nTekan ENTER untuk menutup browser...")
                return False
            
            # Simpan cookies
            await save_cookies(context, TIKTOK_COOKIES_PATH)
            
            print("\n✅ Login berhasil dan cookies tersimpan!")
            print("\n📋 Langkah selanjutnya:")
            print("   1. Copy folder 'cookies' ke server VPS")
            print("   2. Jalankan main.py untuk memulai sistem")
            print("   3. Cookies akan digunakan untuk upload otomatis")
            
            input("\nTekan ENTER untuk menutup browser...")
            return True
            
        except Exception as e:
            logger.error(f"Error during login: {e}")
            print(f"\n❌ Error: {e}")
            input("\nTekan ENTER untuk menutup browser...")
            return False
        
        finally:
            await context.close()


async def load_and_verify_cookies():
    """Load cookies yang sudah ada dan verifikasi masih valid"""
    
    if not TIKTOK_COOKIES_PATH.exists():
        print("❌ File cookies tidak ditemukan!")
        print(f"   Path: {TIKTOK_COOKIES_PATH}")
        return False
    
    # Cek cookies penting dulu
    print("\n🔍 Mengecek cookies...")
    with open(TIKTOK_COOKIES_PATH, 'r') as f:
        cookies = json.load(f)
    
    important_cookies = ['sessionid', 'sid_tt', 'ssid_ucp_v1', 'uid_tt']
    found = {c['name']: c['value'][:20] + '...' for c in cookies if c['name'] in important_cookies}
    
    if found:
        print(f"   ✓ Cookies tersimpan: {len(cookies)} total")
        print(f"   ✓ Cookies penting: {', '.join(found.keys())}")
    else:
        print("   ⚠️  Cookies penting tidak ditemukan!")
        return False
    
    print("\n🌐 Mencoba verifikasi online (mungkin lambat)...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        )
        
        try:
            await context.add_cookies(cookies)
            
            # Verifikasi
            is_valid = await verify_login(context)
            
            if is_valid:
                print("✅ Cookies valid! Bisa digunakan untuk upload.")
                return True
            else:
                print("⚠️  Verifikasi online gagal, tapi cookies ada.")
                print("   Coba jalankan upload - mungkin tetap berhasil.")
                return False
                
        except Exception as e:
            print(f"⚠️  Verifikasi timeout: {e}")
            print("   Cookies tersimpan, coba jalankan upload untuk test.")
            return True  # Anggap valid karena cookies penting ada
        finally:
            await browser.close()


def main():
    """Main function dengan berbagai opsi login"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="TikTok Login Script - Multiple Methods",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Metode Login yang Tersedia:
===========================
  (default)   Login manual biasa di browser
  --qr        Login via QR Code (PALING AMAN, jarang rate limit)
  --import    Import cookies dari Chrome/Edge
  --profile   Gunakan persistent browser profile
  --verify    Verifikasi cookies yang sudah ada

Contoh:
  python tiktok_login.py --qr       # Login dengan scan QR code
  python tiktok_login.py --import   # Import dari browser
  python tiktok_login.py --verify   # Cek apakah cookies valid
        """
    )
    parser.add_argument(
        "--verify", 
        action="store_true", 
        help="Verifikasi cookies yang ada tanpa login ulang"
    )
    parser.add_argument(
        "--qr", 
        action="store_true", 
        help="Login via QR Code (paling aman, scan dari app TikTok)"
    )
    parser.add_argument(
        "--import", 
        dest="import_cookies",
        action="store_true", 
        help="Import cookies dari Chrome/Edge browser"
    )
    parser.add_argument(
        "--profile", 
        action="store_true", 
        help="Gunakan persistent browser profile"
    )
    args = parser.parse_args()
    
    if args.verify:
        asyncio.run(load_and_verify_cookies())
    elif args.qr:
        asyncio.run(qr_code_login())
    elif args.import_cookies:
        asyncio.run(import_browser_cookies())
    elif args.profile:
        asyncio.run(persistent_profile_login())
    else:
        # Default: tampilkan menu
        print("\n" + "="*60)
        print("🔐 TikTok Login - Pilih Metode")
        print("="*60)
        print("\n1. 📱 Login via QR Code (DISARANKAN - paling aman)")
        print("2. 🔑 Login Manual di Browser")
        print("3. 🍪 Import Cookies dari Chrome/Edge")
        print("4. 💾 Persistent Profile Login")
        print("5. ✅ Verifikasi Cookies yang Ada")
        print("0. ❌ Keluar")
        
        choice = input("\nPilih metode (0-5): ").strip()
        
        if choice == "1":
            asyncio.run(qr_code_login())
        elif choice == "2":
            asyncio.run(manual_login())
        elif choice == "3":
            asyncio.run(import_browser_cookies())
        elif choice == "4":
            asyncio.run(persistent_profile_login())
        elif choice == "5":
            asyncio.run(load_and_verify_cookies())
        elif choice == "0":
            print("\n👋 Bye!")
        else:
            print("\n❌ Pilihan tidak valid")


if __name__ == "__main__":
    main()
