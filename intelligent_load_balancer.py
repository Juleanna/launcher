"""
Система интеллектуальной балансировки нагрузки и распределения ресурсов
"""

import asyncio
import time
import json
import logging
import random
import statistics
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import deque, defaultdict
from enum import Enum
import threading

logger = logging.getLogger(__name__)

class LoadBalancingStrategy(Enum):
    """Стратегии балансировки нагрузки"""
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED_RESPONSE_TIME = "weighted_response_time"
    ADAPTIVE_PERFORMANCE = "adaptive_performance"
    GEOGRAPHIC_PROXIMITY = "geographic_proximity"
    MACHINE_LEARNING = "machine_learning"

@dataclass
class ServerHealth:
    """Состояние здоровья сервера"""
    server_id: str
    url: str
    response_time: float = 0.0
    success_rate: float = 1.0
    active_connections: int = 0
    max_connections: int = 100
    cpu_usage: float = 0.0
    bandwidth_usage: float = 0.0
    last_check: float = field(default_factory=time.time)
    consecutive_failures: int = 0
    health_score: float = 1.0
    region: str = "unknown"

@dataclass
class Request:
    """Запрос к серверу"""
    request_id: str
    url: str
    priority: int = 1  # 1 = высший приоритет
    size_estimate: int = 0
    timeout: float = 30.0
    retry_count: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    user_region: str = "unknown"

@dataclass
class LoadMetrics:
    """Метрики нагрузки"""
    timestamp: float
    server_id: str
    response_time: float
    success: bool
    bytes_transferred: int
    connection_time: float

