"""
Telegram Bot untuk menerima video
Video akan disimpan ke folder dan dimasukkan ke queue database
"""
import os
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from telegram import Update, Bot
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    ContextTypes,
    filters
)

from config import (
    TELEGRAM_BOT_TOKEN, 
    ALLOWED_USER_IDS, 
    VIDEOS_DIR,
    TIKTOK_DEFAULT_CAPTION,
    LOGS_DIR
)
from database import db, STATUS_PENDING, STATUS_POSTED, STATUS_FAILED
from logger_setup import setup_logger

logger = setup_logger("telegram_bot")


def is_authorized(user_id: int) -> bool:
    """Cek apakah user diizinkan menggunakan bot"""
    # Jika ALLOWED_USER_IDS kosong, izinkan semua
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /start"""
    user = update.effective_user
    
    if not is_authorized(user.id):
        await update.message.reply_text("⛔ Kamu tidak diizinkan menggunakan bot ini.")
        logger.warning(f"Unauthorized access attempt from user {user.id}")
        return
    
    welcome_message = f"""
🎬 *TikTok Auto Uploader Bot*

Halo {user.first_name}! 

Kirim video ke bot ini dan video akan otomatis diposting ke TikTok pada jadwal:
• 06:00 WIB
• 09:00 WIB  
• 12:00 WIB

*Perintah tersedia:*
/status - Lihat status queue
/queue - Lihat daftar video pending
/help - Bantuan

Cukup kirim video kapan saja! 📹
"""
    await update.message.reply_text(welcome_message, parse_mode="Markdown")
    logger.info(f"User {user.id} started the bot")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /help"""
    if not is_authorized(update.effective_user.id):
        return
    
    help_text = """
📖 *Panduan Penggunaan*

*Mengirim Video:*
1. Kirim video langsung ke chat ini
2. Opsional: Tambahkan caption yang akan digunakan di TikTok
3. Video akan masuk ke antrian

*Perintah:*
• /start - Mulai bot
• /status - Statistik video (pending/posted/failed)
• /queue - Lihat antrian video pending
• /debug - Lihat screenshot debug terbaru
• /clearall - Hapus SEMUA video dari database
• /clearpending - Hapus semua video pending
• /clearfailed - Hapus semua video failed
• /help - Tampilkan bantuan ini

*Catatan:*
- Video diproses secara FIFO (First In First Out)
- Jika upload gagal, akan dicoba 1x lagi
- Caption default: #fyp #viral #foryou
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /status"""
    if not is_authorized(update.effective_user.id):
        return
    
    stats = db.get_stats()
    
    status_text = f"""
📊 *Status Video Queue*

⏳ Pending: {stats[STATUS_PENDING]} video
✅ Posted: {stats[STATUS_POSTED]} video
❌ Failed: {stats[STATUS_FAILED]} video

Total: {sum(stats.values())} video
"""
    await update.message.reply_text(status_text, parse_mode="Markdown")
    logger.info(f"Status requested by user {update.effective_user.id}")


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /debug - kirim screenshot debug terbaru"""
    if not is_authorized(update.effective_user.id):
        return
    
    user_id = update.effective_user.id
    
    # Daftar screenshot debug yang mungkin ada
    debug_files = [
        ("debug_login_check.png", "🔐 Login Check"),
        ("debug_before_input.png", "📥 Before Input"),
        ("debug_after_search.png", "🔍 After Search"),
        ("debug_input_not_found.png", "❌ Input Not Found"),
        ("debug_before_post.png", "📸 Before Post"),
        ("debug_after_post.png", "📸 After Post"),
        ("debug_final.png", "🏁 Final State"),
        ("debug_error.png", "❌ Error State"),
    ]
    
    found_any = False
    
    for filename, caption in debug_files:
        filepath = LOGS_DIR / filename
        if filepath.exists():
            try:
                # Get file modification time
                mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
                time_str = mtime.strftime("%Y-%m-%d %H:%M:%S")
                
                with open(filepath, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=f"{caption}\n📁 {filename}\n🕐 {time_str}"
                    )
                found_any = True
            except Exception as e:
                logger.error(f"Error sending debug file {filename}: {e}")
                await update.message.reply_text(f"❌ Error mengirim {filename}: {e}")
    
    if not found_any:
        await update.message.reply_text("📭 Tidak ada screenshot debug yang tersedia.\n\nScreenshot akan dibuat saat upload berjalan.")
    
    logger.info(f"Debug screenshots requested by user {user_id}")


async def clearall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /clearall - hapus semua video dari database"""
    if not is_authorized(update.effective_user.id):
        return
    
    user_id = update.effective_user.id
    
    # Get stats sebelum hapus
    stats = db.get_stats()
    total = sum(stats.values())
    
    if total == 0:
        await update.message.reply_text("📭 Database sudah kosong, tidak ada video untuk dihapus.")
        return
    
    # Hapus semua video
    deleted = db.delete_all_videos()
    
    # Hapus file video dari folder
    deleted_files = 0
    try:
        for video_file in VIDEOS_DIR.glob("*.mp4"):
            try:
                video_file.unlink()
                deleted_files += 1
            except Exception as e:
                logger.error(f"Failed to delete file {video_file}: {e}")
    except Exception as e:
        logger.error(f"Error cleaning video files: {e}")
    
    message = f"""
🗑️ *Semua Video Dihapus!*

📊 Database: {deleted} video dihapus
📁 File: {deleted_files} file dihapus

Statistik sebelum dihapus:
• Pending: {stats[STATUS_PENDING]}
• Posted: {stats[STATUS_POSTED]}
• Failed: {stats[STATUS_FAILED]}
"""
    await update.message.reply_text(message, parse_mode="Markdown")
    logger.info(f"All videos deleted by user {user_id}: {deleted} records, {deleted_files} files")


