"""
Модуль для загрузки и отображения веб-контента (новостей) в лаунчере
"""

import logging
import requests
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                           QScrollArea, QPushButton, QFrame, QTextBrowser,
                           QProgressBar, QMessageBox)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt, QUrl
from PyQt5.QtGui import QFont, QPixmap, QDesktopServices
from configparser import ConfigParser
import html2text

logger = logging.getLogger(__name__)

class NewsItem:
    """Класс для представления новости"""
    
    def __init__(self, title: str, content: str, date: str = None, 
                 image_url: str = None, url: str = None, author: str = None):
        self.title = title
        self.content = content
        self.date = date or datetime.now().strftime("%Y-%m-%d %H:%M")
        self.image_url = image_url
        self.url = url
        self.author = author

class WebContentLoader(QThread):
    """Поток для загрузки веб-контента"""
    
    content_loaded = pyqtSignal(str, list)  # source_name, news_list
    error_occurred = pyqtSignal(str, str)   # source_name, error_message
    
    def __init__(self, sources: Dict[str, str], parent=None):
        super().__init__(parent)
        self.sources = sources
        self.html_parser = html2text.HTML2Text()
        self.html_parser.ignore_links = False
        self.html_parser.ignore_images = False
        
    def run(self):
        """Основной метод загрузки контента"""
        for source_name, url in self.sources.items():
            try:
                news_list = self.load_from_url(url, source_name)
                self.content_loaded.emit(source_name, news_list)
            except Exception as e:
                logger.error(f"Ошибка загрузки контента для {source_name}: {e}")
                self.error_occurred.emit(source_name, str(e))
    
    def load_from_url(self, url: str, source_name: str) -> List[NewsItem]:
        """Загрузка контента с URL"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        content_type = response.headers.get('content-type', '').lower()
        
        if 'application/json' in content_type:
            return self.parse_json_feed(response.json(), source_name)
        elif 'application/rss' in content_type or 'text/xml' in content_type:
            return self.parse_rss_feed(response.text, source_name)
        else:
            return self.parse_html_content(response.text, source_name)
    
    def parse_json_feed(self, data: dict, source_name: str) -> List[NewsItem]:
        """Парсинг JSON фида"""
        news_items = []
        
        if 'items' in data:  # JSON Feed format
            for item in data['items'][:10]:  # Ограничиваем 10 новостями
                news_items.append(NewsItem(
                    title=item.get('title', 'Без названия'),
                    content=self.html_parser.handle(item.get('content_html', item.get('content_text', ''))),
                    date=item.get('date_published', ''),
                    url=item.get('url', ''),
                    author=item.get('author', {}).get('name', source_name)
                ))
        elif 'posts' in data:  # Простой формат
            for item in data['posts'][:10]:
                news_items.append(NewsItem(
                    title=item.get('title', 'Без названия'),
                    content=self.html_parser.handle(item.get('content', '')),
                    date=item.get('date', ''),
                    url=item.get('link', ''),
                    author=item.get('author', source_name)
                ))
        
        return news_items
    
    def parse_rss_feed(self, xml_content: str, source_name: str) -> List[NewsItem]:
        """Парсинг RSS фида"""
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_content)
            news_items = []
            
            # Поиск элементов item в RSS
            items = root.findall('.//item')[:10]  # Ограничиваем 10 новостями
            
            for item in items:
                title = item.find('title')
                description = item.find('description')
                link = item.find('link')
                pub_date = item.find('pubDate')
                
                news_items.append(NewsItem(
                    title=title.text if title is not None else 'Без названия',
                    content=self.html_parser.handle(description.text if description is not None else ''),
                    date=pub_date.text if pub_date is not None else '',
                    url=link.text if link is not None else '',
                    author=source_name
                ))
            
            return news_items
            
        except Exception as e:
            logger.error(f"Ошибка парсинга RSS: {e}")
            return []
    
    def parse_html_content(self, html_content: str, source_name: str) -> List[NewsItem]:
        """Парсинг HTML контента (базовая реализация)"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Простое извлечение контента - можно настроить под конкретный сайт
            title_tag = soup.find('h1') or soup.find('title')
            title = title_tag.get_text().strip() if title_tag else 'Информация с сайта'
            
            # Извлекаем основной контент
            content_tags = soup.find_all(['p', 'div', 'article'], limit=5)
            content = '\n\n'.join([tag.get_text().strip() for tag in content_tags if tag.get_text().strip()])
            
            return [NewsItem(
                title=title,
                content=content[:1000] + '...' if len(content) > 1000 else content,
                author=source_name
            )]
            
        except ImportError:
            # Если BeautifulSoup не установлен, используем html2text
            text_content = self.html_parser.handle(html_content)
            return [NewsItem(
                title=f"Информация с {source_name}",
                content=text_content[:1000] + '...' if len(text_content) > 1000 else text_content,
                author=source_name
            )]
        except Exception as e:
            logger.error(f"Ошибка парсинга HTML: {e}")
            return []

