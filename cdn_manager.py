"""
Система управления CDN и выбора оптимальных зеркал
"""

import asyncio
import aiohttp
import time
import json
import logging
import random
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class Mirror:
    """Информация о зеркале/CDN"""
    url: str
    name: str
    region: str = "unknown"
    priority: int = 1  # 1 = высший, 10 = низший
    response_time: float = float('inf')
    success_rate: float = 1.0
    bandwidth: float = 0.0  # МБ/с
    last_checked: float = 0.0
    failures: int = 0
    total_requests: int = 0
    active: bool = True


@dataclass 
class DownloadStats:
    """Статистика загрузки"""
    start_time: float = field(default_factory=time.time)
    bytes_downloaded: int = 0
    total_size: int = 0
    speed: float = 0.0
    
    @property
    def progress(self) -> float:
        if self.total_size > 0:
            return self.bytes_downloaded / self.total_size
        return 0.0


class CDNManager:
    """Менеджер CDN и зеркал"""
    
    def __init__(self, config_file: str = "cdn_config.json"):
        self.mirrors: List[Mirror] = []
        self.config_file = config_file
        self.performance_history = {}
        self.load_config()
        
    def load_config(self):
        """Загрузка конфигурации CDN"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            self.mirrors = []
            for mirror_data in config.get('mirrors', []):
                mirror = Mirror(
                    url=mirror_data['url'],
                    name=mirror_data['name'],
                    region=mirror_data.get('region', 'unknown'),
                    priority=mirror_data.get('priority', 1)
                )
                self.mirrors.append(mirror)
                
            logger.info(f"Загружено {len(self.mirrors)} зеркал")
            
        except FileNotFoundError:
            # Создаем конфигурацию по умолчанию
            self._create_default_config()
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации CDN: {e}")
            self._create_default_config()
    
    def _create_default_config(self):
        """Создание конфигурации по умолчанию"""
        default_mirrors = [
            {
                "url": "https://cdn1.example.com/",
                "name": "Main CDN",
                "region": "global",
                "priority": 1
            },
            {
                "url": "https://cdn2.example.com/",
                "name": "Backup CDN",
                "region": "global", 
                "priority": 2
            },
            {
                "url": "https://mirror.example.com/",
                "name": "Mirror Server",
                "region": "eu",
                "priority": 3
            }
        ]
        
        config = {
            "mirrors": default_mirrors,
            "check_interval": 300,
            "timeout": 30,
            "max_failures": 3
        }
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self.load_config()
            
        except Exception as e:
            logger.error(f"Ошибка создания конфигурации по умолчанию: {e}")
    
    async def check_mirror_health(self, mirror: Mirror) -> bool:
        """Проверка здоровья зеркала"""
        try:
            start_time = time.time()
            
            async with aiohttp.ClientSession() as session:
                # Проверяем доступность с помощью HEAD запроса
                test_url = urljoin(mirror.url, "version.txt")
                
                async with session.head(
                    test_url, 
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    response_time = time.time() - start_time
                    mirror.response_time = response_time
                    mirror.last_checked = time.time()
                    
                    if response.status == 200:
                        mirror.total_requests += 1
                        mirror.failures = max(0, mirror.failures - 1)  # Уменьшаем счетчик ошибок
                        mirror.active = True
                        
                        # Обновляем коэффициент успешности
                        success_requests = mirror.total_requests - mirror.failures
                        mirror.success_rate = success_requests / max(mirror.total_requests, 1)
                        
                        logger.debug(f"Зеркало {mirror.name} доступно (время ответа: {response_time:.2f}с)")
                        return True
                    else:
                        raise aiohttp.ClientError(f"HTTP {response.status}")
                        
        except Exception as e:
            mirror.failures += 1
            mirror.total_requests += 1
            mirror.last_checked = time.time()
            
            # Деактивируем зеркало при превышении лимита ошибок
            if mirror.failures >= 3:
                mirror.active = False
                logger.warning(f"Зеркало {mirror.name} деактивировано (ошибки: {mirror.failures})")
            
            logger.debug(f"Зеркало {mirror.name} недоступно: {e}")
            return False
    
    async def check_all_mirrors(self):
        """Проверка всех зеркал"""
        tasks = [self.check_mirror_health(mirror) for mirror in self.mirrors]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        active_count = sum(1 for mirror in self.mirrors if mirror.active)
        logger.info(f"Активных зеркал: {active_count}/{len(self.mirrors)}")
    
    def get_best_mirror(self, file_path: str = None) -> Optional[Mirror]:
        """Выбор лучшего зеркала"""
        active_mirrors = [m for m in self.mirrors if m.active]
        
        if not active_mirrors:
            logger.error("Нет доступных зеркал!")
            return None
        
        # Сортируем по приоритету, времени ответа и коэффициенту успешности
        def mirror_score(mirror: Mirror) -> float:
            # Чем меньше score, тем лучше зеркало
            priority_score = mirror.priority * 100
            response_score = mirror.response_time * 1000
            failure_score = (1 - mirror.success_rate) * 10000
            
            return priority_score + response_score + failure_score
        
        active_mirrors.sort(key=mirror_score)
        
        best_mirror = active_mirrors[0]
        logger.info(f"Выбрано лучшее зеркало: {best_mirror.name} "
                   f"(время ответа: {best_mirror.response_time:.2f}с, "
                   f"успешность: {best_mirror.success_rate:.1%})")
        
        return best_mirror
    
    def get_fallback_mirrors(self, exclude_mirror: Mirror = None, count: int = 2) -> List[Mirror]:
        """Получение резервных зеркал"""
        active_mirrors = [m for m in self.mirrors if m.active and m != exclude_mirror]
        
        # Сортируем по приоритету и производительности
        active_mirrors.sort(key=lambda m: (m.priority, m.response_time))
        
        return active_mirrors[:count]
    
    async def download_with_fallback(self, file_path: str, local_path: str, 
                                   progress_callback=None) -> bool:
        """Загрузка с автоматическим переключением на резервные зеркала"""
        
        best_mirror = self.get_best_mirror(file_path)
        if not best_mirror:
            return False
        
        # Список зеркал для попыток загрузки
        mirrors_to_try = [best_mirror] + self.get_fallback_mirrors(best_mirror)
        
        for mirror in mirrors_to_try:
            try:
                success = await self._download_from_mirror(
                    mirror, file_path, local_path, progress_callback
                )
                
                if success:
                    logger.info(f"Файл успешно загружен с зеркала {mirror.name}")
                    return True
                    
            except Exception as e:
                logger.warning(f"Ошибка загрузки с зеркала {mirror.name}: {e}")
                # Увеличиваем счетчик ошибок
                mirror.failures += 1
                mirror.total_requests += 1
                continue
        
        logger.error("Не удалось загрузить файл ни с одного зеркала")
        return False
    
    async def _download_from_mirror(self, mirror: Mirror, file_path: str, 
                                  local_path: str, progress_callback=None) -> bool:
        """Загрузка файла с конкретного зеркала"""
        download_url = urljoin(mirror.url, file_path.lstrip('/'))
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    download_url,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as response:
                    
                    if response.status != 200:
                        raise aiohttp.ClientError(f"HTTP {response.status}")
                    
                    total_size = int(response.headers.get('content-length', 0))
                    stats = DownloadStats(total_size=total_size)
                    
                    with open(local_path, 'wb') as f:
                        start_time = time.time()
                        
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            stats.bytes_downloaded += len(chunk)
                            
                            # Вычисляем скорость
                            elapsed = time.time() - start_time
                            if elapsed > 0:
                                stats.speed = stats.bytes_downloaded / elapsed / 1024 / 1024  # МБ/с
                            
                            # Обновляем статистику зеркала
                            mirror.bandwidth = stats.speed
                            
                            # Вызываем callback для обновления прогресса
                            if progress_callback:
                                progress_callback(stats.progress, stats.speed)
                    
                    # Обновляем статистику успешной загрузки
                    mirror.total_requests += 1
                    success_requests = mirror.total_requests - mirror.failures
                    mirror.success_rate = success_requests / mirror.total_requests
                    
                    return True
                    
            except Exception as e:
                logger.error(f"Ошибка загрузки с {mirror.name}: {e}")
                raise
    
    def update_mirror_performance(self, mirror_url: str, response_time: float, 
                                success: bool, bandwidth: float = 0.0):
        """Обновление статистики производительности зеркала"""
        for mirror in self.mirrors:
            if mirror.url == mirror_url:
                mirror.response_time = response_time
                mirror.bandwidth = bandwidth
                mirror.last_checked = time.time()
                mirror.total_requests += 1
                
                if not success:
                    mirror.failures += 1
                else:
                    # Уменьшаем счетчик ошибок при успешной загрузке
                    mirror.failures = max(0, mirror.failures - 1)
                
                # Обновляем коэффициент успешности
                success_requests = mirror.total_requests - mirror.failures
                mirror.success_rate = success_requests / mirror.total_requests
                
                # Деактивируем зеркало при критическом количестве ошибок
                if mirror.failures >= 5 and mirror.success_rate < 0.5:
                    mirror.active = False
                    logger.warning(f"Зеркало {mirror.name} автоматически деактивировано")
                
                break
    
    def get_statistics(self) -> dict:
        """Получение статистики зеркал"""
        stats = {
            'total_mirrors': len(self.mirrors),
            'active_mirrors': sum(1 for m in self.mirrors if m.active),
            'mirrors': []
        }
        
        for mirror in self.mirrors:
            mirror_stats = {
                'name': mirror.name,
                'url': mirror.url,
                'region': mirror.region,
                'active': mirror.active,
                'response_time': mirror.response_time,
                'success_rate': mirror.success_rate,
                'bandwidth': mirror.bandwidth,
                'total_requests': mirror.total_requests,
                'failures': mirror.failures,
                'priority': mirror.priority
            }
            stats['mirrors'].append(mirror_stats)
        
        return stats
    
    def save_performance_data(self):
        """Сохранение данных о производительности"""
        performance_file = "cdn_performance.json"
        
        try:
            data = {
                'last_updated': time.time(),
                'mirrors': []
            }
            
            for mirror in self.mirrors:
                mirror_data = {
                    'url': mirror.url,
                    'response_time': mirror.response_time,
                    'success_rate': mirror.success_rate,
                    'bandwidth': mirror.bandwidth,
                    'failures': mirror.failures,
                    'total_requests': mirror.total_requests,
                    'last_checked': mirror.last_checked
                }
                data['mirrors'].append(mirror_data)
            
            with open(performance_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Ошибка сохранения данных производительности: {e}")


class LoadBalancer:
    """Балансировщик нагрузки для распределения запросов между зеркалами"""
    
    def __init__(self, cdn_manager: CDNManager):
        self.cdn_manager = cdn_manager
        self.round_robin_index = 0
        self.request_counts = {}  # Счетчики запросов по зеркалам
    
    def get_mirror_by_strategy(self, strategy: str = "best_response") -> Optional[Mirror]:
        """Выбор зеркала по стратегии балансировки"""
        
        active_mirrors = [m for m in self.cdn_manager.mirrors if m.active]
        if not active_mirrors:
            return None
        
        if strategy == "round_robin":
            return self._round_robin_selection(active_mirrors)
        elif strategy == "least_connections":
            return self._least_connections_selection(active_mirrors) 
        elif strategy == "weighted_response":
            return self._weighted_response_selection(active_mirrors)
        else:  # best_response (по умолчанию)
            return self.cdn_manager.get_best_mirror()
    
    def _round_robin_selection(self, mirrors: List[Mirror]) -> Mirror:
        """Циклический выбор зеркала"""
        mirror = mirrors[self.round_robin_index % len(mirrors)]
        self.round_robin_index += 1
        return mirror
    
    def _least_connections_selection(self, mirrors: List[Mirror]) -> Mirror:
        """Выбор зеркала с наименьшим количеством запросов"""
        return min(mirrors, key=lambda m: self.request_counts.get(m.url, 0))
    
    def _weighted_response_selection(self, mirrors: List[Mirror]) -> Mirror:
        """Взвешенный выбор на основе времени ответа"""
        # Инвертируем время ответа для весов (быстрые зеркала получают больший вес)
        weights = []
        for mirror in mirrors:
            if mirror.response_time > 0:
                weight = 1 / mirror.response_time
            else:
                weight = 1.0
            weights.append(weight)
        
        # Выбираем зеркало на основе весов
        total_weight = sum(weights)
        if total_weight == 0:
            return random.choice(mirrors)
        
        random_value = random.uniform(0, total_weight)
        cumulative_weight = 0
        
        for i, weight in enumerate(weights):
            cumulative_weight += weight
            if random_value <= cumulative_weight:
                return mirrors[i]
        
        return mirrors[-1]  # Fallback
    
    def record_request(self, mirror_url: str):
        """Запись запроса к зеркалу"""
        self.request_counts[mirror_url] = self.request_counts.get(mirror_url, 0) + 1
    
    def get_load_stats(self) -> dict:
        """Получение статистики нагрузки"""
        return {
            'request_counts': self.request_counts.copy(),
            'round_robin_index': self.round_robin_index,
            'total_requests': sum(self.request_counts.values())
        }


# Глобальный экземпляр менеджера CDN
_cdn_manager = None
_load_balancer = None

def get_cdn_manager() -> CDNManager:
    """Получение глобального экземпляра менеджера CDN"""
    global _cdn_manager
    if _cdn_manager is None:
        _cdn_manager = CDNManager()
    return _cdn_manager

def get_load_balancer() -> LoadBalancer:
    """Получение экземпляра балансировщика нагрузки"""
    global _load_balancer
    if _load_balancer is None:
        _load_balancer = LoadBalancer(get_cdn_manager())
    return _load_balancer