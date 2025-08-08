"""
Система оптимизации пропускной способности и управления трафиком
"""

import asyncio
import aiohttp
import time
import json
import logging
import statistics
import os
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from collections import deque
import threading

logger = logging.getLogger(__name__)

@dataclass
class BandwidthSample:
    """Образец измерения пропускной способности"""
    timestamp: float
    bytes_per_second: float
    source: str  # "download", "upload", "peer"
    
@dataclass
class ConnectionProfile:
    """Профиль соединения пользователя"""
    estimated_bandwidth: float = 0.0  # МБ/с
    peak_bandwidth: float = 0.0
    average_bandwidth: float = 0.0
    latency: float = 0.0  # мс
    connection_type: str = "unknown"  # "broadband", "mobile", "slow"
    reliability_score: float = 1.0  # 0.0 - 1.0
    last_updated: float = field(default_factory=time.time)

@dataclass
class DownloadChunk:
    """Чанк для параллельной загрузки"""
    start: int
    end: int
    url: str
    completed: bool = False
    bytes_downloaded: int = 0
    speed: float = 0.0
    retry_count: int = 0

class BandwidthMonitor:
    """Мониторинг пропускной способности"""
    
    def __init__(self, sample_size: int = 100):
        self.samples: deque = deque(maxlen=sample_size)
        self.current_speed = 0.0
        self.peak_speed = 0.0
        self.average_speed = 0.0
        self._lock = threading.Lock()
    
    def add_sample(self, bytes_downloaded: int, time_elapsed: float, source: str = "download"):
        """Добавление образца скорости"""
        if time_elapsed > 0:
            bytes_per_second = bytes_downloaded / time_elapsed
            
            with self._lock:
                sample = BandwidthSample(
                    timestamp=time.time(),
                    bytes_per_second=bytes_per_second,
                    source=source
                )
                
                self.samples.append(sample)
                self.current_speed = bytes_per_second / 1024 / 1024  # МБ/с
                
                # Обновляем статистику
                if self.samples:
                    speeds = [s.bytes_per_second / 1024 / 1024 for s in self.samples]
                    self.peak_speed = max(speeds)
                    self.average_speed = statistics.mean(speeds)
    
    def get_current_bandwidth(self) -> float:
        """Получение текущей пропускной способности в МБ/с"""
        with self._lock:
            return self.current_speed
    
    def get_average_bandwidth(self, window_seconds: int = 60) -> float:
        """Получение средней пропускной способности за окно времени"""
        current_time = time.time()
        cutoff_time = current_time - window_seconds
        
        with self._lock:
            recent_samples = [
                s for s in self.samples 
                if s.timestamp >= cutoff_time
            ]
            
            if recent_samples:
                speeds = [s.bytes_per_second / 1024 / 1024 for s in recent_samples]
                return statistics.mean(speeds)
            
            return 0.0
    
    def get_statistics(self) -> dict:
        """Получение статистики мониторинга"""
        with self._lock:
            return {
                'current_speed_mbps': self.current_speed,
                'average_speed_mbps': self.average_speed,
                'peak_speed_mbps': self.peak_speed,
                'samples_count': len(self.samples),
                'last_sample_time': self.samples[-1].timestamp if self.samples else 0
            }

