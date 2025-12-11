import re
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QLineEdit, QRadioButton, QButtonGroup, QTableView,
    QStatusBar
    )
from PyQt6.QtSql import QSqlQueryModel
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl
from PyQt6Ads import CDockManager, CDockWidget, DockWidgetArea, CDockAreaWidget

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
        self.dock_manager.dockWidgetRemoved.connect(self._on_widget_closed)
        self.source_tab.sig_source_added.connect(self.add_pdf)
        self.source_tab.sig_open_pdf.connect(self.open_pdf)
        self.source_tab.sig_source_removed.connect(self.remove_pdf)
        self.search_tab.sig_open_pdf.connect(self.open_pdf)
        bus.timedMessage.connect(self.statusbar.showMessage)
        bus.message.connect(self.statusbar.showMessage)

    def _on_widget_closed(self, widget):
        """ 
        Fix dangling reference of central area
        
        When the last dock widget in an area is closed, the area is deleted.
        Here we reset the reference before the area is destroyed.
        """
        if self.central_area and self.central_area.dockWidgetsCount() == 0:
            self.central_area = None

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

    def open_tab(self, doc: dict):
        pdf_path = doc.get("path")
        title = doc.get("title")

        # If already exists then activate
        if self.registry.exists(pdf_path):
            existing = self.registry.get(pdf_path)
            existing.setAsCurrentTab()
            return existing
        
        # Create a new widget
        pdf_viewer = PdfViewer()
        pdf_viewer.loadDocument(pdf_path)
        widget = CDockWidget(title[:15])
        widget.setFeature(CDockWidget.DockWidgetFeature.DockWidgetDeleteOnClose, True)
        widget.setWidget(pdf_viewer)
        widget.setObjectName(pdf_path)
        widget.closed.connect(self.search_dock_widget.setAsCurrentTab) 

        if self.central_area:
            self.dock_manager.addDockWidgetTabToArea(widget, self.central_area)
        else:
           self.central_area = self.dock_manager.addDockWidget(DockWidgetArea.RightDockWidgetArea, widget)

        self.registry.register(widget)
        return widget
    
    def highlight_terms(self, pdf_viewer: PdfViewer, doc: dict):
        # Apply highlights if query provided
        query = doc.get("query")
        matched_terms = doc.get("terms")
        pno = doc.get("page")
        print(f"highlight page '{pno}': {query}")
        if query:
            page = pdf_viewer.fitzdoc[pno]
            for annot in page.annots():
                if annot.type[0] == 8: 
                    page.delete_annot(annot)
            for term in matched_terms:
                # pdf_viewer.fitzdoc.xref_set_key(page.xref, "Annots", "null") 
                                        
                quads = page.search_for(str(term), quads=True)
                for q in quads:
                    highlight = page.add_highlight_annot(q)
                    highlight.set_colors(stroke=(1, 1, 0))  # yellow
                    highlight.update()

            pdf_viewer.page_navigator.jump(pno)

    def open_pdf(self, doc: dict, ext):
        if ext:
            pdf_path = doc.get("path")
            if pdf_path:
                QDesktopServices.openUrl(QUrl.fromLocalFile(pdf_path))
        else:
            dw: CDockWidget = self.open_tab(doc)
            self.highlight_terms(dw.widget(), doc)