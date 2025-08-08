"""
Визуальный редактор UI для лаунчера
Позволяет создавать и редактировать интерфейс лаунчера в режиме реального времени
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize, QTimer
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPixmap, QIcon
from configparser import ConfigParser

logger = logging.getLogger(__name__)


class DraggableWidget(QWidget):
    """Базовый класс для перетаскиваемых элементов UI"""
    
    position_changed = pyqtSignal(object, QPoint)  # виджет, новая позиция
    size_changed = pyqtSignal(object, QSize)       # виджет, новый размер
    selected = pyqtSignal(object)                  # виджет выделен
    
    def __init__(self, widget_type: str, parent=None):
        super().__init__(parent)
        self.widget_type = widget_type
        self.is_selected = False
        self.is_dragging = False
        self.is_resizing = False
        self.drag_start_position = QPoint()
        self.resize_start_position = QPoint()
        self.resize_start_geometry = QRect()
        
        # Настройки по умолчанию
        self.properties = {
            'x': 0,
            'y': 0,
            'width': 100,
            'height': 30,
            'text': f'{widget_type}',
            'font_size': 12,
            'font_family': 'Arial',
            'background_color': '#ffffff',
            'text_color': '#000000',
            'border_width': 1,
            'border_color': '#cccccc',
            'border_radius': 0,
            'opacity': 1.0,
            'visible': True
        }
        
        self.setMinimumSize(20, 20)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.update_appearance()
    
    def update_appearance(self):
        """Обновление внешнего вида виджета"""
        try:
            # Устанавливаем размер и позицию
            self.setGeometry(
                self.properties['x'],
                self.properties['y'], 
                self.properties['width'],
                self.properties['height']
            )
            
            # Создаем стиль
            style = self.create_style_sheet()
            self.setStyleSheet(style)
            
            # Обновляем текст и шрифт для текстовых элементов
            if self.widget_type in ['label', 'button']:
                try:
                    font = QFont(self.properties['font_family'], self.properties['font_size'])
                    self.setFont(font)
                    if hasattr(self, 'setText'):
                        self.setText(str(self.properties['text']))
                except Exception:
                    pass
            
            # Видимость
            self.setVisible(self.properties['visible'])
            
            # Прозрачность
            self.setWindowOpacity(self.properties['opacity'])
            
        except Exception:
            pass
    
    def create_style_sheet(self) -> str:
        """Создание CSS стилей"""
        border_style = f"{self.properties['border_width']}px solid {self.properties['border_color']}"
        
        style = f"""
        QWidget {{
            background-color: {self.properties['background_color']};
            color: {self.properties['text_color']};
            border: {border_style};
            border-radius: {self.properties['border_radius']}px;
        }}
        """
        
        if self.is_selected:
            style += """
            QWidget {
                border: 2px dashed #ff6b6b;
            }
            """
        
        return style
    
    def set_property(self, key: str, value: Any):
        """Установка свойства виджета"""
        if key in self.properties:
            self.properties[key] = value
            self.update_appearance()
            return True
        return False
    
    def get_property(self, key: str) -> Any:
        """Получение свойства виджета"""
        return self.properties.get(key)
    
    def get_all_properties(self) -> Dict[str, Any]:
        """Получение всех свойств"""
        return self.properties.copy()
    
    def set_selected(self, selected: bool):
        """Установка состояния выделения"""
        if self.is_selected != selected:
            self.is_selected = selected
            self.update_appearance()
            if selected:
                self.selected.emit(self)
    
    def mousePressEvent(self, event):
        """Обработка нажатия мыши"""
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.globalPos()
            self.resize_start_position = event.pos()
            self.resize_start_geometry = self.geometry()
            
            # Проверяем, в углу ли нажатие (для ресайза)
            corner_size = 10
            widget_rect = self.rect()
            
            if (event.pos().x() >= widget_rect.width() - corner_size and 
                event.pos().y() >= widget_rect.height() - corner_size):
                self.is_resizing = True
                self.setCursor(Qt.SizeFDiagCursor)
            else:
                self.is_dragging = True
                self.setCursor(Qt.ClosedHandCursor)
            
            self.set_selected(True)
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Обработка перемещения мыши"""
        if not (event.buttons() & Qt.LeftButton):
            return
        
        if self.is_dragging:
            # Перетаскивание
            delta = event.globalPos() - self.drag_start_position
            new_pos = self.pos() + delta
            
            # Ограничиваем в пределах родительского виджета
            if self.parent():
                parent_rect = self.parent().rect()
                new_pos.setX(max(0, min(parent_rect.width() - self.width(), new_pos.x())))
                new_pos.setY(max(0, min(parent_rect.height() - self.height(), new_pos.y())))
            
            self.move(new_pos)
            self.properties['x'] = new_pos.x()
            self.properties['y'] = new_pos.y()
            self.position_changed.emit(self, new_pos)
            self.drag_start_position = event.globalPos()
            
        elif self.is_resizing:
            # Изменение размера
            delta = event.pos() - self.resize_start_position
            new_geometry = self.resize_start_geometry
            new_geometry.setWidth(max(20, new_geometry.width() + delta.x()))
            new_geometry.setHeight(max(20, new_geometry.height() + delta.y()))
            
            self.setGeometry(new_geometry)
            self.properties['width'] = new_geometry.width()
            self.properties['height'] = new_geometry.height()
            self.size_changed.emit(self, new_geometry.size())
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Обработка отпускания мыши"""
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            self.is_resizing = False
            self.setCursor(Qt.ArrowCursor)
        
        super().mouseReleaseEvent(event)
    
    def enterEvent(self, event):
        """Курсор над виджетом"""
        if not self.is_dragging and not self.is_resizing:
            # Проверяем, над углом ли курсор
            cursor_pos = self.mapFromGlobal(self.cursor().pos())
            corner_size = 10
            
            if (cursor_pos.x() >= self.width() - corner_size and 
                cursor_pos.y() >= self.height() - corner_size):
                self.setCursor(Qt.SizeFDiagCursor)
            else:
                self.setCursor(Qt.OpenHandCursor)
        
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Курсор ушел с виджета"""
        if not self.is_dragging and not self.is_resizing:
            self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)
    
    def paintEvent(self, event):
        """Отрисовка виджета"""
        super().paintEvent(event)
        
        # Рисуем индикатор изменения размера
        if self.is_selected:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Рисуем уголок для ресайза
            corner_size = 10
            corner_rect = QRect(
                self.width() - corner_size,
                self.height() - corner_size,
                corner_size,
                corner_size
            )
            
            painter.fillRect(corner_rect, QBrush(QColor(255, 107, 107, 128)))
            painter.setPen(QPen(QColor(255, 107, 107), 1))
            painter.drawRect(corner_rect)


