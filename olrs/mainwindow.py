import re
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QLineEdit, QRadioButton, QButtonGroup, QTableView
    )
from PyQt6.QtSql import QSqlQueryModel
from PyQt6.QtCore import pyqtSignal as Signal

from pyqtspinner import WaitingSpinner

from db_manager import DbManager
from source_manager import SourceManager
from config import SYNONYM_FILE

from indexer import WhooshBackend, BackendManager
from pdf_reader import PDFIndexWorker
from synonym import SynonymManager
from searcher import SearchWidget

from pymupdf_qt_viewer.pymupdfviewer import PdfViewer


class MainWindow(QMainWindow):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.db = DbManager.instance()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.backend = WhooshBackend()
        self.manager = BackendManager(self.backend)

        # --- tabs ---
        self.search_tab = SearchWidget(self.db, self.manager)
        self.source_tab = SourceManager(self.db)
        self.synonym_tab = SynonymManager(SYNONYM_FILE)

        self.tabs.addTab(self.search_tab, "Search")
        self.tabs.addTab(self.source_tab , "Library")
        self.tabs.addTab(self.synonym_tab , "Synonym")

        self.statusBar().showMessage("Ready.", 7000)
        self.waitinspinner = WaitingSpinner(self, True, True)
        
        # --- Signals ---
        self.source_tab.sig_source_added.connect(self.add_pdf)
        self.source_tab.sig_source_removed.connect(self.remove_pdf)
        self.search_tab.sig_open_pdf.connect(self.open_pdf)

    def startSpinner(self, m: str = ""):
        self.statusBar().showMessage(m, 7000)
        self.waitinspinner.start()
        QApplication.processEvents()
    
    def stopSpinner(self, m: str = ""):
        self.waitinspinner.stop()
        self.statusBar().showMessage(m, 7000)

    def add_pdf(self, source: dict):
        self.startSpinner()
        self.worker = PDFIndexWorker(self.manager, [source])
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        # self.worker.finished.connect(self.on_error)
        self.worker.start()

    def remove_pdf(self, filepath):
        self.backend.delete_index(filepath)

    def on_progress(self, pdf_path, current_page, total_pages):
        # self.progress_bar.setMaximum(total_pages)
        # self.progress_bar.setValue(current_page)
        self.statusBar().showMessage(f"Indexing {pdf_path}: page {current_page}/{total_pages}", 7000)

    def on_finished(self, pdf_path):
        self.stopSpinner(f"Finished indexing {pdf_path}")
        # self.progress_bar.setValue(0)

    def open_pdf(self, pdf_path: str, pno: int, query: str, matched_terms: set):
        pdf_viewer = PdfViewer()
        pdf_viewer.loadDocument(pdf_path)

        # Apply highlights if query provided
        if query:
            for term in matched_terms:
                for page in pdf_viewer.fitzdoc:
                    quads = page.search_for(str(term), quads=True)
                    for q in quads:
                        highlight = page.add_highlight_annot(q)
                        highlight.set_colors(stroke=(1, 1, 0))  # yellow
                        highlight.update()

        pdf_viewer.page_navigator.jump(pno)
        pdf_viewer.showMaximized()