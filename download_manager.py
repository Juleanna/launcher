"""
Менеджер загрузок с поддержкой возобновления и паузы
"""

import os
import json
import asyncio
import aiohttp
import logging
from typing import Dict, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime

try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False
    logging.warning("aiofiles недоступен - используется синхронное чтение файлов")

logger = logging.getLogger(__name__)

@dataclass
class DownloadState:
    """Состояние загрузки для возобновления"""
    url: str
    dest_path: str
    total_size: int
    downloaded_size: int
    supports_resume: bool
    created_at: str
    last_modified: str = ""
    etag: str = ""
    chunk_size: int = 8192

    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DownloadState':
        return cls(**data)

class ResumableDownload:
    """Класс для возобновляемых загрузок"""
    
    def __init__(self, url: str, dest_path: str, 
                 progress_callback: Optional[Callable] = None,
                 stats_callback: Optional[Callable] = None):
        self.url = url
        self.dest_path = dest_path
        self.progress_callback = progress_callback
        self.stats_callback = stats_callback
        
        self.temp_file = f"{dest_path}.tmp"
        self.state_file = f"{dest_path}.state"
        self.state: Optional[DownloadState] = None
        
        self.is_paused = False
        self.is_cancelled = False
        self.start_time = None
    
    def save_state(self):
        """Сохранение состояния загрузки"""
        if self.state:
            try:
                with open(self.state_file, 'w', encoding='utf-8') as f:
                    json.dump(self.state.to_dict(), f)
                logger.debug(f"Состояние сохранено: {self.state_file}")
            except Exception as e:
                logger.error(f"Ошибка сохранения состояния: {e}")
    
    def load_state(self) -> bool:
        """Загрузка состояния загрузки"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                self.state = DownloadState.from_dict(state_data)
                logger.debug(f"Состояние загружено: {self.state_file}")
                return True
        except Exception as e:
            logger.error(f"Ошибка загрузки состояния: {e}")
        return False
    
    def cleanup_state(self):
        """Очистка временных файлов"""
        for file_path in [self.temp_file, self.state_file]:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"Не удалось удалить {file_path}: {e}")
    
    async def check_resume_support(self, session: aiohttp.ClientSession) -> tuple:
        """Проверка поддержки возобновления загрузки"""
        try:
            async with session.head(self.url) as response:
                if response.status != 200:
                    logger.warning(f"HEAD запрос вернул {response.status}")
                    return False, 0, {}
                
                headers = dict(response.headers)
                supports_resume = 'accept-ranges' in headers and headers['accept-ranges'] == 'bytes'
                content_length = int(headers.get('content-length', 0))
                
                return supports_resume, content_length, headers
                
        except Exception as e:
            logger.warning(f"Ошибка проверки поддержки возобновления: {e}")
            return False, 0, {}
    
    async def download(self, session: aiohttp.ClientSession) -> bool:
        """Основной метод загрузки"""
        try:
            self.start_time = asyncio.get_event_loop().time()
            
            # Загружаем существующее состояние
            resumed = self.load_state()
            
            # Проверяем поддержку возобновления
            supports_resume, total_size, headers = await self.check_resume_support(session)
            
            # Если это новая загрузка
            if not resumed or not self.state:
                self.state = DownloadState(
                    url=self.url,
                    dest_path=self.dest_path,
                    total_size=total_size,
                    downloaded_size=0,
                    supports_resume=supports_resume,
                    created_at=datetime.now().isoformat(),
                    last_modified=headers.get('last-modified', ''),
                    etag=headers.get('etag', '')
                )
            else:
                # Проверяем, не изменился ли файл на сервере
                if (self.state.etag and headers.get('etag') and 
                    self.state.etag != headers.get('etag')):
                    logger.info("Файл изменился на сервере, начинаем загрузку заново")
                    self.state.downloaded_size = 0
                    if os.path.exists(self.temp_file):
                        os.remove(self.temp_file)
            
            # Сохраняем начальное состояние
            self.save_state()
            
            # Настраиваем заголовки для возобновления
            request_headers = {}
            if self.state.supports_resume and self.state.downloaded_size > 0:
                request_headers['Range'] = f'bytes={self.state.downloaded_size}-'
                logger.info(f"Возобновляем загрузку с позиции {self.state.downloaded_size}")
            
            # Начинаем загрузку
            async with session.get(self.url, headers=request_headers) as response:
                if response.status not in [200, 206]:
                    raise Exception(f"HTTP {response.status}: {response.reason}")
                
                # Обновляем размер файла если это частичная загрузка
                if response.status == 206:
                    content_range = response.headers.get('content-range', '')
                    if content_range:
                        # Парсим "bytes 0-1023/2048" формат
                        parts = content_range.split('/')
                        if len(parts) == 2 and parts[1].isdigit():
                            self.state.total_size = int(parts[1])
                
                # Открываем файл для записи
                mode = 'ab' if self.state.downloaded_size > 0 else 'wb'
                if AIOFILES_AVAILABLE:
                    async with aiofiles.open(self.temp_file, mode) as f:
                        await self._download_chunks(response, f)
                else:
                    with open(self.temp_file, mode) as f:
                        await self._download_chunks_sync(response, f)
            
            # Проверяем завершенность загрузки
            if self.state.total_size > 0 and self.state.downloaded_size >= self.state.total_size:
                # Перемещаем временный файл в конечное место
                if os.path.exists(self.dest_path):
                    os.remove(self.dest_path)
                os.rename(self.temp_file, self.dest_path)
                
                # Очищаем временные файлы
                self.cleanup_state()
                
                logger.info(f"Загрузка завершена: {self.dest_path}")
                return True
            else:
                logger.warning("Загрузка не завершена полностью")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка загрузки {self.url}: {e}")
            # Сохраняем состояние при ошибке для возможности возобновления
            self.save_state()
            raise
    
    async def _download_chunks(self, response, f):
        """Асинхронная загрузка чанками"""
        async for chunk in response.content.iter_chunked(self.state.chunk_size):
            if self.is_cancelled:
                logger.info("Загрузка отменена")
                return
            
            # Пауза
            while self.is_paused and not self.is_cancelled:
                await asyncio.sleep(0.1)
            
            if self.is_cancelled:
                return
            
            await f.write(chunk)
            self.state.downloaded_size += len(chunk)
            
            # Обновляем прогресс
            self._update_progress()
            
            # Периодически сохраняем состояние
            if self.state.downloaded_size % (self.state.chunk_size * 100) == 0:
                self.save_state()
    
    async def _download_chunks_sync(self, response, f):
        """Синхронная загрузка чанками"""
        async for chunk in response.content.iter_chunked(self.state.chunk_size):
            if self.is_cancelled:
                logger.info("Загрузка отменена")
                return
            
            # Пауза
            while self.is_paused and not self.is_cancelled:
                await asyncio.sleep(0.1)
            
            if self.is_cancelled:
                return
            
            f.write(chunk)
            self.state.downloaded_size += len(chunk)
            
            # Обновляем прогресс
            self._update_progress()
            
            # Периодически сохраняем состояние
            if self.state.downloaded_size % (self.state.chunk_size * 100) == 0:
                self.save_state()
    
    def _update_progress(self):
        """Обновление прогресса и статистики"""
        # Обновляем прогресс
        if self.progress_callback:
            progress = int((self.state.downloaded_size / self.state.total_size) * 100) if self.state.total_size > 0 else 0
            self.progress_callback(min(progress, 100))
        
        # Обновляем статистику
        if self.stats_callback and self.start_time:
            elapsed = asyncio.get_event_loop().time() - self.start_time
            if elapsed > 0:
                speed = self.state.downloaded_size / elapsed / 1024  # КБ/с
                remaining_bytes = self.state.total_size - self.state.downloaded_size
                eta = remaining_bytes / (speed * 1024) if speed > 0 else 0
                
                stats = f"Скорость: {speed:.1f} КБ/с"
                if eta > 0:
                    stats += f", Осталось: {eta:.0f} сек"
                self.stats_callback(stats)
    
    def pause(self):
        """Приостановить загрузку"""
        self.is_paused = True
        self.save_state()
        logger.info(f"Загрузка приостановлена: {self.url}")
    
    def resume(self):
        """Возобновить загрузку"""
        self.is_paused = False
        logger.info(f"Загрузка возобновлена: {self.url}")
    
    def cancel(self):
        """Отменить загрузку"""
        self.is_cancelled = True
        self.cleanup_state()
        logger.info(f"Загрузка отменена: {self.url}")

class DownloadManager:
    """Менеджер для управления множественными загрузками"""
    
    def __init__(self):
        self.downloads: Dict[str, ResumableDownload] = {}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=600),
            connector=aiohttp.TCPConnector(limit=10)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def add_download(self, url: str, dest_path: str, 
                    progress_callback: Optional[Callable] = None,
                    stats_callback: Optional[Callable] = None) -> str:
        """Добавить загрузку в очередь"""
        download_id = f"{url}_{dest_path}"
        
        download = ResumableDownload(
            url=url, 
            dest_path=dest_path,
            progress_callback=progress_callback,
            stats_callback=stats_callback
        )
        
        self.downloads[download_id] = download
        return download_id
    
    async def start_download(self, download_id: str) -> bool:
        """Запустить загрузку"""
        if download_id not in self.downloads:
            logger.error(f"Загрузка не найдена: {download_id}")
            return False
        
        download = self.downloads[download_id]
        try:
            result = await download.download(self.session)
            if result:
                # Удаляем завершенную загрузку из списка
                del self.downloads[download_id]
            return result
        except Exception as e:
            logger.error(f"Ошибка выполнения загрузки {download_id}: {e}")
            return False
    
    def pause_download(self, download_id: str):
        """Приостановить загрузку"""
        if download_id in self.downloads:
            self.downloads[download_id].pause()
    
    def resume_download(self, download_id: str):
        """Возобновить загрузку"""
        if download_id in self.downloads:
            self.downloads[download_id].resume()
    
    def cancel_download(self, download_id: str):
        """Отменить загрузку"""
        if download_id in self.downloads:
            self.downloads[download_id].cancel()
            del self.downloads[download_id]
    
    def get_download_state(self, download_id: str) -> Optional[DownloadState]:
        """Получить состояние загрузки"""
        if download_id in self.downloads:
            return self.downloads[download_id].state
        return None
    
    def list_active_downloads(self) -> list:
        """Список активных загрузок"""
        return list(self.downloads.keys())

# Глобальный экземпляр менеджера загрузок
_download_manager = None

def get_download_manager() -> DownloadManager:
    """Получение глобального экземпляра менеджера загрузок"""
    global _download_manager
    if _download_manager is None:
        _download_manager = DownloadManager()
    return _download_manager