class UIButton(QPushButton, DraggableWidget):
    """Кнопка"""
    
    # Явно объявляем сигналы для множественного наследования
    position_changed = pyqtSignal(object, QPoint)
    size_changed = pyqtSignal(object, QSize)
    selected = pyqtSignal(object)
    
    def __init__(self, parent=None):
        QPushButton.__init__(self, parent)
        DraggableWidget.__init__(self, 'button', parent)
        self.properties['text'] = 'Кнопка'
        self.setText(self.properties['text'])
        self.update_appearance()


class UILabel(QLabel, DraggableWidget):
    """Текстовая метка"""
    
    # Явно объявляем сигналы для множественного наследования
    position_changed = pyqtSignal(object, QPoint)
    size_changed = pyqtSignal(object, QSize)
    selected = pyqtSignal(object)
    
    def __init__(self, parent=None):
        QLabel.__init__(self, parent)
        DraggableWidget.__init__(self, 'label', parent)
        self.properties['text'] = 'Текст'
        self.properties['background_color'] = 'transparent'
        # Устанавливаем базовые свойства
        self.setText(self.properties['text'])
        self.update_appearance()


class UIProgressBar(QProgressBar, DraggableWidget):
    """Прогресс-бар"""
    
    # Явно объявляем сигналы для множественного наследования
    position_changed = pyqtSignal(object, QPoint)
    size_changed = pyqtSignal(object, QSize)
    selected = pyqtSignal(object)
    
    def __init__(self, parent=None):
        QProgressBar.__init__(self, parent)
        DraggableWidget.__init__(self, 'progress', parent)
        self.properties['width'] = 200
        self.properties['height'] = 25
        self.setValue(50)
        self.update_appearance()


class UIImageLabel(QLabel, DraggableWidget):
    """Изображение"""
    
    # Явно объявляем сигналы для множественного наследования
    position_changed = pyqtSignal(object, QPoint)
    size_changed = pyqtSignal(object, QSize)
    selected = pyqtSignal(object)
    
    def __init__(self, parent=None):
        QLabel.__init__(self, parent)
        DraggableWidget.__init__(self, 'image', parent)
        self.properties.update({
            'image_path': '',
            'scale_mode': 'KeepAspectRatio',  # KeepAspectRatio, ScaleToFit, IgnoreAspectRatio
            'width': 150,
            'height': 100
        })
        self.setText("Изображение")
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border: 1px dashed #ccc;")
        self.update_appearance()
    
    def set_image(self, image_path: str):
        """Установка изображения"""
        try:
            if os.path.exists(image_path):
                pixmap = QPixmap(image_path)
                if not pixmap.isNull():
                    # Масштабируем в зависимости от режима
                    if self.properties['scale_mode'] == 'KeepAspectRatio':
                        scaled_pixmap = pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    elif self.properties['scale_mode'] == 'ScaleToFit':
                        scaled_pixmap = pixmap.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    else:
                        scaled_pixmap = pixmap
                    
                    self.setPixmap(scaled_pixmap)
                    self.properties['image_path'] = image_path
                    return True
        except Exception:
            pass
        
        return False


