"""
Система управления резервными копиями и откат изменений
"""

import os
import json
import zipfile
import logging
import shutil
from datetime import datetime
from typing import List, Optional, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

class BackupManager:
    """Менеджер резервных копий"""
    
    def __init__(self, backup_dir: str = "launcher_backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        self.index_file = self.backup_dir / "backup_index.json"
        self.backups_index = self.load_index()
    
    def load_index(self) -> dict:
        """Загрузка индекса резервных копий"""
        try:
            if self.index_file.exists():
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки индекса резервных копий: {e}")
        return {}
    
    def save_index(self):
        """Сохранение индекса резервных копий"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.backups_index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения индекса резервных копий: {e}")
    
    def create_backup(self, version: str, source_files: List[str], 
                     description: str = "") -> Optional[str]:
        """Создание резервной копии"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"backup_v{version}_{timestamp}.zip"
            backup_path = self.backup_dir / backup_filename
            
            logger.info(f"Создание резервной копии: {backup_filename}")
            
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as backup_zip:
                # Создаем манифест файлов для восстановления
                manifest = {
                    'version': version,
                    'created_at': datetime.now().isoformat(),
                    'files': []
                }
                
                for file_path in source_files:
                    if os.path.exists(file_path):
                        try:
                            # Получаем относительный путь
                            rel_path = os.path.relpath(file_path)
                            file_size = os.path.getsize(file_path)
                            
                            # Добавляем файл в архив
                            backup_zip.write(file_path, rel_path)
                            
                            # Обновляем манифест
                            manifest['files'].append({
                                'path': rel_path,
                                'size': file_size,
                                'original_path': file_path
                            })
                            
                        except Exception as file_error:
                            logger.warning(f"Не удалось добавить файл {file_path}: {file_error}")
                            continue
                
                # Добавляем манифест в архив
                manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
                backup_zip.writestr("backup_manifest.json", manifest_json)
            
            # Обновляем индекс резервных копий
            backup_info = {
                'filename': backup_filename,
                'version': version,
                'created_at': datetime.now().isoformat(),
                'description': description,
                'files_count': len(manifest['files']),
                'size_bytes': os.path.getsize(backup_path)
            }
            
            self.backups_index[version] = backup_info
            self.save_index()
            
            logger.info(f"Резервная копия создана: {backup_filename} "
                       f"({len(manifest['files'])} файлов, "
                       f"{backup_info['size_bytes']} байт)")
            
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"Ошибка создания резервной копии: {e}")
            return None
    
    def list_backups(self) -> List[dict]:
        """Получение списка всех резервных копий"""
        backups = []
        for version, backup_info in self.backups_index.items():
            backup_path = self.backup_dir / backup_info['filename']
            if backup_path.exists():
                backups.append({
                    'version': version,
                    'path': str(backup_path),
                    **backup_info
                })
        
        # Сортируем по дате создания (новые первые)
        backups.sort(key=lambda x: x['created_at'], reverse=True)
        return backups
    
    def get_backup_info(self, version: str) -> Optional[dict]:
        """Получение информации о конкретной резервной копии"""
        if version in self.backups_index:
            backup_info = self.backups_index[version].copy()
            backup_path = self.backup_dir / backup_info['filename']
            if backup_path.exists():
                backup_info['path'] = str(backup_path)
                return backup_info
        return None
    
    def delete_backup(self, version: str) -> bool:
        """Удаление резервной копии"""
        try:
            if version in self.backups_index:
                backup_info = self.backups_index[version]
                backup_path = self.backup_dir / backup_info['filename']
                
                if backup_path.exists():
                    backup_path.unlink()
                
                del self.backups_index[version]
                self.save_index()
                
                logger.info(f"Резервная копия удалена: {version}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка удаления резервной копии {version}: {e}")
        
        return False
    
    def cleanup_old_backups(self, keep_count: int = 10):
        """Очистка старых резервных копий"""
        try:
            backups = self.list_backups()
            if len(backups) > keep_count:
                old_backups = backups[keep_count:]
                for backup in old_backups:
                    self.delete_backup(backup['version'])
                
                logger.info(f"Удалено {len(old_backups)} старых резервных копий")
                
        except Exception as e:
            logger.error(f"Ошибка очистки старых резервных копий: {e}")
    
    def get_storage_stats(self) -> dict:
        """Получение статистики использования места"""
        total_size = 0
        total_files = 0
        backup_count = 0
        
        for backup_info in self.backups_index.values():
            backup_path = self.backup_dir / backup_info['filename']
            if backup_path.exists():
                total_size += backup_info.get('size_bytes', 0)
                total_files += backup_info.get('files_count', 0)
                backup_count += 1
        
        return {
            'backup_count': backup_count,
            'total_files': total_files,
            'total_size_bytes': total_size,
            'backup_directory': str(self.backup_dir)
        }

