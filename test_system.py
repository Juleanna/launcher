#!/usr/bin/env python3
"""
РЎРєСЂРёРїС‚ РґР»СЏ С‚РµСЃС‚РёСЂРѕРІР°РЅРёСЏ СЃРёСЃС‚РµРјС‹ Р»Р°СѓРЅС‡РµСЂР°
"""

import sys
import os

def test_imports():
    """РўРµСЃС‚РёСЂРѕРІР°РЅРёРµ РёРјРїРѕСЂС‚РѕРІ РІСЃРµС… РјРѕРґСѓР»РµР№"""
    print("РўРµСЃС‚РёСЂРѕРІР°РЅРёРµ РёРјРїРѕСЂС‚РѕРІ РјРѕРґСѓР»РµР№...")
    
    modules_to_test = [
        ("crypto_verifier", "Проверка подписей (клиент)"),
        ("crypto_signer", "Подпись и генерация ключей (офлайн)"),
        ("download_manager", "Менеджер загрузок"), 
        ("backup_manager", "Резервные копии/откат"),
        ("delta_updates", "Delta-обновления"),
        ("ui_enhancements", "Улучшения UI"),
        ("cache_manager", "Кэш"),
        ("p2p_distribution", "P2P распределение"),
        ("cdn_manager", "CDN менеджер"),
        ("bandwidth_optimizer", "Оптимизация пропускной способности"),
        ("intelligent_load_balancer", "Интеллектуальный балансировщик")
    ]
    
    results = []
    
    for module_name, description in modules_to_test:
        try:
            __import__(module_name)
            print(f"[OK] {description}: OK")
            results.append((module_name, True, None))
        except ImportError as e:
            print(f"[ERROR] {description}: РћС€РёР±РєР° РёРјРїРѕСЂС‚Р° - {e}")
            results.append((module_name, False, str(e)))
        except Exception as e:
            print(f"[WARNING] {description}: Р”СЂСѓРіР°СЏ РѕС€РёР±РєР° - {e}")
            results.append((module_name, False, str(e)))
    
    return results

def test_dependencies():
    """РџСЂРѕРІРµСЂРєР° Р·Р°РІРёСЃРёРјРѕСЃС‚РµР№"""
    print("\nРџСЂРѕРІРµСЂРєР° Р·Р°РІРёСЃРёРјРѕСЃС‚РµР№...")
    
    dependencies = [
        ("PyQt5", "GUI С„СЂРµР№РјРІРѕСЂРє"),
        ("requests", "HTTP РєР»РёРµРЅС‚"),
        ("aiohttp", "РђСЃРёРЅС…СЂРѕРЅРЅС‹Р№ HTTP"),
        ("cryptography", "РљСЂРёРїС‚РѕРіСЂР°С„РёСЏ"),
        ("bsdiff4", "Delta-РѕР±РЅРѕРІР»РµРЅРёСЏ"),
        ("aiofiles", "РђСЃРёРЅС…СЂРѕРЅРЅР°СЏ СЂР°Р±РѕС‚Р° СЃ С„Р°Р№Р»Р°РјРё")
    ]
    
    for package, description in dependencies:
        try:
            __import__(package)
            print(f"[OK] {description} ({package}): OK")
        except ImportError:
            print(f"[ERROR] {description} ({package}): РќР• РЈРЎРўРђРќРћР’Р›Р•Рќ")

def test_configuration():
    """РџСЂРѕРІРµСЂРєР° С„Р°Р№Р»РѕРІ РєРѕРЅС„РёРіСѓСЂР°С†РёРё"""
    print("\nРџСЂРѕРІРµСЂРєР° РєРѕРЅС„РёРіСѓСЂР°С†РёРё...")
    
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
            print(f"[OK] {filename}: РќР°Р№РґРµРЅ")
        else:
            status = "[ERROR] РћРўРЎРЈРўРЎРўР’РЈР•Рў (РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Р№)" if required else "[WARNING] РћС‚СЃСѓС‚СЃС‚РІСѓРµС‚ (РЅРµРѕР±СЏР·Р°С‚РµР»СЊРЅС‹Р№)"
            print(f"{status}: {filename}")

