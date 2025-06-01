import sys
from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt
from ui_launcher import Ui_LauncherWindow

class Launcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_LauncherWindow()  # Create an instance of the Ui_LauncherWindow class
        self.ui.setupUi(self)  # Set up the user interface
        self.setWindowTitle("Launcher")  # Set window title
        self.setWindowIcon(QIcon("assets/icons/download.png"))  # Set window icon
        
       
        self.show()  # Display the main window

    def select_files(self):
        # Method to handle the "Download" button click
        pass

    def update(self):
        # Method to handle the "Update" button click
        pass

    def open_settings_dialog(self):
        # Method to open the settings dialog window
        pass

    def clear_download_list(self):
        # Method to clear the download list
        pass

    def mousePressEvent(self, event):
        # Handle mouse press event to enable window dragging
        if event.button() == Qt.LeftButton:
            self.dragPos = event.globalPos()
            event.accept()

    def mouseMoveEvent(self, event):
        # Handle mouse move event for window dragging
        if event.buttons() == Qt.LeftButton:
            self.move(self.pos() + event.globalPos() - self.dragPos)
            self.dragPos = event.globalPos()
            event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    launcher = Launcher()
    sys.exit(app.exec_())
