"""
Улучшения пользовательского интерфейса и статистика
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QThread
from PyQt5.QtGui import QFont, QPixmap, QIcon
import time

logger = logging.getLogger(__name__)

class StatisticsManager:
    """Менеджер статистики загрузок и обновлений"""
    
    def __init__(self, stats_file: str = "launcher_stats.json"):
        self.stats_file = stats_file
        self.stats = self.load_stats()
    
    def load_stats(self) -> dict:
        """Загрузка статистики из файла"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки статистики: {e}")
        
        return {
            'downloads': [],
            'updates': [],
            'total_downloaded_mb': 0,
            'total_update_count': 0,
            'average_speed_mbps': 0,
            'first_run_date': datetime.now().isoformat(),
            'last_run_date': datetime.now().isoformat()
        }
    
    def save_stats(self):
        """Сохранение статистики в файл"""
        try:
            self.stats['last_run_date'] = datetime.now().isoformat()
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения статистики: {e}")
    
    def record_download(self, file_name: str, file_size: int, download_time: float, speed: float):
        """Запись информации о загрузке"""
        download_record = {
            'file_name': file_name,
            'file_size_mb': round(file_size / 1024 / 1024, 2),
            'download_time_sec': round(download_time, 2),
            'speed_mbps': round(speed, 2),
            'timestamp': datetime.now().isoformat()
        }
        
        self.stats['downloads'].append(download_record)
        self.stats['total_downloaded_mb'] += download_record['file_size_mb']
        
        # Обновляем среднюю скорость
        speeds = [d['speed_mbps'] for d in self.stats['downloads']]
        self.stats['average_speed_mbps'] = round(sum(speeds) / len(speeds), 2)
        
        # Ограничиваем размер истории
        if len(self.stats['downloads']) > 100:
            self.stats['downloads'] = self.stats['downloads'][-100:]
        
        self.save_stats()
    
    def record_update(self, from_version: str, to_version: str, update_type: str, success: bool):
        """Запись информации об обновлении"""
        update_record = {
            'from_version': from_version,
            'to_version': to_version,
            'update_type': update_type,  # 'full', 'delta', 'p2p'
            'success': success,
            'timestamp': datetime.now().isoformat()
        }
        
        self.stats['updates'].append(update_record)
        if success:
            self.stats['total_update_count'] += 1
        
        # Ограничиваем размер истории
        if len(self.stats['updates']) > 50:
            self.stats['updates'] = self.stats['updates'][-50:]
        
        self.save_stats()
    
    def get_summary(self) -> dict:
        """Получение сводной статистики"""
        return {
            'total_downloads': len(self.stats['downloads']),
            'total_updates': self.stats['total_update_count'],
            'total_downloaded_mb': self.stats['total_downloaded_mb'],
            'average_speed_mbps': self.stats['average_speed_mbps'],
            'first_run_date': self.stats['first_run_date'],
            'last_run_date': self.stats['last_run_date']
        }
    
    def get_recent_downloads(self, count: int = 10) -> List[dict]:
        """Получение последних загрузок"""
        return self.stats['downloads'][-count:] if self.stats['downloads'] else []
    
    def get_recent_updates(self, count: int = 10) -> List[dict]:
        """Получение последних обновлений"""
        return self.stats['updates'][-count:] if self.stats['updates'] else []

