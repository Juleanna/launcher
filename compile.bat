@echo off
REM Сборка лаунчера через PyInstaller .spec (переносимо, без хардкода путей)
pyinstaller --noconfirm --clean Launcher.spec

REM Альтернативный способ (без .spec), если нужно быстро:
REM pyinstaller --onefile --windowed --icon=images\logo.png Launcher.py

pause