class RollbackManager:
    """Менеджер отката изменений"""
    
    def __init__(self, backup_manager: BackupManager):
        self.backup_manager = backup_manager
    
    def prepare_rollback(self, version: str, files: List[str]) -> bool:
        """Подготовка отката - создание резервной копии перед обновлением"""
        try:
            return self.backup_manager.create_backup(
                version=version,
                source_files=files,
                description=f"Автоматическая резервная копия перед обновлением"
            ) is not None
        except Exception as e:
            logger.error(f"Ошибка подготовки отката: {e}")
            return False
    
    def perform_rollback(self, target_version: str) -> bool:
        """Выполнение отката к указанной версии"""
        try:
            backup_info = self.backup_manager.get_backup_info(target_version)
            if not backup_info:
                logger.error(f"Резервная копия для версии {target_version} не найдена")
                return False
            
            backup_path = backup_info['path']
            logger.info(f"Начинаем откат к версии {target_version}")
            
            # Извлекаем архив во временную папку
            temp_extract_dir = Path("temp_restore")
            temp_extract_dir.mkdir(exist_ok=True)
            
            try:
                with zipfile.ZipFile(backup_path, 'r') as backup_zip:
                    backup_zip.extractall(temp_extract_dir)
                
                # Читаем манифест
                manifest_path = temp_extract_dir / "backup_manifest.json"
                if not manifest_path.exists():
                    raise Exception("Манифест резервной копии не найден")
                
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                
                # Восстанавливаем файлы
                restored_count = 0
                for file_info in manifest['files']:
                    try:
                        source_path = temp_extract_dir / file_info['path']
                        target_path = file_info['original_path']
                        
                        if source_path.exists():
                            # Создаем директорию если необходимо
                            os.makedirs(os.path.dirname(target_path), exist_ok=True)
                            
                            # Копируем файл
                            shutil.copy2(str(source_path), target_path)
                            restored_count += 1
                            
                            logger.debug(f"Восстановлен файл: {target_path}")
                    
                    except Exception as file_error:
                        logger.warning(f"Не удалось восстановить файл {file_info['path']}: {file_error}")
                        continue
                
                logger.info(f"Откат завершен: восстановлено {restored_count}/{len(manifest['files'])} файлов")
                return restored_count > 0
                
            finally:
                # Удаляем временную папку
                try:
                    shutil.rmtree(temp_extract_dir)
                except Exception as cleanup_error:
                    logger.warning(f"Не удалось очистить временную папку: {cleanup_error}")
            
        except Exception as e:
            logger.error(f"Ошибка отката к версии {target_version}: {e}")
            return False
    
    def get_rollback_options(self) -> List[dict]:
        """Получение списка доступных версий для отката"""
        backups = self.backup_manager.list_backups()
        rollback_options = []
        
        for backup in backups:
            option = {
                'version': backup['version'],
                'created_at': backup['created_at'],
                'description': backup.get('description', ''),
                'files_count': backup.get('files_count', 0),
                'size_mb': round(backup.get('size_bytes', 0) / 1024 / 1024, 2)
            }
            rollback_options.append(option)
        
        return rollback_options
    
    def create_pre_rollback_backup(self, current_version: str, files_to_backup: List[str]) -> bool:
        """Создание резервной копии перед откатом"""
        try:
            backup_path = self.backup_manager.create_backup(
                version=f"{current_version}_pre_rollback",
                source_files=files_to_backup,
                description=f"Автоматическая резервная копия перед откатом"
            )
            
            if backup_path:
                logger.info("Создана резервная копия перед откатом")
                return True
            else:
                logger.warning("Не удалось создать резервную копию перед откатом")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка создания резервной копии перед откатом: {e}")
            return False

# Интеграция с системой обновлений
def create_automatic_backup(version: str, game_directory: str, 
                           backup_manager: BackupManager) -> Optional[str]:
    """Создание автоматической резервной копии перед обновлением"""
    try:
        # Собираем список файлов для резервного копирования
        files_to_backup = []
        
        for root, dirs, files in os.walk(game_directory):
            # Исключаем временные и системные файлы
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                if not file.startswith('.') and not file.endswith('.tmp'):
                    file_path = os.path.join(root, file)
                    files_to_backup.append(file_path)
        
        if files_to_backup:
            return backup_manager.create_backup(
                version=version,
                source_files=files_to_backup,
                description=f"Автоматическая резервная копия перед обновлением до {version}"
            )
        else:
            logger.warning("Нет файлов для создания резервной копии")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка создания автоматической резервной копии: {e}")
        return None

# Глобальные экземпляры
_backup_manager = None
_rollback_manager = None

def get_backup_manager() -> BackupManager:
    """Получение глобального экземпляра менеджера резервных копий"""
    global _backup_manager
    if _backup_manager is None:
        _backup_manager = BackupManager()
    return _backup_manager

def get_rollback_manager() -> RollbackManager:
    """Получение глобального экземпляра менеджера отката"""
    global _rollback_manager
    if _rollback_manager is None:
        _rollback_manager = RollbackManager(get_backup_manager())
    return _rollback_manager