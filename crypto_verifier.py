import os
import json
import hashlib
import base64
import logging
import requests
from pathlib import Path
from typing import Optional
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature

logger = logging.getLogger(__name__)


class Verifier:
    """Проверка подписи и целостности обновлений (только публичный ключ)."""

    def __init__(self, keys_dir: str = "crypto_keys", public_key_url: Optional[str] = None):
        self.keys_dir = Path(keys_dir)
        self.keys_dir.mkdir(exist_ok=True)
        self.public_key_path = self.keys_dir / "public_key.pem"
        self.cached_public_key_path = self.keys_dir / "cached_public_key.pem"
        self.public_key_url = public_key_url
        self._cached_public_key = None

    def download_public_key(self):
        if not self.public_key_url:
            logger.warning("Не задан URL публичного ключа для загрузки")
            return None
        try:
            resp = requests.get(self.public_key_url, timeout=30, verify=True, headers={'User-Agent': 'GameLauncher/1.0'})
            resp.raise_for_status()
            key_data = resp.text
            if not key_data.startswith('-----BEGIN PUBLIC KEY-----'):
                raise ValueError("Некорректный формат публичного ключа (ожидается PEM)")
            public_key = load_pem_public_key(key_data.encode('utf-8'))
            with open(self.cached_public_key_path, 'w', encoding='utf-8') as f:
                f.write(key_data)
            logger.info("Публичный ключ загружен и закеширован")
            return public_key
        except requests.RequestException as e:
            logger.error(f"Ошибка загрузки публичного ключа: {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка обработки публичного ключа: {e}")
            return None

    def load_public_key(self):
        try:
            if self._cached_public_key:
                return self._cached_public_key
            if self.cached_public_key_path.exists():
                try:
                    with open(self.cached_public_key_path, 'rb') as f:
                        self._cached_public_key = load_pem_public_key(f.read())
                    logger.info("Публичный ключ взят из кеша")
                    return self._cached_public_key
                except Exception as e:
                    logger.warning(f"Ошибка чтения кеша публичного ключа: {e}")
            if self.public_key_path.exists():
                with open(self.public_key_path, 'rb') as f:
                    self._cached_public_key = load_pem_public_key(f.read())
                logger.info("Публичный ключ загружен с диска")
                return self._cached_public_key
            if self.public_key_url:
                self._cached_public_key = self.download_public_key()
                return self._cached_public_key
            logger.error("Публичный ключ недоступен: нет ни локального, ни URL")
            return None
        except Exception as e:
            logger.error(f"Ошибка загрузки публичного ключа: {e}")
            return None

    @staticmethod
    def hash_file(file_path: str) -> Optional[str]:
        try:
            h = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception as e:
            logger.error(f"Ошибка хеширования файла {file_path}: {e}")
            return None

    def verify_file_signature(self, file_path: str, signature_data: dict) -> bool:
        try:
            public_key = self.load_public_key()
            if not public_key:
                logger.error("Публичный ключ отсутствует — проверка невозможна")
                return False
            current_hash = self.hash_file(file_path)
            if current_hash != signature_data.get('file_hash'):
                logger.error(f"Хеш файла не совпадает: {file_path}")
                return False
            signature = base64.b64decode(signature_data['signature'])
            public_key.verify(
                signature,
                current_hash.encode('utf-8'),
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            return True
        except InvalidSignature:
            logger.error(f"Подпись файла недействительна: {file_path}")
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки подписи {file_path}: {e}")
            return False

    def verify_manifest(self, manifest_path: str, files_directory: Optional[str] = None) -> bool:
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            for relative_path, info in manifest.get('files', {}).items():
                full_path = Path(files_directory) / relative_path if files_directory else Path(relative_path)
                if not full_path.exists():
                    logger.warning(f"Файл отсутствует: {full_path}")
                    return False
                if full_path.stat().st_size != info['size']:
                    logger.error(f"Несовпадение размера файла: {full_path}")
                    return False
                signature_data = {
                    'file_hash': info['hash'],
                    'signature': info['signature'],
                    'algorithm': info['algorithm'],
                }
                if not self.verify_file_signature(str(full_path), signature_data):
                    return False
            return True
        except Exception as e:
            logger.error(f"Ошибка проверки манифеста: {e}")
            return False


def verify_update_integrity(update_archive: str, manifest_path: Optional[str] = None, public_key_url: Optional[str] = None) -> bool:
    verifier = Verifier(public_key_url=public_key_url)
    if manifest_path and os.path.exists(manifest_path):
        return verifier.verify_manifest(manifest_path)
    expected_hash_file = f"{update_archive}.hash"
    if os.path.exists(expected_hash_file):
        with open(expected_hash_file, 'r') as f:
            expected_hash = f.read().strip()
        actual_hash = verifier.hash_file(update_archive)
        return actual_hash == expected_hash
    logger.warning(f"Нет доступных данных для проверки целостности: {update_archive}")
    return False


def refresh_public_key(public_key_url: str) -> bool:
    verifier = Verifier(public_key_url=public_key_url)
    if verifier.cached_public_key_path.exists():
        verifier.cached_public_key_path.unlink()
    verifier._cached_public_key = None
    return verifier.download_public_key() is not None