def test_basic_functionality():
    """РўРµСЃС‚ Р±Р°Р·РѕРІРѕР№ С„СѓРЅРєС†РёРѕРЅР°Р»СЊРЅРѕСЃС‚Рё"""
    print("\nРўРµСЃС‚РёСЂРѕРІР°РЅРёРµ Р±Р°Р·РѕРІРѕР№ С„СѓРЅРєС†РёРѕРЅР°Р»СЊРЅРѕСЃС‚Рё...")
    
    # РўРµСЃС‚ СЃРёСЃС‚РµРјС‹ Р»РѕРіРёСЂРѕРІР°РЅРёСЏ
    try:
        import launcher_log_config
        print("[OK] РЎРёСЃС‚РµРјР° Р»РѕРіРёСЂРѕРІР°РЅРёСЏ: OK")
    except Exception as e:
        print(f"[ERROR] РЎРёСЃС‚РµРјР° Р»РѕРіРёСЂРѕРІР°РЅРёСЏ: {e}")
    
    # РўРµСЃС‚ РєРµС€Р°
    try:
        from cache_manager import get_cache_manager
        cache = get_cache_manager()
        print("[OK] РњРµРЅРµРґР¶РµСЂ РєРµС€Р°: OK")
    except Exception as e:
        print(f"[ERROR] РњРµРЅРµРґР¶РµСЂ РєРµС€Р°: {e}")
    
    # РўРµСЃС‚ P2P (Р±РµР· СЃРµС‚РµРІС‹С… РѕРїРµСЂР°С†РёР№)
    try:
        from p2p_distribution import P2PDistributor
        p2p = P2PDistributor()
        peer_id = p2p.get_peer_id()
        print(f"[OK] P2P СЃРёСЃС‚РµРјР°: OK (ID: {peer_id[:8]}...)")
    except Exception as e:
        print(f"[ERROR] P2P СЃРёСЃС‚РµРјР°: {e}")

def show_system_info():
    """РџРѕРєР°Р·Р°С‚СЊ РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ СЃРёСЃС‚РµРјРµ"""
    print("\nРРЅС„РѕСЂРјР°С†РёСЏ Рѕ СЃРёСЃС‚РµРјРµ:")
    print(f"Python РІРµСЂСЃРёСЏ: {sys.version}")
    print(f"РћРїРµСЂР°С†РёРѕРЅРЅР°СЏ СЃРёСЃС‚РµРјР°: {os.name}")
    print(f"Р Р°Р±РѕС‡Р°СЏ РґРёСЂРµРєС‚РѕСЂРёСЏ: {os.getcwd()}")
    print(f"РџСѓС‚СЊ Рє Python: {sys.executable}")

def main():
    """Р“Р»Р°РІРЅР°СЏ С„СѓРЅРєС†РёСЏ С‚РµСЃС‚Р°"""
    print("РўРµСЃС‚РёСЂРѕРІР°РЅРёРµ СЃРёСЃС‚РµРјС‹ Р»Р°СѓРЅС‡РµСЂР°")
    print("=" * 50)
    
    show_system_info()
    
    # РћСЃРЅРѕРІРЅС‹Рµ С‚РµСЃС‚С‹
    import_results = test_imports()
    test_dependencies() 
    test_configuration()
    test_basic_functionality()
    
    # РС‚РѕРіРѕРІС‹Р№ РѕС‚С‡РµС‚
    print("\n" + "=" * 50)
    print("РРўРћР“РћР’Р«Р™ РћРўР§Р•Рў")
    print("=" * 50)
    
    successful_imports = sum(1 for _, success, _ in import_results if success)
    total_imports = len(import_results)
    
    print(f"РЈСЃРїРµС€РЅС‹Рµ РёРјРїРѕСЂС‚С‹: {successful_imports}/{total_imports}")
    
    if successful_imports == total_imports:
        print("Р’РЎР• РњРћР”РЈР›Р Р—РђР“Р РЈР–Р•РќР« РЈРЎРџР•РЁРќРћ!")
        print("РЎРёСЃС‚РµРјР° Р»Р°СѓРЅС‡РµСЂР° РіРѕС‚РѕРІР° Рє СЂР°Р±РѕС‚Рµ.")
    elif successful_imports >= total_imports * 0.7:
        print("Р‘РћР›Р¬РЁРРќРЎРўР’Рћ РњРћР”РЈР›Р•Р™ Р РђР‘РћРўРђР•Рў")
        print("РћСЃРЅРѕРІРЅР°СЏ С„СѓРЅРєС†РёРѕРЅР°Р»СЊРЅРѕСЃС‚СЊ РґРѕСЃС‚СѓРїРЅР°.")
        print("РќРµРєРѕС‚РѕСЂС‹Рµ СЂР°СЃС€РёСЂРµРЅРЅС‹Рµ С„СѓРЅРєС†РёРё РјРѕРіСѓС‚ Р±С‹С‚СЊ РЅРµРґРѕСЃС‚СѓРїРЅС‹.")
    else:
        print("РљР РРўРР§Р•РЎРљРР• РћРЁРР‘РљР")
        print("РўСЂРµР±СѓРµС‚СЃСЏ СѓСЃС‚Р°РЅРѕРІРєР° Р·Р°РІРёСЃРёРјРѕСЃС‚РµР№:")
        print("pip install -r requirements.txt")
    
    print("\nР”Р»СЏ Р·Р°РїСѓСЃРєР° Р»Р°СѓРЅС‡РµСЂР° РёСЃРїРѕР»СЊР·СѓР№С‚Рµ:")
    print("python Launcher.py")
    
    print("\nР”РѕРєСѓРјРµРЅС‚Р°С†РёСЏ:")
    print("- USER_GUIDE.md - Р СѓРєРѕРІРѕРґСЃС‚РІРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ")
    print("- ADVANCED_NETWORK_FEATURES.md - Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅС‹Рµ С„СѓРЅРєС†РёРё")
    
    return successful_imports == total_imports

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

