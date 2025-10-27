import sys
import os
import hashlib
import aiohttp
import asyncio
import zipfile
import re
import logging
import ssl
from urllib.parse import urlparse
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu, QAction, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QPushButton, QWidget, QHBoxLayout, QMessageBox, QProgressBar, QInputDialog
from PyQt5.QtCore import QUrl, Qt, QTimer, QThread, pyqtSignal,QPoint
from PyQt5.QtGui import QIcon, QDesktopServices, QPixmap
from PyQt5.uic import loadUi
from configparser import ConfigParser
import requests
import res
from io import BytesIO
from packaging.version import parse as parse_version
import subprocess
try:
    from crypto_verifier import verify_update_integrity
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    verify_update_integrity = None

try:
    from download_manager import DownloadManager, ResumableDownload
    RESUMABLE_DOWNLOADS = True
except ImportError:
    RESUMABLE_DOWNLOADS = False
    DownloadManager = None
    ResumableDownload = None

try:
    from backup_manager import BackupManager, RollbackManager
    BACKUP_AVAILABLE = True
except ImportError:
    BACKUP_AVAILABLE = False
    BackupManager = None
    RollbackManager = None

try:
    from delta_updates import DeltaApplier, is_delta_update_beneficial
    DELTA_UPDATES_AVAILABLE = True
except ImportError:
    DELTA_UPDATES_AVAILABLE = False
    DeltaApplier = None
    is_delta_update_beneficial = None

try:
    from ui_enhancements import (StatisticsManager, EnhancedProgressBar, 
                                StatisticsWidget, TabbedInfoWidget)
    UI_ENHANCEMENTS_AVAILABLE = True
    EnhancedInfoWidget = TabbedInfoWidget  # Псевдоним для совместимости
except ImportError:
    UI_ENHANCEMENTS_AVAILABLE = False
    StatisticsManager = None
    EnhancedProgressBar = None
    StatisticsWidget = None
    EnhancedInfoWidget = None

try:
    from cache_manager import get_cache_manager, get_metadata_cache
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    get_cache_manager = None
    get_metadata_cache = None

try:
    from web_content_manager import WebContentManager
    WEB_CONTENT_AVAILABLE = True
except ImportError:
    WEB_CONTENT_AVAILABLE = False
    WebContentManager = None

# Настройка улучшенной системы логирования
try:
    from launcher_log_config import setup_logging, LauncherLogger
    logger = setup_logging(logging.INFO)
    launcher_logger = LauncherLogger(__name__)