class EnhancedProgressBar(QProgressBar):
    """Расширенный прогресс-бар с дополнительной информацией"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(True)
        self.current_speed = 0.0
        self.eta_seconds = 0
        self.bytes_downloaded = 0
        self.total_bytes = 0
        
    def update_progress(self, percentage: int, speed_mbps: float = 0.0, 
                       downloaded: int = 0, total: int = 0):
        """Обновление прогресса с дополнительной информацией"""
        self.setValue(percentage)
        self.current_speed = speed_mbps
        self.bytes_downloaded = downloaded
        self.total_bytes = total
        
        # Вычисляем ETA
        if speed_mbps > 0 and total > downloaded:
            remaining_mb = (total - downloaded) / 1024 / 1024
            self.eta_seconds = int(remaining_mb / speed_mbps)
        else:
            self.eta_seconds = 0
        
        self.update_text()
    
    def update_text(self):
        """Обновление текста прогресс-бара"""
        text_parts = [f"{self.value()}%"]
        
        if self.current_speed > 0:
            text_parts.append(f"{self.current_speed:.1f} МБ/с")
        
        if self.eta_seconds > 0:
            if self.eta_seconds < 60:
                text_parts.append(f"~{self.eta_seconds}с")
            elif self.eta_seconds < 3600:
                text_parts.append(f"~{self.eta_seconds//60}м")
            else:
                text_parts.append(f"~{self.eta_seconds//3600}ч")
        
        if self.total_bytes > 0:
            downloaded_mb = self.bytes_downloaded / 1024 / 1024
            total_mb = self.total_bytes / 1024 / 1024
            text_parts.append(f"{downloaded_mb:.1f}/{total_mb:.1f} МБ")
        
        self.setFormat(" | ".join(text_parts))

class LogViewer(QTextEdit):
    """Просмотрщик логов с автообновлением"""
    
    def __init__(self, log_file: str, parent=None):
        super().__init__(parent)
        self.log_file = log_file
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 9))
        
        # Таймер для автообновления
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.refresh_logs)
        self.update_timer.start(2000)  # Обновление каждые 2 секунды
        
        # Отслеживание позиции файла
        self.last_position = 0
        self.max_lines = 1000
        
        self.refresh_logs()
    
    def refresh_logs(self):
        """Обновление содержимого логов"""
        try:
            if not os.path.exists(self.log_file):
                return
            
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(self.last_position)
                new_content = f.read()
                
                if new_content:
                    # Добавляем новый контент
                    self.append(new_content.rstrip())
                    
                    # Ограничиваем количество строк
                    document = self.document()
                    if document.lineCount() > self.max_lines:
                        cursor = self.textCursor()
                        cursor.movePosition(cursor.Start)
                        cursor.movePosition(cursor.Down, cursor.KeepAnchor, 
                                          document.lineCount() - self.max_lines)
                        cursor.removeSelectedText()
                    
                    # Автоскролл вниз
                    scrollbar = self.verticalScrollBar()
                    scrollbar.setValue(scrollbar.maximum())
                
                self.last_position = f.tell()
                
        except Exception as e:
            logger.error(f"Ошибка обновления логов: {e}")
    
    def clear_logs(self):
        """Очистка отображаемых логов"""
        self.clear()
        self.last_position = 0

class StatisticsWidget(QWidget):
    """Виджет отображения статистики"""
    
    def __init__(self, stats_manager: StatisticsManager, parent=None):
        super().__init__(parent)
        self.stats_manager = stats_manager
        self.setup_ui()
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_stats)
        self.refresh_timer.start(5000)  # Обновление каждые 5 секунд
    
    def setup_ui(self):
        """Настройка интерфейса"""
        layout = QVBoxLayout()
        
        # Заголовок
        title = QLabel("Статистика загрузок")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(title)
        
        # Общая статистика
        self.summary_group = QGroupBox("Общая статистика")
        summary_layout = QGridLayout()
        
        self.total_downloads_label = QLabel("Загрузок: 0")
        self.total_updates_label = QLabel("Обновлений: 0") 
        self.total_size_label = QLabel("Загружено: 0 МБ")
        self.avg_speed_label = QLabel("Средняя скорость: 0 МБ/с")
        
        summary_layout.addWidget(self.total_downloads_label, 0, 0)
        summary_layout.addWidget(self.total_updates_label, 0, 1)
        summary_layout.addWidget(self.total_size_label, 1, 0)
        summary_layout.addWidget(self.avg_speed_label, 1, 1)
        
        self.summary_group.setLayout(summary_layout)
        layout.addWidget(self.summary_group)
        
        # Таблица последних загрузок
        self.downloads_group = QGroupBox("Последние загрузки")
        downloads_layout = QVBoxLayout()
        
        self.downloads_table = QTableWidget(0, 4)
        self.downloads_table.setHorizontalHeaderLabels([
            "Файл", "Размер (МБ)", "Скорость (МБ/с)", "Время"
        ])
        self.downloads_table.horizontalHeader().setStretchLastSection(True)
        
        downloads_layout.addWidget(self.downloads_table)
        self.downloads_group.setLayout(downloads_layout)
        layout.addWidget(self.downloads_group)
        
        # Таблица последних обновлений
        self.updates_group = QGroupBox("Последние обновления")
        updates_layout = QVBoxLayout()
        
        self.updates_table = QTableWidget(0, 4)
        self.updates_table.setHorizontalHeaderLabels([
            "От версии", "К версии", "Тип", "Время"
        ])
        self.updates_table.horizontalHeader().setStretchLastSection(True)
        
        updates_layout.addWidget(self.updates_table)
        self.updates_group.setLayout(updates_layout)
        layout.addWidget(self.updates_group)
        
        self.setLayout(layout)
        self.refresh_stats()
    
    def refresh_stats(self):
        """Обновление отображаемой статистики"""
        try:
            summary = self.stats_manager.get_summary()
            
            # Обновляем общую статистику
            self.total_downloads_label.setText(f"Загрузок: {summary['total_downloads']}")
            self.total_updates_label.setText(f"Обновлений: {summary['total_updates']}")
            self.total_size_label.setText(f"Загружено: {summary['total_downloaded_mb']:.1f} МБ")
            self.avg_speed_label.setText(f"Средняя скорость: {summary['average_speed_mbps']:.1f} МБ/с")
            
            # Обновляем таблицу загрузок
            downloads = self.stats_manager.get_recent_downloads(10)
            self.downloads_table.setRowCount(len(downloads))
            
            for i, download in enumerate(downloads):
                self.downloads_table.setItem(i, 0, QTableWidgetItem(download['file_name']))
                self.downloads_table.setItem(i, 1, QTableWidgetItem(f"{download['file_size_mb']:.1f}"))
                self.downloads_table.setItem(i, 2, QTableWidgetItem(f"{download['speed_mbps']:.1f}"))
                
                # Форматируем время
                timestamp = datetime.fromisoformat(download['timestamp'])
                time_str = timestamp.strftime("%H:%M:%S")
                self.downloads_table.setItem(i, 3, QTableWidgetItem(time_str))
            
            # Обновляем таблицу обновлений
            updates = self.stats_manager.get_recent_updates(10)
            self.updates_table.setRowCount(len(updates))
            
            for i, update in enumerate(updates):
                self.updates_table.setItem(i, 0, QTableWidgetItem(update['from_version']))
                self.updates_table.setItem(i, 1, QTableWidgetItem(update['to_version']))
                self.updates_table.setItem(i, 2, QTableWidgetItem(update['update_type']))
                
                # Форматируем время
                timestamp = datetime.fromisoformat(update['timestamp'])
                time_str = timestamp.strftime("%H:%M:%S")
                self.updates_table.setItem(i, 3, QTableWidgetItem(time_str))
        
        except Exception as e:
            logger.error(f"Ошибка обновления статистики: {e}")

class NetworkStatusWidget(QWidget):
    """Виджет отображения состояния сети"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
        # Таймер для обновления статуса
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(3000)  # Обновление каждые 3 секунды
    
    def setup_ui(self):
        """Настройка интерфейса"""
        layout = QVBoxLayout()
        
        # P2P статус
        self.p2p_group = QGroupBox("P2P Сеть")
        p2p_layout = QGridLayout()
        
        self.p2p_status_label = QLabel("Статус: Отключен")
        self.p2p_peers_label = QLabel("Пиры: 0")
        self.p2p_uploaded_label = QLabel("Отдано: 0 МБ")
        self.p2p_downloaded_label = QLabel("Получено: 0 МБ")
        
        p2p_layout.addWidget(self.p2p_status_label, 0, 0)
        p2p_layout.addWidget(self.p2p_peers_label, 0, 1)
        p2p_layout.addWidget(self.p2p_uploaded_label, 1, 0)
        p2p_layout.addWidget(self.p2p_downloaded_label, 1, 1)
        
        self.p2p_group.setLayout(p2p_layout)
        layout.addWidget(self.p2p_group)
        
        # CDN статус
        self.cdn_group = QGroupBox("CDN")
        cdn_layout = QGridLayout()
        
        self.cdn_current_label = QLabel("Текущий: Не выбран")
        self.cdn_response_label = QLabel("Отклик: N/A")
        self.cdn_mirrors_label = QLabel("Зеркал: 0")
        
        cdn_layout.addWidget(self.cdn_current_label, 0, 0)
        cdn_layout.addWidget(self.cdn_response_label, 0, 1)
        cdn_layout.addWidget(self.cdn_mirrors_label, 1, 0)
        
        self.cdn_group.setLayout(cdn_layout)
        layout.addWidget(self.cdn_group)
        
        # Пропускная способность
        self.bandwidth_group = QGroupBox("Пропускная способность")
        bandwidth_layout = QGridLayout()
        
        self.current_speed_label = QLabel("Текущая: 0 МБ/с")
        self.peak_speed_label = QLabel("Пиковая: 0 МБ/с")
        self.connection_type_label = QLabel("Тип: Неизвестен")
        
        bandwidth_layout.addWidget(self.current_speed_label, 0, 0)
        bandwidth_layout.addWidget(self.peak_speed_label, 0, 1)
        bandwidth_layout.addWidget(self.connection_type_label, 1, 0)
        
        self.bandwidth_group.setLayout(bandwidth_layout)
        layout.addWidget(self.bandwidth_group)
        
        self.setLayout(layout)
    
    def update_status(self):
        """Обновление статуса сети"""
        try:
            # Получаем статистику P2P если доступна
            try:
                from p2p_distribution import P2PDistributor
                # Здесь можно получить реальную статистику P2P
                self.p2p_status_label.setText("Статус: Активен")
            except:
                self.p2p_status_label.setText("Статус: Недоступен")
            
            # Получаем статистику CDN если доступна
            try:
                from cdn_manager import get_cdn_manager
                # Здесь можно получить реальную статистику CDN
                self.cdn_current_label.setText("Текущий: Автовыбор")
            except:
                self.cdn_current_label.setText("Текущий: Недоступен")
                
        except Exception as e:
            logger.error(f"Ошибка обновления статуса сети: {e}")

