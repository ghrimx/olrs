import sys
import logging
import logging.config
from uuid import uuid4

from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import Qt
from mainwindow import MainWindow

from qt_theme_manager import theme_icon_manager, Theme

logger = logging.getLogger(__name__)


def main() -> int:
    """Initializes the application and runs it.

    Returns:
        int: The exit status code.
    """
    # Initialize the App
    app: QApplication = QApplication(sys.argv)
    app.setOrganizationName("FAMHP")
    app.setOrganizationDomain("famhp.net")
    app.setApplicationName("Olrs")
    app.setStyle("Fusion") 
    app.setWindowIcon(QIcon(":mylogo"))

    if theme_icon_manager.is_dark_mode(app):
        theme_icon_manager.set_theme(Theme.DARK)
    else:
        theme_icon_manager.set_theme(Theme.LIGHT)

    # Splashscreen
    pixmap = QPixmap(":mylogo")
    splash = QSplashScreen(pixmap, Qt.WindowType.WindowStaysOnTopHint)
    splash.show()
    splash.showMessage("Starting ...", Qt.AlignmentFlag.AlignBottom, Qt.GlobalColor.white)

    app.processEvents()

    # Post init configuration
    splash.showMessage("Post Init Config ...", Qt.AlignmentFlag.AlignBottom, Qt.GlobalColor.white)

    app.processEvents()

    # Init logger
    logger.info(f"Current logging level: {logging.getLevelName(logging.root.level)}")

    # Set Taskbar Icon
    try:
        from ctypes import windll
        appid = "fahmp.inspectormate.v1.0"
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
    except ImportError:
        logger.error(ImportError.msg)
        pass

    splash.showMessage("Connecting to the database ...")

    logger.info(f"Starting InspectorMate...")


    # Initialize the main window
    mainwindow: MainWindow = MainWindow()
    mainwindow.show()

    splash.finish(mainwindow)


    return sys.exit(app.exec())

if __name__ == '__main__':
    sys.exit(main())