class AdaptiveBandwidthController:
    """Адаптивный контроллер пропускной способности"""
    
    def __init__(self, initial_connections: int = 4):
        self.max_connections = initial_connections
        self.min_connections = 1
        self.max_connections_limit = 16
        self.current_connections = initial_connections
        self.chunk_size = 1024 * 1024  # 1MB начальный размер чанка
        self.min_chunk_size = 64 * 1024  # 64KB минимум
        self.max_chunk_size = 8 * 1024 * 1024  # 8MB максимум
        
        self.performance_history = deque(maxlen=10)
        self.adjustment_threshold = 0.1  # 10% изменение для корректировки
        
    def analyze_performance(self, download_speed: float, target_speed: float):
        """Анализ производительности и корректировка параметров"""
        
        performance_ratio = download_speed / max(target_speed, 0.1)
        self.performance_history.append(performance_ratio)
        
        if len(self.performance_history) < 3:
            return  # Недостаточно данных
        
        # Вычисляем тренд производительности
        recent_performance = statistics.mean(list(self.performance_history)[-3:])
        
        if recent_performance < 0.8:  # Производительность ниже 80% от цели
            self._increase_aggressiveness()
        elif recent_performance > 1.2:  # Производительность выше 120% от цели
            self._decrease_aggressiveness()
    
    def _increase_aggressiveness(self):
        """Увеличение агрессивности загрузки"""
        # Увеличиваем количество соединений
        if self.current_connections < self.max_connections_limit:
            self.current_connections = min(
                self.current_connections + 1,
                self.max_connections_limit
            )
            logger.debug(f"Увеличено количество соединений до {self.current_connections}")
        
        # Увеличиваем размер чанка
        if self.chunk_size < self.max_chunk_size:
            self.chunk_size = min(
                int(self.chunk_size * 1.5),
                self.max_chunk_size
            )
            logger.debug(f"Увеличен размер чанка до {self.chunk_size // 1024}KB")
    
    def _decrease_aggressiveness(self):
        """Уменьшение агрессивности загрузки"""
        # Уменьшаем количество соединений
        if self.current_connections > self.min_connections:
            self.current_connections = max(
                self.current_connections - 1,
                self.min_connections
            )
            logger.debug(f"Уменьшено количество соединений до {self.current_connections}")
        
        # Уменьшаем размер чанка
        if self.chunk_size > self.min_chunk_size:
            self.chunk_size = max(
                int(self.chunk_size * 0.8),
                self.min_chunk_size
            )
            logger.debug(f"Уменьшен размер чанка до {self.chunk_size // 1024}KB")
    
    def get_optimal_chunk_size(self, file_size: int) -> int:
        """Получение оптимального размера чанка для файла"""
        if file_size < self.chunk_size * 2:
            # Для маленьких файлов используем меньший чанк
            return max(file_size // 4, self.min_chunk_size)
        
        return self.chunk_size
    
    def get_connection_count(self) -> int:
        """Получение оптимального количества соединений"""
        return self.current_connections

class ParallelDownloader:
    """Параллельный загрузчик с оптимизацией пропускной способности"""
    
    def __init__(self, bandwidth_monitor: BandwidthMonitor, 
                 controller: AdaptiveBandwidthController):
        self.bandwidth_monitor = bandwidth_monitor
        self.controller = controller
        self.active_downloads = {}
        self.download_stats = {}
    
    async def download_file(self, url: str, local_path: str, 
                          progress_callback: Optional[Callable] = None,
                          expected_size: Optional[int] = None) -> bool:
        """Параллельная загрузка файла с оптимизацией"""
        
        try:
            # Определяем размер файла если не указан
            if expected_size is None:
                expected_size = await self._get_file_size(url)
            
            if expected_size is None:
                logger.warning("Не удалось определить размер файла, используем обычную загрузку")
                return await self._simple_download(url, local_path, progress_callback)
            
            # Проверяем поддержку Range requests
            if not await self._check_range_support(url):
                logger.info("Сервер не поддерживает Range requests, используем обычную загрузку")
                return await self._simple_download(url, local_path, progress_callback)
            
            # Создаем чанки для параллельной загрузки
            chunks = self._create_chunks(url, expected_size)
            
            # Загружаем чанки параллельно
            success = await self._download_chunks_parallel(
                chunks, local_path, progress_callback, expected_size
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка параллельной загрузки: {e}")
            return False
    
    async def _get_file_size(self, url: str) -> Optional[int]:
        """Определение размера файла"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url) as response:
                    if response.status == 200:
                        return int(response.headers.get('content-length', 0))
        except Exception as e:
            logger.debug(f"Ошибка получения размера файла: {e}")
        
        return None
    
    async def _check_range_support(self, url: str) -> bool:
        """Проверка поддержки Range requests"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url) as response:
                    accept_ranges = response.headers.get('accept-ranges', '')
                    return 'bytes' in accept_ranges.lower()
        except Exception as e:
            logger.debug(f"Ошибка проверки Range support: {e}")
        
        return False
    
    def _create_chunks(self, url: str, file_size: int) -> List[DownloadChunk]:
        """Создание чанков для параллельной загрузки"""
        chunk_size = self.controller.get_optimal_chunk_size(file_size)
        connection_count = self.controller.get_connection_count()
        
        # Адаптируем количество соединений к размеру файла
        optimal_connections = min(
            connection_count,
            max(1, file_size // chunk_size)
        )
        
        chunks = []
        chunk_file_size = file_size // optimal_connections
        
        for i in range(optimal_connections):
            start = i * chunk_file_size
            if i == optimal_connections - 1:
                end = file_size - 1  # Последний чанк получает остаток
            else:
                end = start + chunk_file_size - 1
            
            chunk = DownloadChunk(
                start=start,
                end=end,
                url=url
            )
            chunks.append(chunk)
        
        logger.info(f"Создано {len(chunks)} чанков для параллельной загрузки")
        return chunks
    
    async def _download_chunks_parallel(self, chunks: List[DownloadChunk], 
                                      local_path: str, progress_callback: Optional[Callable],
                                      total_size: int) -> bool:
        """Параллельная загрузка чанков"""
        
        total_downloaded = 0
        download_start_time = time.time()
        
        # Временные файлы для чанков
        chunk_files = []
        for i, chunk in enumerate(chunks):
            chunk_file = f"{local_path}.chunk{i}"
            chunk_files.append(chunk_file)
        
        try:
            # Запускаем загрузку всех чанков параллельно
            tasks = []
            for i, chunk in enumerate(chunks):
                task = self._download_single_chunk(chunk, chunk_files[i])
                tasks.append(task)
            
            # Мониторим прогресс
            while not all(chunk.completed for chunk in chunks):
                await asyncio.sleep(0.1)
                
                # Обновляем статистику
                current_downloaded = sum(chunk.bytes_downloaded for chunk in chunks)
                if progress_callback:
                    progress = current_downloaded / total_size
                    elapsed = time.time() - download_start_time
                    speed = current_downloaded / elapsed / 1024 / 1024 if elapsed > 0 else 0
                    progress_callback(progress, speed)
                
                # Обновляем мониторинг пропускной способности
                if current_downloaded > total_downloaded:
                    bytes_diff = current_downloaded - total_downloaded
                    self.bandwidth_monitor.add_sample(bytes_diff, 0.1, "parallel_download")
                    total_downloaded = current_downloaded
            
            # Ждем завершения всех задач
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Проверяем успешность загрузки всех чанков
            if not all(chunk.completed for chunk in chunks):
                raise Exception("Не все чанки загружены успешно")
            
            # Объединяем чанки в финальный файл
            await self._merge_chunks(chunk_files, local_path)
            
            # Обновляем контроллер производительности
            total_elapsed = time.time() - download_start_time
            actual_speed = total_size / total_elapsed / 1024 / 1024
            target_speed = self.bandwidth_monitor.get_average_bandwidth()
            self.controller.analyze_performance(actual_speed, target_speed)
            
            logger.info(f"Параллельная загрузка завершена за {total_elapsed:.1f}с со скоростью {actual_speed:.1f} МБ/с")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка параллельной загрузки чанков: {e}")
            return False
        
        finally:
            # Удаляем временные файлы
            for chunk_file in chunk_files:
                try:
                    if os.path.exists(chunk_file):
                        os.unlink(chunk_file)
                except Exception as e:
                    logger.warning(f"Не удалось удалить временный файл {chunk_file}: {e}")
    
    async def _download_single_chunk(self, chunk: DownloadChunk, chunk_file: str):
        """Загрузка одного чанка"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                headers = {
                    'Range': f'bytes={chunk.start}-{chunk.end}'
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(chunk.url, headers=headers) as response:
                        if response.status not in [200, 206]:
                            raise aiohttp.ClientError(f"HTTP {response.status}")
                        
                        start_time = time.time()
                        
                        with open(chunk_file, 'wb') as f:
                            async for data in response.content.iter_chunked(8192):
                                f.write(data)
                                chunk.bytes_downloaded += len(data)
                        
                        elapsed = time.time() - start_time
                        chunk.speed = chunk.bytes_downloaded / elapsed / 1024 / 1024 if elapsed > 0 else 0
                        chunk.completed = True
                        
                        logger.debug(f"Чанк {chunk.start}-{chunk.end} загружен со скоростью {chunk.speed:.1f} МБ/с")
                        return
                        
            except Exception as e:
                chunk.retry_count += 1
                logger.warning(f"Ошибка загрузки чанка {chunk.start}-{chunk.end} (попытка {attempt + 1}): {e}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
        
        logger.error(f"Не удалось загрузить чанк {chunk.start}-{chunk.end} после {max_retries} попыток")
    
    async def _merge_chunks(self, chunk_files: List[str], output_file: str):
        """Объединение чанков в финальный файл"""
        with open(output_file, 'wb') as output:
            for chunk_file in chunk_files:
                if os.path.exists(chunk_file):
                    with open(chunk_file, 'rb') as chunk:
                        output.write(chunk.read())
    
    async def _simple_download(self, url: str, local_path: str, 
                             progress_callback: Optional[Callable] = None) -> bool:
        """Простая загрузка без параллелизации"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return False
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    start_time = time.time()
                    
                    with open(local_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Обновляем прогресс
                            if progress_callback and total_size > 0:
                                progress = downloaded / total_size
                                elapsed = time.time() - start_time
                                speed = downloaded / elapsed / 1024 / 1024 if elapsed > 0 else 0
                                progress_callback(progress, speed)
                    
                    return True
                    
        except Exception as e:
            logger.error(f"Ошибка простой загрузки: {e}")
            return False

class NetworkOptimizer:
    """Оптимизатор сетевых операций"""
    
    def __init__(self):
        self.bandwidth_monitor = BandwidthMonitor()
        self.controller = AdaptiveBandwidthController()
        self.parallel_downloader = ParallelDownloader(self.bandwidth_monitor, self.controller)
        self.connection_profile = ConnectionProfile()
        
    async def initialize(self):
        """Инициализация и калибровка соединения"""
        logger.info("Инициализация оптимизатора сетевых операций...")
        
        # Выполняем тестирование соединения
        await self._calibrate_connection()
        
        # Определяем тип соединения
        self._classify_connection()
        
        logger.info(f"Соединение откалибровано: {self.connection_profile.estimated_bandwidth:.1f} МБ/с")
    
    async def _calibrate_connection(self):
        """Калибровка параметров соединения"""
        # Простая калибровка - можно расширить более сложным тестированием
        try:
            test_url = "https://httpbin.org/bytes/1024"  # 1KB тестовый файл
            
            # Делаем несколько тестовых запросов
            speeds = []
            for _ in range(3):
                start_time = time.time()
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(test_url) as response:
                        if response.status == 200:
                            await response.read()
                
                elapsed = time.time() - start_time
                if elapsed > 0:
                    speed = 1024 / elapsed / 1024  # МБ/с
                    speeds.append(speed)
            
            if speeds:
                self.connection_profile.estimated_bandwidth = statistics.mean(speeds)
                self.connection_profile.peak_bandwidth = max(speeds)
                
        except Exception as e:
            logger.warning(f"Ошибка калибровки соединения: {e}")
            # Устанавливаем консервативные значения по умолчанию
            self.connection_profile.estimated_bandwidth = 1.0  # 1 МБ/с
            self.connection_profile.peak_bandwidth = 1.0
    
    def _classify_connection(self):
        """Классификация типа соединения"""
        bandwidth = self.connection_profile.estimated_bandwidth
        
        if bandwidth >= 10:  # >= 10 МБ/с
            self.connection_profile.connection_type = "broadband"
            # Настройки для быстрого соединения
            self.controller.max_connections_limit = 16
            self.controller.current_connections = 8
        elif bandwidth >= 1:  # 1-10 МБ/с
            self.connection_profile.connection_type = "mobile"
            # Настройки для мобильного соединения
            self.controller.max_connections_limit = 8
            self.controller.current_connections = 4
        else:  # < 1 МБ/с
            self.connection_profile.connection_type = "slow"
            # Консервативные настройки для медленного соединения
            self.controller.max_connections_limit = 4
            self.controller.current_connections = 2
    
    async def optimized_download(self, url: str, local_path: str,
                               progress_callback: Optional[Callable] = None) -> bool:
        """Оптимизированная загрузка файла"""
        return await self.parallel_downloader.download_file(
            url, local_path, progress_callback
        )
    
    def get_statistics(self) -> dict:
        """Получение полной статистики оптимизатора"""
        return {
            'connection_profile': {
                'estimated_bandwidth_mbps': self.connection_profile.estimated_bandwidth,
                'peak_bandwidth_mbps': self.connection_profile.peak_bandwidth,
                'connection_type': self.connection_profile.connection_type,
                'reliability_score': self.connection_profile.reliability_score
            },
            'bandwidth_monitor': self.bandwidth_monitor.get_statistics(),
            'controller': {
                'current_connections': self.controller.current_connections,
                'chunk_size_kb': self.controller.chunk_size // 1024,
                'performance_samples': len(self.controller.performance_history)
            }
        }

# Глобальный экземпляр оптимизатора
_network_optimizer = None

def get_network_optimizer() -> NetworkOptimizer:
    """Получение глобального экземпляра оптимизатора"""
    global _network_optimizer
    if _network_optimizer is None:
        _network_optimizer = NetworkOptimizer()
    return _network_optimizer