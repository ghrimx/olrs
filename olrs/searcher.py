import re
from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex, QVariant, pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QLineEdit, QRadioButton, QButtonGroup, QTableView
    )

from db_manager import DbManager
from config import EULanguage
from indexer import BackendManager
from common import SearchMode
from message_bus import bus

class SearchResultsModel(QAbstractTableModel):
    def __init__(self, results=None, parent=None):
        super().__init__(parent)
        self._results = results or []

        self._columns = [
            ("Title", "title"),
            ("Short Title", "short_title"),
            ("Page", "page"),
            ("Section", "section"),
            ("Language", "lang"),
            ("Score", "score"),
            ("Path", "path"),
            ("Doc ID", "doc_id"),
        ]

    def rowCount(self, parent=QModelIndex()):
        return len(self._results)

    def columnCount(self, parent=QModelIndex()):
        return len(self._columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return QVariant()

        row = index.row()
        col = index.column()
        field_name = self._columns[col][1]

        value = self._results[row].get(field_name)

        if role == Qt.ItemDataRole.DisplayRole:
            return str(value)
        return QVariant()

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return QVariant()

        if orientation == Qt.Orientation.Horizontal:
            return self._columns[section][0]

        return str(section + 1)

    def get_row(self, row: int):
        """Return the full result dict for a given row."""
        if 0 <= row < len(self._results):
            return self._results[row]
        return None

    def update_results(self, results):
        """Replace model content."""
        self.beginResetModel()
        self._results = results
        self.endResetModel()


class SearchWidget(QWidget):
    sig_query = Signal()
    sig_open_pdf = Signal(object)

    def __init__(self, db: DbManager, manager: BackendManager):
        super().__init__()
        self.setWindowTitle("Search Widget")
        self.db = db
        self.manager = manager

        layout = QVBoxLayout()
        self.setLayout(layout)

        # --- Controls ---
        hbox = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Enter search query...")
        self.language_combo = QComboBox()
        for l in EULanguage:
            self.language_combo.addItem(l.value)
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
        self.model = SearchResultsModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        for i in [4, 6, 7]:
            self.table.hideColumn(i)
        # self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        # --- Signals ---
        # self.search_btn.clicked.connect(self.sig_query)
        self.search_btn.clicked.connect(self.do_search)
        self.table.doubleClicked.connect(self.open_pdf)
        self.input.returnPressed.connect(self.do_search)
    
    def do_search(self):
        query = self.input.text()
        lang = self.language_combo.currentText()
        mode = SearchMode.PARTIAL if self.partial_radio.isChecked() else SearchMode.WHOLE

        results, matched_terms = self.manager.search(query, lang, mode)

        self.matched_terms: set = matched_terms
        all_sources = self.db.all_sources()

        for r in results:
            doc_id = r.get('doc_id').split('#')[0]
            if doc_id in all_sources:
                r['title'] = all_sources.get(doc_id).get('title')
                r['short_title'] = all_sources.get(doc_id).get('short_title')
        self.model.update_results(results)
        self.table.resizeColumnsToContents()
        bus.timedMessage.emit(f"[Results: {len(results)}]", 5000)

    def open_pdf(self, index: QModelIndex):
        path = self.model.data(self.model.index(index.row(), 6))
        page = self.model.data(self.model.index(index.row(), 2))
        title = self.model.data(self.model.index(index.row(), 1)) 
        if title.strip() == "":
            title = self.model.data(self.model.index(index.row(), 0)) 

        try:
            pno = int(page) - 1
        except Exception:
            pno = 0

        # Apply highlights if query provided
        query = self.input.text().strip()
        query_terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2]
        self.matched_terms.add(t for t in query_terms)

        doc = {"path":path, "title":title, "page": pno, "query":query, "terms":self.matched_terms}
        self.sig_open_pdf.emit(doc)




