#!/usr/bin/env python3
"""
Запуск визуального редактора UI для лаунчера
"""

import sys
import os

def main():
    """Главная функция запуска"""
    try:
        # Добавляем текущую директорию в путь Python
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        
        # Импортируем и запускаем UI редактор
        from ui_editor import launch_ui_editor
        
        print("Запуск визуального редактора UI лаунчера...")
        sys.exit(launch_ui_editor())
        
    except ImportError as e:
        print(f"Ошибка импорта: {e}")
        print("Убедитесь, что файл ui_editor.py находится в той же папке")
        sys.exit(1)
        
    except Exception as e:
        print(f"Ошибка запуска редактора: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()