class ElementInspector(QWidget):
    """Панель инспектора свойств элемента"""
    
    property_changed = pyqtSignal(object, str, object)  # виджет, ключ, значение
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_widget = None
        self.property_editors = {}
        self.setup_ui()
    
    def setup_ui(self):
        """Настройка интерфейса"""
        layout = QVBoxLayout()
        
        # Заголовок
        self.title_label = QLabel("Инспектор свойств")
        self.title_label.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(self.title_label)
        
        # Скроллируемая область для свойств
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.properties_widget = QWidget()
        self.properties_layout = QFormLayout()
        self.properties_widget.setLayout(self.properties_layout)
        scroll_area.setWidget(self.properties_widget)
        
        layout.addWidget(scroll_area)
        self.setLayout(layout)
        
        # Placeholder когда нет выделенного элемента
        self.show_no_selection()
    
    def show_no_selection(self):
        """Показать сообщение об отсутствии выделения"""
        self.clear_properties()
        label = QLabel("Выберите элемент для редактирования")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #666; font-style: italic; padding: 20px;")
        self.properties_layout.addRow(label)
    
    def clear_properties(self):
        """Очистка списка свойств"""
        while self.properties_layout.count():
            child = self.properties_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.property_editors.clear()
    
    def set_widget(self, widget: DraggableWidget):
        """Установка виджета для редактирования"""
        if self.current_widget == widget:
            return
        
        self.current_widget = widget
        self.clear_properties()
        
        if widget is None:
            self.show_no_selection()
            return
        
        # Заголовок с типом виджета
        header = QLabel(f"Свойства: {widget.widget_type}")
        header.setFont(QFont("Arial", 10, QFont.Bold))
        header.setStyleSheet("background-color: #f0f0f0; padding: 5px; margin: 2px 0;")
        self.properties_layout.addRow(header)
        
        # Создаем редакторы для каждого свойства
        properties = widget.get_all_properties()
        
        for key, value in properties.items():
            editor = self.create_property_editor(key, value)
            if editor:
                self.properties_layout.addRow(key.replace('_', ' ').title(), editor)
                self.property_editors[key] = editor
        
        # Специальные свойства для изображений
        if isinstance(widget, UIImageLabel):
            self.add_image_specific_properties()
    
    def create_property_editor(self, key: str, value: Any) -> QWidget:
        """Создание редактора для свойства"""
        if key in ['x', 'y', 'width', 'height', 'font_size', 'border_width', 'border_radius']:
            # Числовые значения
            spinbox = QSpinBox()
            spinbox.setRange(-9999, 9999)
            spinbox.setValue(int(value))
            spinbox.valueChanged.connect(
                lambda v, k=key: self.on_property_changed(k, v)
            )
            return spinbox
            
        elif key in ['opacity']:
            # Вещественные значения
            spinbox = QDoubleSpinBox()
            spinbox.setRange(0.0, 1.0)
            spinbox.setSingleStep(0.1)
            spinbox.setValue(float(value))
            spinbox.valueChanged.connect(
                lambda v, k=key: self.on_property_changed(k, v)
            )
            return spinbox
            
        elif key in ['background_color', 'text_color', 'border_color']:
            # Цвета
            button = QPushButton()
            button.setStyleSheet(f"background-color: {value}; border: 1px solid #ccc;")
            button.setFixedSize(50, 25)
            button.clicked.connect(
                lambda checked, k=key, v=value: self.open_color_dialog(k, v)
            )
            return button
            
        elif key in ['font_family']:
            # Выбор шрифта
            combobox = QComboBox()
            fonts = ['Arial', 'Times New Roman', 'Courier New', 'Verdana', 'Tahoma', 'Georgia']
            combobox.addItems(fonts)
            if value in fonts:
                combobox.setCurrentText(value)
            combobox.currentTextChanged.connect(
                lambda v, k=key: self.on_property_changed(k, v)
            )
            return combobox
            
        elif key in ['visible']:
            # Булевые значения
            checkbox = QCheckBox()
            checkbox.setChecked(bool(value))
            checkbox.toggled.connect(
                lambda v, k=key: self.on_property_changed(k, v)
            )
            return checkbox
            
        elif key in ['text']:
            # Текстовые значения
            lineedit = QLineEdit()
            lineedit.setText(str(value))
            lineedit.textChanged.connect(
                lambda v, k=key: self.on_property_changed(k, v)
            )
            return lineedit
            
        else:
            # Общие текстовые поля
            lineedit = QLineEdit()
            lineedit.setText(str(value))
            lineedit.textChanged.connect(
                lambda v, k=key: self.on_property_changed(k, v)
            )
            return lineedit
    
    def add_image_specific_properties(self):
        """Добавление специфичных свойств для изображений"""
        if not isinstance(self.current_widget, UIImageLabel):
            return
        
        # Выбор файла изображения
        file_layout = QHBoxLayout()
        file_button = QPushButton("Выбрать изображение")
        file_button.clicked.connect(self.select_image_file)
        file_layout.addWidget(file_button)
        
        file_widget = QWidget()
        file_widget.setLayout(file_layout)
        self.properties_layout.addRow("Изображение:", file_widget)
        
        # Режим масштабирования
        scale_combo = QComboBox()
        scale_combo.addItems(['KeepAspectRatio', 'ScaleToFit', 'IgnoreAspectRatio'])
        scale_combo.setCurrentText(self.current_widget.get_property('scale_mode'))
        scale_combo.currentTextChanged.connect(
            lambda v: self.on_property_changed('scale_mode', v)
        )
        self.properties_layout.addRow("Масштабирование:", scale_combo)
    
    def select_image_file(self):
        """Выбор файла изображения"""
        if not isinstance(self.current_widget, UIImageLabel):
            return
        
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(
            self,
            "Выберите изображение",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp)"
        )
        
        if file_path:
            if self.current_widget.set_image(file_path):
                self.property_changed.emit(self.current_widget, 'image_path', file_path)
    
    def open_color_dialog(self, key: str, current_color: str):
        """Открытие диалога выбора цвета"""
        color = QColorDialog.getColor(QColor(current_color), self)
        if color.isValid():
            color_name = color.name()
            self.on_property_changed(key, color_name)
            
            # Обновляем кнопку
            if key in self.property_editors:
                button = self.property_editors[key]
                button.setStyleSheet(f"background-color: {color_name}; border: 1px solid #ccc;")
    
    def on_property_changed(self, key: str, value: Any):
        """Обработка изменения свойства"""
        if self.current_widget:
            self.current_widget.set_property(key, value)
            self.property_changed.emit(self.current_widget, key, value)


