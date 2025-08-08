"""
Система delta-обновлений для оптимизации загрузок
"""

import os
import json
import hashlib
import logging
import zipfile
import tempfile
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime

try:
    import bsdiff4
    BSDIFF4_AVAILABLE = True
except ImportError:
    BSDIFF4_AVAILABLE = False
    logging.warning("bsdiff4 недоступен - delta-обновления отключены")

logger = logging.getLogger(__name__)

@dataclass
class FileChange:
    """Информация об изменении файла"""
    file_path: str
    change_type: str  # 'add', 'delete', 'modify', 'replace'
    old_hash: Optional[str] = None
    new_hash: Optional[str] = None
    old_size: Optional[int] = None
    new_size: Optional[int] = None
    delta_size: Optional[int] = None
    
    def to_dict(self) -> dict:
        """Преобразование в словарь для JSON"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FileChange':
        """Создание из словаря"""
        return cls(**data)

@dataclass
class DeltaInfo:
    """Информация о delta-пакете"""
    source_version: str
    target_version: str
    delta_size: int
    original_size: int
    compression_ratio: float
    files_count: int
    created_at: str

class DeltaGenerator:
    """Генератор delta-обновлений"""
    
    def __init__(self):
        if not BSDIFF4_AVAILABLE:
            logger.warning("Delta-генератор недоступен без bsdiff4")
    
    def hash_file(self, file_path: str) -> str:
        """Вычисление SHA-256 хеша файла"""
        hasher = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Ошибка хеширования файла {file_path}: {e}")
            return ""
    
    def create_file_manifest(self, directory: str) -> Dict[str, Dict]:
        """Создание манифеста файлов директории"""
        manifest = {}
        try:
            for root, dirs, files in os.walk(directory):
                # Исключаем системные директории
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'logs', 'launcher_data', 'launcher_backups', '__pycache__'}]
                
                for file in files:
                    if file.startswith('.') or file.endswith(('.tmp', '.log', '.pyc')):
                        continue
                    
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, directory)
                    
                    # Нормализуем путь для кроссплатформенности
                    relative_path = relative_path.replace('\\', '/')
                    
                    try:
                        file_hash = self.hash_file(file_path)
                        file_size = os.path.getsize(file_path)
                        
                        manifest[relative_path] = {
                            'hash': file_hash,
                            'size': file_size,
                            'mtime': os.path.getmtime(file_path)
                        }
                    except Exception as e:
                        logger.warning(f"Ошибка обработки файла {file_path}: {e}")
                        continue
            
            logger.info(f"Создан манифест для {len(manifest)} файлов")
            return manifest
            
        except Exception as e:
            logger.error(f"Ошибка создания манифеста: {e}")
            return {}
    
    def compare_manifests(self, old_manifest: Dict, new_manifest: Dict) -> List[FileChange]:
        """Сравнение манифестов для определения изменений"""
        changes = []
        
        try:
            all_files = set(old_manifest.keys()) | set(new_manifest.keys())
            
            for file_path in all_files:
                old_info = old_manifest.get(file_path)
                new_info = new_manifest.get(file_path)
                
                if old_info is None:
                    # Новый файл
                    changes.append(FileChange(
                        file_path=file_path,
                        change_type='add',
                        new_hash=new_info['hash'],
                        new_size=new_info['size']
                    ))
                elif new_info is None:
                    # Удаленный файл
                    changes.append(FileChange(
                        file_path=file_path,
                        change_type='delete',
                        old_hash=old_info['hash'],
                        old_size=old_info['size']
                    ))
                elif old_info['hash'] != new_info['hash']:
                    # Изменённый файл
                    changes.append(FileChange(
                        file_path=file_path,
                        change_type='modify',
                        old_hash=old_info['hash'],
                        new_hash=new_info['hash'],
                        old_size=old_info['size'],
                        new_size=new_info['size']
                    ))
            
            logger.info(f"Найдено изменений: {len(changes)}")
            return changes
            
        except Exception as e:
            logger.error(f"Ошибка сравнения манифестов: {e}")
            return []
    
    def create_binary_delta(self, old_file: str, new_file: str) -> Optional[bytes]:
        """Создание бинарной дельты между двумя файлами"""
        if not BSDIFF4_AVAILABLE:
            return None
        
        try:
            with open(old_file, 'rb') as f:
                old_data = f.read()
            with open(new_file, 'rb') as f:
                new_data = f.read()
            
            # Используем bsdiff4 для создания дельты
            delta = bsdiff4.diff(old_data, new_data)
            
            # Проверяем эффективность дельты
            compression_ratio = len(delta) / len(new_data) if len(new_data) > 0 else 1.0
            
            # Если дельта больше 80% от нового файла, лучше передать полный файл
            if compression_ratio > 0.8:
                logger.debug(f"Дельта неэффективна для {os.path.basename(new_file)}: {compression_ratio:.2f}")
                return None
            
            logger.debug(f"Создана дельта для {os.path.basename(new_file)}: {len(delta)} байт (коэффициент: {compression_ratio:.2f})")
            return delta
            
        except Exception as e:
            logger.error(f"Ошибка создания дельты для {old_file} -> {new_file}: {e}")
            return None
    
    def generate_delta_package(self, old_dir: str, new_dir: str, 
                              old_version: str, new_version: str,
                              output_path: str) -> Optional[DeltaInfo]:
        """Генерация пакета delta-обновления"""
        if not BSDIFF4_AVAILABLE:
            logger.warning("Delta-пакеты недоступны без bsdiff4")
            return None
        
        try:
            logger.info(f"Создание delta-пакета: {old_version} -> {new_version}")
            
            # Создаем манифесты
            old_manifest = self.create_file_manifest(old_dir)
            new_manifest = self.create_file_manifest(new_dir)
            
            if not old_manifest or not new_manifest:
                logger.error("Не удалось создать манифесты")
                return None
            
            # Находим изменения
            changes = self.compare_manifests(old_manifest, new_manifest)
            
            if not changes:
                logger.info("Изменений не найдено")
                return None
            
            total_delta_size = 0
            total_original_size = 0
            processed_files = 0
            
            # Создаем временную директорию для дельт
            with tempfile.TemporaryDirectory() as temp_dir:
                delta_manifest = {
                    'source_version': old_version,
                    'target_version': new_version,
                    'changes': []
                }
                
                for change in changes:
                    try:
                        if change.change_type == 'add':
                            # Для новых файлов копируем полностью
                            source_file = os.path.join(new_dir, change.file_path)
                            if os.path.exists(source_file):
                                dest_path = os.path.join(temp_dir, 'files', change.file_path)
                                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                
                                with open(source_file, 'rb') as src, open(dest_path, 'wb') as dst:
                                    data = src.read()
                                    dst.write(data)
                                    total_delta_size += len(data)
                                    total_original_size += len(data)
                                
                                change.delta_size = change.new_size
                                processed_files += 1
                        
                        elif change.change_type == 'modify':
                            # Для изменённых файлов создаем дельту
                            old_file = os.path.join(old_dir, change.file_path)
                            new_file = os.path.join(new_dir, change.file_path)
                            
                            if os.path.exists(old_file) and os.path.exists(new_file):
                                delta_data = self.create_binary_delta(old_file, new_file)
                                
                                if delta_data:
                                    # Сохраняем дельту
                                    delta_path = os.path.join(temp_dir, 'deltas', f"{change.file_path}.delta")
                                    os.makedirs(os.path.dirname(delta_path), exist_ok=True)
                                    
                                    with open(delta_path, 'wb') as f:
                                        f.write(delta_data)
                                    
                                    change.delta_size = len(delta_data)
                                    total_delta_size += len(delta_data)
                                    total_original_size += change.new_size or 0
                                    processed_files += 1
                                else:
                                    # Если дельта неэффективна, копируем полный файл
                                    dest_path = os.path.join(temp_dir, 'files', change.file_path)
                                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                    
                                    with open(new_file, 'rb') as src, open(dest_path, 'wb') as dst:
                                        data = src.read()
                                        dst.write(data)
                                        total_delta_size += len(data)
                                        total_original_size += len(data)
                                    
                                    change.delta_size = change.new_size
                                    change.change_type = 'replace'  # Помечаем как полная замена
                                    processed_files += 1
                        
                        # Добавляем изменение в манифест (включая удаления)
                        delta_manifest['changes'].append(change.to_dict())
                        
                    except Exception as e:
                        logger.error(f"Ошибка обработки изменения {change.file_path}: {e}")
                        continue
                
                # Сохраняем манифест дельты
                manifest_path = os.path.join(temp_dir, 'delta_manifest.json')
                with open(manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(delta_manifest, f, indent=2, ensure_ascii=False)
                
                # Создаем финальный архив
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as delta_zip:
                    # Добавляем манифест
                    delta_zip.write(manifest_path, 'delta_manifest.json')
                    
                    # Добавляем все файлы из временной директории
                    for root, dirs, files in os.walk(temp_dir):
                        for file in files:
                            if file == 'delta_manifest.json':
                                continue
                            
                            file_path = os.path.join(root, file)
                            arc_path = os.path.relpath(file_path, temp_dir)
                            delta_zip.write(file_path, arc_path)
            
            # Вычисляем коэффициент сжатия
            compression_ratio = total_delta_size / total_original_size if total_original_size > 0 else 0.0
            
            delta_info = DeltaInfo(
                source_version=old_version,
                target_version=new_version,
                delta_size=total_delta_size,
                original_size=total_original_size,
                compression_ratio=compression_ratio,
                files_count=processed_files,
                created_at=datetime.now().isoformat()
            )
            
            logger.info(f"Delta-пакет создан: {output_path}")
            logger.info(f"Размер дельты: {total_delta_size} байт, оригинал: {total_original_size} байт")
            logger.info(f"Коэффициент сжатия: {compression_ratio:.2f}, файлов: {processed_files}")
            
            return delta_info
            
        except Exception as e:
            logger.error(f"Ошибка создания delta-пакета: {e}")
            return None

class DeltaApplier:
    """Применение delta-обновлений"""
    
    def __init__(self):
        self.temp_dir = None
        if not BSDIFF4_AVAILABLE:
            logger.warning("Delta-применение недоступно без bsdiff4")
    
    def apply_binary_delta(self, old_file: str, delta_data: bytes, output_file: str) -> bool:
        """Применение бинарной дельты к файлу"""
        if not BSDIFF4_AVAILABLE:
            return False
        
        try:
            with open(old_file, 'rb') as f:
                old_data = f.read()
            
            # Применяем дельту
            new_data = bsdiff4.patch(old_data, delta_data)
            
            # Записываем результат
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, 'wb') as f:
                f.write(new_data)
            
            logger.debug(f"Дельта применена: {os.path.basename(old_file)} -> {os.path.basename(output_file)}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка применения дельты {old_file}: {e}")
            return False
    
    def apply_delta_package(self, delta_package: str, target_dir: str, 
                           progress_callback=None) -> bool:
        """Применение пакета delta-обновления"""
        if not BSDIFF4_AVAILABLE:
            logger.warning("Применение delta-пакетов недоступно без bsdiff4")
            return False
        
        try:
            logger.info(f"Применение delta-пакета: {delta_package}")
            
            with tempfile.TemporaryDirectory() as temp_dir:
                self.temp_dir = temp_dir
                
                # Извлекаем архив
                with zipfile.ZipFile(delta_package, 'r') as delta_zip:
                    delta_zip.extractall(temp_dir)
                
                # Читаем манифест
                manifest_path = os.path.join(temp_dir, 'delta_manifest.json')
                if not os.path.exists(manifest_path):
                    logger.error("Манифест дельты не найден")
                    return False
                
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    delta_manifest = json.load(f)
                
                changes = [FileChange.from_dict(change) for change in delta_manifest['changes']]
                total_changes = len(changes)
                processed_changes = 0
                
                logger.info(f"Применение {total_changes} изменений")
                
                for change in changes:
                    try:
                        target_file = os.path.join(target_dir, change.file_path)
                        
                        if change.change_type == 'delete':
                            # Удаляем файл
                            if os.path.exists(target_file):
                                os.remove(target_file)
                                logger.debug(f"Удален файл: {change.file_path}")
                        
                        elif change.change_type == 'add' or change.change_type == 'replace':
                            # Копируем новый файл
                            source_file = os.path.join(temp_dir, 'files', change.file_path)
                            if os.path.exists(source_file):
                                os.makedirs(os.path.dirname(target_file), exist_ok=True)
                                with open(source_file, 'rb') as src, open(target_file, 'wb') as dst:
                                    dst.write(src.read())
                                logger.debug(f"Скопирован файл: {change.file_path}")
                        
                        elif change.change_type == 'modify':
                            # Применяем дельту
                            delta_file = os.path.join(temp_dir, 'deltas', f"{change.file_path}.delta")
                            if os.path.exists(delta_file) and os.path.exists(target_file):
                                with open(delta_file, 'rb') as f:
                                    delta_data = f.read()
                                
                                temp_target = f"{target_file}.tmp"
                                if self.apply_binary_delta(target_file, delta_data, temp_target):
                                    os.replace(temp_target, target_file)
                                    logger.debug(f"Применена дельта: {change.file_path}")
                                else:
                                    if os.path.exists(temp_target):
                                        os.remove(temp_target)
                                    raise Exception("Ошибка применения дельты")
                        
                        processed_changes += 1
                        
                        # Обновляем прогресс
                        if progress_callback:
                            progress = int((processed_changes / total_changes) * 100)
                            progress_callback(progress)
                        
                    except Exception as e:
                        logger.error(f"Ошибка применения изменения {change.file_path}: {e}")
                        return False
                
                logger.info(f"Delta-пакет успешно применен: {processed_changes}/{total_changes} изменений")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка применения delta-пакета: {e}")
            return False

# Интеграция с существующей системой обновлений
def is_delta_update_beneficial(old_size: int, new_size: int, delta_size: int) -> bool:
    """Определение эффективности delta-обновления"""
    if old_size == 0 or new_size == 0:
        return False
    
    # Delta эффективна если она меньше 70% от размера нового файла
    return (delta_size / new_size) < 0.7

def create_delta_manifest_entry(file_path: str, delta_info: DeltaInfo) -> dict:
    """Создание записи о delta-обновлении для манифеста"""
    return {
        'type': 'delta',
        'source_version': delta_info.source_version,
        'target_version': delta_info.target_version,
        'delta_size': delta_info.delta_size,
        'original_size': delta_info.original_size,
        'compression_ratio': delta_info.compression_ratio,
        'files_count': delta_info.files_count
    }

# Глобальные экземпляры
_delta_generator = None
_delta_applier = None

def get_delta_generator() -> Optional[DeltaGenerator]:
    """Получение экземпляра генератора дельт"""
    global _delta_generator
    if _delta_generator is None and BSDIFF4_AVAILABLE:
        _delta_generator = DeltaGenerator()
    return _delta_generator

def get_delta_applier() -> Optional[DeltaApplier]:
    """Получение экземпляра применения дельт"""
    global _delta_applier
    if _delta_applier is None and BSDIFF4_AVAILABLE:
        _delta_applier = DeltaApplier()
    return _delta_applier