async def clearpending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /clearpending - hapus semua video pending"""
    if not is_authorized(update.effective_user.id):
        return
    
    user_id = update.effective_user.id
    pending_count = db.get_pending_count()
    
    if pending_count == 0:
        await update.message.reply_text("📭 Tidak ada video pending untuk dihapus.")
        return
    
    # Hapus semua pending
    deleted = db.delete_all_pending()
    
    message = f"🗑️ *{deleted} video pending* berhasil dihapus dari antrian!"
    await update.message.reply_text(message, parse_mode="Markdown")
    logger.info(f"Pending videos deleted by user {user_id}: {deleted} records")


async def clearfailed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /clearfailed - hapus semua video failed"""
    if not is_authorized(update.effective_user.id):
        return
    
    user_id = update.effective_user.id
    stats = db.get_stats()
    failed_count = stats[STATUS_FAILED]
    
    if failed_count == 0:
        await update.message.reply_text("📭 Tidak ada video failed untuk dihapus.")
        return
    
    # Hapus semua failed
    deleted = db.delete_all_failed()
    
    message = f"🗑️ *{deleted} video failed* berhasil dihapus!"
    await update.message.reply_text(message, parse_mode="Markdown")
    logger.info(f"Failed videos deleted by user {user_id}: {deleted} records")


