"""
Database handler untuk video queue
Menggunakan SQLite dengan FIFO queue
"""
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

# Status video
STATUS_PENDING = "pending"
STATUS_POSTED = "posted"
STATUS_FAILED = "failed"


class VideoDatabase:
    """Handler untuk database video queue"""
    
    def __init__(self, db_path: Path = DATABASE_PATH):
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        """Context manager untuk koneksi database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_db(self):
        """Inisialisasi tabel database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    caption TEXT,
                    status TEXT DEFAULT 'pending',
                    retry_count INTEGER DEFAULT 0,
                    telegram_file_id TEXT,
                    telegram_user_id INTEGER,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    posted_at TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Index untuk query cepat
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status 
                ON videos(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at 
                ON videos(created_at)
            """)
            
            logger.info("Database initialized successfully")
    
    def add_video(
        self, 
        filename: str, 
        filepath: str, 
        caption: Optional[str] = None,
        telegram_file_id: Optional[str] = None,
        telegram_user_id: Optional[int] = None
    ) -> int:
        """
        Menambahkan video baru ke queue
        Returns: video_id
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO videos 
                (filename, filepath, caption, telegram_file_id, telegram_user_id, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (filename, filepath, caption, telegram_file_id, telegram_user_id, STATUS_PENDING))
            
            video_id = cursor.lastrowid
            logger.info(f"Video added to queue: {filename} (ID: {video_id})")
            return video_id
    
    def get_next_pending(self) -> Optional[Dict[str, Any]]:
        """
        Mengambil video pending paling lama (FIFO)
        Returns: dict video atau None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM videos 
                WHERE status = ? 
                ORDER BY created_at ASC 
                LIMIT 1
            """, (STATUS_PENDING,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def update_status(
        self, 
        video_id: int, 
        status: str, 
        error_message: Optional[str] = None
    ):
        """Update status video"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            posted_at = datetime.now() if status == STATUS_POSTED else None
            
            cursor.execute("""
                UPDATE videos 
                SET status = ?, 
                    error_message = ?,
                    posted_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, error_message, posted_at, video_id))
            
            logger.info(f"Video {video_id} status updated to: {status}")
    
    def increment_retry(self, video_id: int) -> int:
        """
        Increment retry count
        Returns: retry count baru
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE videos 
                SET retry_count = retry_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (video_id,))
            
            cursor.execute("SELECT retry_count FROM videos WHERE id = ?", (video_id,))
            row = cursor.fetchone()
            return row["retry_count"] if row else 0
    
    def get_pending_count(self) -> int:
        """Menghitung jumlah video pending"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM videos WHERE status = ?", 
                (STATUS_PENDING,)
            )
            row = cursor.fetchone()
            return row["count"] if row else 0
    
    def get_stats(self) -> Dict[str, int]:
        """Mendapatkan statistik video"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    status,
                    COUNT(*) as count 
                FROM videos 
                GROUP BY status
            """)
            
            stats = {
                STATUS_PENDING: 0,
                STATUS_POSTED: 0,
                STATUS_FAILED: 0
            }
            
            for row in cursor.fetchall():
                stats[row["status"]] = row["count"]
            
            return stats
    
    def get_all_pending(self) -> List[Dict[str, Any]]:
        """Mendapatkan semua video pending"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM videos 
                WHERE status = ? 
                ORDER BY created_at ASC
            """, (STATUS_PENDING,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def delete_video(self, video_id: int) -> bool:
        """Hapus video dari database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM videos WHERE id = ?", (video_id,))
            return cursor.rowcount > 0


# Singleton instance
db = VideoDatabase()
