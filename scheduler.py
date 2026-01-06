"""
Scheduler untuk posting otomatis ke TikTok
Menggunakan APScheduler untuk scheduling
"""
import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from config import (
    POSTING_SCHEDULE,
    TIMEZONE,
    MAX_RETRY
)
from database import db, STATUS_PENDING, STATUS_POSTED, STATUS_FAILED
from tiktok_uploader import TikTokUploader
from logger_setup import setup_logger

logger = setup_logger("scheduler")


class VideoScheduler:
    """
    Scheduler untuk posting video ke TikTok
    """
    
    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.timezone = pytz.timezone(TIMEZONE)
        self.uploader = TikTokUploader()
        self.is_uploading = False  # Lock untuk mencegah concurrent upload
    
    async def post_next_video(self):
        """
        Posting video berikutnya dari queue
        """
        # Cek lock
        if self.is_uploading:
            logger.warning("Upload sedang berjalan, skip scheduled job ini")
            return
        
        self.is_uploading = True
        
        try:
            # Ambil video pending berikutnya
            video = db.get_next_pending()
            
            if not video:
                logger.info("Tidak ada video pending dalam queue")
                return
            
            video_id = video['id']
            video_path = video['filepath']
            caption = video['caption']
            filename = video['filename']
            retry_count = video['retry_count']
            
            logger.info(f"=== Starting scheduled upload ===")
            logger.info(f"Video ID: {video_id}")
            logger.info(f"Filename: {filename}")
            logger.info(f"Caption: {caption[:50] if caption else 'N/A'}...")
            logger.info(f"Retry count: {retry_count}")
            
            # Cek file exists
            if not Path(video_path).exists():
                logger.error(f"File tidak ditemukan: {video_path}")
                db.update_status(video_id, STATUS_FAILED, "File tidak ditemukan")
                return
            
            # Upload video
            success, message = await self.uploader.upload_video(video_path, caption)
            
            if success:
                # Update status ke posted
                db.update_status(video_id, STATUS_POSTED)
                logger.info(f"✅ Video {video_id} berhasil diupload: {message}")
                
                # Hapus file video untuk menghemat ruang (opsional)
                # Uncomment baris berikut jika ingin otomatis hapus file setelah upload
                # try:
                #     os.remove(video_path)
                #     logger.info(f"File deleted: {video_path}")
                # except Exception as e:
                #     logger.warning(f"Failed to delete file: {e}")
                
            else:
                # Gagal - cek retry
                new_retry = db.increment_retry(video_id)
                
                if new_retry <= MAX_RETRY:
                    logger.warning(f"Upload gagal, akan retry ({new_retry}/{MAX_RETRY}): {message}")
                    # Tidak update status, biarkan pending untuk retry berikutnya
                else:
                    # Sudah melebihi max retry
                    db.update_status(video_id, STATUS_FAILED, message)
                    logger.error(f"❌ Video {video_id} gagal setelah {MAX_RETRY} retry: {message}")
                    
        except Exception as e:
            logger.error(f"Error dalam scheduled job: {e}")
            
        finally:
            self.is_uploading = False
            logger.info("=== Scheduled upload completed ===\n")
    
    def _parse_schedule_time(self, time_str: str) -> tuple:
        """Parse time string (HH:MM) ke hour dan minute"""
        parts = time_str.strip().split(':')
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return hour, minute
    
    def setup_scheduler(self):
        """Setup scheduler dengan jadwal posting"""
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        
        logger.info(f"Setting up scheduler with timezone: {TIMEZONE}")
        logger.info(f"Posting schedule: {POSTING_SCHEDULE}")
        
        for time_str in POSTING_SCHEDULE:
            hour, minute = self._parse_schedule_time(time_str)
            
            # Buat trigger cron
            trigger = CronTrigger(
                hour=hour,
                minute=minute,
                timezone=self.timezone
            )
            
            # Tambahkan job
            self.scheduler.add_job(
                self.post_next_video,
                trigger=trigger,
                id=f"post_video_{hour:02d}{minute:02d}",
                name=f"Post Video at {hour:02d}:{minute:02d}",
                replace_existing=True
            )
            
            logger.info(f"Scheduled job added: {hour:02d}:{minute:02d} {TIMEZONE}")
    
    async def start(self):
        """Start scheduler"""
        if not self.scheduler:
            self.setup_scheduler()
        
        self.scheduler.start()
        logger.info("Scheduler started!")
        
        # Log next run times
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time
            logger.info(f"Next run for '{job.name}': {next_run}")
    
    def stop(self):
        """Stop scheduler"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
    
    async def run_now(self):
        """Manual trigger untuk testing"""
        logger.info("Manual trigger: posting video sekarang...")
        await self.post_next_video()
    
    def get_status(self) -> dict:
        """Get scheduler status"""
        if not self.scheduler:
            return {"status": "not_initialized", "jobs": []}
        
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None
            })
        
        return {
            "status": "running" if self.scheduler.running else "stopped",
            "timezone": str(self.timezone),
            "jobs": jobs,
            "is_uploading": self.is_uploading
        }


# Singleton instance
scheduler = VideoScheduler()


async def run_scheduler_standalone():
    """Jalankan scheduler secara standalone"""
    logger.info("Starting scheduler in standalone mode...")
    
    await scheduler.start()
    
    try:
        # Keep running
        while True:
            await asyncio.sleep(60)
            
            # Log heartbeat setiap 10 menit
            # Ini membantu untuk monitoring
            
    except asyncio.CancelledError:
        logger.info("Scheduler cancelled")
    except KeyboardInterrupt:
        logger.info("Scheduler interrupted")
    finally:
        scheduler.stop()


if __name__ == "__main__":
    """Jalankan scheduler standalone untuk testing"""
    import argparse
    
    parser = argparse.ArgumentParser(description="TikTok Video Scheduler")
    parser.add_argument(
        "--run-now", 
        action="store_true",
        help="Langsung posting video sekarang (untuk testing)"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Tampilkan status queue"
    )
    args = parser.parse_args()
    
    if args.status:
        stats = db.get_stats()
        print("\n📊 Status Video Queue:")
        print(f"   Pending: {stats[STATUS_PENDING]}")
        print(f"   Posted: {stats[STATUS_POSTED]}")
        print(f"   Failed: {stats[STATUS_FAILED]}")
        
    elif args.run_now:
        asyncio.run(scheduler.run_now())
    else:
        asyncio.run(run_scheduler_standalone())
