import re
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QLineEdit, QRadioButton, QButtonGroup, QTableView,
    QStatusBar
    )
from PyQt6.QtSql import QSqlQueryModel

from PyQt6Ads import CDockManager, CDockWidget, DockWidgetArea

from pyqtspinner import WaitingSpinner

from db_manager import DbManager
from source_manager import SourceManager
from config import SYNONYM_FILE

from indexer import WhooshBackend, BackendManager
from pdf_reader import PDFIndexWorker
from synonym import SynonymManager
from searcher import SearchWidget

from pymupdf_qt_viewer.pymupdfviewer import PdfViewer

from message_bus import bus

import weakref
from typing import Dict, Optional


class DockRegistry:
    def __init__(self):
        # { "name": weakref to CDockWidget }
        self._widgets: Dict[str, weakref.ReferenceType] = {}

    def register(self, widget: CDockWidget):
        name = widget.objectName()
        self._widgets[name] = weakref.ref(widget)

        # auto-unregister when closed
        widget.closed.connect(lambda: self.unregister(name))

    def unregister(self, name: str):
        if name in self._widgets:
            del self._widgets[name]

    def exists(self, name: str) -> bool:
        return name in self._widgets and self._widgets[name]() is not None

    def get(self, name: str) -> Optional[CDockWidget]:
        ref = self._widgets.get(name)
        if ref is None:
            return None
        return ref()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Open Legal Reference Finder")
        self.db = DbManager.instance()

        CDockManager.setConfigFlag(CDockManager.eConfigFlag.OpaqueSplitterResize, True)
        CDockManager.setConfigFlag(CDockManager.eConfigFlag.XmlCompressionEnabled, False)
        CDockManager.setConfigFlag(CDockManager.eConfigFlag.FocusHighlighting, True)
        CDockManager.setAutoHideConfigFlags(CDockManager.eAutoHideFlag.DefaultAutoHideConfig)
        self.dock_manager = CDockManager(self)
        self.registry = DockRegistry()
        self.central_area = None

        self.backend = WhooshBackend()
        self.manager = BackendManager(self.backend)

        # --- tabs ---
        self.search_tab = SearchWidget(self.db, self.manager)
        self.source_tab = SourceManager(self.db)
        self.synonym_tab = SynonymManager(SYNONYM_FILE)

        self.search_dock_widget = CDockWidget("Search", self)
        self.search_dock_widget.setWidget(self.search_tab)
        self.search_dock_widget.setFeature(CDockWidget.DockWidgetFeature.DockWidgetClosable, False)
        self.left_area = self.dock_manager.addDockWidget(DockWidgetArea.LeftDockWidgetArea, self.search_dock_widget)

        self.source_doc_widget = CDockWidget("Library", self) 
        self.source_doc_widget.setWidget(self.source_tab)
        self.source_doc_widget.setFeature(CDockWidget.DockWidgetFeature.DockWidgetClosable, False)
        self.dock_manager.addDockWidgetTabToArea(self.source_doc_widget, self.left_area)

        self.synonym_dock_widget = CDockWidget("Synonym", self) 
        self.synonym_dock_widget.setWidget(self.synonym_tab)
        self.dock_manager.addDockWidgetTabToArea(self.synonym_dock_widget, self.left_area)

        self.search_dock_widget.setAsCurrentTab()

        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Ready.", 7000)
        self.waitinspinner = WaitingSpinner(self, True, True)
        
        # --- Signals ---
        self.source_tab.sig_source_added.connect(self.add_pdf)
        self.source_tab.sig_open_pdf.connect(self.open_pdf)
        self.source_tab.sig_source_removed.connect(self.remove_pdf)
        self.search_tab.sig_open_pdf.connect(self.open_pdf)
        bus.timedMessage.connect(self.statusbar.showMessage)
        bus.message.connect(self.statusbar.showMessage)

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

    def open_tab(self, name: str, create_fn):

        # If already exists then activate
        if self.registry.exists(name):
            existing = self.registry.get(name)
            existing.setAsCurrentTab()
            return existing

        # Create a new widget
        widget = create_fn()
        widget.setObjectName(name)

        if self.central_area:
            self.dock_manager.addDockWidgetTabToArea(widget, self.central_area)
        else:
           self.central_area = self.dock_manager.addDockWidget(DockWidgetArea.RightDockWidgetArea, widget)

        self.registry.register(widget)
        return widget
    
    def create_pdfviewer(self, doc: dict):
        query = doc.get("query")
        pdf_path = doc.get("path")
        matched_terms = doc.get("terms")
        pno = doc.get("page")
        title = doc.get("title")
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
        # pdf_viewer.showMaximized()

        doc_dock_widget = CDockWidget(title[:15])
        doc_dock_widget.setFeature(CDockWidget.DockWidgetFeature.DockWidgetDeleteOnClose, True)
        doc_dock_widget.closed.connect(self.search_dock_widget.setAsCurrentTab) 
        doc_dock_widget.setWidget(pdf_viewer)
        return doc_dock_widget
        # self.dock_manager.addDockWidgetTabToArea(doc_dock_widget, self.central_area)

    def open_pdf(self, doc: dict, ext = False):
        if not ext:
            pdf_path = doc.get("path")
            dw: CDockWidget = self.open_tab(pdf_path, lambda: self.create_pdfviewer(doc))
            dw.widget().page_navigator.jump(doc.get("page"))

        else:
            print('open externaly')