class WidgetToolbox(QWidget):
    """Панель инструментов с виджетами"""
    
    widget_requested = pyqtSignal(str)  # тип виджета для создания
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Настройка интерфейса"""
        layout = QVBoxLayout()
        
        # Заголовок
        title = QLabel("Элементы UI")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(title)
        
        # Кнопки для создания виджетов
        widgets_info = [
            ('button', 'Кнопка', '🔘'),
            ('label', 'Текст', '📝'),
            ('progress', 'Прогресс-бар', '▬'),
            ('image', 'Изображение', '🖼️'),
        ]
        
        for widget_type, name, icon in widgets_info:
            button = QPushButton(f"{icon} {name}")
            button.setFixedHeight(35)
            button.clicked.connect(lambda checked, wt=widget_type: self.widget_requested.emit(wt))
            layout.addWidget(button)
        
        layout.addStretch()
        self.setLayout(layout)


class DesignCanvas(QWidget):
    """Холст для дизайна"""
    
    widget_selected = pyqtSignal(object)  # выделенный виджет
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.widgets = []
        self.selected_widget = None
        self.grid_size = 10
        self.show_grid = True
        self.snap_to_grid = True
        
        self.setStyleSheet("background-color: white;")
        self.setMinimumSize(800, 600)
        self.setAcceptDrops(True)
        
        # Контекстное меню
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
    
    def add_widget(self, widget_type: str, position: QPoint = None) -> DraggableWidget:
        """Добавление виджета на холст"""
        if position is None:
            position = QPoint(50, 50)
        
        # Привязка к сетке
        if self.snap_to_grid:
            position = self.snap_point_to_grid(position)
        
        widget = None
        if widget_type == 'button':
            widget = UIButton(self)
        elif widget_type == 'label':
            widget = UILabel(self)
        elif widget_type == 'progress':
            widget = UIProgressBar(self)
        elif widget_type == 'image':
            widget = UIImageLabel(self)
        
        if widget:
            widget.set_property('x', position.x())
            widget.set_property('y', position.y())
            widget.position_changed.connect(self.on_widget_position_changed)
            widget.size_changed.connect(self.on_widget_size_changed)
            widget.selected.connect(self.on_widget_selected)
            widget.show()
            
            self.widgets.append(widget)
            self.select_widget(widget)
            
            return widget
        
        return None
    
    def remove_widget(self, widget: DraggableWidget):
        """Удаление виджета"""
        if widget in self.widgets:
            self.widgets.remove(widget)
            if self.selected_widget == widget:
                self.selected_widget = None
                self.widget_selected.emit(None)
            widget.deleteLater()
    
    def select_widget(self, widget: DraggableWidget):
        """Выделение виджета"""
        # Предотвращаем рекурсию и ненужные обновления
        if self.selected_widget == widget:
            return
            
        # Снимаем выделение с предыдущего
        if self.selected_widget:
            self.selected_widget.set_selected(False)
        
        # Выделяем новый
        self.selected_widget = widget
        if widget:
            widget.set_selected(True)
        
        self.widget_selected.emit(widget)
        self.update()
    
    def on_widget_position_changed(self, widget, position):
        """Обработка изменения позиции виджета"""
        if self.snap_to_grid:
            snapped_pos = self.snap_point_to_grid(position)
            if snapped_pos != position:
                widget.move(snapped_pos)
                widget.set_property('x', snapped_pos.x())
                widget.set_property('y', snapped_pos.y())
    
    def on_widget_size_changed(self, widget, size):
        """Обработка изменения размера виджета"""
        pass  # Дополнительная логика при необходимости
    
    def on_widget_selected(self, widget):
        """Обработка выделения виджета"""
        # Предотвращаем рекурсию - проверяем, не выделен ли уже этот виджет
        if self.selected_widget != widget:
            self.select_widget(widget)
    
    def snap_point_to_grid(self, point: QPoint) -> QPoint:
        """Привязка точки к сетке"""
        if not self.snap_to_grid:
            return point
        
        snapped_x = round(point.x() / self.grid_size) * self.grid_size
        snapped_y = round(point.y() / self.grid_size) * self.grid_size
        return QPoint(snapped_x, snapped_y)
    
    def show_context_menu(self, position):
        """Показать контекстное меню"""
        menu = QMenu(self)
        
        if self.selected_widget:
            delete_action = QAction("Удалить", self)
            delete_action.triggered.connect(lambda: self.remove_widget(self.selected_widget))
            menu.addAction(delete_action)
            
            copy_action = QAction("Копировать", self)
            copy_action.triggered.connect(self.copy_selected_widget)
            menu.addAction(copy_action)
        
        menu.addSeparator()
        
        grid_action = QAction("Показывать сетку", self)
        grid_action.setCheckable(True)
        grid_action.setChecked(self.show_grid)
        grid_action.toggled.connect(self.toggle_grid)
        menu.addAction(grid_action)
        
        snap_action = QAction("Привязка к сетке", self)
        snap_action.setCheckable(True)
        snap_action.setChecked(self.snap_to_grid)
        snap_action.toggled.connect(self.toggle_snap_to_grid)
        menu.addAction(snap_action)
        
        menu.exec_(self.mapToGlobal(position))
    
    def copy_selected_widget(self):
        """Копирование выделенного виджета"""
        if not self.selected_widget:
            return
        
        # Создаем копию со смещением
        new_position = QPoint(
            self.selected_widget.x() + 20,
            self.selected_widget.y() + 20
        )
        
        new_widget = self.add_widget(self.selected_widget.widget_type, new_position)
        if new_widget:
            # Копируем все свойства кроме позиции
            properties = self.selected_widget.get_all_properties().copy()
            properties['x'] = new_position.x()
            properties['y'] = new_position.y()
            
            for key, value in properties.items():
                new_widget.set_property(key, value)
    
    def toggle_grid(self, show):
        """Переключение отображения сетки"""
        self.show_grid = show
        self.update()
    
    def toggle_snap_to_grid(self, snap):
        """Переключение привязки к сетке"""
        self.snap_to_grid = snap
    
    def mousePressEvent(self, event):
        """Обработка клика по холсту"""
        if event.button() == Qt.LeftButton:
            # Если кликнули не по виджету, снимаем выделение
            widget = self.childAt(event.pos())
            if not isinstance(widget, DraggableWidget):
                self.select_widget(None)
        
        super().mousePressEvent(event)
    
    def paintEvent(self, event):
        """Отрисовка холста"""
        super().paintEvent(event)
        
        if self.show_grid:
            painter = QPainter(self)
            painter.setPen(QPen(QColor(200, 200, 200), 1, Qt.DotLine))
            
            # Рисуем вертикальные линии
            for x in range(0, self.width(), self.grid_size):
                painter.drawLine(x, 0, x, self.height())
            
            # Рисуем горизонтальные линии  
            for y in range(0, self.height(), self.grid_size):
                painter.drawLine(0, y, self.width(), y)
    
    def clear_canvas(self):
        """Очистка холста"""
        widgets_copy = self.widgets.copy()
        for widget in widgets_copy:
            self.remove_widget(widget)
    
    def get_widgets_data(self) -> List[Dict]:
        """Получение данных всех виджетов для сохранения"""
        data = []
        for widget in self.widgets:
            widget_data = {
                'type': widget.widget_type,
                'properties': widget.get_all_properties()
            }
            
            # Дополнительные данные для специальных виджетов
            if isinstance(widget, UIImageLabel):
                widget_data['image_path'] = widget.get_property('image_path')
            
            data.append(widget_data)
        
        return data
    
    def load_widgets_data(self, data: List[Dict]):
        """Загрузка данных виджетов"""
        self.clear_canvas()
        
        for widget_data in data:
            widget = self.add_widget(
                widget_data['type'],
                QPoint(
                    widget_data['properties']['x'],
                    widget_data['properties']['y']
                )
            )
            
            if widget:
                # Устанавливаем все свойства
                for key, value in widget_data['properties'].items():
                    widget.set_property(key, value)
                
                # Специальная обработка для изображений
                if isinstance(widget, UIImageLabel) and 'image_path' in widget_data:
                    widget.set_image(widget_data['image_path'])
        
        # Снимаем выделение
        self.select_widget(None)


class UIEditor(QMainWindow):
    """Главное окно визуального редактора UI"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self.is_modified = False
        self.setup_ui()
        self.connect_signals()
        
        # Автосохранение
        self.autosave_timer = QTimer()
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start(30000)  # Каждые 30 секунд
    
    def setup_ui(self):
        """Настройка интерфейса"""
        self.setWindowTitle("Редактор UI лаунчера")
        self.setGeometry(100, 100, 1400, 800)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Основной лейаут
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Левая панель - инструменты
        left_panel = QVBoxLayout()
        
        self.toolbox = WidgetToolbox()
        left_panel.addWidget(self.toolbox)
        
        # Правая панель - инспектор
        self.inspector = ElementInspector()
        
        # Центральная область - холст
        self.canvas = DesignCanvas()
        
        # Компоновка
        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        left_widget.setFixedWidth(200)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.addWidget(self.inspector)
        right_widget.setLayout(right_layout)
        right_widget.setFixedWidth(300)
        
        main_layout.addWidget(left_widget)
        main_layout.addWidget(self.canvas, 1)
        main_layout.addWidget(right_widget)
        
        # Меню и тулбар
        self.create_menu_bar()
        self.create_toolbar()
        
        # Статусная строка
        self.statusBar().showMessage("Готов к работе")
    
    def create_menu_bar(self):
        """Создание меню"""
        menubar = self.menuBar()
        
        # Файл
        file_menu = menubar.addMenu('Файл')
        
        new_action = QAction('Новый', self)
        new_action.setShortcut('Ctrl+N')
        new_action.triggered.connect(self.new_project)
        file_menu.addAction(new_action)
        
        open_action = QAction('Открыть', self)
        open_action.setShortcut('Ctrl+O')
        open_action.triggered.connect(self.open_project)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        save_action = QAction('Сохранить', self)
        save_action.setShortcut('Ctrl+S')
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)
        
        save_as_action = QAction('Сохранить как...', self)
        save_as_action.setShortcut('Ctrl+Shift+S')
        save_as_action.triggered.connect(self.save_project_as)
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        export_action = QAction('Экспорт в Python', self)
        export_action.triggered.connect(self.export_to_python)
        file_menu.addAction(export_action)
        
        # Редактирование
        edit_menu = menubar.addMenu('Редактирование')
        
        undo_action = QAction('Отменить', self)
        undo_action.setShortcut('Ctrl+Z')
        edit_menu.addAction(undo_action)
        
        redo_action = QAction('Повторить', self)
        redo_action.setShortcut('Ctrl+Y')
        edit_menu.addAction(redo_action)
        
        # Вид
        view_menu = menubar.addMenu('Вид')
        
        grid_action = QAction('Показать сетку', self)
        grid_action.setCheckable(True)
        grid_action.setChecked(True)
        grid_action.toggled.connect(self.canvas.toggle_grid)
        view_menu.addAction(grid_action)
        
        snap_action = QAction('Привязка к сетке', self)
        snap_action.setCheckable(True)
        snap_action.setChecked(True)
        snap_action.toggled.connect(self.canvas.toggle_snap_to_grid)
        view_menu.addAction(snap_action)
    
    def create_toolbar(self):
        """Создание панели инструментов"""
        toolbar = self.addToolBar('Главная')
        
        new_action = QAction(QIcon(), 'Новый', self)
        new_action.triggered.connect(self.new_project)
        toolbar.addAction(new_action)
        
        open_action = QAction(QIcon(), 'Открыть', self)
        open_action.triggered.connect(self.open_project)
        toolbar.addAction(open_action)
        
        save_action = QAction(QIcon(), 'Сохранить', self)
        save_action.triggered.connect(self.save_project)
        toolbar.addAction(save_action)
        
        toolbar.addSeparator()
        
        preview_action = QAction(QIcon(), 'Предварительный просмотр', self)
        preview_action.triggered.connect(self.show_preview)
        toolbar.addAction(preview_action)
    
    def connect_signals(self):
        """Подключение сигналов"""
        self.toolbox.widget_requested.connect(self.add_widget_to_canvas)
        self.canvas.widget_selected.connect(self.inspector.set_widget)
        self.inspector.property_changed.connect(self.on_property_changed)
    
    def add_widget_to_canvas(self, widget_type: str):
        """Добавление виджета на холст"""
        widget = self.canvas.add_widget(widget_type)
        if widget:
            self.set_modified(True)
            self.statusBar().showMessage(f"Добавлен элемент: {widget_type}")
    
    def on_property_changed(self, widget, key, value):
        """Обработка изменения свойства"""
        self.set_modified(True)
        self.statusBar().showMessage(f"Изменено свойство {key}")
    
    def set_modified(self, modified: bool):
        """Установка флага изменений"""
        self.is_modified = modified
        title = "Редактор UI лаунчера"
        if self.current_file:
            title += f" - {os.path.basename(self.current_file)}"
        if modified:
            title += " *"
        self.setWindowTitle(title)
    
    def new_project(self):
        """Новый проект"""
        if self.check_save_changes():
            self.canvas.clear_canvas()
            self.current_file = None
            self.set_modified(False)
            self.statusBar().showMessage("Создан новый проект")
    
    def open_project(self):
        """Открыть проект"""
        if not self.check_save_changes():
            return
        
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(
            self,
            "Открыть проект UI",
            "",
            "UI Projects (*.ui.json)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.canvas.load_widgets_data(data.get('widgets', []))
                self.current_file = file_path
                self.set_modified(False)
                self.statusBar().showMessage(f"Загружен проект: {os.path.basename(file_path)}")
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка загрузки проекта: {e}")
    
    def save_project(self):
        """Сохранить проект"""
        if self.current_file:
            self.save_to_file(self.current_file)
        else:
            self.save_project_as()
    
    def save_project_as(self):
        """Сохранить проект как"""
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getSaveFileName(
            self,
            "Сохранить проект UI",
            "",
            "UI Projects (*.ui.json)"
        )
        
        if file_path:
            if not file_path.endswith('.ui.json'):
                file_path += '.ui.json'
            self.save_to_file(file_path)
    
    def save_to_file(self, file_path: str):
        """Сохранение в файл"""
        try:
            project_data = {
                'version': '1.0',
                'widgets': self.canvas.get_widgets_data(),
                'canvas_settings': {
                    'grid_size': self.canvas.grid_size,
                    'show_grid': self.canvas.show_grid,
                    'snap_to_grid': self.canvas.snap_to_grid
                }
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, indent=2, ensure_ascii=False)
            
            self.current_file = file_path
            self.set_modified(False)
            self.statusBar().showMessage(f"Проект сохранен: {os.path.basename(file_path)}")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка сохранения проекта: {e}")
    
    def autosave(self):
        """Автосохранение"""
        if self.is_modified and self.current_file:
            backup_file = self.current_file + '.backup'
            try:
                self.save_to_file(backup_file)
            except Exception:
                pass
    
    def export_to_python(self):
        """Экспорт в Python код"""
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getSaveFileName(
            self,
            "Экспорт в Python",
            "",
            "Python Files (*.py)"
        )
        
        if file_path:
            try:
                python_code = self.generate_python_code()
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(python_code)
                
                self.statusBar().showMessage(f"Экспорт выполнен: {os.path.basename(file_path)}")
                QMessageBox.information(self, "Экспорт", f"Код успешно экспортирован в {file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка экспорта: {e}")
    
    def generate_python_code(self) -> str:
        """Генерация Python кода"""
        code_lines = [
            "# Автоматически сгенерированный код UI",
            "# Создано с помощью UI Editor",
            "",
            "from PyQt5.QtWidgets import *",
            "from PyQt5.QtCore import Qt",
            "from PyQt5.QtGui import QFont, QPixmap",
            "",
            "class GeneratedUI(QWidget):",
            "    def __init__(self, parent=None):",
            "        super().__init__(parent)",
            "        self.setup_ui()",
            "",
            "    def setup_ui(self):",
        ]
        
        widgets_data = self.canvas.get_widgets_data()
        
        for i, widget_data in enumerate(widgets_data):
            widget_type = widget_data['type']
            props = widget_data['properties']
            var_name = f"{widget_type}_{i}"
            
            # Создание виджета
            if widget_type == 'button':
                code_lines.append(f"        self.{var_name} = QPushButton(self)")
            elif widget_type == 'label':
                code_lines.append(f"        self.{var_name} = QLabel(self)")
            elif widget_type == 'progress':
                code_lines.append(f"        self.{var_name} = QProgressBar(self)")
            elif widget_type == 'image':
                code_lines.append(f"        self.{var_name} = QLabel(self)")
            
            # Установка свойств
            code_lines.append(f"        self.{var_name}.setGeometry({props['x']}, {props['y']}, {props['width']}, {props['height']})")
            
            if 'text' in props and props['text']:
                code_lines.append(f"        self.{var_name}.setText('{props['text']}')")
            
            # Шрифт
            if props.get('font_family') or props.get('font_size'):
                font_family = props.get('font_family', 'Arial')
                font_size = props.get('font_size', 12)
                code_lines.append(f"        self.{var_name}.setFont(QFont('{font_family}', {font_size}))")
            
            # Стили
            style_parts = []
            if props.get('background_color'):
                style_parts.append(f"background-color: {props['background_color']}")
            if props.get('text_color'):
                style_parts.append(f"color: {props['text_color']}")
            if props.get('border_width') and props.get('border_color'):
                style_parts.append(f"border: {props['border_width']}px solid {props['border_color']}")
            if props.get('border_radius'):
                style_parts.append(f"border-radius: {props['border_radius']}px")
            
            if style_parts:
                style_str = "; ".join(style_parts)
                code_lines.append(f"        self.{var_name}.setStyleSheet('{style_str}')")
            
            # Видимость
            if not props.get('visible', True):
                code_lines.append(f"        self.{var_name}.setVisible(False)")
            
            code_lines.append("")
        
        return "\n".join(code_lines)
    
    def show_preview(self):
        """Показать предварительный просмотр"""
        preview_dialog = PreviewDialog(self.canvas.get_widgets_data(), self)
        preview_dialog.exec_()
    
    def check_save_changes(self) -> bool:
        """Проверка необходимости сохранения изменений"""
        if not self.is_modified:
            return True
        
        reply = QMessageBox.question(
            self,
            "Сохранить изменения?",
            "Проект был изменен. Сохранить изменения перед продолжением?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self.save_project()
            return not self.is_modified  # True если сохранение прошло успешно
        elif reply == QMessageBox.No:
            return True
        else:
            return False
    
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        if self.check_save_changes():
            event.accept()
        else:
            event.ignore()


class PreviewDialog(QDialog):
    """Диалог предварительного просмотра"""
    
    def __init__(self, widgets_data: List[Dict], parent=None):
        super().__init__(parent)
        self.widgets_data = widgets_data
        self.setWindowTitle("Предварительный просмотр")
        self.setModal(True)
        self.resize(900, 700)
        self.setup_ui()
    
    def setup_ui(self):
        """Настройка интерфейса"""
        layout = QVBoxLayout()
        
        # Область предварительного просмотра
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        self.preview_widget = QWidget()
        self.preview_widget.setStyleSheet("background-color: white;")
        self.preview_widget.setMinimumSize(800, 600)
        
        # Создаем виджеты для предварительного просмотра
        for widget_data in self.widgets_data:
            self.create_preview_widget(widget_data)
        
        scroll_area.setWidget(self.preview_widget)
        layout.addWidget(scroll_area)
        
        # Кнопки
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept)
        buttons_layout.addWidget(close_button)
        
        layout.addLayout(buttons_layout)
        self.setLayout(layout)
    
    def create_preview_widget(self, widget_data: Dict):
        """Создание виджета для предварительного просмотра"""
        widget_type = widget_data['type']
        props = widget_data['properties']
        
        widget = None
        if widget_type == 'button':
            widget = QPushButton(self.preview_widget)
        elif widget_type == 'label':
            widget = QLabel(self.preview_widget)
        elif widget_type == 'progress':
            widget = QProgressBar(self.preview_widget)
            widget.setValue(50)  # Демонстрационное значение
        elif widget_type == 'image':
            widget = QLabel(self.preview_widget)
            if props.get('image_path') and os.path.exists(props['image_path']):
                pixmap = QPixmap(props['image_path'])
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(
                        props['width'], props['height'],
                        Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    widget.setPixmap(scaled_pixmap)
            else:
                widget.setText("Изображение")
                widget.setAlignment(Qt.AlignCenter)
        
        if widget:
            # Применяем свойства
            widget.setGeometry(props['x'], props['y'], props['width'], props['height'])
            
            if hasattr(widget, 'setText') and 'text' in props:
                widget.setText(props['text'])
            
            # Шрифт
            if props.get('font_family') or props.get('font_size'):
                font = QFont(props.get('font_family', 'Arial'), props.get('font_size', 12))
                widget.setFont(font)
            
            # Стили
            style_parts = []
            if props.get('background_color'):
                style_parts.append(f"background-color: {props['background_color']}")
            if props.get('text_color'):
                style_parts.append(f"color: {props['text_color']}")
            if props.get('border_width') and props.get('border_color'):
                style_parts.append(f"border: {props['border_width']}px solid {props['border_color']}")
            if props.get('border_radius'):
                style_parts.append(f"border-radius: {props['border_radius']}px")
            
            if style_parts:
                widget.setStyleSheet("; ".join(style_parts))
            
            widget.setVisible(props.get('visible', True))
            widget.show()


def launch_ui_editor():
    """Запуск редактора UI"""
    import sys
    
    app = QApplication(sys.argv)
    app.setApplicationName("UI Editor")
    app.setApplicationVersion("1.0")
    
    editor = UIEditor()
    editor.show()
    
    return app.exec_()


if __name__ == '__main__':
    launch_ui_editor()