class TabbedInfoWidget(QTabWidget):
    """Табовый виджет с информацией"""
    
    def __init__(self, stats_manager: StatisticsManager, parent=None):
        super().__init__(parent)
        self.stats_manager = stats_manager
        self.setup_tabs()
    
    def setup_tabs(self):
        """Настройка вкладок"""
        # Вкладка статистики
        self.stats_widget = StatisticsWidget(self.stats_manager)
        self.addTab(self.stats_widget, "Статистика")
        
        # Вкладка состояния сети
        self.network_widget = NetworkStatusWidget()
        self.addTab(self.network_widget, "Сеть")
        
        # Вкладка логов
        if os.path.exists("logs/launcher.log"):
            self.log_viewer = LogViewer("logs/launcher.log")
            self.addTab(self.log_viewer, "Логи")

# Глобальные экземпляры
_stats_manager = None

def get_stats_manager() -> StatisticsManager:
    """Получение глобального экземпляра менеджера статистики"""
    global _stats_manager
    if _stats_manager is None:
        _stats_manager = StatisticsManager()
    return _stats_manager

def create_enhanced_progress_bar() -> EnhancedProgressBar:
    """Создание расширенного прогресс-бара"""
    return EnhancedProgressBar()

def create_tabbed_info_widget(parent=None) -> TabbedInfoWidget:
    """Создание табового виджета с информацией"""
    return TabbedInfoWidget(get_stats_manager(), parent)