async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /queue"""
    if not is_authorized(update.effective_user.id):
        return
    
    pending_videos = db.get_all_pending()
    
    if not pending_videos:
        await update.message.reply_text("📭 Tidak ada video dalam antrian.")
        return
    
    queue_text = "📋 *Antrian Video Pending:*\n\n"
    
    for i, video in enumerate(pending_videos[:10], 1):  # Max 10 video
        created = video["created_at"][:16] if video["created_at"] else "N/A"
        caption = video["caption"][:30] + "..." if video["caption"] and len(video["caption"]) > 30 else (video["caption"] or "-")
        queue_text += f"{i}. `{video['filename']}`\n   Caption: {caption}\n   Ditambahkan: {created}\n\n"
    
    if len(pending_videos) > 10:
        queue_text += f"_...dan {len(pending_videos) - 10} video lainnya_"
    
    await update.message.reply_text(queue_text, parse_mode="Markdown")


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk video yang dikirim"""
    user = update.effective_user
    
    if not is_authorized(user.id):
        await update.message.reply_text("⛔ Kamu tidak diizinkan menggunakan bot ini.")
        return
    
    message = update.message
    video = message.video or message.document
    
    if not video:
        return
    
    # Validasi file
    if message.document:
        mime_type = message.document.mime_type or ""
        if not mime_type.startswith("video/"):
            await message.reply_text("❌ File harus berupa video.")
            return
    
    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    original_name = video.file_name if hasattr(video, 'file_name') and video.file_name else "video"
    extension = Path(original_name).suffix if Path(original_name).suffix else ".mp4"
    filename = f"{timestamp}_{user.id}{extension}"
    filepath = VIDEOS_DIR / filename
    
    # Kirim pesan "sedang memproses"
    processing_msg = await message.reply_text("⏳ Mengunduh video...")
    
    try:
        # Download video
        file = await video.get_file()
        await file.download_to_drive(filepath)
        
        # Ambil caption
        caption = message.caption or TIKTOK_DEFAULT_CAPTION
        
        # Simpan ke database
        video_id = db.add_video(
            filename=filename,
            filepath=str(filepath),
            caption=caption,
            telegram_file_id=video.file_id,
            telegram_user_id=user.id
        )
        
        # Get stats
        pending_count = db.get_pending_count()
        
        success_message = f"""
✅ *Video Berhasil Ditambahkan!*

📄 File: `{filename}`
📝 Caption: {caption[:50]}{'...' if len(caption) > 50 else ''}
🔢 Posisi dalam antrian: #{pending_count}
🆔 Video ID: {video_id}

Video akan diposting sesuai jadwal 🕐
"""
        await processing_msg.edit_text(success_message, parse_mode="Markdown")
        logger.info(f"Video saved: {filename} from user {user.id}")
        
    except Exception as e:
        error_message = f"❌ Gagal menyimpan video: {str(e)}"
        await processing_msg.edit_text(error_message)
        logger.error(f"Error saving video from user {user.id}: {e}")


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pesan yang tidak dikenal"""
    if not is_authorized(update.effective_user.id):
        return
    
    await update.message.reply_text(
        "🤔 Kirim video untuk ditambahkan ke antrian, atau gunakan /help untuk bantuan."
    )


def create_bot_application() -> Application:
    """Membuat dan mengkonfigurasi bot application"""
    
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN tidak ditemukan!")
    
    # Build application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("queue", queue_command))
    application.add_handler(CommandHandler("debug", debug_command))
    application.add_handler(CommandHandler("clearall", clearall_command))
    application.add_handler(CommandHandler("clearpending", clearpending_command))
    application.add_handler(CommandHandler("clearfailed", clearfailed_command))
    
    # Video handler
    application.add_handler(MessageHandler(
        filters.VIDEO | filters.Document.VIDEO, 
        handle_video
    ))
    
    # Unknown message handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_unknown
    ))
    
    logger.info("Telegram bot application created")
    return application


async def run_bot():
    """Menjalankan bot secara async"""
    application = create_bot_application()
    
    logger.info("Starting Telegram bot...")
    
    # Initialize and start
    await application.initialize()
    await application.start()
    
    # drop_pending_updates=True untuk abaikan pesan lama
    # allowed_updates untuk filter update yang diterima
    # Retry jika ada konflik dengan instance lain
    max_retries = 3
    for attempt in range(max_retries):
        try:
            await application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"]
            )
            break
        except Exception as e:
            if "Conflict" in str(e) and attempt < max_retries - 1:
                logger.warning(f"Conflict detected, retrying in 5 seconds... (attempt {attempt + 1})")
                await asyncio.sleep(5)
            else:
                raise
    
    logger.info("Telegram bot is running!")
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Stopping Telegram bot...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info("Telegram bot stopped")


if __name__ == "__main__":
    """Jalankan bot secara standalone untuk testing"""
    from config import validate_config
    
    if not validate_config():
        exit(1)
    
    asyncio.run(run_bot())
