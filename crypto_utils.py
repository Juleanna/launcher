"""
Утилиты для криптографической безопасности лаунчера
"""

import os
import json
import hashlib
import hmac
import base64
import logging
import requests
import ssl
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from cryptography.exceptions import InvalidSignature

logger = logging.getLogger(__name__)

class CryptoManager:
    """Менеджер криптографических операций"""
    
    def __init__(self, keys_dir="crypto_keys"):
        self.keys_dir = Path(keys_dir)
        self.keys_dir.mkdir(exist_ok=True)
        self.private_key_path = self.keys_dir / "private_key.pem"
        self.public_key_path = self.keys_dir / "public_key.pem"
        
    def generate_keys(self):
        """Генерация RSA ключей для подписи"""
        try:
            # Генерируем приватный ключ
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            
            # Получаем публичный ключ
            public_key = private_key.public_key()
            
            # Сохраняем приватный ключ
            pem_private = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            with open(self.private_key_path, 'wb') as f:
                f.write(pem_private)
            
            # Сохраняем публичный ключ
            pem_public = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            with open(self.public_key_path, 'wb') as f:
                f.write(pem_public)
                
            logger.info("Криптографические ключи успешно сгенерированы")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка генерации ключей: {e}")
            return False
    
    def load_private_key(self):
        """Загрузка приватного ключа"""
        try:
            if not self.private_key_path.exists():
                logger.warning("Приватный ключ не найден, генерируем новый")
                if not self.generate_keys():
                    return None
            
            with open(self.private_key_path, 'rb') as f:
                private_key = load_pem_private_key(f.read(), password=None)
            
            return private_key
            
        except Exception as e:
            logger.error(f"Ошибка загрузки приватного ключа: {e}")
            return None
    
    def load_public_key(self):
        """Загрузка публичного ключа"""
        try:
            if not self.public_key_path.exists():
                logger.error("Публичный ключ не найден")
                return None
            
            with open(self.public_key_path, 'rb') as f:
                public_key = load_pem_public_key(f.read())
            
            return public_key
            
        except Exception as e:
            logger.error(f"Ошибка загрузки публичного ключа: {e}")
            return None
    
    def sign_file(self, file_path):
        """Создание цифровой подписи файла"""
        try:
            private_key = self.load_private_key()
            if not private_key:
                return None
            
            # Вычисляем хеш файла
            file_hash = self.hash_file(file_path)
            if not file_hash:
                return None
            
            # Создаем подпись
            signature = private_key.sign(
                file_hash.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # Кодируем в base64 для удобства
            signature_b64 = base64.b64encode(signature).decode('utf-8')
            
            logger.info(f"Подпись создана для файла: {file_path}")
            return {
                'file_hash': file_hash,
                'signature': signature_b64,
                'algorithm': 'RSA-PSS-SHA256'
            }
            
        except Exception as e:
            logger.error(f"Ошибка создания подписи для {file_path}: {e}")
            return None
    
    def verify_file_signature(self, file_path, signature_data):
        """Проверка цифровой подписи файла"""
        try:
            public_key = self.load_public_key()
            if not public_key:
                logger.error("Не удалось загрузить публичный ключ для проверки")
                return False
            
            # Проверяем хеш файла
            current_hash = self.hash_file(file_path)
            if current_hash != signature_data.get('file_hash'):
                logger.error(f"Хеш файла не совпадает: {file_path}")
                return False
            
            # Декодируем подпись
            signature = base64.b64decode(signature_data['signature'])
            
            # Проверяем подпись
            public_key.verify(
                signature,
                current_hash.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            logger.info(f"Подпись файла успешно проверена: {file_path}")
            return True
            
        except InvalidSignature:
            logger.error(f"Неверная подпись файла: {file_path}")
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки подписи {file_path}: {e}")
            return False
    
    def hash_file(self, file_path):
        """Вычисление SHA-256 хеша файла"""
        try:
            h = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception as e:
            logger.error(f"Ошибка хеширования файла {file_path}: {e}")
            return None
    
    def create_manifest(self, files_directory, manifest_path):
        """Создание манифеста с подписями всех файлов"""
        try:
            manifest = {
                'version': '1.0',
                'files': {},
                'created_at': str(Path().cwd())
            }
            
            for file_path in Path(files_directory).rglob('*'):
                if file_path.is_file() and not file_path.name.startswith('.'):
                    relative_path = str(file_path.relative_to(files_directory))
                    signature_data = self.sign_file(file_path)
                    
                    if signature_data:
                        manifest['files'][relative_path] = {
                            'size': file_path.stat().st_size,
                            'hash': signature_data['file_hash'],
                            'signature': signature_data['signature'],
                            'algorithm': signature_data['algorithm']
                        }
            
            # Сохраняем манифест
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            
            # Подписываем сам манифест
            manifest_signature = self.sign_file(manifest_path)
            if manifest_signature:
                signature_path = f"{manifest_path}.sig"
                with open(signature_path, 'w', encoding='utf-8') as f:
                    json.dump(manifest_signature, f, indent=2)
            
            logger.info(f"Манифест создан: {manifest_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка создания манифеста: {e}")
            return False
    
    def verify_manifest(self, manifest_path, files_directory=None):
        """Проверка манифеста и всех файлов в нем"""
        try:
            # Проверяем подпись самого манифеста
            signature_path = f"{manifest_path}.sig"
            if os.path.exists(signature_path):
                with open(signature_path, 'r', encoding='utf-8') as f:
                    manifest_signature = json.load(f)
                
                if not self.verify_file_signature(manifest_path, manifest_signature):
                    logger.error("Подпись манифеста недействительна")
                    return False
            
            # Загружаем манифест
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            
            verified_files = 0
            total_files = len(manifest['files'])
            
            for relative_path, file_info in manifest['files'].items():
                if files_directory:
                    full_path = Path(files_directory) / relative_path
                else:
                    full_path = Path(relative_path)
                
                if not full_path.exists():
                    logger.warning(f"Файл не найден: {full_path}")
                    continue
                
                # Проверяем размер файла
                if full_path.stat().st_size != file_info['size']:
                    logger.error(f"Размер файла не совпадает: {full_path}")
                    return False
                
                # Проверяем подпись
                signature_data = {
                    'file_hash': file_info['hash'],
                    'signature': file_info['signature'],
                    'algorithm': file_info['algorithm']
                }
                
                if self.verify_file_signature(full_path, signature_data):
                    verified_files += 1
                else:
                    logger.error(f"Проверка подписи не прошла: {full_path}")
                    return False
            
            logger.info(f"Манифест успешно проверен: {verified_files}/{total_files} файлов")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки манифеста: {e}")
            return False

# Утилиты для интеграции с существующим кодом
def verify_update_integrity(update_archive, manifest_path=None):
    """Проверка целостности архива обновления"""
    crypto_manager = CryptoManager()
    
    if manifest_path and os.path.exists(manifest_path):
        # Проверяем через манифест
        return crypto_manager.verify_manifest(manifest_path)
    else:
        # Проверяем хеш архива
        expected_hash_file = f"{update_archive}.hash"
        if os.path.exists(expected_hash_file):
            with open(expected_hash_file, 'r') as f:
                expected_hash = f.read().strip()
            
            actual_hash = crypto_manager.hash_file(update_archive)
            return actual_hash == expected_hash
    
    logger.warning(f"Не найдены данные для проверки целостности: {update_archive}")
    return False