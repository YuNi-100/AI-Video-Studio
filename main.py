import sys
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow
from app.ui.theme import STYLE

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AI Video Studio")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
