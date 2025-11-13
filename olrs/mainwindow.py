from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QComboBox, QPushButton, QLineEdit,
    QRadioButton, QButtonGroup, QTableView, QLabel
    )
from PyQt6.QtSql import QSqlQueryModel
from PyQt6.QtCore import pyqtSignal as Signal

from db_manager import DbManager
from source_manager import SourceManager
from config import Language

from indexer import WhooshBackend
from pdf_reader import PDFIndexWorker
from searcher import SearchManager

class SearchWidget(QWidget):
    sig_query = Signal()

    def __init__(self,):
        super().__init__()
        self.setWindowTitle("Search Widget")
        self.resize(1000, 600)

        layout = QVBoxLayout()
        self.setLayout(layout)

        # --- Controls ---
        hbox = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Enter search query...")
        self.language_combo = QComboBox()
        for l in Language:
            self.language_combo.addItem(l.name)
        self.search_btn = QPushButton("Search")

        # --- Search options ---
        self.partial_radio = QRadioButton("Partial")
        self.whole_radio = QRadioButton("Whole-word")
        self.search_option = QButtonGroup()
        self.search_option.addButton(self.partial_radio)
        self.search_option.addButton(self.whole_radio)
        self.partial_radio.setChecked(True)

        hbox.addWidget(self.input)
        hbox.addWidget(self.search_btn)
        hbox.addWidget(self.language_combo)
        hbox.addWidget(self.partial_radio)
        hbox.addWidget(self.whole_radio)
        layout.addLayout(hbox)

        # --- Results view ---
        self.model = QSqlQueryModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        layout.addWidget(self.table)

        # --- Signals ---
        self.search_btn.clicked.connect(self.sig_query)
        # self.table.doubleClicked.connect(self.open_pdf)


class MainWindow(QMainWindow):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.db = DbManager.instance()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.backend = WhooshBackend()
        self.manager = SearchManager(self.backend)

        # --- tabs ---
        self.search_tab = SearchWidget()
        self.source_tab = SourceManager(self.db)

        self.tabs.addTab(self.search_tab, "Search")
        self.tabs.addTab(self.source_tab , "Library")

        self.statusBar().showMessage("Ready.", 7000)

        # --- Signals ---
        self.source_tab.sig_source_added.connect(self.add_pdfs)
        self.search_tab.sig_query.connect(self.do_search)

    def add_pdfs(self, source: dict):
        files = source.get("files")
        lang = source.get("lang")
        self.worker = PDFIndexWorker(self.manager, files, lang)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def do_search(self):
        query = self.search_tab.input.text()
        lang = self.search_tab.language_combo.currentText()
        results = self.manager.search(query, lang)
        print(results)

    def on_progress(self, pdf_path, current_page, total_pages):
        # self.progress_bar.setMaximum(total_pages)
        # self.progress_bar.setValue(current_page)
        print(f"Indexing {pdf_path}: page {current_page}/{total_pages}")

    def on_finished(self, pdf_path):
        print(f"Finished indexing {pdf_path}")
        # self.progress_bar.setValue(0)