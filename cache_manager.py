"""
Система кэширования метаданных для лаунчера
"""

import os
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CacheManager:
    """Менеджер кэша метаданных"""
    
    def __init__(self, cache_dir="launcher_cache", default_ttl=3600):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.default_ttl = default_ttl  # Время жизни кэша в секундах (по умолчанию 1 час)
        self.index_file = self.cache_dir / "cache_index.json"
        self.index = self.load_index()
        
    def load_index(self) -> dict:
        """Загрузка индекса кэша"""
        try:
            if self.index_file.exists():
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки индекса кэша: {e}")
        return {}
    
    def save_index(self):
        """Сохранение индекса кэша"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения индекса кэша: {e}")
    
    def _get_cache_key(self, url: str, params: Dict = None) -> str:
        """Создание ключа кэша на основе URL и параметров"""
        cache_string = url
        if params:
            # Сортируем параметры для получения консистентного ключа
            sorted_params = sorted(params.items())
            cache_string += str(sorted_params)
        
        return hashlib.md5(cache_string.encode('utf-8')).hexdigest()
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """Получение пути к файлу кэша"""
        return self.cache_dir / f"{cache_key}.json"
    
    def is_valid(self, cache_key: str) -> bool:
        """Проверка валидности кэша"""
        try:
            if cache_key not in self.index:
                return False
            
            cache_info = self.index[cache_key]
            created_time = cache_info.get('created_time', 0)
            ttl = cache_info.get('ttl', self.default_ttl)
            
            return time.time() - created_time < ttl
        except Exception as e:
            logger.error(f"Ошибка проверки валидности кэша {cache_key}: {e}")
            return False
    
    def get(self, url: str, params: Dict = None) -> Optional[Any]:
        """Получение данных из кэша"""
        try:
            cache_key = self._get_cache_key(url, params)
            
            if not self.is_valid(cache_key):
                return None
            
            cache_path = self._get_cache_path(cache_key)
            if not cache_path.exists():
                # Удаляем запись из индекса если файл не существует
                if cache_key in self.index:
                    del self.index[cache_key]
                    self.save_index()
                return None
            
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.debug(f"Данные получены из кэша: {cache_key}")
            return data
            
        except Exception as e:
            logger.error(f"Ошибка получения данных из кэша для {url}: {e}")
            return None
    
    def set(self, url: str, data: Any, params: Dict = None, ttl: int = None) -> bool:
        """Сохранение данных в кэш"""
        try:
            cache_key = self._get_cache_key(url, params)
            cache_path = self._get_cache_path(cache_key)
            
            # Сохраняем данные
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Обновляем индекс
            self.index[cache_key] = {
                'url': url,
                'params': params or {},
                'created_time': time.time(),
                'ttl': ttl or self.default_ttl,
                'size': os.path.getsize(cache_path)
            }
            
            self.save_index()
            logger.debug(f"Данные сохранены в кэш: {cache_key}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения данных в кэш для {url}: {e}")
            return False
    
    def delete(self, url: str, params: Dict = None) -> bool:
        """Удаление данных из кэша"""
        try:
            cache_key = self._get_cache_key(url, params)
            cache_path = self._get_cache_path(cache_key)
            
            # Удаляем файл
            if cache_path.exists():
                cache_path.unlink()
            
            # Удаляем из индекса
            if cache_key in self.index:
                del self.index[cache_key]
                self.save_index()
            
            logger.debug(f"Данные удалены из кэша: {cache_key}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка удаления данных из кэша для {url}: {e}")
            return False
    
    def clear_expired(self) -> int:
        """Очистка просроченного кэша"""
        try:
            expired_keys = []
            current_time = time.time()
            
            for cache_key, cache_info in self.index.items():
                created_time = cache_info.get('created_time', 0)
                ttl = cache_info.get('ttl', self.default_ttl)
                
                if current_time - created_time >= ttl:
                    expired_keys.append(cache_key)
            
            # Удаляем просроченные записи
            for cache_key in expired_keys:
                cache_path = self._get_cache_path(cache_key)
                if cache_path.exists():
                    cache_path.unlink()
                del self.index[cache_key]
            
            if expired_keys:
                self.save_index()
                logger.info(f"Удалено {len(expired_keys)} просроченных записей кэша")
            
            return len(expired_keys)
            
        except Exception as e:
            logger.error(f"Ошибка очистки просроченного кэша: {e}")
            return 0
    
    def clear_all(self) -> bool:
        """Полная очистка кэша"""
        try:
            # Удаляем все файлы кэша
            for cache_path in self.cache_dir.glob("*.json"):
                if cache_path.name != "cache_index.json":
                    cache_path.unlink()
            
            # Очищаем индекс
            self.index = {}
            self.save_index()
            
            logger.info("Кэш полностью очищен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка полной очистки кэша: {e}")
            return False
    
    def get_stats(self) -> dict:
        """Получение статистики кэша"""
        try:
            total_size = 0
            valid_count = 0
            expired_count = 0
            current_time = time.time()
            
            for cache_key, cache_info in self.index.items():
                total_size += cache_info.get('size', 0)
                created_time = cache_info.get('created_time', 0)
                ttl = cache_info.get('ttl', self.default_ttl)
                
                if current_time - created_time < ttl:
                    valid_count += 1
                else:
                    expired_count += 1
            
            return {
                'total_entries': len(self.index),
                'valid_entries': valid_count,
                'expired_entries': expired_count,
                'total_size_bytes': total_size,
                'cache_dir': str(self.cache_dir)
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики кэша: {e}")
            return {}

class MetadataCache:
    """Специализированный кэш для метаданных обновлений"""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager
    
    def get_version_info(self, server_url: str) -> Optional[dict]:
        """Получение информации о версии из кэша"""
        return self.cache_manager.get(f"{server_url}/version.txt", ttl=300)  # 5 минут
    
    def set_version_info(self, server_url: str, version_info: dict) -> bool:
        """Сохранение информации о версии в кэш"""
        return self.cache_manager.set(f"{server_url}/version.txt", version_info, ttl=300)
    
    def get_files_list(self, server_url: str, version: str) -> Optional[dict]:
        """Получение списка файлов из кэша"""
        return self.cache_manager.get(f"{server_url}/files_list_v{version}.txt", ttl=1800)  # 30 минут
    
    def set_files_list(self, server_url: str, version: str, files_list: dict) -> bool:
        """Сохранение списка файлов в кэш"""
        return self.cache_manager.set(f"{server_url}/files_list_v{version}.txt", files_list, ttl=1800)
    
    def get_manifest(self, manifest_url: str) -> Optional[dict]:
        """Получение манифеста из кэша"""
        return self.cache_manager.get(manifest_url, ttl=3600)  # 1 час
    
    def set_manifest(self, manifest_url: str, manifest_data: dict) -> bool:
        """Сохранение манифеста в кэш"""
        return self.cache_manager.set(manifest_url, manifest_data, ttl=3600)
    
    def invalidate_version(self, server_url: str, version: str = None):
        """Инвалидация кэша для конкретной версии"""
        # Удаляем информацию о версии
        self.cache_manager.delete(f"{server_url}/version.txt")
        
        # Если указана версия, удаляем связанные с ней данные
        if version:
            self.cache_manager.delete(f"{server_url}/files_list_v{version}.txt")

def format_cache_size(size_bytes: int) -> str:
    """Форматирование размера кэша в читаемый вид"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

# Глобальный экземпляр менеджера кэша
_cache_manager = None

def get_cache_manager() -> CacheManager:
    """Получение глобального экземпляра менеджера кэша"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager

def get_metadata_cache() -> MetadataCache:
    """Получение экземпляра кэша метаданных"""
    return MetadataCache(get_cache_manager())