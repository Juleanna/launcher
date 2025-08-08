"""
P2P система распределения обновлений
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Dict, List, Set, Optional
import aiohttp
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class Peer:
    """Информация о пире"""
    id: str
    ip: str
    port: int
    available_files: Set[str]
    last_seen: float
    upload_speed: float = 0.0
    download_speed: float = 0.0

class P2PDistributor:
    """P2P распределитель обновлений"""
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.peers: Dict[str, Peer] = {}
        self.local_files: Set[str] = set()
        self.tracker_url = "https://tracker.example.com/announce"
        
    async def announce_to_tracker(self):
        """Анонсирование в трекере"""
        try:
            data = {
                'peer_id': self.get_peer_id(),
                'port': self.port,
                'files': list(self.local_files)
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.tracker_url, json=data) as response:
                    if response.status == 200:
                        tracker_data = await response.json()
                        await self.update_peer_list(tracker_data.get('peers', []))
        except Exception as e:
            logger.error(f"Ошибка анонсирования в трекере: {e}")
    
    async def download_from_peers(self, file_hash: str, file_name: str) -> bool:
        """Загрузка файла от пиров"""
        available_peers = [p for p in self.peers.values() if file_hash in p.available_files]
        
        if not available_peers:
            return False
        
        # Сортируем по скорости загрузки
        available_peers.sort(key=lambda p: p.upload_speed, reverse=True)
        
        for peer in available_peers[:3]:  # Пробуем до 3 лучших пиров
            try:
                if await self._download_chunk_from_peer(peer, file_hash, file_name):
                    return True
            except Exception as e:
                logger.warning(f"Ошибка загрузки от пира {peer.id}: {e}")
        
        return False
    
    def get_peer_id(self) -> str:
        """Генерация ID пира"""
        import platform
        import getpass
        unique_string = f"{platform.node()}-{getpass.getuser()}-launcher"
        return hashlib.sha256(unique_string.encode()).hexdigest()[:16]
    
    async def update_peer_list(self, peers_data: List[dict]):
        """Обновление списка пиров"""
        current_time = time.time()
        
        for peer_data in peers_data:
            try:
                peer_id = peer_data.get('peer_id')
                if peer_id and peer_id != self.get_peer_id():
                    peer = Peer(
                        id=peer_id,
                        ip=peer_data.get('ip', ''),
                        port=peer_data.get('port', 8080),
                        available_files=set(peer_data.get('files', [])),
                        last_seen=current_time,
                        upload_speed=peer_data.get('upload_speed', 0.0),
                        download_speed=peer_data.get('download_speed', 0.0)
                    )
                    self.peers[peer_id] = peer
            except Exception as e:
                logger.warning(f"Ошибка обработки данных пира: {e}")
    
    async def _download_chunk_from_peer(self, peer: Peer, file_hash: str, file_name: str) -> bool:
        """Загрузка файла от конкретного пира"""
        try:
            url = f"http://{peer.ip}:{peer.port}/download/{file_hash}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        content = await response.read()
                        
                        # Проверяем хеш загруженного файла
                        actual_hash = hashlib.sha256(content).hexdigest()
                        if actual_hash == file_hash:
                            # Сохраняем файл
                            with open(file_name, 'wb') as f:
                                f.write(content)
                            
                            logger.info(f"Файл {file_name} успешно загружен от пира {peer.id}")
                            return True
                        else:
                            logger.error(f"Несоответствие хеша файла от пира {peer.id}")
                            return False
                    else:
                        logger.warning(f"Пир {peer.id} вернул статус {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Ошибка загрузки от пира {peer.id}: {e}")
            return False
    
    async def start_server(self):
        """Запуск P2P сервера для раздачи файлов"""
        from aiohttp import web
        
        async def handle_download(request):
            file_hash = request.match_info['file_hash']
            
            # Поиск файла по хешу
            for file_path in self.local_files:
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    
                    actual_hash = hashlib.sha256(content).hexdigest()
                    if actual_hash == file_hash:
                        return web.Response(
                            body=content,
                            content_type='application/octet-stream',
                            headers={'Content-Length': str(len(content))}
                        )
            
            return web.Response(status=404, text="File not found")
        
        app = web.Application()
        app.router.add_get('/download/{file_hash}', handle_download)
        
        try:
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', self.port)
            await site.start()
            logger.info(f"P2P сервер запущен на порту {self.port}")
        except Exception as e:
            logger.error(f"Ошибка запуска P2P сервера: {e}")
    
    def add_local_file(self, file_path: str):
        """Добавление локального файла для раздачи"""
        if os.path.exists(file_path):
            self.local_files.add(file_path)
            logger.info(f"Файл добавлен для раздачи: {file_path}")
    
    def get_file_hash(self, file_path: str) -> Optional[str]:
        """Получение хеша файла"""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    content = f.read()
                return hashlib.sha256(content).hexdigest()
        except Exception as e:
            logger.error(f"Ошибка получения хеша файла {file_path}: {e}")
        return None
    
    def cleanup_inactive_peers(self, timeout: int = 300):
        """Очистка неактивных пиров"""
        current_time = time.time()
        inactive_peers = []
        
        for peer_id, peer in self.peers.items():
            if current_time - peer.last_seen > timeout:
                inactive_peers.append(peer_id)
        
        for peer_id in inactive_peers:
            del self.peers[peer_id]
            logger.info(f"Удален неактивный пир: {peer_id}")
    
    def get_statistics(self) -> dict:
        """Получение статистики P2P системы"""
        return {
            'total_peers': len(self.peers),
            'local_files': len(self.local_files),
            'available_files_from_peers': sum(len(peer.available_files) for peer in self.peers.values()),
            'average_upload_speed': sum(peer.upload_speed for peer in self.peers.values()) / max(len(self.peers), 1),
            'server_port': self.port
        }


class P2PIntegration:
    """Интеграция P2P в основной лаунчер"""
    
    def __init__(self, launcher):
        self.launcher = launcher
        self.p2p_distributor = P2PDistributor()
        self.enabled = False
    
    def enable_p2p(self, port: int = 8080):
        """Включение P2P режима"""
        try:
            self.p2p_distributor.port = port
            self.enabled = True
            logger.info("P2P режим включен")
        except Exception as e:
            logger.error(f"Ошибка включения P2P: {e}")
            self.enabled = False
    
    async def download_with_p2p(self, file_url: str, local_path: str) -> bool:
        """Загрузка файла с использованием P2P"""
        if not self.enabled:
            return False
        
        try:
            # Получаем хеш файла из URL или манифеста
            file_hash = self._extract_hash_from_url(file_url)
            if not file_hash:
                return False
            
            # Пытаемся загрузить от пиров
            success = await self.p2p_distributor.download_from_peers(file_hash, local_path)
            
            if success:
                # Добавляем файл для раздачи другим
                self.p2p_distributor.add_local_file(local_path)
                return True
            
        except Exception as e:
            logger.error(f"Ошибка P2P загрузки: {e}")
        
        return False
    
    def _extract_hash_from_url(self, file_url: str) -> Optional[str]:
        """Извлечение хеша файла из URL или вычисление"""
        # Это упрощенная реализация - в реальности хеш должен браться из манифеста
        import urllib.parse
        parsed_url = urllib.parse.urlparse(file_url)
        filename = os.path.basename(parsed_url.path)
        
        # Для демонстрации используем имя файла как основу для хеша
        return hashlib.sha256(filename.encode()).hexdigest()
    
    async def start_p2p_services(self):
        """Запуск P2P сервисов"""
        if self.enabled:
            await asyncio.gather(
                self.p2p_distributor.start_server(),
                self._periodic_announce(),
                self._periodic_cleanup()
            )
    
    async def _periodic_announce(self):
        """Периодическое анонсирование в трекере"""
        while self.enabled:
            try:
                await self.p2p_distributor.announce_to_tracker()
                await asyncio.sleep(300)  # Каждые 5 минут
            except Exception as e:
                logger.error(f"Ошибка периодического анонсирования: {e}")
                await asyncio.sleep(60)
    
    async def _periodic_cleanup(self):
        """Периодическая очистка неактивных пиров"""
        while self.enabled:
            try:
                self.p2p_distributor.cleanup_inactive_peers()
                await asyncio.sleep(600)  # Каждые 10 минут
            except Exception as e:
                logger.error(f"Ошибка очистки пиров: {e}")
                await asyncio.sleep(120)