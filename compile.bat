pyinstaller Launcher.spec

pause

C:\Users\Юля\AppData\Local\Programs\Python\Python312\Lib\site-packages\PyQt5\Qt5\plugins\platforms

cd F:\soft\launcher
F:\python\Scripts\pyinstaller.exe --onefile --windowed --icon=images\logo.png --add-data "C:\PQt5\PyQt5\Qt5\plugins;PyQt5\Qt\plugins" Launcher.py

