import os
import sys
import hashlib
import zipfile
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QVBoxLayout, QPushButton, QLabel, QProgressBar, QWidget, QLineEdit, QMessageBox
from PyQt5.QtCore import Qt, QThread, pyqtSignal

class HashGeneratorThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    
    def __init__(self, directory, output_file, version):
        super().__init__()
        self.directory = directory
        self.output_file = output_file
        self.version = version
    
    def run(self):
        try:
            total_files = sum([len(files) for r, d, files in os.walk(self.directory)])
            if total_files == 0:
                self.finished.emit("Выбранный каталог пуст.")
                return

            processed_files = 0
            zip_filename = f"{self.output_file[:-4]}.zip"  # Меняем расширение файла на .zip
            
            with zipfile.ZipFile(zip_filename, 'w') as zipf:
                with open(self.output_file, 'w', encoding='utf-8') as f:
                    f.write(f"version {self.version}\n")
                    for root, _, files in os.walk(self.directory):
                        for file in files:
                            file_path = os.path.join(root, file)
                            file_size = os.path.getsize(file_path)
                            file_hash = self.hash_file(file_path)
                            relative_path = os.path.relpath(file_path, self.directory)
                            f.write(f"{relative_path} {file_hash} {file_size}\n")
                            zipf.write(file_path, relative_path)  # Добавляем файл в архив
                            
                            processed_files += 1
                            progress_percent = int((processed_files / total_files) * 100)
                            self.progress.emit(progress_percent)
            
            self.finished.emit(f"Файл обновлений с хешами и архив {zip_filename} успешно созданы.")
        except Exception as e:
            self.finished.emit(f"Ошибка: {str(e)}")
    
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
        self.layout.addWidget(self.version_input)
        
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
        
    def select_directory(self):
        self.directory = QFileDialog.getExistingDirectory(self, "Выбрать директорию")
        self.check_ready()
        
    def select_output_file(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        self.output_file, _ = QFileDialog.getSaveFileName(self, "Сохранить файл", "", "Text Files (*.txt);;All Files (*)", options=options)
        self.check_ready()
        
    def check_ready(self):
        if self.directory and self.output_file and self.version_input.text():
            self.generate_button.setEnabled(True)
        
    def generate_update_file(self):
        self.generate_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.thread = HashGeneratorThread(self.directory, self.output_file, self.version_input.text())
        self.thread.progress.connect(self.update_progress)
        self.thread.finished.connect(self.update_status)
        self.thread.start()
    
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
