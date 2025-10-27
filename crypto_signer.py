import json
import base64
import logging
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

logger = logging.getLogger(__name__)


class Signer:
    """Создание пары ключей и подпись файлов/манифеста (офлайн-утилита)."""

    def __init__(self, keys_dir: str = "crypto_keys"):
        self.keys_dir = Path(keys_dir)
        self.keys_dir.mkdir(exist_ok=True)
        self.private_key_path = self.keys_dir / "private_key.pem"
        self.public_key_path = self.keys_dir / "public_key.pem"

    def generate_keys(self) -> bool:
        try:
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            public_key = private_key.public_key()

            pem_private = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            with open(self.private_key_path, 'wb') as f:
                f.write(pem_private)

            pem_public = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            with open(self.public_key_path, 'wb') as f:
                f.write(pem_public)

            logger.info("Сгенерирована пара ключей (private/public)")
            return True
        except Exception as e:
            logger.error(f"Ошибка генерации ключей: {e}")
            return False

    def has_private_key(self) -> bool:
        try:
            return self.private_key_path.exists()
        except Exception:
            return False

    def load_private_key(self):
        try:
            if not self.private_key_path.exists():
                logger.warning("Приватный ключ отсутствует. Сгенерируйте его через generate_keys().")
                return None
            with open(self.private_key_path, 'rb') as f:
                return load_pem_private_key(f.read(), password=None)
        except Exception as e:
            logger.error(f"Ошибка загрузки приватного ключа: {e}")
            return None

    @staticmethod
    def hash_file(file_path: str):
        try:
            import hashlib
            h = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception as e:
            logger.error(f"Ошибка хеширования файла {file_path}: {e}")
            return None

    def sign_file(self, file_path: str):
        try:
            private_key = self.load_private_key()
            if not private_key:
                return None
            file_hash = self.hash_file(file_path)
            if not file_hash:
                return None
            signature = private_key.sign(
                file_hash.encode('utf-8'),
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            return {
                'file_hash': file_hash,
                'signature': base64.b64encode(signature).decode('utf-8'),
                'algorithm': 'RSA-PSS-SHA256',
            }
        except Exception as e:
            logger.error(f"Ошибка подписи файла {file_path}: {e}")
            return None

    def create_manifest(self, files_directory: str, manifest_path: str) -> bool:
        try:
            manifest = {'version': '1.0', 'files': {}, 'created_at': str(Path().cwd())}
            for file_path in Path(files_directory).rglob('*'):
                if file_path.is_file() and not file_path.name.startswith('.'):
                    rel = str(file_path.relative_to(files_directory)).replace('\\', '/')
                    sig = self.sign_file(str(file_path))
                    if sig:
                        manifest['files'][rel] = {
                            'size': file_path.stat().st_size,
                            'hash': sig['file_hash'],
                            'signature': sig['signature'],
                            'algorithm': sig['algorithm'],
                        }
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            logger.info(f"Манифест создан: {manifest_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка создания манифеста: {e}")
            return False