class PredictiveModel:
    """Простая модель для предсказания нагрузки"""
    
    def __init__(self, history_size: int = 1000):
        self.history: deque = deque(maxlen=history_size)
        self.server_patterns = defaultdict(list)
        self._lock = threading.Lock()
    
    def add_sample(self, server_id: str, metrics: LoadMetrics):
        """Добавление образца данных"""
        with self._lock:
            self.history.append(metrics)
            self.server_patterns[server_id].append({
                'timestamp': metrics.timestamp,
                'response_time': metrics.response_time,
                'success': metrics.success,
                'load': metrics.bytes_transferred
            })
            
            # Ограничиваем размер истории для каждого сервера
            if len(self.server_patterns[server_id]) > 200:
                self.server_patterns[server_id] = self.server_patterns[server_id][-100:]
    
    def predict_response_time(self, server_id: str) -> float:
        """Предсказание времени ответа сервера"""
        with self._lock:
            if server_id not in self.server_patterns:
                return 1.0  # Дефолтное значение
            
            recent_samples = self.server_patterns[server_id][-10:]
            if not recent_samples:
                return 1.0
            
            # Простое предсказание на основе скользящего среднего
            response_times = [s['response_time'] for s in recent_samples if s['success']]
            if response_times:
                return statistics.mean(response_times)
            
            return 5.0  # Высокое время для серверов с ошибками
    
    def predict_success_probability(self, server_id: str) -> float:
        """Предсказание вероятности успеха запроса"""
        with self._lock:
            if server_id not in self.server_patterns:
                return 0.8  # Консервативная оценка
            
            recent_samples = self.server_patterns[server_id][-20:]
            if not recent_samples:
                return 0.8
            
            success_count = sum(1 for s in recent_samples if s['success'])
            return success_count / len(recent_samples)
    
    def get_server_load_trend(self, server_id: str) -> str:
        """Определение тренда нагрузки сервера"""
        with self._lock:
            if server_id not in self.server_patterns:
                return "stable"
            
            recent_samples = self.server_patterns[server_id][-10:]
            if len(recent_samples) < 5:
                return "stable"
            
            # Анализируем тренд времени ответа
            first_half = recent_samples[:len(recent_samples)//2]
            second_half = recent_samples[len(recent_samples)//2:]
            
            avg_first = statistics.mean(s['response_time'] for s in first_half)
            avg_second = statistics.mean(s['response_time'] for s in second_half)
            
            if avg_second > avg_first * 1.2:
                return "increasing"
            elif avg_second < avg_first * 0.8:
                return "decreasing"
            else:
                return "stable"

class IntelligentLoadBalancer:
    """Интеллектуальный балансировщик нагрузки"""
    
    def __init__(self, strategy: LoadBalancingStrategy = LoadBalancingStrategy.ADAPTIVE_PERFORMANCE):
        self.strategy = strategy
        self.servers: Dict[str, ServerHealth] = {}
        self.request_queue: asyncio.Queue = asyncio.Queue()
        self.predictive_model = PredictiveModel()
        self.metrics_history: deque = deque(maxlen=10000)
        
        # Счетчики для round-robin
        self.round_robin_index = 0
        
        # Веса для различных факторов
        self.weights = {
            'response_time': 0.3,
            'success_rate': 0.3,
            'active_connections': 0.2,
            'predicted_performance': 0.2
        }
        
        # Статистика
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        
        self._lock = threading.Lock()
    
    def add_server(self, server_id: str, url: str, max_connections: int = 100, region: str = "unknown"):
        """Добавление сервера в пул"""
        with self._lock:
            server = ServerHealth(
                server_id=server_id,
                url=url,
                max_connections=max_connections,
                region=region
            )
            self.servers[server_id] = server
            logger.info(f"Добавлен сервер {server_id}: {url} (регион: {region})")
    
    def remove_server(self, server_id: str):
        """Удаление сервера из пула"""
        with self._lock:
            if server_id in self.servers:
                del self.servers[server_id]
                logger.info(f"Сервер {server_id} удален из пула")
    
    def update_server_health(self, server_id: str, response_time: float, 
                           success: bool, active_connections: int = None):
        """Обновление состояния здоровья сервера"""
        with self._lock:
            if server_id not in self.servers:
                return
            
            server = self.servers[server_id]
            server.response_time = response_time
            server.last_check = time.time()
            
            if active_connections is not None:
                server.active_connections = active_connections
            
            # Обновляем коэффициент успешности
            if success:
                server.consecutive_failures = 0
                # Постепенно улучшаем success_rate
                server.success_rate = min(1.0, server.success_rate * 0.9 + 0.1)
            else:
                server.consecutive_failures += 1
                # Постепенно ухудшаем success_rate
                server.success_rate = max(0.0, server.success_rate * 0.9)
            
            # Вычисляем общую оценку здоровья
            server.health_score = self._calculate_health_score(server)
            
            # Добавляем метрики в модель предсказания
            metrics = LoadMetrics(
                timestamp=time.time(),
                server_id=server_id,
                response_time=response_time,
                success=success,
                bytes_transferred=0,
                connection_time=response_time
            )
            self.predictive_model.add_sample(server_id, metrics)
    
    def _calculate_health_score(self, server: ServerHealth) -> float:
        """Вычисление общей оценки здоровья сервера"""
        score = 1.0
        
        # Фактор времени ответа (чем меньше, тем лучше)
        if server.response_time > 0:
            response_factor = max(0.1, 1.0 - (server.response_time - 0.1) / 5.0)
            score *= response_factor
        
        # Фактор успешности
        score *= server.success_rate
        
        # Фактор загруженности
        if server.max_connections > 0:
            connection_factor = 1.0 - (server.active_connections / server.max_connections)
            score *= max(0.1, connection_factor)
        
        # Штраф за последовательные ошибки
        if server.consecutive_failures > 0:
            failure_penalty = max(0.1, 1.0 - (server.consecutive_failures * 0.2))
            score *= failure_penalty
        
        return max(0.0, min(1.0, score))
    
    def select_best_server(self, request: Request) -> Optional[str]:
        """Выбор лучшего сервера для запроса"""
        with self._lock:
            available_servers = [
                s for s in self.servers.values() 
                if s.health_score > 0.1 and s.consecutive_failures < 5
            ]
            
            if not available_servers:
                logger.error("Нет доступных серверов!")
                return None
            
            if self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
                return self._round_robin_selection(available_servers)
            elif self.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
                return self._least_connections_selection(available_servers)
            elif self.strategy == LoadBalancingStrategy.WEIGHTED_RESPONSE_TIME:
                return self._weighted_response_time_selection(available_servers)
            elif self.strategy == LoadBalancingStrategy.GEOGRAPHIC_PROXIMITY:
                return self._geographic_proximity_selection(available_servers, request)
            elif self.strategy == LoadBalancingStrategy.MACHINE_LEARNING:
                return self._ml_based_selection(available_servers, request)
            else:  # ADAPTIVE_PERFORMANCE
                return self._adaptive_performance_selection(available_servers, request)
    
    def _round_robin_selection(self, servers: List[ServerHealth]) -> str:
        """Циклический выбор сервера"""
        server = servers[self.round_robin_index % len(servers)]
        self.round_robin_index += 1
        return server.server_id
    
    def _least_connections_selection(self, servers: List[ServerHealth]) -> str:
        """Выбор сервера с наименьшим количеством соединений"""
        best_server = min(servers, key=lambda s: s.active_connections)
        return best_server.server_id
    
    def _weighted_response_time_selection(self, servers: List[ServerHealth]) -> str:
        """Взвешенный выбор на основе времени ответа"""
        # Инвертируем время ответа для весов
        weights = []
        for server in servers:
            if server.response_time > 0:
                weight = 1.0 / server.response_time * server.success_rate
            else:
                weight = 1.0 * server.success_rate
            weights.append(weight)
        
        if sum(weights) == 0:
            return random.choice(servers).server_id
        
        # Выбираем сервер на основе весов
        total_weight = sum(weights)
        random_value = random.uniform(0, total_weight)
        cumulative_weight = 0
        
        for i, weight in enumerate(weights):
            cumulative_weight += weight
            if random_value <= cumulative_weight:
                return servers[i].server_id
        
        return servers[-1].server_id
    
    def _geographic_proximity_selection(self, servers: List[ServerHealth], request: Request) -> str:
        """Выбор сервера на основе географической близости"""
        # Приоритет серверам из того же региона
        same_region_servers = [s for s in servers if s.region == request.user_region]
        
        if same_region_servers:
            # Выбираем лучший сервер из того же региона
            best_server = max(same_region_servers, key=lambda s: s.health_score)
            return best_server.server_id
        else:
            # Выбираем лучший сервер в целом
            best_server = max(servers, key=lambda s: s.health_score)
            return best_server.server_id
    
    def _ml_based_selection(self, servers: List[ServerHealth], request: Request) -> str:
        """Выбор сервера на основе машинного обучения"""
        best_score = -1
        best_server_id = None
        
        for server in servers:
            # Предсказываем производительность
            predicted_response_time = self.predictive_model.predict_response_time(server.server_id)
            predicted_success = self.predictive_model.predict_success_probability(server.server_id)
            
            # Учитываем тренд нагрузки
            load_trend = self.predictive_model.get_server_load_trend(server.server_id)
            trend_factor = {
                'decreasing': 1.2,
                'stable': 1.0,
                'increasing': 0.8
            }.get(load_trend, 1.0)
            
            # Комбинируем факторы
            score = (
                predicted_success * 0.4 +
                (1.0 / max(predicted_response_time, 0.1)) * 0.3 +
                server.health_score * 0.2 +
                trend_factor * 0.1
            )
            
            if score > best_score:
                best_score = score
                best_server_id = server.server_id
        
        return best_server_id or servers[0].server_id
    
    def _adaptive_performance_selection(self, servers: List[ServerHealth], request: Request) -> str:
        """Адаптивный выбор на основе производительности"""
        # Комбинируем различные факторы с весами
        best_score = -1
        best_server_id = None
        
        for server in servers:
            score = 0
            
            # Фактор времени ответа
            if server.response_time > 0:
                response_score = 1.0 / server.response_time
            else:
                response_score = 1.0
            score += response_score * self.weights['response_time']
            
            # Фактор успешности
            score += server.success_rate * self.weights['success_rate']
            
            # Фактор загруженности соединений
            if server.max_connections > 0:
                connection_score = 1.0 - (server.active_connections / server.max_connections)
            else:
                connection_score = 1.0
            score += connection_score * self.weights['active_connections']
            
            # Предсказанная производительность
            predicted_performance = self.predictive_model.predict_success_probability(server.server_id)
            score += predicted_performance * self.weights['predicted_performance']
            
            # Бонус за высокий приоритет запроса к менее загруженному серверу
            if request.priority == 1:  # Высокий приоритет
                score *= (1.0 + connection_score * 0.1)
            
            if score > best_score:
                best_score = score
                best_server_id = server.server_id
        
        return best_server_id or servers[0].server_id
    
    async def process_request(self, request: Request) -> Tuple[bool, str, float]:
        """Обработка запроса с балансировкой"""
        start_time = time.time()
        
        # Выбираем лучший сервер
        selected_server_id = self.select_best_server(request)
        if not selected_server_id:
            return False, "Нет доступных серверов", 0.0
        
        with self._lock:
            server = self.servers[selected_server_id]
            server.active_connections += 1
            self.total_requests += 1
        
        try:
            # Симуляция обработки запроса
            # В реальной реализации здесь был бы актуальный HTTP-запрос
            await asyncio.sleep(0.1)  # Имитация задержки
            
            # Имитируем вероятность успеха на основе здоровья сервера
            success = random.random() < server.health_score
            
            processing_time = time.time() - start_time
            
            # Обновляем статистику сервера
            self.update_server_health(
                selected_server_id, 
                processing_time, 
                success, 
                server.active_connections - 1
            )
            
            if success:
                self.successful_requests += 1
                return True, f"Успешно обработано сервером {selected_server_id}", processing_time
            else:
                self.failed_requests += 1
                return False, f"Ошибка на сервере {selected_server_id}", processing_time
        
        finally:
            with self._lock:
                server.active_connections = max(0, server.active_connections - 1)
    
    def get_server_statistics(self) -> Dict[str, Any]:
        """Получение статистики серверов"""
        with self._lock:
            stats = {
                'total_servers': len(self.servers),
                'strategy': self.strategy.value,
                'total_requests': self.total_requests,
                'successful_requests': self.successful_requests,
                'failed_requests': self.failed_requests,
                'success_rate': self.successful_requests / max(self.total_requests, 1),
                'servers': {}
            }
            
            for server_id, server in self.servers.items():
                server_stats = {
                    'url': server.url,
                    'health_score': server.health_score,
                    'response_time': server.response_time,
                    'success_rate': server.success_rate,
                    'active_connections': server.active_connections,
                    'max_connections': server.max_connections,
                    'consecutive_failures': server.consecutive_failures,
                    'region': server.region,
                    'predicted_response_time': self.predictive_model.predict_response_time(server_id),
                    'predicted_success_rate': self.predictive_model.predict_success_probability(server_id),
                    'load_trend': self.predictive_model.get_server_load_trend(server_id)
                }
                stats['servers'][server_id] = server_stats
            
            return stats
    
    def optimize_weights(self):
        """Автоматическая оптимизация весов на основе истории"""
        # Простая оптимизация - можно улучшить более сложными алгоритмами
        if len(self.metrics_history) < 100:
            return
        
        # Анализируем корреляции между факторами и успехом
        # Это упрощенная версия - в продакшене нужна более сложная оптимизация
        recent_metrics = list(self.metrics_history)[-100:]
        
        # Здесь можно реализовать алгоритм оптимизации весов
        # на основе истории успешности различных стратегий
        logger.debug("Веса оптимизированы на основе исторических данных")
    
    def set_strategy(self, strategy: LoadBalancingStrategy):
        """Изменение стратегии балансировки"""
        self.strategy = strategy
        logger.info(f"Стратегия балансировки изменена на: {strategy.value}")
    
    async def health_check_loop(self, interval: int = 30):
        """Периодическая проверка здоровья серверов"""
        while True:
            try:
                # Здесь можно реализовать актуальные HTTP проверки здоровья
                with self._lock:
                    for server_id, server in self.servers.items():
                        # Имитируем проверку здоровья
                        current_time = time.time()
                        if current_time - server.last_check > interval * 2:
                            # Сервер давно не отвечал - снижаем оценку
                            server.health_score *= 0.9
                            server.consecutive_failures += 1
                
                # Оптимизируем веса периодически
                self.optimize_weights()
                
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле проверки здоровья: {e}")
                await asyncio.sleep(interval)


# Глобальный экземпляр балансировщика
_load_balancer = None

def get_load_balancer() -> IntelligentLoadBalancer:
    """Получение глобального экземпляра балансировщика"""
    global _load_balancer
    if _load_balancer is None:
        _load_balancer = IntelligentLoadBalancer()
    return _load_balancer

async def create_request(url: str, priority: int = 1, user_region: str = "unknown") -> Request:
    """Создание запроса для обработки"""
    import uuid
    return Request(
        request_id=str(uuid.uuid4()),
        url=url,
        priority=priority,
        user_region=user_region
    )