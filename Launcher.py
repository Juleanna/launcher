import sys
import os
import hashlib
import aiohttp
import asyncio
import zipfile
import urllib.request
import re
from PyQt5.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu, QAction, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QPushButton, QWidget, QHBoxLayout, QMessageBox, QProgressBar
from PyQt5.QtCore import QUrl, Qt, QTimer, QThread, pyqtSignal,QPoint
from PyQt5.QtGui import QIcon, QDesktopServices, QPixmap
from PyQt5.uic import loadUi
from configparser import ConfigParser
import requests
import res
from io import BytesIO
from packaging.version import parse as parse_version
import subprocess

class UpdateThread(QThread):
    file_progress = pyqtSignal(int)
    overall_progress = pyqtSignal(int)
    update_finished_launcher = pyqtSignal(bool, str)
    update_finished = pyqtSignal(bool, str)

    def __init__(self, config):
        super().__init__()
        self.config = config

    async def update_launcher(self):
        launcher_update_url = self.config.get('Update', 'launcher_update_url')
        launcher_update_filename = self.config.get('Update', 'launcher_update_filename')

        async with aiohttp.ClientSession() as session:
            try:
                # Проверка необходимости обновления лаунчера
                needs_update, new_launcher_version = await self.check_for_launcher_update()
                if not needs_update:
                    self.update_finished_launcher.emit(True, "Лаунчер уже обновлен до последней версии.")
                    return

                launcher_update_url = os.path.join(launcher_update_url, launcher_update_filename)
                await self.fetch_file(session, launcher_update_url, launcher_update_filename)

                with zipfile.ZipFile(launcher_update_filename, 'r') as zip_ref:
                    zip_ref.extractall()

                # Обновляем версию лаунчера в конфигурации
                self.config.set('Launcher', 'version', new_launcher_version)
                with open('launcher_config.ini', 'w', encoding='utf-8') as configfile:
                    self.config.write(configfile)
                print(f"Launcher version updated to {new_launcher_version}")

                self.update_finished_launcher.emit(True, "Обновление лаунчера завершено успешно!")
            except Exception as e:
                print(f"Launcher update failed: {e}")
                self.update_finished_launcher.emit(False, f"Ошибка обновления лаунчера: {e}")

    async def fetch_file(self, session, url, dest):
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to fetch {url}: HTTP {response.status}")
                file_size = int(response.headers.get('Content-Length', 0))
                with open(dest, 'wb') as f:
                    downloaded_size = 0
                    while True:
                        chunk = await response.content.read(1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        self.file_progress.emit(int((downloaded_size / file_size) * 100))
        except Exception as e:
            print(f"Error fetching file {url}: {e}")
            raise

    def hash_file(self, filepath):
        h = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        return h.hexdigest()
    
    def get_versions_to_update(self, current_version, latest_version):
        current_version = self.extract_version(current_version)
        latest_version = self.extract_version(latest_version)

        if current_version is None or latest_version is None:
            return []

        versions_to_update = []

        while current_version < latest_version:
            current_version = self.increment_version(current_version)
            versions_to_update.append(str(current_version))

        return versions_to_update

    def increment_version(self, version):
        major, minor, micro = version.split('.')
        return '.'.join([major, minor, str(int(micro) + 1)])

    def extract_version(self, version_string):
        version_parts = re.findall(r'\d+\.\d+\.\d+', version_string)
        if version_parts:
            return version_parts[0]
        else:
            return None

    async def update_files(self):
        update_url = self.config.get('Update', 'update_url')
        version_file = self.config.get('Update', 'version_file')
        files_list_prefix = self.config.get('Update', 'files_list_prefix')

        async with aiohttp.ClientSession() as session:
            try:
                version_url = os.path.join(update_url, version_file)
                await self.fetch_file(session, version_url, version_file)

                with open(version_file, 'r', encoding='utf-8') as f:
                    latest_version = f.read().strip()

                current_version = self.config.get('Server', 'version')

                if latest_version != current_version:
                    versions_to_update = self.get_versions_to_update(current_version, latest_version)

                    total_files_to_process = 0
                    processed_files = 0

                    for version in versions_to_update:
                        files_list_prefix_name = f"{files_list_prefix}{version}.txt"
                        files_list_url = os.path.join(update_url, files_list_prefix_name)
                        await self.fetch_file(session, files_list_url, files_list_prefix_name)

                        zip_filename = f"{files_list_prefix}{version}.zip"
                        zip_url = os.path.join(update_url, zip_filename)
                        await self.fetch_file(session, zip_url, zip_filename)

                        with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
                            zip_ref.extractall()

                        files_list = f"{files_list_prefix}{version}.txt"
                        with open(files_list, 'r', encoding='utf-8') as f:
                            lines = f.readlines()

                        total_files = len(lines) - 1
                        total_files_to_process += total_files

                        for line in lines:
                            parts = line.strip().split()
                            if len(parts) != 3:
                                print(f"Skipping invalid line: {line.strip()}")
                                continue

                            file_name, expected_hash, file_size_str = parts
                            try:
                                file_size = int(file_size_str)
                            except ValueError:
                                print(f"Skipping invalid file size: {file_size_str}")
                                continue

                            local_file = os.path.join(os.getcwd(), file_name)

                            if os.path.exists(local_file):
                                local_hash = self.hash_file(local_file)
                                if local_hash == expected_hash:
                                    processed_files += 1

                            self.overall_progress.emit(int((processed_files / total_files_to_process) * 100))

                            self.config.set('Server', 'version', version)
                            with open('launcher_config.ini', 'w', encoding='utf-8') as configfile:
                                self.config.write(configfile)

                    self.update_finished.emit(True, "Обновление завершено успешно!")
                else:
                    self.update_finished.emit(False, "У вас уже установлена последняя версия.")
            except Exception as e:
                print(f"Update failed: {e}")
                self.update_finished.emit(False, f"Ошибка обновления: {e}")

    async def check_for_launcher_update(self):
        update_url = self.config.get('Update', 'update_url')
        version_file = self.config.get('Update', 'version_file')

        async with aiohttp.ClientSession() as session:
            try:
                version_url = os.path.join(update_url, version_file)
                async with session.get(version_url) as response:
                    if response.status != 200:
                        raise Exception(f"Failed to fetch version file: HTTP {response.status}")

                    version_content = await response.text()
                    for line in version_content.splitlines():
                        if line.startswith('LauncherVersion='):
                            latest_version = line.split('=')[1].strip()
                            current_version = self.config.get('Launcher', 'version')

                            if parse_version(latest_version) > parse_version(current_version):
                                return True, latest_version

                    return False, current_version
            except Exception as e:
                print(f"Error checking for launcher update: {e}")
                return False, str(e)


    def run(self):
        needs_update, latest_version = asyncio.run(self.check_for_launcher_update())
        if needs_update:
            print(f"Updating launcher to version {latest_version}")
            asyncio.run(self.update_launcher())
            
        else:
            print(f"No launcher update needed. Current version: {latest_version}")
            asyncio.run(self.update_files())

class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        loadUi('launcher.ui', self)
        
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.oldPos = self.pos()
        self.moving = False

        self.config = ConfigParser()
        self.config.read('launcher_config.ini', encoding='utf-8')

        server_name = self.config.get('Server', 'name')
        version = self.config.get('Server', 'version')
        self.Name_server.setText(server_name)
        self.Version.setText(f"Version: {version}")

        self.Name_server.setStyleSheet("font-size: 14pt; font-weight: 600; color: #ffffff;")
        self.Version.setStyleSheet("color: #ffffff;")

        self.default_button_color = self.config.get('ButtonColors', 'default', fallback='#ffcd00')
        self.active_button_color = self.config.get('ButtonColors', 'active', fallback='#ffffff')
        self.slider_interval = self.config.getint('Slider', 'interval', fallback=5000)

        self.telegram_url = self.config.get('Links', 'telegram')
        self.vk_url = self.config.get('Links', 'vk')
        self.discord_url = self.config.get('Links', 'discord')
        self.website_url = self.config.get('Links', 'website')
        self.facebook_url = self.config.get('Links', 'facebook')
        self.instagram_url = self.config.get('Links', 'instagram')

        icon_path = self.config.get('Icon', 'path')
        self.setWindowIcon(QIcon(icon_path))

        self.Telegram.clicked.connect(self.open_telegram)
        self.VK.clicked.connect(self.open_vk)
        self.Discord.clicked.connect(self.open_discord)
        self.Site.clicked.connect(self.open_website)
        self.Facebook.clicked.connect(self.open_facebook)
        self.Instagram.clicked.connect(self.open_instagram)

        # Настройка иконки в трее
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(icon_path))

        tray_menu = QMenu(self)
        restore_action = QAction("Restore", self)
        quit_action = QAction("Quit", self)
        tray_menu.addAction(restore_action)
        tray_menu.addAction(quit_action)

        restore_action.triggered.connect(self.showNormal)
        quit_action.triggered.connect(QApplication.instance().quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        # Связываем событие нажатия кнопки свертывания в трей с функцией
        self.Minimize.clicked.connect(self.minimize_to_tray)

        self.update_button.setStyleSheet(f"background-color: {self.default_button_color}; color: #000000;")
        self.update_button.setText("Играть")
        self.update_button.clicked.connect(self.toggle_update)

        # Настройка слайдера изображений
        images_folder = self.config.get('Images', 'folder')
        self.image_files = [os.path.join(images_folder, f) for f in os.listdir(images_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]
        self.current_image_index = 0

        self.graphics_view = self.findChild(QGraphicsView, 'Baner')
        self.graphics_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.graphics_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.graphics_view.setStyleSheet("border: none;")  # Убираем бордер
        self.scene = QGraphicsScene()
        self.graphics_view.setScene(self.scene)
    
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.show_next_image)
        self.timer.start(self.slider_interval)  # Используе

        self.is_updating = False
        self.update_thread = UpdateThread(self.config)
        self.update_thread.file_progress.connect(self.update_file_progress)
        self.update_thread.overall_progress.connect(self.update_overall_progress)
        self.update_thread.update_finished_launcher.connect(self.update_finished_launcher)
        self.update_thread.update_finished.connect(self.update_finished)

        # Настройка кнопок для ручного переключения
        self.banner_controls = self.findChild(QWidget, 'BannerControls')
        self.control_layout = self.findChild(QHBoxLayout, 'horizontalLayout')
        self.control_layout.setContentsMargins(0, 0, 0, 0)  # Устанавливаем отступы программно
        self.buttons = []

        for i in range(len(self.image_files)):
            btn = QPushButton(self.banner_controls)
            btn.setFixedSize(10, 10)
            btn.setStyleSheet(f"border-radius: 5px; background-color: {self.default_button_color};")
            btn.clicked.connect(lambda checked, index=i: self.show_image(index))
            self.control_layout.addWidget(btn)
            self.buttons.append(btn)

        self.show_next_image()

        self.update_launcher_on_startup()

    def update_launcher_on_startup(self):
        self.update_thread.start()

    def open_telegram(self):
        QDesktopServices.openUrl(QUrl(self.telegram_url))

    def open_vk(self):
        QDesktopServices.openUrl(QUrl(self.vk_url))

    def open_discord(self):
        QDesktopServices.openUrl(QUrl(self.discord_url))

    def open_website(self):
        QDesktopServices.openUrl(QUrl(self.website_url))

    def open_facebook(self):
        QDesktopServices.openUrl(QUrl(self.facebook_url))

    def open_instagram(self):
        QDesktopServices.openUrl(QUrl(self.instagram_url))

    def show_next_image(self):
        self.show_image(self.current_image_index)
        self.current_image_index = (self.current_image_index + 1) % len(self.image_files)

    def show_image(self, index):
        if self.image_files:
            image_path = self.image_files[index]
            image = QPixmap(image_path)
            image = image.scaled(self.graphics_view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)

            self.scene.clear()
            item = QGraphicsPixmapItem(image)
            self.scene.addItem(item)
            self.scene.setSceneRect(0, 0, self.graphics_view.width(), self.graphics_view.height())

            self.current_image_index = index
            self.update_buttons()

    def toggle_update(self):
        if self.is_updating:
            self.stop_update()
        else:
            self.start_update()

    def update_buttons(self):
        for i, btn in enumerate(self.buttons):
            if i == self.current_image_index:
                btn.setStyleSheet(f"border-radius: 5px; background-color: {self.active_button_color};")
            else:
                btn.setStyleSheet(f"border-radius: 5px; background-color: {self.default_button_color};")


    def start_update(self):
        self.update_thread.start()
        self.update_button.setStyleSheet(f"background-color: {self.active_button_color}; color: #000000;")
        self.update_button.setText("Остановить")
        self.is_updating = True

    def stop_update(self):
        self.update_thread.terminate()
        self.update_button.setStyleSheet(f"background-color: {self.default_button_color}; color: #000000;")
        self.update_button.setText("Играть")
        self.is_updating = False

    def update_file_progress(self, value):
        self.file_progress_bar.setValue(value)

    def update_overall_progress(self, value):
        self.overall_progress_bar.setValue(value)

    def update_finished(self, success, message):
        QMessageBox.information(self, "Обновление завершено", message)
        self.update_button.setStyleSheet(f"background-color: {self.default_button_color}; color: #000000;")
        self.update_button.setText("Играть")
        self.is_updating = False

    def restart_launcher(self):
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def update_finished_launcher(self, success, message):
        self.is_updating = True
        msg_box = QMessageBox()
        msg_box.setWindowTitle("Обновление завершено")
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setStandardButtons(QMessageBox.Ok)
        
        msg_box.buttonClicked.connect(self.restart_launcher)
        msg_box.exec_()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.oldPos = event.globalPos()
            self.moving = True

    def mouseMoveEvent(self, event):
        if self.moving:
            delta = QPoint(event.globalPos() - self.oldPos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.oldPos = event.globalPos()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.moving = False

    def minimize_to_tray(self):
        self.hide()
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.showNormal()
            self.tray_icon.hide()

    def check_launcher_update(self):
        current_launcher_version = self.config.get('Launcher', 'version')
        version_file = 'version.txt'

        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('LauncherVersion='):
                        latest_launcher_version = line.strip().split('=')[1].strip()
                        break
        except Exception as e:
            print(f"Error reading launcher version from {version_file}: {e}")
            return False

        if latest_launcher_version is None:
            print(f"Warning: 'LauncherVersion=' not found in {version_file}")
            return False

        print(f"Current launcher version: {current_launcher_version}")
        print(f"Latest launcher version: {latest_launcher_version}")

        return latest_launcher_version != current_launcher_version


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec_())
