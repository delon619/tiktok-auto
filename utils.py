"""
Utility functions untuk TikTok Auto System
"""
import os
import asyncio
from pathlib import Path
from datetime import datetime, timedelta

from config import VIDEOS_DIR, DATA_DIR
from database import db, STATUS_PENDING, STATUS_POSTED, STATUS_FAILED
from logger_setup import setup_logger

logger = setup_logger("utils")


def cleanup_old_videos(days: int = 7, dry_run: bool = True) -> list:
    """
    Hapus video yang sudah diposting lebih dari X hari
    
    Args:
        days: Hapus file lebih tua dari X hari
        dry_run: Jika True, hanya tampilkan yang akan dihapus tanpa menghapus
        
    Returns:
        List file yang dihapus (atau akan dihapus jika dry_run)
    """
    deleted_files = []
    cutoff_date = datetime.now() - timedelta(days=days)
    
    for file_path in VIDEOS_DIR.iterdir():
        if not file_path.is_file():
            continue
        
        # Cek waktu modifikasi
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        
        if mtime < cutoff_date:
            deleted_files.append(str(file_path))
            
            if not dry_run:
                try:
                    file_path.unlink()
                    logger.info(f"Deleted old video: {file_path.name}")
                except Exception as e:
                    logger.error(f"Failed to delete {file_path.name}: {e}")
    
    return deleted_files


def get_disk_usage() -> dict:
    """Get disk usage untuk folder videos"""
    total_size = 0
    file_count = 0
    
    for file_path in VIDEOS_DIR.iterdir():
        if file_path.is_file():
            total_size += file_path.stat().st_size
            file_count += 1
    
    return {
        "folder": str(VIDEOS_DIR),
        "file_count": file_count,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2)
    }


def reset_failed_videos() -> int:
    """
    Reset semua video dengan status failed ke pending
    Berguna jika ingin retry upload yang gagal
    
    Returns:
        Jumlah video yang di-reset
    """
    from database import VideoDatabase
    
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE videos 
            SET status = ?, retry_count = 0, error_message = NULL
            WHERE status = ?
        """, (STATUS_PENDING, STATUS_FAILED))
        
        count = cursor.rowcount
    
    logger.info(f"Reset {count} failed videos to pending")
    return count


def export_queue_to_csv(output_path: str = None) -> str:
    """
    Export queue ke file CSV
    
    Returns:
        Path ke file CSV
    """
    import csv
    
    if not output_path:
        output_path = DATA_DIR / f"queue_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos ORDER BY created_at")
        rows = cursor.fetchall()
        
        if not rows:
            return None
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Header
            writer.writerow([description[0] for description in cursor.description])
            # Data
            for row in rows:
                writer.writerow(row)
    
    logger.info(f"Queue exported to: {output_path}")
    return str(output_path)


def print_system_status():
    """Print status lengkap sistem"""
    print("\n" + "="*60)
    print("📊 TIKTOK AUTO SYSTEM STATUS")
    print("="*60)
    
    # Queue stats
    stats = db.get_stats()
    print(f"\n📋 Queue Status:")
    print(f"   ⏳ Pending: {stats[STATUS_PENDING]} videos")
    print(f"   ✅ Posted:  {stats[STATUS_POSTED]} videos")
    print(f"   ❌ Failed:  {stats[STATUS_FAILED]} videos")
    print(f"   📊 Total:   {sum(stats.values())} videos")
    
    # Disk usage
    disk = get_disk_usage()
    print(f"\n💾 Disk Usage:")
    print(f"   📁 Folder:     {disk['folder']}")
    print(f"   📄 Files:      {disk['file_count']}")
    print(f"   📏 Total Size: {disk['total_size_mb']} MB")
    
    # Cookies status
    from config import TIKTOK_COOKIES_PATH
    print(f"\n🍪 Cookies:")
    if TIKTOK_COOKIES_PATH.exists():
        mtime = datetime.fromtimestamp(TIKTOK_COOKIES_PATH.stat().st_mtime)
        age = datetime.now() - mtime
        print(f"   ✅ File exists")
        print(f"   📅 Last modified: {mtime.strftime('%Y-%m-%d %H:%M')}")
        print(f"   ⏰ Age: {age.days} days")
        
        if age.days > 14:
            print(f"   ⚠️  WARNING: Cookies mungkin perlu di-refresh!")
    else:
        print(f"   ❌ File not found!")
        print(f"   ⚠️  Jalankan tiktok_login.py untuk login")
    
    # Next pending
    next_video = db.get_next_pending()
    print(f"\n📹 Next Video to Post:")
    if next_video:
        print(f"   🆔 ID:       {next_video['id']}")
        print(f"   📄 Filename: {next_video['filename']}")
        print(f"   📝 Caption:  {next_video['caption'][:40]}...")
        print(f"   📅 Added:    {next_video['created_at']}")
    else:
        print(f"   📭 No pending videos")
    
    # Posting schedule
    from config import POSTING_SCHEDULE, TIMEZONE
    print(f"\n⏰ Posting Schedule ({TIMEZONE}):")
    for time in POSTING_SCHEDULE:
        print(f"   • {time}")
    
    print("\n" + "="*60)


async def test_tiktok_connection() -> bool:
    """Test koneksi ke TikTok"""
    from tiktok_uploader import TikTokUploader
    
    print("\n🔍 Testing TikTok connection...")
    
    uploader = TikTokUploader()
    success, message = await uploader.test_connection()
    
    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")
    
    return success


def main():
    """CLI untuk utility functions"""
    import argparse
    
    parser = argparse.ArgumentParser(description="TikTok Auto Utilities")
    parser.add_argument("--status", action="store_true", help="Show system status")
    parser.add_argument("--cleanup", type=int, metavar="DAYS", help="Cleanup videos older than DAYS")
    parser.add_argument("--cleanup-dry", type=int, metavar="DAYS", help="Show what would be cleaned up")
    parser.add_argument("--reset-failed", action="store_true", help="Reset failed videos to pending")
    parser.add_argument("--export", action="store_true", help="Export queue to CSV")
    parser.add_argument("--test-tiktok", action="store_true", help="Test TikTok connection")
    
    args = parser.parse_args()
    
    if args.status:
        print_system_status()
        
    elif args.cleanup:
        files = cleanup_old_videos(args.cleanup, dry_run=False)
        print(f"Deleted {len(files)} files")
        
    elif args.cleanup_dry:
        files = cleanup_old_videos(args.cleanup_dry, dry_run=True)
        print(f"Would delete {len(files)} files:")
        for f in files:
            print(f"  - {f}")
            
    elif args.reset_failed:
        count = reset_failed_videos()
        print(f"Reset {count} failed videos")
        
    elif args.export:
        path = export_queue_to_csv()
        if path:
            print(f"Exported to: {path}")
        else:
            print("No data to export")
            
    elif args.test_tiktok:
        asyncio.run(test_tiktok_connection())
        
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
