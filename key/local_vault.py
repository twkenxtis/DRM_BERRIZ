import os
import sqlite3
from typing import Any, Dict, Optional, Tuple, List

import orjson
from pathlib import Path

from static.route import Route


class SQLiteKeyVault:
    DB_FILE: Path = Route().DB_FILE

    def __init__(self):
        os.makedirs(os.path.dirname(self.DB_FILE), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """初始化數據庫和表結構"""
        with sqlite3.connect(self.DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS key_vault (
                    key TEXT PRIMARY KEY,
                    value_type TEXT NOT NULL,
                    value_data TEXT NOT NULL,
                    drm_type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 創建更新時間的觸發器
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS update_timestamp
                AFTER UPDATE ON key_vault
                FOR EACH ROW
                BEGIN
                    UPDATE key_vault SET updated_at = CURRENT_TIMESTAMP 
                    WHERE key = OLD.key;
                END
            ''')
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """獲取數據庫連接"""
        return sqlite3.connect(self.DB_FILE)

    def _serialize_value(self, value: Any) -> Tuple[str, str]:
        if isinstance(value, (str, int, float, bool)):
            return (type(value).__name__, str(value))
        else:
            return ('json', orjson.dumps(value).decode('utf-8'))

    def _deserialize_value(self, value_type: str, value_data: str) -> Any:
        if value_type == 'str':
            return value_data
        elif value_type == 'int':
            return int(value_data)
        elif value_type == 'float':
            return float(value_data)
        elif value_type == 'bool':
            return value_data.lower() == 'true'
        elif value_type == 'json':
            return orjson.loads(value_data.encode('utf-8'))
        else:
            raise ValueError(f"Unsupported value type: {value_type}")

    def store(self, new_data: Dict[str, Any], drm_type: str = "unknown") -> None:
        """存儲多個鍵值對，並指定 DRM 類型"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            for key, value in new_data.items():
                value_type, value_data = self._serialize_value(value)
                
                cursor.execute('''
                    INSERT OR REPLACE INTO key_vault 
                    (key, value_type, value_data, drm_type)
                    VALUES (?, ?, ?, ?)
                ''', (key, value_type, value_data, drm_type))
            
            conn.commit()

    async def store_single(self, key: str, value: Any, drm_type: str = "unknown") -> None:
        """存儲單個鍵值對，並指定 DRM 類型"""
        self.store({key: value}, drm_type)

    async def retrieve(self, key: str) -> Optional[Any]:
        """檢索指定鍵的值"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT value_type, value_data 
                FROM key_vault WHERE key = ?
            ''', (key,))
            
            result: Optional[Tuple[str, str]] = cursor.fetchone()
            if result:
                return self._deserialize_value(*result)
            return None

    def retrieve_with_drm_type(self, key: str) -> Optional[Tuple[Any, str]]:
        """檢索指定鍵的值和 DRM 類型"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT value_type, value_data, drm_type 
                FROM key_vault WHERE key = ?
            ''', (key,))
            
            result: Optional[Tuple[str, str, str]] = cursor.fetchone()
            if result:
                value: Any = self._deserialize_value(result[0], result[1])
                return value, result[2]  # 返回值和 DRM 類型
            return None

    def contains(self, key: str) -> bool:
        """檢查鍵是否存在"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM key_vault WHERE key = ?', (key,))
            return cursor.fetchone() is not None

    def delete(self, key: str) -> bool:
        """刪除指定鍵"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM key_vault WHERE key = ?', (key,))
            conn.commit()
            return cursor.rowcount > 0

    def get_all(self) -> Dict[str, Any]:
        """獲取所有鍵值對"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT key, value_type, value_data 
                FROM key_vault
            ''')
            
            results: Dict[str, Any] = {}
            for row in cursor.fetchall():
                key: str = row[0]
                value: Any = self._deserialize_value(row[1], row[2])
                results[key] = value
            
            return results

    def get_all_with_drm_type(self) -> Dict[str, Tuple[Any, str]]:
        """獲取所有鍵值對及其 DRM 類型"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT key, value_type, value_data, drm_type 
                FROM key_vault
            ''')
            
            results: Dict[str, Tuple[Any, str]] = {}
            for row in cursor.fetchall():
                key: str = row[0]
                value: Any = self._deserialize_value(row[1], row[2])
                results[key] = (value, row[3])  # 存儲為 (值, DRM 類型)
            
            return results

    def get_by_drm_type(self, drm_type: str) -> Dict[str, Any]:
        """根據 DRM 類型獲取鍵值對"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT key, value_type, value_data 
                FROM key_vault WHERE drm_type = ?
            ''', (drm_type,))
            
            results: Dict[str, Any] = {}
            for row in cursor.fetchall():
                key: str = row[0]
                value: Any = self._deserialize_value(row[1], row[2])
                results[key] = value
            
            return results

    def clear(self) -> None:
        """清空所有數據"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM key_vault')
            conn.commit()

    def keys(self) -> List[str]:
        """獲取所有鍵的列表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT key FROM key_vault')
            return [row[0] for row in cursor.fetchall()]

    def count(self) -> int:
        """獲取鍵值對數量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM key_vault')
            result: Optional[Tuple[int]] = cursor.fetchone()
            return result[0] if result else 0

    def count_by_drm_type(self, drm_type: str) -> int:
        """根據 DRM 類型獲取鍵值對數量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM key_vault WHERE drm_type = ?', (drm_type,))
            result: Optional[Tuple[int]] = cursor.fetchone()
            return result[0] if result else 0