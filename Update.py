import os
import sys
import hashlib
import zipfile
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QVBoxLayout, QPushButton, QLabel, QProgressBar, QWidget, QLineEdit, QMessageBox, QCheckBox
from PyQt5.QtCore import Qt, QThread, pyqtSignal
try:
    from crypto_signer import Signer as CryptoManager
    CRYPTO_AVAILABLE = True
except ImportError:
    print("Криптографические модули недоступны. Подписи отключены.")
    CRYPTO_AVAILABLE = False
    CryptoManager = None

try:
    from delta_updates import DeltaGenerator
    DELTA_AVAILABLE = True
except ImportError:
    print("Delta-обновления недоступны.")
    DELTA_AVAILABLE = False
    DeltaGenerator = None

class HashGeneratorThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    
    def __init__(self, directory, output_file, version, create_signatures=False):
        super().__init__()
        self.directory = directory
        self.output_file = output_file
        self.version = version
        self.create_signatures = create_signatures
        self.crypto_manager = CryptoManager() if CRYPTO_AVAILABLE and create_signatures else None
    
    def run(self):
        try:
            # Если включена подпись и ключей нет — сгенерировать (только в офлайн-утилите)
            if self.crypto_manager:
                try:
                    from pathlib import Path
                    if not Path(self.crypto_manager.private_key_path).exists():
                        ok = self.crypto_manager.generate_keys()
                        if not ok:
                            self.finished.emit("Не удалось сгенерировать пару ключей для подписи")
                            return
                except Exception:
                    self.finished.emit("Ошибка подготовки ключей для подписи")
                    return
            # Подсчитываем общее количество файлов
            total_files = 0
            for root, dirs, files in os.walk(self.directory):
                # Пропускаем скрытые папки и системные файлы
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                total_files += len([f for f in files if not f.startswith('.') and not f.endswith('.tmp')])
            
            if total_files == 0:
                self.finished.emit("Выбранный каталог пуст или не содержит подходящих файлов.")
                return

            processed_files = 0
            # Создаем имя ZIP файла на основе версии
            base_name = os.path.splitext(os.path.basename(self.output_file))[0]
            if base_name.startswith('files_list'):
                zip_filename = f"{base_name}.zip"
            else:
                zip_filename = f"files_list_v{self.version}.zip"
            
            # Полный путь с учетом директории выходного файла
            output_dir = os.path.dirname(self.output_file)
            if output_dir:
                zip_filename = os.path.join(output_dir, zip_filename)
            else:
                zip_filename = zip_filename
            
            # Используем компрессию для уменьшения размера архива
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
                with open(self.output_file, 'w', encoding='utf-8') as f:
                    f.write(f"version {self.version}\n")
                    
                    for root, dirs, files in os.walk(self.directory):
                        # Пропускаем скрытые папки
                        dirs[:] = [d for d in dirs if not d.startswith('.')]
                        
                        for file in files:
                            # Пропускаем системные и временные файлы
                            if file.startswith('.') or file.endswith('.tmp'):
                                continue
                                
                            file_path = os.path.join(root, file)
                            
                            try:
                                file_size = os.path.getsize(file_path)
                                file_hash = self.hash_file(file_path)
                                relative_path = os.path.relpath(file_path, self.directory)
                                
                                # Нормализуем путь для кроссплатформенности
                                relative_path = relative_path.replace('\\', '/')
                                
                                f.write(f"{relative_path} {file_hash} {file_size}\n")
                                zipf.write(file_path, relative_path)
                                
                                processed_files += 1
                                progress_percent = int((processed_files / total_files) * 100)
                                self.progress.emit(progress_percent)
                                
                            except (OSError, IOError) as e:
                                print(f"Ошибка обработки файла {file_path}: {e}")
                                continue
            
            result_message = f"Файл обновлений с хешами и архив {zip_filename} успешно созданы.\nОбработано файлов: {processed_files}"
            
            # Создаем манифест с подписями
            if self.crypto_manager:
                try:
                    manifest_path = f"{zip_filename}.manifest"
                    if self.crypto_manager.create_manifest(self.directory, manifest_path):
                        result_message += f"\nМанифест с подписями создан: {manifest_path}"
                        
                        # Создаем хеш-файл для архива
                        archive_hash = self.hash_file(zip_filename)
                        hash_file_path = f"{zip_filename}.hash"
                        with open(hash_file_path, 'w') as hf:
                            hf.write(archive_hash)
                        result_message += f"\nХеш-файл создан: {hash_file_path}"
                    else:
                        result_message += "\nОшибка создания манифеста"
                except Exception as e:
                    result_message += f"\nОшибка создания подписей: {e}"
            
            self.finished.emit(result_message)
            
        except Exception as e:
            self.finished.emit(f"Ошибка создания обновления: {str(e)}")
    
    def hash_file(self, filepath):
        try:
            h = hashlib.sha256()
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception as e:
            raise Exception(f"Ошибка хеширования файла {filepath}: {str(e)}")

class UpdateGeneratorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Update Generator")
        self.setGeometry(300, 300, 600, 250)
        
        self.directory = ""
        self.output_file = ""
        
        self.initUI()
        
    def initUI(self):
        self.layout = QVBoxLayout()
        
        self.select_dir_button = QPushButton("Выбрать директорию с файлами")
        self.select_dir_button.clicked.connect(self.select_directory)
        self.layout.addWidget(self.select_dir_button)
        
        self.select_output_button = QPushButton("Выбрать выходной файл")
        self.select_output_button.clicked.connect(self.select_output_file)
        self.layout.addWidget(self.select_output_button)

        self.version_label = QLabel("Версия:")
        self.layout.addWidget(self.version_label)
        
        self.version_input = QLineEdit()
        self.version_input.textChanged.connect(self.check_ready)  # Добавляем связь с проверкой
        self.version_input.textChanged.connect(self.update_output_filename_suggestion)  # Обновляем подсказку
        self.version_input.setPlaceholderText("Например: 1.2.3")
        self.layout.addWidget(self.version_input)
        
        # Чекбокс для создания подписей
        self.create_signatures_checkbox = QCheckBox("Создавать цифровые подписи")
        self.create_signatures_checkbox.setEnabled(CRYPTO_AVAILABLE)
        self.create_signatures_checkbox.setChecked(CRYPTO_AVAILABLE)
        if not CRYPTO_AVAILABLE:
            self.create_signatures_checkbox.setToolTip("Криптографические модули недоступны")
        self.layout.addWidget(self.create_signatures_checkbox)
        
        # Поля для delta-обновлений
        if DELTA_AVAILABLE:
            self.old_version_label = QLabel("Предыдущая версия (для delta):")
            self.layout.addWidget(self.old_version_label)
            
            self.old_version_input = QLineEdit()
            self.old_version_input.setPlaceholderText("Оставьте пустым для обычного обновления")
            self.layout.addWidget(self.old_version_input)
            
            self.old_directory_button = QPushButton("Выбрать старую версию (опционально)")
            self.old_directory_button.clicked.connect(self.select_old_directory)
            self.layout.addWidget(self.old_directory_button)
            
            self.old_directory = ""
        
        self.generate_button = QPushButton("Сгенерировать файл обновлений")
        self.generate_button.clicked.connect(self.generate_update_file)
        self.generate_button.setEnabled(False)
        self.layout.addWidget(self.generate_button)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Статус: Ожидание")
        self.layout.addWidget(self.status_label)
        
               
        container = QWidget()
        container.setLayout(self.layout)
        self.setCentralWidget(container)
        
        # Выполняем начальную проверку готовности
        self.check_ready()
        
    def select_directory(self):
        self.directory = QFileDialog.getExistingDirectory(self, "Выбрать директорию (новая версия)")
        self.check_ready()
    
    def select_old_directory(self):
        if DELTA_AVAILABLE:
            self.old_directory = QFileDialog.getExistingDirectory(self, "Выбрать директорию (старая версия)")
            self.check_ready()  # Проверяем готовность после выбора старой версии
        
    def select_output_file(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        
        # Предлагаем имя файла на основе версии
        version = self.version_input.text().strip()
        suggested_name = f"files_list_v{version}.txt" if version else "files_list.txt"
        
        self.output_file, _ = QFileDialog.getSaveFileName(
            self, "Сохранить файл", suggested_name, 
            "Text Files (*.txt);;All Files (*)", options=options
        )
        self.check_ready()
        
    def check_ready(self):
        # Основные требования: директория, выходной файл и версия
        ready = bool(self.directory and self.output_file and self.version_input.text().strip())
        
        self.generate_button.setEnabled(ready)
        
        # Обновляем статус
        if ready:
            self.status_label.setText("Статус: Готов к генерации")
        else:
            missing = []
            if not self.directory:
                missing.append("директория")
            if not self.output_file:
                missing.append("выходной файл")
            if not self.version_input.text().strip():
                missing.append("версия")
            
            self.status_label.setText(f"Статус: Не хватает - {', '.join(missing)}")
    
    def update_output_filename_suggestion(self):
        """Обновление предложения имени файла при изменении версии"""
        version = self.version_input.text().strip()
        if version and hasattr(self, 'select_output_button'):
            self.select_output_button.setText(f"Выбрать выходной файл (files_list_v{version}.txt)")
        
    def generate_update_file(self):
        self.generate_button.setEnabled(False)
        self.progress_bar.setValue(0)
        create_sigs = self.create_signatures_checkbox.isChecked()
        
        # Проверяем, нужно ли создать delta-обновление
        create_delta = (DELTA_AVAILABLE and hasattr(self, 'old_directory') and 
                       self.old_directory and hasattr(self, 'old_version_input') and 
                       self.old_version_input.text().strip())
        
        if create_delta:
            old_version = self.old_version_input.text().strip()
            new_version = self.version_input.text().strip()
            
            # Создаем delta-обновление
            self.create_delta_update(old_version, new_version)
        else:
            # Обычное обновление
            self.thread = HashGeneratorThread(self.directory, self.output_file, self.version_input.text(), create_sigs)
            self.thread.progress.connect(self.update_progress)
            self.thread.finished.connect(self.update_status)
            self.thread.start()
    
    def create_delta_update(self, old_version, new_version):
        """Создание delta-обновления"""
        try:
            self.status_label.setText("Статус: Создание delta-обновления...")
            
            delta_generator = DeltaGenerator()
            
            # Создаем имя для delta-пакета
            base_name = os.path.splitext(self.output_file)[0]
            delta_output = f"{base_name}_delta_{old_version}_to_{new_version}.zip"
            
            self.progress_bar.setValue(10)
            
            # Генерируем delta-пакет
            delta_info = delta_generator.generate_delta_package(
                old_dir=self.old_directory,
                new_dir=self.directory,
                old_version=old_version,
                new_version=new_version,
                output_path=delta_output
            )
            
            self.progress_bar.setValue(90)
            
            if delta_info:
                message = f"Delta-обновление создано: {delta_output}\n"
                message += f"Размер delta: {delta_info.delta_size} байт\n"
                message += f"Оригинальный размер: {delta_info.original_size} байт\n"
                message += f"Коэффициент сжатия: {delta_info.compression_ratio:.2f}\n"
                message += f"Файлов обработано: {delta_info.files_count}"
                
                # Также создаем обычное обновление
                create_sigs = self.create_signatures_checkbox.isChecked()
                self.thread = HashGeneratorThread(self.directory, self.output_file, new_version, create_sigs)
                self.thread.progress.connect(self.update_progress)
                self.thread.finished.connect(lambda msg: self.update_status(message + "\n\n" + msg))
                self.thread.start()
            else:
                self.update_status("Ошибка создания delta-обновления")
                self.generate_button.setEnabled(True)
            
            self.progress_bar.setValue(100)
            
        except Exception as e:
            error_message = f"Ошибка создания delta-обновления: {str(e)}"
            self.update_status(error_message)
            self.generate_button.setEnabled(True)
            QMessageBox.critical(self, "Ошибка", error_message)
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
        
    def update_status(self, message):
        self.status_label.setText(f"Статус: {message}")
        self.generate_button.setEnabled(True)
        QMessageBox.information(self, "Информация", message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UpdateGeneratorApp()
    window.show()
    sys.exit(app.exec_())

