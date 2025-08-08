"""
Конфигурация логирования для лаунчера
"""

import logging
import logging.handlers
import os
from datetime import datetime

def setup_logging(log_level=logging.INFO, max_log_files=5, max_file_size=10*1024*1024):
    """
    Настройка системы логирования
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
        max_log_files: Максимальное количество файлов логов
        max_file_size: Максимальный размер файла лога в байтах
    """
    
    # Создаем папку для логов если её нет
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Основной логгер
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Очищаем существующие хэндлеры
    logger.handlers.clear()
    
    # Форматтер для логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Ротирующийся файловый хэндлер
    log_filename = os.path.join(log_dir, 'launcher.log')
    file_handler = logging.handlers.RotatingFileHandler(
        log_filename,
        maxBytes=max_file_size,
        backupCount=max_log_files,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Консольный хэндлер для важных сообщений
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)  # Только предупреждения и ошибки в консоль
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Отдельный файл для ошибок
    error_log_filename = os.path.join(log_dir, 'launcher_errors.log')
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_filename,
        maxBytes=max_file_size,
        backupCount=max_log_files,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)
    
    # Логируем старт приложения
    logger.info("="*50)
    logger.info(f"Запуск лаунчера {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*50)
    
    return logger

# Дополнительные утилиты для логирования
class LauncherLogger:
    """Обёртка для удобного логирования в лаунчере"""
    
    def __init__(self, name):
        self.logger = logging.getLogger(name)
    
    def log_download_start(self, url, size):
        """Логирование начала загрузки"""
        self.logger.info(f"Начинаем загрузку: {url} (размер: {size} байт)")
    
    def log_download_progress(self, filename, progress, speed=None):
        """Логирование прогресса загрузки"""
        if speed:
            self.logger.debug(f"Загрузка {filename}: {progress}% (скорость: {speed:.1f} КБ/с)")
        else:
            self.logger.debug(f"Загрузка {filename}: {progress}%")
    
    def log_download_complete(self, filename, total_size, duration):
        """Логирование завершения загрузки"""
        avg_speed = (total_size / duration / 1024) if duration > 0 else 0
        self.logger.info(f"Загрузка завершена: {filename} ({total_size} байт за {duration:.1f} сек, средняя скорость: {avg_speed:.1f} КБ/с)")
    
    def log_extraction_start(self, archive_path):
        """Логирование начала распаковки"""
        self.logger.info(f"Начинаем распаковку архива: {archive_path}")
    
    def log_extraction_complete(self, archive_path, files_count):
        """Логирование завершения распаковки"""
        self.logger.info(f"Распаковка завершена: {archive_path} ({files_count} файлов)")
    
    def log_security_warning(self, message):
        """Логирование предупреждений безопасности"""
        self.logger.warning(f"БЕЗОПАСНОСТЬ: {message}")
    
    def log_security_error(self, message):
        """Логирование ошибок безопасности"""
        self.logger.error(f"КРИТИЧЕСКАЯ БЕЗОПАСНОСТЬ: {message}")