except ImportError:
    # Фоллбэк на базовое логирование если модуль недоступен
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('launcher.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    launcher_logger = None

# Логирование недоступных модулей после инициализации logger
if not CRYPTO_AVAILABLE:
    logger.warning("Криптографические модули недоступны. Цифровые подписи отключены.")
if not RESUMABLE_DOWNLOADS:
    logger.warning("Менеджер загрузок недоступен. Пауза/возобновление отключено.")
if not BACKUP_AVAILABLE:
    logger.warning("Менеджер резервных копий недоступен. Откат обновлений отключен.")
if not DELTA_UPDATES_AVAILABLE:
    logger.warning("Модуль delta-обновлений недоступен. Используется полное обновление.")
if not UI_ENHANCEMENTS_AVAILABLE:
    logger.warning("Улучшения UI недоступны. Используется обычный интерфейс.")
if not CACHE_AVAILABLE:
    logger.warning("Кэширование недоступно.")
if not WEB_CONTENT_AVAILABLE:
    logger.warning("Веб-контент модуль недоступен. Новости не будут отображаться.")

# Константы безопасности
# Константы безопасности
MAX_ARCHIVE_SIZE = 100 * 1024 * 1024  # 100 MB максимальный размер архива
MAX_EXTRACTED_SIZE = 500 * 1024 * 1024  # 500 MB максимальный размер распакованных файлов
ALLOWED_FILE_EXTENSIONS = {
    '.exe', '.dll', '.dat', '.txt', '.cfg', '.ini', '.xml', '.json',
    '.png', '.jpg', '.jpeg',
    '.pak', '.bin', '.pack'
}
DATA_DIR = "launcher_data"  # Директория для данных лаунчера
BACKUP_DIR = "launcher_backups"  # Директория для резервных копий

def validate_url(url):
    """Проверка URL на безопасность с принудительным HTTPS"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ['http', 'https']:
            logger.error(f"Недопустимая схема URL: {parsed.scheme}")
            return False, None
        if not parsed.netloc:
            logger.error("Отсутствует хост в URL")
            return False, None
            
        # Принудительное перенаправление HTTP на HTTPS
        if parsed.scheme == 'http':
            https_url = url.replace('http://', 'https://', 1)
            logger.warning(f"URL автоматически перенаправлен на HTTPS: {url} -> {https_url}")
            return True, https_url
            
        return True, url
    except Exception as e:
        logger.error(f"Ошибка валидации URL {url}: {e}")
        return False, None

def force_https_config():
    """Принудительное обновление конфигурации на HTTPS"""
    config_updated = False
    config = ConfigParser()
    config.read('launcher_config.ini', encoding='utf-8')
    
    # Проверяем и обновляем URLs в секции Update
    for key in ['update_url', 'launcher_update_url']:
        if config.has_option('Update', key):
            url = config.get('Update', key)
            if url.startswith('http://'):
                https_url = url.replace('http://', 'https://', 1)
                config.set('Update', key, https_url)
                logger.info(f"Конфигурация обновлена: {key} = {https_url}")
                config_updated = True
    
    # Проверяем Links секцию
    if config.has_section('Links'):
        for key in config.options('Links'):
            url = config.get('Links', key)
            if url.startswith('http://'):
                https_url = url.replace('http://', 'https://', 1)
                config.set('Links', key, https_url)
                logger.info(f"Ссылка обновлена: {key} = {https_url}")
                config_updated = True
    
    if config_updated:
        with open('launcher_config.ini', 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        logger.info("Конфигурация сохранена с HTTPS URLs")
    
    return config_updated

def safe_extract_archive(archive_path, extract_to="."):
    """Безопасная распаковка архива с проверками"""
    try:
        # Проверка размера архива
        archive_size = os.path.getsize(archive_path)
        if archive_size > MAX_ARCHIVE_SIZE:
            raise Exception(f"Архив слишком большой: {archive_size} байт")
        
        extracted_size = 0
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            for member in zip_ref.infolist():
                # Проверка на path traversal
                if member.filename.startswith('/') or '..' in member.filename:
                    logger.warning(f"Подозрительный путь в архиве: {member.filename}")
                    continue
                
                # Проверка расширения файла
                file_ext = Path(member.filename).suffix.lower()
                if file_ext and file_ext not in ALLOWED_FILE_EXTENSIONS:
                    logger.warning(f"Недопустимое расширение файла: {file_ext}")
                    continue
                
                # Проверка общего размера распакованных файлов
                extracted_size += member.file_size
                if extracted_size > MAX_EXTRACTED_SIZE:
                    raise Exception(f"Общий размер распакованных файлов превышает лимит: {extracted_size}")
                
                # Безопасная распаковка
                safe_path = os.path.normpath(os.path.join(extract_to, member.filename))
                if not safe_path.startswith(os.path.abspath(extract_to)):
                    logger.warning(f"Попытка записи за пределы директории: {safe_path}")
                    continue
                
                zip_ref.extract(member, extract_to)
                
        logger.info(f"Архив {archive_path} успешно распакован")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка распаковки архива {archive_path}: {e}")
        raise

class UpdateThread(QThread):
    file_progress = pyqtSignal(int)
    overall_progress = pyqtSignal(int)
    update_finished_launcher = pyqtSignal(bool, str)
    update_finished = pyqtSignal(bool, str)
    download_stats = pyqtSignal(str)  # Новый сигнал для статистики загрузки
    download_paused = pyqtSignal(bool)  # Ссигнал о паузе/возобновлении

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.start_time = None
        self.total_downloaded = 0
        self.download_manager = None
        self.current_download_id = None
        self.is_paused = False
        
        # Инициализация менеджера резервных копий
        if BACKUP_AVAILABLE:
            self.backup_manager = BackupManager()
            self.rollback_manager = RollbackManager(self.backup_manager)
        else:
            self.backup_manager = None
            self.rollback_manager = None
        
        # Инициализация delta-обновлений
        if DELTA_UPDATES_AVAILABLE:
            self.delta_applier = DeltaApplier()
        else:
            self.delta_applier = None
            
        # Инициализация статистики
        if UI_ENHANCEMENTS_AVAILABLE:
            self.stats_manager = StatisticsManager()
        else:
            self.stats_manager = None
            
        # Инициализация кэша
        if CACHE_AVAILABLE:
            self.cache_manager = get_cache_manager()
            self.metadata_cache = get_metadata_cache()
            # Очищаем просроченные записи при старте
            self.cache_manager.clear_expired()
        else:
            self.cache_manager = None
            self.metadata_cache = None
            
        self.current_download_start = None
        self.current_file_name = ""
        self.update_start_time = None

    async def update_launcher(self):
        launcher_update_url = self.config.get('Update', 'launcher_update_url')
        launcher_update_filename = self.config.get('Update', 'launcher_update_filename')

        # Проверка URL на безопасность
        full_url = os.path.join(launcher_update_url, launcher_update_filename).replace('\\', '/')
        url_valid, secure_url = validate_url(full_url)
        if not url_valid:
            self.update_finished_launcher.emit(False, "Небезопасный URL для обновления лаунчера")
            return
        full_url = secure_url

        connector = aiohttp.TCPConnector(ssl=ssl.create_default_context())
        timeout = aiohttp.ClientTimeout(total=300)  # 5 минут таймаут
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            try:
                logger.info("Начинаем проверку обновления лаунчера")
                
                # Проверка необходимости обновления лаунчера
                needs_update, new_launcher_version = await self.check_for_launcher_update()
                if not needs_update:
                    logger.info("Лаунчер уже обновлен до последней версии")
                    self.update_finished_launcher.emit(True, "Лаунчер уже обновлен до последней версии.")
                    return

                logger.info(f"Скачиваем обновление лаунчера версии {new_launcher_version}")
                # Используем возобновляемую загрузку если доступно
                if RESUMABLE_DOWNLOADS:
                    await self.fetch_file_resumable(full_url, launcher_update_filename)
                else:
                    await self.fetch_file(session, full_url, launcher_update_filename)

                # Проверка целостности обновления лаунчера
                if CRYPTO_AVAILABLE:
                    try:
                        public_key_url = self.config.get('Update', 'public_key_url', fallback=None)
                        if verify_update_integrity(launcher_update_filename, public_key_url=public_key_url):
                            logger.info("Целостность обновления лаунчера подтверждена")
                        else:
                            logger.warning("Не удалось проверить подпись обновления лаунчера")
                    except Exception as e:
                        logger.warning(f"Ошибка проверки целостности: {e}")
                
                # Безопасная распаковка архива
                safe_extract_archive(launcher_update_filename)

                # Обновляем версию лаунчера в конфигурации
                self.config.set('Launcher', 'version', new_launcher_version)
                with open('launcher_config.ini', 'w', encoding='utf-8') as configfile:
                    self.config.write(configfile)
                
                logger.info(f"Версия лаунчера обновлена до {new_launcher_version}")
                self.update_finished_launcher.emit(True, "Обновление лаунчера завершено успешно!")
                
            except Exception as e:
                logger.error(f"Ошибка обновления лаунчера: {e}")
                self.update_finished_launcher.emit(False, f"Ошибка обновления лаунчера: {e}")

    async def fetch_file_resumable(self, url, dest):
        """Загрузка файла с поддержкой паузы/возобновления"""
        if not RESUMABLE_DOWNLOADS:
            # Используем старый метод
            async with aiohttp.ClientSession() as session:
                await self.fetch_file(session, url, dest)
            return
        
        try:
            async with DownloadManager() as dm:
                self.download_manager = dm
                
                def progress_callback(progress):
                    self.file_progress.emit(progress)
                
                def stats_callback(stats):
                    self.download_stats.emit(stats)
                
                self.current_download_id = dm.add_download(
                    url=url,
                    dest_path=dest,
                    progress_callback=progress_callback,
                    stats_callback=stats_callback
                )
                
                # Запускаем загрузку
                success = await dm.start_download(self.current_download_id)
                
                if not success:
                    raise Exception("Ошибка загрузки")
                
                self.current_download_id = None
                self.download_manager = None
                
        except Exception as e:
            logger.error(f"Ошибка возобновляемой загрузки: {e}")
            raise

    async def fetch_file(self, session, url, dest):
        """Безопасная загрузка файла с проверками и статистикой"""
        try:
            logger.info(f"Начинаем загрузку файла: {url}")
            
            # Проверка URL перед загрузкой
            url_valid, secure_url = validate_url(url)
            if not url_valid:
                raise Exception(f"Небезопасный URL: {url}")
            url = secure_url  # Используем безопасный URL
            
            if self.start_time is None:
                self.start_time = asyncio.get_event_loop().time()
            
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"Ошибка загрузки {url}: HTTP {response.status}")
                
                file_size = int(response.headers.get('Content-Length', 0))
                
                # Проверка размера файла
                if file_size > MAX_ARCHIVE_SIZE:
                    raise Exception(f"Файл слишком большой: {file_size} байт")
                
                logger.info(f"Размер файла: {file_size} байт")
                
                # Создаем временный файл для безопасной загрузки
                temp_dest = f"{dest}.tmp"
                try:
                    with open(temp_dest, 'wb') as f:
                        downloaded_size = 0
                        chunk_size = 8192  # Увеличенный размер чанка для лучшей производительности
                        last_update_time = asyncio.get_event_loop().time()
                        
                        while True:
                            chunk = await response.content.read(chunk_size)
                            if not chunk:
                                break
                            
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            self.total_downloaded += len(chunk)
                            
                            # Проверка на превышение заявленного размера
                            if file_size > 0 and downloaded_size > file_size * 1.1:  # 10% допуск
                                raise Exception("Размер загружаемого файла превышает заявленный")
                            
                            # Обновляем прогресс и статистику каждые 0.5 секунд
                            current_time = asyncio.get_event_loop().time()
                            if current_time - last_update_time >= 0.5:
                                if file_size > 0:
                                    progress = int((downloaded_size / file_size) * 100)
                                    self.file_progress.emit(min(progress, 100))
                                
                                # Расчет скорости загрузки
                                elapsed_time = current_time - self.start_time
                                if elapsed_time > 0:
                                    speed_bps = self.total_downloaded / elapsed_time
                                    speed_kbps = speed_bps / 1024
                                    
                                    # Расчет оставшегося времени
                                    if file_size > 0 and speed_bps > 0:
                                        remaining_bytes = file_size - downloaded_size
                                        remaining_time = remaining_bytes / speed_bps
                                        
                                        stats = f"Скорость: {speed_kbps:.1f} КБ/с, Осталось: {remaining_time:.0f} сек"
                                    else:
                                        stats = f"Скорость: {speed_kbps:.1f} КБ/с"
                                    
                                    self.download_stats.emit(stats)
                                
                                last_update_time = current_time
                    
                    # Перемещаем временный файл в конечное место только после успешной загрузки
                    if os.path.exists(dest):
                        os.remove(dest)
                    os.rename(temp_dest, dest)
                    
                    logger.info(f"Файл успешно загружен: {dest} ({downloaded_size} байт)")
                    
                except Exception as e:
                    # Удаляем временный файл в случае ошибки
                    if os.path.exists(temp_dest):
                        os.remove(temp_dest)
                    raise
                    
        except Exception as e:
            logger.error(f"Ошибка загрузки файла {url}: {e}")
            raise

    def hash_file(self, filepath):
        h = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        return h.hexdigest()
    
    def get_versions_to_update(self, current_version, latest_version):
        current_version = self.extract_version(current_version)
        latest_version = self.extract_version(latest_version)

        if current_version is None or latest_version is None:
            return []

        versions_to_update = []

        while current_version < latest_version:
            current_version = self.increment_version(current_version)
            versions_to_update.append(str(current_version))

        return versions_to_update

    def increment_version(self, version):
        major, minor, micro = version.split('.')
        return '.'.join([major, minor, str(int(micro) + 1)])

    def extract_version(self, version_string):
        version_parts = re.findall(r'\d+\.\d+\.\d+', version_string)
        if version_parts:
            return version_parts[0]
        else:
            return None

    async def create_pre_update_backup(self):
        """Создание резервной копии перед обновлением"""
        if not self.backup_manager:
            logger.info("Менеджер резервных копий недоступен")
            return True
        
        try:
            current_version = self.config.get('Server', 'version')
            game_files = self.get_current_game_files()
            
            if not game_files:
                logger.warning("Нет файлов для резервного копирования")
                return True
            
            logger.info(f"Создание резервной копии версии {current_version}")
            
            if self.rollback_manager.prepare_rollback(current_version, game_files):
                logger.info("Резервная копия создана успешно")
                return True
            else:
                logger.error("Ошибка создания резервной копии")
                return False
                
        except Exception as e:
            logger.error(f"Критическая ошибка создания резервной копии: {e}")
            return False

    async def update_files(self):
        update_url = self.config.get('Update', 'update_url')
        version_file = self.config.get('Update', 'version_file')
        files_list_prefix = self.config.get('Update', 'files_list_prefix')

        # Проверка URL на безопасность
        url_valid, secure_update_url = validate_url(update_url)
        if not url_valid:
            self.update_finished.emit(False, "Небезопасный URL сервера обновлений")
            return
        update_url = secure_update_url  # Используем безопасный URL

        connector = aiohttp.TCPConnector(ssl=ssl.create_default_context())
        timeout = aiohttp.ClientTimeout(total=600)  # 10 минут таймаут для обновлений
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            try:
                logger.info("Начинаем проверку обновлений игры")
                
                # Запоминаем время начала обновления
                self.update_start_time = asyncio.get_event_loop().time()
                
                # Создаем резервную копию перед обновлением
                backup_created = await self.create_pre_update_backup()
                if not backup_created:
                    logger.warning("Продолжаем обновление без резервной копии")
                
                # Проверяем кэш для информации о версии
                latest_version = None
                version_from_cache = False
                
                if self.metadata_cache:
                    cached_version = self.metadata_cache.get_version_info(update_url)
                    if cached_version:
                        latest_version = cached_version.get('version')
                        version_from_cache = True
                        logger.info(f"Информация о версии из кэша: {latest_version}")
                
                if not latest_version:
                    # Загружаем с сервера
                    version_url = os.path.join(update_url, version_file).replace('\\', '/')
                    if RESUMABLE_DOWNLOADS:
                        await self.fetch_file_resumable(version_url, version_file)
                    else:
                        await self.fetch_file(session, version_url, version_file)

                    with open(version_file, 'r', encoding='utf-8') as f:
                        latest_version = f.read().strip()
                    
                    # Сохраняем в кэш
                    if self.metadata_cache:
                        self.metadata_cache.set_version_info(update_url, {'version': latest_version})
                        logger.debug("Информация о версии сохранена в кэш")

                current_version = self.config.get('Server', 'version')
                logger.info(f"Текущая версия: {current_version}, последняя версия: {latest_version}")

                if latest_version != current_version:
                    versions_to_update = self.get_versions_to_update(current_version, latest_version)
                    logger.info(f"Версии для обновления: {versions_to_update}")

                    total_files_to_process = 0
                    processed_files = 0

                    # Сначала подсчитываем общее количество файлов
                    for version in versions_to_update:
                        files_list_prefix_name = f"{files_list_prefix}{version}.txt"
                        
                        # Проверяем кэш
                        files_from_cache = None
                        if self.metadata_cache:
                            files_from_cache = self.metadata_cache.get_files_list(update_url, version)
                        
                        if files_from_cache:
                            lines = files_from_cache.get('lines', [])
                            logger.debug(f"Список файлов версии {version} из кэша")
                        else:
                            # Загружаем с сервера
                            files_list_url = os.path.join(update_url, files_list_prefix_name).replace('\\', '/')
                            if RESUMABLE_DOWNLOADS:
                                await self.fetch_file_resumable(files_list_url, files_list_prefix_name)
                            else:
                                await self.fetch_file(session, files_list_url, files_list_prefix_name)

                            with open(files_list_prefix_name, 'r', encoding='utf-8') as f:
                                lines = f.readlines()
                            
                            # Сохраняем в кэш
                            if self.metadata_cache:
                                self.metadata_cache.set_files_list(update_url, version, {'lines': lines})
                                logger.debug(f"Список файлов версии {version} сохранен в кэш")
                        
                        total_files_to_process += len([line for line in lines if line.strip() and not line.startswith('version')])

                    logger.info(f"Всего файлов для обработки: {total_files_to_process}")

                    # Теперь обрабатываем файлы
                    for version in versions_to_update:
                        logger.info(f"Обрабатываем версию {version}")
                        
                        # Проверяем наличие delta-обновления
                        delta_processed = False
                        if DELTA_UPDATES_AVAILABLE and self.delta_applier:
                            delta_filename = f"delta_{current_version}_to_{version}.zip"
                            delta_url = os.path.join(update_url, delta_filename).replace('\\', '/')
                            
                            try:
                                # Пытаемся скачать delta-обновление
                                if RESUMABLE_DOWNLOADS:
                                    await self.fetch_file_resumable(delta_url, delta_filename)
                                else:
                                    await self.fetch_file(session, delta_url, delta_filename)
                                
                                logger.info(f"Найдено delta-обновление: {delta_filename}")
                                
                                # Применяем delta-обновление
                                current_dir = os.getcwd()
                                if self.delta_applier.apply_delta_package(delta_filename, current_dir, 
                                                                         lambda p: self.file_progress.emit(p)):
                                    logger.info(f"Delta-обновление применено успешно")
                                    delta_processed = True
                                    
                                    # Удаляем временные файлы
                                    if os.path.exists(delta_filename):
                                        os.remove(delta_filename)
                                else:
                                    logger.warning(f"Ошибка применения delta-обновления, переходим к полному обновлению")
                                    # Удаляем поврежденный файл
                                    if os.path.exists(delta_filename):
                                        os.remove(delta_filename)
                                        
                            except Exception as delta_error:
                                logger.info(f"Delta-обновление недоступно для версии {version}: {delta_error}")
                                # Продолжаем с полным обновлением
                        
                        # Если delta-обновление не сработало, делаем полное обновление
                        if not delta_processed:
                            zip_filename = f"{files_list_prefix}{version}.zip"
                            zip_url = os.path.join(update_url, zip_filename).replace('\\', '/')
                            if RESUMABLE_DOWNLOADS:
                                await self.fetch_file_resumable(zip_url, zip_filename)
                            else:
                                await self.fetch_file(session, zip_url, zip_filename)

                        # Проверка целостности архива
                        if CRYPTO_AVAILABLE:
                            manifest_path = f"{zip_filename}.manifest"
                            # Пытаемся скачать манифест для проверки
                            try:
                                manifest_url = f"{zip_url}.manifest"
                                
                                # Проверяем кэш для манифеста
                                manifest_from_cache = False
                                if self.metadata_cache:
                                    cached_manifest = self.metadata_cache.get_manifest(manifest_url)
                                    if cached_manifest:
                                        # Сохраняем кэшированные данные в файл
                                        with open(manifest_path, 'w', encoding='utf-8') as f:
                                            json.dump(cached_manifest, f, indent=2)
                                        manifest_from_cache = True
                                        logger.debug(f"Манифест из кэша: {manifest_path}")
                                
                                if not manifest_from_cache:
                                    # Загружаем с сервера
                                    await self.fetch_file(session, manifest_url, manifest_path)
                                    
                                    # Сохраняем в кэш
                                    if self.metadata_cache and os.path.exists(manifest_path):
                                        try:
                                            with open(manifest_path, 'r', encoding='utf-8') as f:
                                                manifest_data = json.load(f)
                                            self.metadata_cache.set_manifest(manifest_url, manifest_data)
                                            logger.debug(f"Манифест сохранен в кэш: {manifest_path}")
                                        except Exception as cache_error:
                                            logger.warning(f"Ошибка сохранения манифеста в кэш: {cache_error}")
                                
                                public_key_url = self.config.get('Update', 'public_key_url', fallback=None)
                                if verify_update_integrity(zip_filename, manifest_path, public_key_url):
                                    logger.info(f"Целостность архива подтверждена: {zip_filename}")
                                else:
                                    logger.error(f"Нарушена целостность архива: {zip_filename}")
                                    # Инвалидируем кэш при ошибке
                                    if self.metadata_cache:
                                        self.metadata_cache.cache_manager.delete(manifest_url)
                                    raise Exception("Неверная подпись архива")
                            except Exception as manifest_error:
                                logger.warning(f"Не удалось проверить подпись: {manifest_error}")
                                # Продолжаем без проверки подписи
                        
                        # Безопасная распаковка архива
                        safe_extract_archive(zip_filename)

                        files_list = f"{files_list_prefix}{version}.txt"
                        with open(files_list, 'r', encoding='utf-8') as f:
                            lines = f.readlines()

                        for line in lines:
                            line = line.strip()
                            if not line or line.startswith('version'):
                                continue
                                
                            parts = line.split()
                            if len(parts) != 3:
                                logger.warning(f"Пропускаем некорректную строку: {line}")
                                continue

                            file_name, expected_hash, file_size_str = parts
                            try:
                                file_size = int(file_size_str)
                            except ValueError:
                                logger.warning(f"Некорректный размер файла: {file_size_str}")
                                continue

                            local_file = os.path.join(os.getcwd(), file_name)

                            # Проверяем хеш файла если он существует
                            file_valid = False
                            if os.path.exists(local_file):
                                try:
                                    local_hash = self.hash_file(local_file)
                                    file_valid = (local_hash == expected_hash)
                                    if file_valid:
                                        logger.debug(f"Файл {file_name} актуален")
                                    else:
                                        logger.info(f"Файл {file_name} требует обновления")
                                except Exception as e:
                                    logger.error(f"Ошибка проверки хеша файла {file_name}: {e}")

                            processed_files += 1
                            if total_files_to_process > 0:
                                progress = int((processed_files / total_files_to_process) * 100)
                                self.overall_progress.emit(progress)

                        # Обновляем версию в конфигурации после обработки каждой версии
                        current_version = version  # Обновляем для следующей итерации
                        self.config.set('Server', 'version', version)
                        with open('launcher_config.ini', 'w', encoding='utf-8') as configfile:
                            self.config.write(configfile)
                        
                        # Инвалидируем кэш для обновленной версии
                        if self.metadata_cache:
                            self.metadata_cache.invalidate_version(update_url, version)
                        
                        logger.info(f"Версия обновлена до {version}")

                    logger.info("Обновление завершено успешно")
                    
                    # Записываем статистику успешного обновления
                    if self.update_start_time:
                        update_duration = asyncio.get_event_loop().time() - self.update_start_time
                        self.record_update_stats(latest_version, True, total_files_to_process, update_duration)
                    
                    self.update_finished.emit(True, "Обновление завершено успешно!")
                else:
                    logger.info("У вас уже установлена последняя версия")
                    
                    # Записываем статистику (обновление не потребовалось)
                    if self.update_start_time:
                        update_duration = asyncio.get_event_loop().time() - self.update_start_time
                        self.record_update_stats(current_version, True, 0, update_duration)
                    
                    self.update_finished.emit(True, "У вас уже установлена последняя версия.")
                    
            except Exception as e:
                if "refused" in str(e).lower() or "connection" in str(e).lower():
                    logger.warning(f"Сервер обновлений недоступен: {e}")
                    # Проверяем, указан ли localhost в конфигурации
                    update_url = self.config.get('Update', 'update_url')
                    if "127.0.0.1" in update_url or "localhost" in update_url.lower():
                        self.update_finished.emit(True, "Запуск в оффлайн режиме - локальный сервер недоступен. Игра готова к запуску.")
                    else:
                        self.update_finished.emit(False, "Сервер обновлений недоступен. Проверьте подключение к интернету.")
                    return
                else:
                    logger.error(f"Ошибка обновления: {e}")
                
                # Предлагаем откат при ошибке
                if self.rollback_manager and BACKUP_AVAILABLE:
                    try:
                        current_version = self.config.get('Server', 'version')
                        backups = self.backup_manager.list_backups()
                        
                        # Ищем последнюю резервную копию
                        if backups:
                            latest_backup = max(backups, key=lambda x: x['created_at'])
                            logger.info(f"Попытка автоматического отката к версии {latest_backup['version']}")
                            
                            if self.rollback_manager.perform_rollback(latest_backup['version']):
                                self.update_finished.emit(False, f"Ошибка обновления. Выполнен автоматический откат к версии {latest_backup['version']}")
                            else:
                                self.update_finished.emit(False, f"Ошибка обновления: {e}. Откат не удался.")
                        else:
                            self.update_finished.emit(False, f"Ошибка обновления: {e}. Резервные копии не найдены.")
                    except Exception as rollback_error:
                        logger.error(f"Ошибка отката: {rollback_error}")
                        self.update_finished.emit(False, f"Ошибка обновления: {e}")
                    
                    # Записываем статистику неудачного обновления
                    if self.update_start_time:
                        update_duration = asyncio.get_event_loop().time() - self.update_start_time
                        self.record_update_stats(current_version, False, 0, update_duration)
                else:
                    # Записываем статистику неудачного обновления
                    if self.update_start_time:
                        update_duration = asyncio.get_event_loop().time() - self.update_start_time
                        self.record_update_stats(current_version, False, 0, update_duration)
                    
                    self.update_finished.emit(False, f"Ошибка обновления: {e}")

    async def check_for_launcher_update(self):
        update_url = self.config.get('Update', 'update_url')
        version_file = self.config.get('Update', 'version_file')

        async with aiohttp.ClientSession() as session:
            try:
                version_url = os.path.join(update_url, version_file)
                async with session.get(version_url) as response:
                    if response.status != 200:
                        raise Exception(f"Failed to fetch version file: HTTP {response.status}")

                    version_content = await response.text()
                    for line in version_content.splitlines():
                        if line.startswith('LauncherVersion='):
                            latest_version = line.split('=')[1].strip()
                            current_version = self.config.get('Launcher', 'version')

                            if parse_version(latest_version) > parse_version(current_version):
                                return True, latest_version

                    return False, current_version
            except Exception as e:
                if "refused" in str(e).lower() or "connection" in str(e).lower():
                    logger.warning(f"Сервер обновлений недоступен: {e}")
                    update_url = self.config.get('Update', 'update_url')
                    if "127.0.0.1" in update_url or "localhost" in update_url.lower():
                        logger.info("Работа в оффлайн режиме - локальный сервер недоступен")
                        print("Работа в оффлайн режиме - локальный сервер недоступен.")
                    else:
                        print("Сервер обновлений недоступен. Лаунчер будет работать в автономном режиме.")
                else:
                    logger.error(f"Ошибка проверки обновлений лаунчера: {e}")
                    print(f"Error checking for launcher update: {e}")
                return False, str(e)

    async def _run_update_flow(self):
        logger.info("����� �������� ����������")
        if self.isInterruptionRequested():
            self.update_finished.emit(False, "���������� ��������")
            return
        needs_update, latest_version = await self.check_for_launcher_update()
        if self.isInterruptionRequested():
            self.update_finished.emit(False, "���������� ��������")
            return
        if needs_update:
            logger.info(f"�������� ���������� ��������: {latest_version}")
            await self.update_launcher()
        else:
            logger.info(f"������� ��������. ��������� ������: {latest_version}")
            await self.update_files()

    def run(self):
        """������ event loop ������ QThread ��� ����������� ����� ����������."""
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_update_flow())
        except Exception as e:
            logger.error(f"������ � �������� ����������: {e}")
            self.update_finished.emit(False, f"������: {e}")
        finally:
            if loop is not None:
                try:
                    loop.close()
                except Exception:
                    pass

    def pause_download(self):self):
        """Приостановить загрузку"""
        if self.download_manager and self.current_download_id:
            self.download_manager.pause_download(self.current_download_id)
            self.is_paused = True
            self.download_paused.emit(True)
            logger.info("Загрузка приостановлена")
    
    def resume_download(self):
        """Возобновить загрузку"""
        if self.download_manager and self.current_download_id:
            self.download_manager.resume_download(self.current_download_id)
            self.is_paused = False
            self.download_paused.emit(False)
            logger.info("Загрузка возобновлена")
    
    def get_current_game_files(self) -> list:
        """Сбор списка файлов игры для резервного копирования"""
        game_files = []
        try:
            current_dir = os.getcwd()
            
            # Собираем все файлы игры (исключая системные)
            exclude_patterns = {
                'launcher.exe', 'launcher.py', 'update.py', 'launcher.ui',
                'launcher_config.ini', 'launcher.log', 'launcher_errors.log',
                'logs', 'launcher_data', 'launcher_backups', 'crypto_keys',
                '.git', '.gitignore', '__pycache__', '*.pyc', '*.tmp'
            }
            
            for root, dirs, files in os.walk(current_dir):
                # Пропускаем системные папки
                dirs[:] = [d for d in dirs if d not in exclude_patterns and not d.startswith('.')]
                
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, current_dir)
                    
                    # Проверяем, не исключен ли файл
                    if (file not in exclude_patterns and 
                        not file.startswith('.') and 
                        not file.endswith(('.tmp', '.log', '.pyc')) and
                        not any(pattern in rel_path for pattern in exclude_patterns)):
                        
                        game_files.append(file_path)
            
            logger.info(f"Найдено {len(game_files)} файлов для резервного копирования")
            return game_files
            
        except Exception as e:
            logger.error(f"Ошибка сбора файлов для резервного копирования: {e}")
            return []

    def cancel_download(self):
        """Отменить загрузку"""
        if self.download_manager and self.current_download_id:
            self.download_manager.cancel_download(self.current_download_id)
            self.current_download_id = None
            logger.info("Загрузка отменена")
    
    def record_download_stats(self, file_name: str, file_size: int, download_time: float, speed: float):
        """Запись статистики загрузки"""
        if self.stats_manager:
            try:
                self.stats_manager.record_download(file_name, file_size, download_time, speed)
            except Exception as e:
                logger.error(f"Ошибка записи статистики загрузки: {e}")
    
    def record_update_stats(self, version: str, success: bool, files_count: int = 0, duration: float = 0.0):
        """Запись статистики обновления"""
        if self.stats_manager:
            try:
                self.stats_manager.record_update(version, success, files_count, duration)
            except Exception as e:
                logger.error(f"Ошибка записи статистики обновления: {e}")

    def stop_safely(self):
        """Безопасная остановка потока"""
        logger.info("Получен запрос на остановку обновления")
        
        # Если поток уже не запущен, ничего не делаем
        if not self.isRunning():
            logger.debug("Поток обновления уже остановлен")
            return
        
        # Отменяем текущую загрузку
        self.cancel_download()
        
        # Запрашиваем прерывание
        self.requestInterruption()
        
        # Ждем завершения потока
        if not self.wait(3000):  # Ждем 3 секунды
            logger.info("Поток обновления не завершился самостоятельно, выполняем принудительное завершение")
            self.terminate()
            # Ждем завершения после terminate
            if not self.wait(2000):  # Ждем еще 2 секунды
                logger.warning("Поток обновления не отвечает - возможно зависание")
            else:
                logger.info("Поток обновления успешно завершен")
        else:
            logger.info("Поток обновления завершен корректно")

class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        try:
            logger.info("Инициализация окна лаунчера")
            loadUi('launcher.ui', self)
            
            self.setWindowFlag(Qt.FramelessWindowHint)
            self.oldPos = self.pos()
            self.moving = False

            # Инициализация конфигурации с проверкой ошибок
            self.config = ConfigParser()
            try:
                self.config.read('launcher_config.ini', encoding='utf-8')
                # Принудительное обновление конфигурации на HTTPS
                if force_https_config():
                    # Перечитываем конфигурацию после обновления
                    self.config.read('launcher_config.ini', encoding='utf-8')
                logger.info("Конфигурация успешно загружена")
            except Exception as e:
                logger.error(f"Ошибка загрузки конфигурации: {e}")
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить конфигурацию: {e}")
                sys.exit(1)
                
        except Exception as e:
            logger.error(f"Критическая ошибка инициализации: {e}")
            QMessageBox.critical(None, "Критическая ошибка", f"Не удалось инициализировать лаунчер: {e}")
            sys.exit(1)

        server_name = self.config.get('Server', 'name')
        version = self.config.get('Server', 'version')
        self.Name_server.setText(server_name)
        self.Version.setText(f"Version: {version}")

        self.Name_server.setStyleSheet("font-size: 14pt; font-weight: 600; color: #ffffff;")
        self.Version.setStyleSheet("color: #ffffff;")

        self.default_button_color = self.config.get('ButtonColors', 'default', fallback='#ffcd00')
        self.active_button_color = self.config.get('ButtonColors', 'active', fallback='#ffffff')
        self.slider_interval = self.config.getint('Slider', 'interval', fallback=5000)

        self.telegram_url = self.config.get('Links', 'telegram')
        self.vk_url = self.config.get('Links', 'vk')
        self.discord_url = self.config.get('Links', 'discord')
        self.website_url = self.config.get('Links', 'website')
        self.facebook_url = self.config.get('Links', 'facebook')
        self.instagram_url = self.config.get('Links', 'instagram')

        icon_path = self.config.get('Icon', 'path')
        self.setWindowIcon(QIcon(icon_path))

        self.Telegram.clicked.connect(self.open_telegram)
        self.VK.clicked.connect(self.open_vk)
        self.Discord.clicked.connect(self.open_discord)
        self.Site.clicked.connect(self.open_website)
        self.Facebook.clicked.connect(self.open_facebook)
        self.Instagram.clicked.connect(self.open_instagram)

        # Настройка иконки в трее
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(icon_path))

        tray_menu = QMenu(self)
        restore_action = QAction("Restore", self)
        quit_action = QAction("Quit", self)
        tray_menu.addAction(restore_action)
        tray_menu.addAction(quit_action)

        restore_action.triggered.connect(self.showNormal)
        quit_action.triggered.connect(QApplication.instance().quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        # Связываем событие нажатия кнопки свертывания в трей с функцией
        self.Minimize.clicked.connect(self.minimize_to_tray)

        self.update_button.setStyleSheet(f"background-color: {self.default_button_color}; color: #000000;")
        self.update_button.setText("Играть")
        self.update_button.clicked.connect(self.toggle_update)
        
        # Кнопка паузы/возобновления (если доступно)
        if RESUMABLE_DOWNLOADS:
            try:
                self.pause_button = self.findChild(QPushButton, 'pause_button')
                if self.pause_button:
                    self.pause_button.clicked.connect(self.toggle_pause)
                    self.pause_button.setVisible(False)  # Скрываем по умолчанию
                else:
                    logger.info("Кнопка паузы не найдена в UI")
            except Exception as e:
                logger.warning(f"Ошибка инициализации кнопки паузы: {e}")
                self.pause_button = None
        else:
            self.pause_button = None
        
        # Кнопка отката (если доступно)
        if BACKUP_AVAILABLE:
            try:
                self.rollback_button = self.findChild(QPushButton, 'rollback_button')
                if self.rollback_button:
                    self.rollback_button.clicked.connect(self.show_rollback_dialog)
                    self.rollback_button.setText("Откат")
                    self.rollback_button.setStyleSheet(f"background-color: #ff6b6b; color: #ffffff;")
                else:
                    logger.info("Кнопка отката не найдена в UI")
            except Exception as e:
                logger.warning(f"Ошибка инициализации кнопки отката: {e}")
                self.rollback_button = None
        else:
            self.rollback_button = None
        
        # Кнопка UI редактора (если доступна)
        try:
            self.ui_editor_button = self.findChild(QPushButton, 'ui_editor_button')
            if self.ui_editor_button:
                self.ui_editor_button.clicked.connect(self.open_ui_editor)
                self.ui_editor_button.setText("Редактор UI")
                self.ui_editor_button.setStyleSheet(f"background-color: #4CAF50; color: #ffffff;")
            else:
                logger.info("Кнопка UI редактора не найдена в UI")
        except Exception as e:
            logger.warning(f"Ошибка инициализации кнопки UI редактора: {e}")
            self.ui_editor_button = None
        
        # Инициализация статистики и улучшенного UI
        if UI_ENHANCEMENTS_AVAILABLE:
            try:
                self.stats_manager = StatisticsManager()
                self.stats_manager.record_launch()
                
                # Пытаемся найти контейнер для расширенной информации
                info_container = self.findChild(QWidget, 'info_container')
                if info_container:
                    self.enhanced_info_widget = EnhancedInfoWidget(self.stats_manager)
                    info_layout = QVBoxLayout(info_container) if not info_container.layout() else info_container.layout()
                    info_layout.addWidget(self.enhanced_info_widget)
                    logger.info("Расширенный информационный виджет добавлен")
                else:
                    logger.info("Контейнер info_container не найден в UI")
                    self.enhanced_info_widget = None
                
                # Пытаемся заменить обычные прогресс-бары на улучшенные
                progress_container = self.findChild(QWidget, 'progress_container')
                if progress_container:
                    self.enhanced_progress = EnhancedProgressBar()
                    progress_layout = QVBoxLayout(progress_container) if not progress_container.layout() else progress_container.layout()
                    progress_layout.addWidget(self.enhanced_progress)
                    logger.info("Улучшенный виджет прогресса добавлен")
                else:
                    logger.info("Контейнер progress_container не найден в UI")
                    self.enhanced_progress = None
                    
            except Exception as e:
                logger.error(f"Ошибка инициализации улучшенного UI: {e}")
                self.stats_manager = None
                self.enhanced_info_widget = None
                self.enhanced_progress = None
        else:
            self.stats_manager = None
            self.enhanced_info_widget = None
            self.enhanced_progress = None

        # Настройка слайдера изображений с проверкой ошибок
        try:
            images_folder = self.config.get('Images', 'folder')
            if not os.path.exists(images_folder):
                logger.warning(f"Папка с изображениями не найдена: {images_folder}")
                self.image_files = []
            else:
                self.image_files = []
                for f in os.listdir(images_folder):
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                        full_path = os.path.join(images_folder, f)
                        if os.path.exists(full_path):
                            self.image_files.append(full_path)
                        else:
                            logger.warning(f"Файл изображения не найден: {full_path}")
                
                logger.info(f"Найдено {len(self.image_files)} изображений для слайдера")
                
            self.current_image_index = 0
        except Exception as e:
            logger.error(f"Ошибка инициализации слайдера изображений: {e}")
            self.image_files = []
            self.current_image_index = 0

        self.graphics_view = self.findChild(QGraphicsView, 'Baner')
        self.graphics_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.graphics_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.graphics_view.setStyleSheet("border: none;")  # Убираем бордер
        self.scene = QGraphicsScene()
        self.graphics_view.setScene(self.scene)
    
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.show_next_image)
        self.timer.start(self.slider_interval)  # Используе

        self.is_updating = False
        self.download_stats_label = None  # Добавим позже
        
        self.update_thread = UpdateThread(self.config)
        self.update_thread.file_progress.connect(self.update_file_progress)
        self.update_thread.overall_progress.connect(self.update_overall_progress)
        self.update_thread.update_finished_launcher.connect(self.update_finished_launcher)
        self.update_thread.update_finished.connect(self.update_finished)
        self.update_thread.download_stats.connect(self.update_download_stats)
        self.update_thread.download_paused.connect(self.update_pause_state)

        # Настройка кнопок для ручного переключения
        self.banner_controls = self.findChild(QWidget, 'BannerControls')
        self.control_layout = self.findChild(QHBoxLayout, 'horizontalLayout')
        self.control_layout.setContentsMargins(0, 0, 0, 0)  # Устанавливаем отступы программно
        self.buttons = []

        for i in range(len(self.image_files)):
            btn = QPushButton(self.banner_controls)
            btn.setFixedSize(10, 10)
            btn.setStyleSheet(f"border-radius: 5px; background-color: {self.default_button_color};")
            btn.clicked.connect(lambda checked, index=i: self.show_image(index))
            self.control_layout.addWidget(btn)
            self.buttons.append(btn)

        self.show_next_image()

        # Применяем пользовательскую конфигурацию UI если она есть
        self.apply_ui_config()
        
        # Инициализация веб-контента для табов
        self.setup_web_content()

        self.update_launcher_on_startup()

    def update_launcher_on_startup(self):
        self.update_thread.start()

    def open_telegram(self):
        QDesktopServices.openUrl(QUrl(self.telegram_url))

    def open_vk(self):
        QDesktopServices.openUrl(QUrl(self.vk_url))

    def open_discord(self):
        QDesktopServices.openUrl(QUrl(self.discord_url))

    def open_website(self):
        QDesktopServices.openUrl(QUrl(self.website_url))

    def open_facebook(self):
        QDesktopServices.openUrl(QUrl(self.facebook_url))

    def open_instagram(self):
        QDesktopServices.openUrl(QUrl(self.instagram_url))

    def show_next_image(self):
        self.show_image(self.current_image_index)
        self.current_image_index = (self.current_image_index + 1) % len(self.image_files)

    def show_image(self, index):
        """Отображение изображения с обработкой ошибок"""
        try:
            if not self.image_files or index >= len(self.image_files):
                logger.warning("Нет доступных изображений для отображения")
                return
                
            image_path = self.image_files[index]
            
            # Проверяем существование файла
            if not os.path.exists(image_path):
                logger.error(f"Файл изображения не найден: {image_path}")
                return
            
            # Загружаем и масштабируем изображение
            image = QPixmap(image_path)
            if image.isNull():
                logger.error(f"Не удалось загрузить изображение: {image_path}")
                return
                
            # Масштабируем изображение с сохранением пропорций
            scaled_image = image.scaled(
                self.graphics_view.size(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )

            # Обновляем сцену
            self.scene.clear()
            item = QGraphicsPixmapItem(scaled_image)
            self.scene.addItem(item)
            self.scene.setSceneRect(0, 0, self.graphics_view.width(), self.graphics_view.height())

            self.current_image_index = index
            self.update_buttons()
            
            logger.debug(f"Отображено изображение: {os.path.basename(image_path)}")
            
        except Exception as e:
            logger.error(f"Ошибка отображения изображения {index}: {e}")
            # В случае ошибки показываем заглушку или пропускаем
            self.scene.clear()

    def toggle_update(self):
        if self.is_updating:
            self.stop_update()
        else:
            self.start_update()
    
    def toggle_pause(self):
        """Переключение паузы/возобновления"""
        if not self.is_updating or not self.update_thread.isRunning():
            return
        
        if self.update_thread.is_paused:
            self.update_thread.resume_download()
        else:
            self.update_thread.pause_download()
    
    def update_pause_state(self, is_paused):
        """Обновление состояния кнопки паузы"""
        if hasattr(self, 'pause_button') and self.pause_button:
            if is_paused:
                self.pause_button.setText("Возобновить")
                self.pause_button.setStyleSheet(f"background-color: {self.active_button_color}; color: #000000;")
            else:
                self.pause_button.setText("Пауза")
                self.pause_button.setStyleSheet(f"background-color: {self.default_button_color}; color: #000000;")
    
    def show_rollback_dialog(self):
        """Отображение диалога отката"""
        if not BACKUP_AVAILABLE or not hasattr(self.update_thread, 'backup_manager'):
            QMessageBox.warning(self, "Откат", "Менеджер резервных копий недоступен")
            return
        
        try:
            backups = self.update_thread.backup_manager.list_backups()
            
            if not backups:
                QMessageBox.information(self, "Откат", "Резервные копии не найдены")
                return
            
            # Сортируем по дате создания (новые сверху)
            backups.sort(key=lambda x: x['created_at'], reverse=True)
            
            # Создаем список для выбора
            items = []
            for backup in backups:
                from datetime import datetime
                created_date = datetime.fromisoformat(backup['created_at']).strftime("%Y-%m-%d %H:%M")
                item_text = f"Версия {backup['version']} - {created_date} ({backup['files_count']} файлов)"
                items.append(item_text)
            
            # Показываем диалог выбора
            item, ok = QInputDialog.getItem(
                self, 
                "Откат обновления",
                "Выберите версию для отката:",
                items,
                0,
                False
            )
            
            if ok and item:
                # Находим выбранную резервную копию
                selected_index = items.index(item)
                selected_backup = backups[selected_index]
                
                # Подтверждение
                reply = QMessageBox.question(
                    self,
                    "Подтверждение отката",
                    f"Вы уверены, что хотите откатиться к версии {selected_backup['version']}?\n\n"
                    f"Это заменит текущие файлы игры!",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    self.perform_rollback(selected_backup['version'])
                    
        except Exception as e:
            logger.error(f"Ошибка отображения диалога отката: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка отображения списка резервных копий: {e}")
    
    def perform_rollback(self, target_version: str):
        """Выполнение отката"""
        try:
            if hasattr(self.update_thread, 'rollback_manager') and self.update_thread.rollback_manager:
                logger.info(f"Начало отката к версии {target_version}")
                
                if self.update_thread.rollback_manager.perform_rollback(target_version):
                    # Обновляем версию в конфигурации
                    self.config.set('Server', 'version', target_version)
                    with open('launcher_config.ini', 'w', encoding='utf-8') as configfile:
                        self.config.write(configfile)
                    
                    # Обновляем UI
                    self.Version.setText(f"Version: {target_version}")
                    
                    QMessageBox.information(
                        self, 
                        "Откат завершен", 
                        f"Откат к версии {target_version} выполнен успешно!"
                    )
                else:
                    QMessageBox.critical(self, "Ошибка", "Ошибка выполнения отката")
            else:
                QMessageBox.warning(self, "Ошибка", "Менеджер отката недоступен")
                
        except Exception as e:
            logger.error(f"Ошибка выполнения отката: {e}")
            QMessageBox.critical(self, "Ошибка", f"Критическая ошибка отката: {e}")
    
    def show_cache_stats(self):
        """Отображение статистики кэша"""
        if not CACHE_AVAILABLE or not hasattr(self.update_thread, 'cache_manager'):
            QMessageBox.information(self, "Кэш", "Кэширование недоступно")
            return
        
        try:
            cache_stats = self.update_thread.cache_manager.get_stats()
            
            message = f"""Статистика кэша:

Всего записей: {cache_stats.get('total_entries', 0)}
Актуальных: {cache_stats.get('valid_entries', 0)}
Просроченных: {cache_stats.get('expired_entries', 0)}
Общий размер: {self.format_cache_size(cache_stats.get('total_size_bytes', 0))}
Папка кэша: {cache_stats.get('cache_dir', 'N/A')}"""
            
            QMessageBox.information(self, "Статистика кэша", message)
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики кэша: {e}")
            QMessageBox.critical(self, "Ошибка", f"Ошибка получения статистики кэша: {e}")
    
    def clear_cache(self):
        """Очистка кэша"""
        if not CACHE_AVAILABLE or not hasattr(self.update_thread, 'cache_manager'):
            QMessageBox.information(self, "Кэш", "Кэширование недоступно")
            return
        
        reply = QMessageBox.question(
            self,
            "Очистка кэша",
            "Вы уверены, что хотите очистить весь кэш?\n\n"
            "Это может замедлить следующие обновления.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                if self.update_thread.cache_manager.clear_all():
                    QMessageBox.information(self, "Кэш очищен", "Кэш успешно очищен!")
                else:
                    QMessageBox.warning(self, "Ошибка", "Ошибка очистки кэша")
            except Exception as e:
                logger.error(f"Ошибка очистки кэша: {e}")
                QMessageBox.critical(self, "Ошибка", f"Ошибка очистки кэша: {e}")
    
    def format_cache_size(self, size_bytes: int) -> str:
        """Форматирование размера кэша"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def update_buttons(self):
        for i, btn in enumerate(self.buttons):
            if i == self.current_image_index:
                btn.setStyleSheet(f"border-radius: 5px; background-color: {self.active_button_color};")
            else:
                btn.setStyleSheet(f"border-radius: 5px; background-color: {self.default_button_color};")


    def start_update(self):
        """Запуск процесса обновления"""
        try:
            if not self.is_updating:
                logger.info("Запуск процесса обновления")
                
                # Создаем новый поток если предыдущий завершился
                if not self.update_thread.isRunning():
                    self.update_thread = UpdateThread(self.config)
                    self.update_thread.file_progress.connect(self.update_file_progress)
                    self.update_thread.overall_progress.connect(self.update_overall_progress)
                    self.update_thread.update_finished_launcher.connect(self.update_finished_launcher)
                    self.update_thread.update_finished.connect(self.update_finished)
                
                self.update_thread.start()
                self.update_button.setStyleSheet(f"background-color: {self.active_button_color}; color: #000000;")
                self.update_button.setText("Остановить")
                self.is_updating = True
                
                # Показываем кнопку паузы если доступно
                if hasattr(self, 'pause_button') and self.pause_button:
                    self.pause_button.setVisible(True)
                    self.pause_button.setText("Пауза")
                    self.pause_button.setStyleSheet(f"background-color: {self.default_button_color}; color: #000000;")
                
                logger.info("Процесс обновления запущен")
                
        except Exception as e:
            logger.error(f"Ошибка запуска обновления: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось запустить обновление: {e}")

    def stop_update(self):
        """Безопасная остановка процесса обновления"""
        try:
            if self.is_updating and self.update_thread.isRunning():
                logger.info("Остановка процесса обновления")
                
                # Безопасная остановка потока
                self.update_thread.stop_safely()
                
                self.update_button.setStyleSheet(f"background-color: {self.default_button_color}; color: #000000;")
                self.update_button.setText("Играть")
                self.is_updating = False
                
                # Скрываем кнопку паузы
                if hasattr(self, 'pause_button') and self.pause_button:
                    self.pause_button.setVisible(False)
                
                # Сброс прогресс-баров
                self.file_progress_bar.setValue(0)
                self.overall_progress_bar.setValue(0)
                
                logger.info("Процесс обновления остановлен")
                
        except Exception as e:
            logger.error(f"Ошибка остановки обновления: {e}")
            QMessageBox.warning(self, "Предупреждение", f"Ошибка при остановке обновления: {e}")

    def update_file_progress(self, value):
        self.file_progress_bar.setValue(value)
        # Обновляем расширенный виджет прогресса
        if hasattr(self, 'enhanced_progress') and self.enhanced_progress:
            self.enhanced_progress.update_file_progress(value)

    def update_overall_progress(self, value):
        self.overall_progress_bar.setValue(value)
        # Обновляем расширенный виджет прогресса
        if hasattr(self, 'enhanced_progress') and self.enhanced_progress:
            self.enhanced_progress.update_main_progress(value)
        
    def update_download_stats(self, stats):
        """Обновление статистики загрузки"""
        try:
            logger.debug(f"Статистика загрузки: {stats}")
            
            # Отображаем в расширенном виджете
            if hasattr(self, 'enhanced_progress') and self.enhanced_progress:
                # Парсим статистику
                parts = stats.split(', ')
                speed = parts[0].replace('Скорость: ', '') if len(parts) > 0 else ''
                eta = parts[1].replace('Осталось: ', '') if len(parts) > 1 else '--'
                
                self.enhanced_progress.update_stats(speed, eta, '--', '--')
            
            # Если есть statusBar, выводим туда
            if hasattr(self, 'statusBar') and self.statusBar():
                self.statusBar().showMessage(stats)
                
        except Exception as e:
            logger.error(f"Ошибка обновления статистики загрузки: {e}")

    def update_finished(self, success, message):
        QMessageBox.information(self, "Обновление завершено", message)
        self.update_button.setStyleSheet(f"background-color: {self.default_button_color}; color: #000000;")
        self.update_button.setText("Играть")
        self.is_updating = False
        
        # Скрываем кнопку паузы
        if hasattr(self, 'pause_button') and self.pause_button:
            self.pause_button.setVisible(False)
        
        # Обновляем статистику в расширенном UI
        if hasattr(self, 'enhanced_info_widget') and self.enhanced_info_widget:
            try:
                # Обновляем статистику
                self.enhanced_info_widget.stats_widget.update_stats()
            except Exception as e:
                logger.error(f"Ошибка обновления статистики: {e}")

    def restart_launcher(self):
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def update_finished_launcher(self, success, message):
        self.is_updating = True
        msg_box = QMessageBox()
        msg_box.setWindowTitle("Обновление завершено")
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setStandardButtons(QMessageBox.Ok)
        
        msg_box.buttonClicked.connect(self.restart_launcher)
        msg_box.exec_()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.oldPos = event.globalPos()
            self.moving = True

    def mouseMoveEvent(self, event):
        if self.moving:
            delta = QPoint(event.globalPos() - self.oldPos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.oldPos = event.globalPos()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.moving = False

    def minimize_to_tray(self):
        self.hide()
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.showNormal()
            self.tray_icon.hide()

    def check_launcher_update(self):
        current_launcher_version = self.config.get('Launcher', 'version')
        version_file = 'version.txt'

        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('LauncherVersion='):
                        latest_launcher_version = line.strip().split('=')[1].strip()
                        break
        except Exception as e:
            print(f"Error reading launcher version from {version_file}: {e}")
            return False

        if latest_launcher_version is None:
            print(f"Warning: 'LauncherVersion=' not found in {version_file}")
            return False

        print(f"Current launcher version: {current_launcher_version}")
        print(f"Latest launcher version: {latest_launcher_version}")

        return latest_launcher_version != current_launcher_version
    
    def open_ui_editor(self):
        """Открытие UI редактора"""
        try:
            from ui_editor import UIEditor
            
            # Проверяем, не открыт ли уже редактор
            if hasattr(self, 'ui_editor') and self.ui_editor and not self.ui_editor.isHidden():
                self.ui_editor.raise_()
                self.ui_editor.activateWindow()
                return
            
            # Создаем новый экземпляр редактора
            self.ui_editor = UIEditor(self)
            self.ui_editor.setWindowTitle("UI редактор лаунчера")
            
            # Загружаем существующую конфигурацию UI если она есть
            ui_config_file = "launcher_ui_config.ui.json"
            if os.path.exists(ui_config_file):
                try:
                    import json
                    with open(ui_config_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if 'widgets' in data:
                        self.ui_editor.canvas.load_widgets_data(data['widgets'])
                        logger.info(f"Загружена конфигурация UI из {ui_config_file}")
                
                except Exception as e:
                    logger.error(f"Ошибка загрузки конфигурации UI: {e}")
                    QMessageBox.warning(
                        self, 
                        "Предупреждение", 
                        f"Не удалось загрузить конфигурацию UI: {e}"
                    )
            
            # Устанавливаем файл по умолчанию для сохранения
            self.ui_editor.current_file = ui_config_file
            self.ui_editor.set_modified(False)
            
            # Показываем редактор
            self.ui_editor.show()
            logger.info("UI редактор открыт")
            
        except ImportError as e:
            logger.error(f"UI редактор недоступен: {e}")
            QMessageBox.critical(
                self, 
                "Ошибка", 
                "UI редактор недоступен. Убедитесь, что файл ui_editor.py находится в папке лаунчера."
            )
        except Exception as e:
            logger.error(f"Ошибка открытия UI редактора: {e}")
            QMessageBox.critical(
                self, 
                "Ошибка", 
                f"Ошибка открытия UI редактора: {e}"
            )
    
    def apply_ui_config(self, config_file: str = "launcher_ui_config.ui.json"):
        """Применение конфигурации UI к лаунчеру"""
        try:
            if not os.path.exists(config_file):
                logger.info(f"Файл конфигурации UI {config_file} не найден")
                return False
            
            import json
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            widgets_data = data.get('widgets', [])
            
            # Применяем настройки к существующим виджетам
            for widget_data in widgets_data:
                widget_type = widget_data['type']
                props = widget_data['properties']
                
                # Ищем соответствующий виджет в лаунчере
                target_widget = None
                
                if widget_type == 'button':
                    # Ищем кнопки по тексту
                    text = props.get('text', '')
                    if 'играть' in text.lower() or 'play' in text.lower():
                        target_widget = self.update_button
                    elif 'пауза' in text.lower() or 'pause' in text.lower():
                        target_widget = getattr(self, 'pause_button', None)
                    elif 'откат' in text.lower() or 'rollback' in text.lower():
                        target_widget = getattr(self, 'rollback_button', None)
                
                elif widget_type == 'label':
                    text = props.get('text', '')
                    if 'version' in text.lower():
                        target_widget = self.Version
                    elif any(word in text.lower() for word in ['сервер', 'server', 'название']):
                        target_widget = self.Name_server
                
                if target_widget:
                    self.apply_widget_properties(target_widget, props)
            
            logger.info(f"Конфигурация UI применена из {config_file}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка применения конфигурации UI: {e}")
            return False
    
    def apply_widget_properties(self, widget, properties: dict):
        """Применение свойств к виджету"""
        try:
            # Позиция и размер
            if all(key in properties for key in ['x', 'y', 'width', 'height']):
                widget.setGeometry(
                    properties['x'],
                    properties['y'],
                    properties['width'],
                    properties['height']
                )
            
            # Текст
            if hasattr(widget, 'setText') and 'text' in properties:
                widget.setText(properties['text'])
            
            # Шрифт
            if properties.get('font_family') or properties.get('font_size'):
                from PyQt5.QtGui import QFont
                font = QFont(
                    properties.get('font_family', 'Arial'),
                    properties.get('font_size', 12)
                )
                widget.setFont(font)
            
            # Стили
            style_parts = []
            
            if properties.get('background_color'):
                style_parts.append(f"background-color: {properties['background_color']}")
            
            if properties.get('text_color'):
                style_parts.append(f"color: {properties['text_color']}")
            
            if properties.get('border_width') and properties.get('border_color'):
                border_style = f"{properties['border_width']}px solid {properties['border_color']}"
                style_parts.append(f"border: {border_style}")
            
            if properties.get('border_radius'):
                style_parts.append(f"border-radius: {properties['border_radius']}px")
            
            if style_parts:
                widget.setStyleSheet("; ".join(style_parts))
            
            # Видимость
            if 'visible' in properties:
                widget.setVisible(properties['visible'])
            
            # Прозрачность
            if 'opacity' in properties:
                widget.setWindowOpacity(properties['opacity'])
            
        except Exception as e:
            logger.error(f"Ошибка применения свойств к виджету: {e}")
    
    def setup_web_content(self):
        """Настройка веб-контента в табах"""
        try:
            if not WEB_CONTENT_AVAILABLE:
                logger.info("Веб-контент недоступен, пропускаем настройку табов")
                return
                
            # Ищем QTabWidget с именем "info"
            from PyQt5.QtWidgets import QTabWidget
            self.info_tab_widget = self.findChild(QTabWidget, 'info')
            if not self.info_tab_widget:
                logger.warning("QTabWidget 'info' не найден")
                return
            
            # Инициализируем менеджер веб-контента
            self.web_content_manager = WebContentManager()
            
            # Получаем источники новостей из конфигурации
            news_sources = self.web_content_manager.get_news_sources()
            
            if not news_sources:
                logger.info("Источники новостей не настроены")
                return
            
            # Очищаем существующие табы
            self.info_tab_widget.clear()
            
            # Создаем табы для каждого источника новостей
            for source_name in news_sources.keys():
                news_widget = self.web_content_manager.create_news_widget(source_name)
                self.info_tab_widget.addTab(news_widget, source_name)
                logger.info(f"Добавлен таб для источника: {source_name}")
            
            # Запускаем автоматическое обновление
            self.web_content_manager.start_auto_refresh()
            
            # Делаем первую загрузку контента
            self.web_content_manager.refresh_all_content()
            
            logger.info("Веб-контент успешно настроен")
            
        except Exception as e:
            logger.error(f"Ошибка настройки веб-контента: {e}")
            # В случае ошибки оставляем табы по умолчанию
    
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        try:
            # Останавливаем веб-контент
            if hasattr(self, 'web_content_manager') and self.web_content_manager:
                self.web_content_manager.stop_auto_refresh()
                logger.info("Веб-контент остановлен")
            
            # Безопасно останавливаем поток обновления
            if hasattr(self, 'update_thread') and self.update_thread.isRunning():
                logger.info("Останавливаем поток обновления...")
                self.update_thread.stop_safely()
            
            event.accept()
            
        except Exception as e:
            logger.error(f"Ошибка при закрытии лаунчера: {e}")
            event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec_())

