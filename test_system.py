#!/usr/bin/env python3
"""
Скрипт для тестирования системы лаунчера
"""

import sys
import os

def test_imports():
    """Тестирование импортов всех модулей"""
    print("Тестирование импортов модулей...")
    
    modules_to_test = [
        ("crypto_utils", "Криптографические утилиты"),
        ("download_manager", "Менеджер загрузок"), 
        ("backup_manager", "Менеджер резервных копий"),
        ("delta_updates", "Delta-обновления"),
        ("ui_enhancements", "Улучшения UI"),
        ("cache_manager", "Менеджер кеша"),
        ("p2p_distribution", "P2P система"),
        ("cdn_manager", "CDN менеджер"),
        ("bandwidth_optimizer", "Оптимизатор пропускной способности"),
        ("intelligent_load_balancer", "Интеллектуальный балансировщик")
    ]
    
    results = []
    
    for module_name, description in modules_to_test:
        try:
            __import__(module_name)
            print(f"[OK] {description}: OK")
            results.append((module_name, True, None))
        except ImportError as e:
            print(f"[ERROR] {description}: Ошибка импорта - {e}")
            results.append((module_name, False, str(e)))
        except Exception as e:
            print(f"[WARNING] {description}: Другая ошибка - {e}")
            results.append((module_name, False, str(e)))
    
    return results

def test_dependencies():
    """Проверка зависимостей"""
    print("\nПроверка зависимостей...")
    
    dependencies = [
        ("PyQt5", "GUI фреймворк"),
        ("requests", "HTTP клиент"),
        ("aiohttp", "Асинхронный HTTP"),
        ("cryptography", "Криптография"),
        ("bsdiff4", "Delta-обновления"),
        ("aiofiles", "Асинхронная работа с файлами")
    ]
    
    for package, description in dependencies:
        try:
            __import__(package)
            print(f"[OK] {description} ({package}): OK")
        except ImportError:
            print(f"[ERROR] {description} ({package}): НЕ УСТАНОВЛЕН")

def test_configuration():
    """Проверка файлов конфигурации"""
    print("\nПроверка конфигурации...")
    
    config_files = [
        ("launcher_config.ini", False),
        ("launcher_log_config.py", True),
        ("requirements.txt", True),
        ("USER_GUIDE.md", True),
        ("FINAL_IMPROVEMENTS.md", True),
        ("ADVANCED_NETWORK_FEATURES.md", True)
    ]
    
    for filename, required in config_files:
        if os.path.exists(filename):
            print(f"[OK] {filename}: Найден")
        else:
            status = "[ERROR] ОТСУТСТВУЕТ (обязательный)" if required else "[WARNING] Отсутствует (необязательный)"
            print(f"{status}: {filename}")

def test_basic_functionality():
    """Тест базовой функциональности"""
    print("\nТестирование базовой функциональности...")
    
    # Тест системы логирования
    try:
        import launcher_log_config
        print("[OK] Система логирования: OK")
    except Exception as e:
        print(f"[ERROR] Система логирования: {e}")
    
    # Тест кеша
    try:
        from cache_manager import get_cache_manager
        cache = get_cache_manager()
        print("[OK] Менеджер кеша: OK")
    except Exception as e:
        print(f"[ERROR] Менеджер кеша: {e}")
    
    # Тест P2P (без сетевых операций)
    try:
        from p2p_distribution import P2PDistributor
        p2p = P2PDistributor()
        peer_id = p2p.get_peer_id()
        print(f"[OK] P2P система: OK (ID: {peer_id[:8]}...)")
    except Exception as e:
        print(f"[ERROR] P2P система: {e}")

def show_system_info():
    """Показать информацию о системе"""
    print("\nИнформация о системе:")
    print(f"Python версия: {sys.version}")
    print(f"Операционная система: {os.name}")
    print(f"Рабочая директория: {os.getcwd()}")
    print(f"Путь к Python: {sys.executable}")

def main():
    """Главная функция теста"""
    print("Тестирование системы лаунчера")
    print("=" * 50)
    
    show_system_info()
    
    # Основные тесты
    import_results = test_imports()
    test_dependencies() 
    test_configuration()
    test_basic_functionality()
    
    # Итоговый отчет
    print("\n" + "=" * 50)
    print("ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 50)
    
    successful_imports = sum(1 for _, success, _ in import_results if success)
    total_imports = len(import_results)
    
    print(f"Успешные импорты: {successful_imports}/{total_imports}")
    
    if successful_imports == total_imports:
        print("ВСЕ МОДУЛИ ЗАГРУЖЕНЫ УСПЕШНО!")
        print("Система лаунчера готова к работе.")
    elif successful_imports >= total_imports * 0.7:
        print("БОЛЬШИНСТВО МОДУЛЕЙ РАБОТАЕТ")
        print("Основная функциональность доступна.")
        print("Некоторые расширенные функции могут быть недоступны.")
    else:
        print("КРИТИЧЕСКИЕ ОШИБКИ")
        print("Требуется установка зависимостей:")
        print("pip install -r requirements.txt")
    
    print("\nДля запуска лаунчера используйте:")
    print("python Launcher.py")
    
    print("\nДокументация:")
    print("- USER_GUIDE.md - Руководство пользователя")
    print("- ADVANCED_NETWORK_FEATURES.md - Дополнительные функции")
    
    return successful_imports == total_imports

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)