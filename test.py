import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QMessageBox

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("你好窗口")
        self.resize(300, 200)

        button = QPushButton("点击我", self)
        button.setGeometry(100, 80, 100, 40)
        button.clicked.connect(self.show_dialog)

    def show_dialog(self):
        QMessageBox.information(self, "提示", "你好，世界")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
