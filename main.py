"""
Main entry point untuk TikTok Auto System
Menjalankan Telegram Bot + Scheduler secara bersamaan
"""
import asyncio
import signal
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import validate_config, TIKTOK_COOKIES_PATH
from telegram_bot import run_bot, create_bot_application
from scheduler import scheduler
from database import db
from logger_setup import setup_logger

logger = setup_logger("main")


class TikTokAutoSystem:
    """
    Main system yang menjalankan:
    1. Telegram Bot (untuk terima video)
    2. Scheduler (untuk posting otomatis)
    """
    
    def __init__(self):
        self.running = False
        self.telegram_app = None
        self.tasks = []
    
    def _check_prerequisites(self) -> bool:
        """Cek semua prerequisite sebelum start"""
        errors = []
        
        # Cek config
        if not validate_config():
            errors.append("Konfigurasi tidak valid")
        
        # Cek cookies TikTok
        if not TIKTOK_COOKIES_PATH.exists():
            errors.append(
                f"Cookies TikTok tidak ditemukan di: {TIKTOK_COOKIES_PATH}\n"
                "   Jalankan 'python tiktok_login.py' terlebih dahulu untuk login manual."
            )
        
        if errors:
            print("\n❌ Prerequisite check failed:")
            for error in errors:
                print(f"   - {error}")
            return False
        
        return True
    
    async def _run_telegram_bot(self):
        """Jalankan Telegram bot"""
        from telegram.error import Conflict
        
        self.telegram_app = create_bot_application()
        
        await self.telegram_app.initialize()
        await self.telegram_app.start()
        
        # Drop pending updates and handle conflict with retry
        max_retries = 3
        retry_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                await self.telegram_app.updater.start_polling(
                    drop_pending_updates=True,
                    allowed_updates=["message", "callback_query"]
                )
                logger.info("Telegram bot started!")
                break
            except Conflict as e:
                logger.warning(f"Bot conflict detected (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Waiting {retry_delay}s before retry...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error("Failed to start bot after max retries. Another instance may be running.")
                    raise
        
        try:
            while self.running:
                await asyncio.sleep(1)
        finally:
            await self.telegram_app.updater.stop()
            await self.telegram_app.stop()
            await self.telegram_app.shutdown()
    
    async def _run_scheduler(self):
        """Jalankan scheduler"""
        await scheduler.start()
        
        try:
            while self.running:
                await asyncio.sleep(1)
        finally:
            scheduler.stop()
    
    async def _heartbeat(self):
        """Heartbeat untuk monitoring"""
        while self.running:
            await asyncio.sleep(300)  # Setiap 5 menit
            
            stats = db.get_stats()
            sched_status = scheduler.get_status()
            
            logger.info(
                f"[Heartbeat] Queue: {stats['pending']} pending, "
                f"{stats['posted']} posted, {stats['failed']} failed | "
                f"Scheduler: {sched_status['status']}"
            )
    
    def _signal_handler(self, sig, frame):
        """Handle shutdown signal"""
        logger.info(f"Received signal {sig}, shutting down...")
        self.running = False
    
    async def start(self):
        """Start semua komponen"""
        print("\n" + "="*60)
        print("🚀 TikTok Auto Upload System")
        print("="*60)
        
        # Check prerequisites
        if not self._check_prerequisites():
            print("\n❌ System tidak bisa start. Perbaiki error di atas terlebih dahulu.")
            return
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.running = True
        
        # Print info
        stats = db.get_stats()
        print(f"\n📊 Current Queue Status:")
        print(f"   Pending: {stats['pending']} videos")
        print(f"   Posted: {stats['posted']} videos")
        print(f"   Failed: {stats['failed']} videos")
        
        print(f"\n📅 Posting Schedule:")
        from config import POSTING_SCHEDULE, TIMEZONE
        for time in POSTING_SCHEDULE:
            print(f"   • {time} {TIMEZONE}")
        
        print(f"\n✅ System starting...")
        print("   - Telegram Bot: Running")
        print("   - Scheduler: Running")
        print("\n   Press Ctrl+C to stop\n")
        print("="*60 + "\n")
        
        logger.info("="*50)
        logger.info("TikTok Auto System Started")
        logger.info("="*50)
        
        # Create tasks
        self.tasks = [
            asyncio.create_task(self._run_telegram_bot()),
            asyncio.create_task(self._run_scheduler()),
            asyncio.create_task(self._heartbeat()),
        ]
        
        try:
            # Wait for all tasks
            await asyncio.gather(*self.tasks, return_exceptions=True)
        except asyncio.CancelledError:
            logger.info("Tasks cancelled")
        finally:
            self.running = False
            
            # Cancel remaining tasks
            for task in self.tasks:
                if not task.done():
                    task.cancel()
            
            logger.info("System shutdown complete")
            print("\n👋 TikTok Auto System stopped.")
    
    def stop(self):
        """Stop semua komponen"""
        self.running = False


async def main():
    """Main function"""
    system = TikTokAutoSystem()
    await system.start()


def run():
    """Entry point"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")


if __name__ == "__main__":
    run()