class NewsWidget(QWidget):
    """Виджет для отображения новостей"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.news_items = []
        self.setup_ui()
    
    def setup_ui(self):
        """Настройка интерфейса"""
        layout = QVBoxLayout(self)
        
        # Заголовок
        self.title_label = QLabel("Загрузка новостей...")
        self.title_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.title_label.setStyleSheet("color: white; padding: 5px;")
        layout.addWidget(self.title_label)
        
        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Область прокрутки для новостей
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.1);
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.3);
                border-radius: 5px;
            }
        """)
        
        self.news_container = QWidget()
        self.news_layout = QVBoxLayout(self.news_container)
        self.news_layout.setSpacing(10)
        
        self.scroll_area.setWidget(self.news_container)
        layout.addWidget(self.scroll_area)
        
        # Кнопка обновления
        self.refresh_button = QPushButton("Обновить")
        self.refresh_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 205, 0, 0.8);
                border: none;
                border-radius: 5px;
                padding: 8px;
                color: black;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 205, 0, 1.0);
            }
        """)
        layout.addWidget(self.refresh_button)
    
    def show_loading(self):
        """Показать индикатор загрузки"""
        self.title_label.setText("Загрузка новостей...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Индетерминированный прогресс-бар
        self.clear_news()
    
    def hide_loading(self):
        """Скрыть индикатор загрузки"""
        self.progress_bar.setVisible(False)
    
    def set_news(self, source_name: str, news_items: List[NewsItem]):
        """Установить новости для отображения"""
        self.news_items = news_items
        self.title_label.setText(f"Новости - {source_name}")
        self.hide_loading()
        self.display_news()
    
    def clear_news(self):
        """Очистить отображаемые новости"""
        for i in reversed(range(self.news_layout.count())):
            child = self.news_layout.itemAt(i).widget()
            if child:
                child.setParent(None)
    
    def display_news(self):
        """Отобразить новости"""
        self.clear_news()
        
        if not self.news_items:
            no_news_label = QLabel("Нет доступных новостей")
            no_news_label.setStyleSheet("color: rgba(255, 255, 255, 0.7); text-align: center; padding: 20px;")
            self.news_layout.addWidget(no_news_label)
            return
        
        for news_item in self.news_items:
            news_frame = self.create_news_frame(news_item)
            self.news_layout.addWidget(news_frame)
        
        # Добавляем растяжку в конец
        self.news_layout.addStretch()
    
    def create_news_frame(self, news_item: NewsItem) -> QFrame:
        """Создать фрейм для новости"""
        frame = QFrame()
        frame.setFrameStyle(QFrame.Box)
        frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 5px;
                margin: 2px;
                padding: 5px;
            }
        """)
        
        layout = QVBoxLayout(frame)
        
        # Заголовок новости
        title_label = QLabel(news_item.title)
        title_label.setFont(QFont("Arial", 10, QFont.Bold))
        title_label.setStyleSheet("color: white; padding: 2px;")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        
        # Дата и автор
        if news_item.date or news_item.author:
            meta_info = []
            if news_item.date:
                meta_info.append(news_item.date)
            if news_item.author:
                meta_info.append(f"Автор: {news_item.author}")
            
            meta_label = QLabel(" | ".join(meta_info))
            meta_label.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-size: 8pt;")
            layout.addWidget(meta_label)
        
        # Контент новости
        if news_item.content:
            content_label = QLabel(news_item.content[:300] + "..." if len(news_item.content) > 300 else news_item.content)
            content_label.setStyleSheet("color: rgba(255, 255, 255, 0.9); padding: 5px;")
            content_label.setWordWrap(True)
            layout.addWidget(content_label)
        
        # Кнопка "Читать далее" если есть URL
        if news_item.url:
            read_more_btn = QPushButton("Читать далее")
            read_more_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 205, 0, 0.6);
                    border: none;
                    border-radius: 3px;
                    padding: 4px 8px;
                    color: black;
                    font-size: 8pt;
                }
                QPushButton:hover {
                    background-color: rgba(255, 205, 0, 0.8);
                }
            """)
            read_more_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(news_item.url)))
            layout.addWidget(read_more_btn)
        
        return frame
    
    def show_error(self, source_name: str, error_message: str):
        """Показать ошибку"""
        self.title_label.setText(f"Ошибка загрузки - {source_name}")
        self.hide_loading()
        self.clear_news()
        
        error_label = QLabel(f"Не удалось загрузить новости:\n{error_message}")
        error_label.setStyleSheet("color: rgba(255, 100, 100, 0.9); text-align: center; padding: 20px;")
        error_label.setWordWrap(True)
        self.news_layout.addWidget(error_label)

class WebContentManager:
    """Главный менеджер веб-контента"""
    
    def __init__(self, config_file: str = 'launcher_config.ini'):
        self.config_file = config_file
        self.config = ConfigParser()
        self.news_widgets = {}
        self.load_config()
        
        # Таймер для автообновления
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.refresh_all_content)
        
    def load_config(self):
        """Загрузка конфигурации"""
        try:
            self.config.read(self.config_file, encoding='utf-8')
            
            # Если секции нет, создаем с примерами
            if not self.config.has_section('WebContent'):
                self.create_default_config()
                
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации веб-контента: {e}")
            self.create_default_config()
    
    def create_default_config(self):
        """Создание конфигурации по умолчанию"""
        if not self.config.has_section('WebContent'):
            self.config.add_section('WebContent')
        
        # Примеры источников новостей
        self.config.set('WebContent', 'auto_refresh', '1')
        self.config.set('WebContent', 'refresh_interval', '300')  # 5 минут
        
        # Примеры источников
        if not self.config.has_section('NewsSource1'):
            self.config.add_section('NewsSource1')
            self.config.set('NewsSource1', 'name', 'Новости сервера')
            self.config.set('NewsSource1', 'url', 'https://example.com/news.json')
            self.config.set('NewsSource1', 'type', 'json')
            self.config.set('NewsSource1', 'enabled', '1')
        
        # Сохраняем конфигурацию
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                self.config.write(f)
        except Exception as e:
            logger.error(f"Ошибка сохранения конфигурации: {e}")
    
    def get_news_sources(self) -> Dict[str, str]:
        """Получить источники новостей"""
        sources = {}
        
        for section_name in self.config.sections():
            if section_name.startswith('NewsSource'):
                try:
                    if self.config.getboolean(section_name, 'enabled', fallback=True):
                        name = self.config.get(section_name, 'name')
                        url = self.config.get(section_name, 'url')
                        sources[name] = url
                except Exception as e:
                    logger.error(f"Ошибка чтения источника {section_name}: {e}")
        
        return sources
    
    def create_news_widget(self, source_name: str) -> NewsWidget:
        """Создать виджет новостей для источника"""
        widget = NewsWidget()
        
        # Подключаем кнопку обновления
        widget.refresh_button.clicked.connect(lambda: self.refresh_content(source_name))
        
        self.news_widgets[source_name] = widget
        return widget
    
    def refresh_content(self, source_name: str = None):
        """Обновить контент"""
        sources = self.get_news_sources()
        
        if source_name and source_name in sources:
            # Обновляем конкретный источник
            sources = {source_name: sources[source_name]}
        
        if not sources:
            logger.warning("Нет настроенных источников новостей")
            return
        
        # Показываем индикатор загрузки для всех виджетов
        for name in sources.keys():
            if name in self.news_widgets:
                self.news_widgets[name].show_loading()
        
        # Создаем и запускаем поток загрузки
        self.content_loader = WebContentLoader(sources)
        self.content_loader.content_loaded.connect(self.on_content_loaded)
        self.content_loader.error_occurred.connect(self.on_error_occurred)
        self.content_loader.start()
    
    def refresh_all_content(self):
        """Обновить весь контент"""
        self.refresh_content()
    
    def on_content_loaded(self, source_name: str, news_items: List[NewsItem]):
        """Обработчик успешной загрузки контента"""
        if source_name in self.news_widgets:
            self.news_widgets[source_name].set_news(source_name, news_items)
        logger.info(f"Загружено {len(news_items)} новостей для {source_name}")
    
    def on_error_occurred(self, source_name: str, error_message: str):
        """Обработчик ошибки загрузки"""
        if source_name in self.news_widgets:
            self.news_widgets[source_name].show_error(source_name, error_message)
        logger.error(f"Ошибка загрузки для {source_name}: {error_message}")
    
    def start_auto_refresh(self):
        """Запустить автоматическое обновление"""
        if self.config.getboolean('WebContent', 'auto_refresh', fallback=True):
            interval = self.config.getint('WebContent', 'refresh_interval', fallback=300) * 1000
            self.update_timer.start(interval)
            logger.info(f"Автообновление запущено с интервалом {interval//1000} секунд")
    
    def stop_auto_refresh(self):
        """Остановить автоматическое обновление"""
        self.update_timer.stop()
        logger.info("Автообновление остановлено")