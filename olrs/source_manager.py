import shutil
import logging
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QFileDialog,
                             QTableView, QLabel, QMessageBox, QFormLayout, QDialog, QDialogButtonBox,
                             QProgressDialog, QComboBox)
from PyQt6.QtSql import QSqlTableModel
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import Qt, QTimer, pyqtSignal as Signal
import pymupdf

from pdf_reader import PDFIndexWorker

from config import DATA_DIR, EULanguage
from db_manager import DbManager

logger = logging.getLogger(__name__)



class AddSourceDialog(QDialog):
    sig_source_added = Signal(object)

    def __init__(self, db: DbManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Add New Source")
        self.setMinimumWidth(400)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Form fields
        form = QFormLayout()

        self.file_edit = QLineEdit()
        self.file_btn = QPushButton("Browse...")
        self.file_btn.clicked.connect(self.select_file)
        file_box = QHBoxLayout()
        file_box.addWidget(self.file_edit)
        file_box.addWidget(self.file_btn)
        form.addRow("PDF File:", file_box)

        self.title_edit = QLineEdit()
        form.addRow("Title:", self.title_edit)

        self.short_edit = QLineEdit()
        form.addRow("Short Title:", self.short_edit)

        self.url_edit = QLineEdit()
        form.addRow("URL:", self.url_edit)

        self.ref_edit = QLineEdit()
        form.addRow("Reference:", self.ref_edit)

        self.language_combo = QComboBox()
        for l in EULanguage:
            self.language_combo.addItem(l.value)

        form.addRow("Language:", self.language_combo)

        self.page_label = QLabel("—")
        form.addRow("Page count:", self.page_label)

        layout.addLayout(form)

        # OK / Cancel buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.pdf_path = None
        self.page_count = 0

    # --- Handlers ---

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select PDF Source", "", "PDF Files (*.pdf)"
        )
        if not path:
            return
        self.pdf_path = Path(path)
        self.file_edit.setText(str(self.pdf_path))

        try:
            with pymupdf.open(self.pdf_path) as doc:
                self.page_count = len(doc)
            self.page_label.setText(str(self.page_count))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open PDF:\n{e}")
            self.page_label.setText("—")

    # --- Validation and DB insert ---

    def accept(self):
        if not self.pdf_path:
            QMessageBox.warning(self, "Missing file", "Please select a PDF file.")
            return

        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing title", "Please enter a title.")
            return

        short_title = self.short_edit.text().strip()
        url = self.url_edit.text().strip() or None
        reference = self.ref_edit.text().strip() or None
        language = self.language_combo.currentText()

        # Source path
        source = self.pdf_path
        destination = DATA_DIR.joinpath(source.name)

        try:
            shutil.copy2(source, destination)
        except shutil.SameFileError:
            logger.error("Source and destination represents the same file.")
            return
        except PermissionError:
            logger.error("Permission denied.")
            return
        except Exception as e:
            logger.error(f"Error occurred while copying file. err={e}")
            return
        else:
            logger.info("File copied successfully.")

        # Insert into DB
        try:
            self.new_id = self.db.insert_source(
                filename=self.pdf_path.name,
                title=title,
                short_title=short_title or title[:20],
                url=url,
                reference=reference,
                page_count=self.page_count,
                language=language
            )
            QMessageBox.information(self, "Added", f"Source added (ID {self.new_id})")
        except Exception as e:
            QMessageBox.critical(self, "Database error", str(e))
            return
        else:
            self.sig_source_added.emit({"doc_id": self.new_id, "path": destination.as_posix(), "lang": language})
            super().accept()

        

class SourceManager(QWidget):
    sig_source_added = Signal(object)
    sig_source_removed = Signal(object)

    def __init__(self, db: DbManager):
        super().__init__()
        self.db = db
        self.reindex_queue = []
        self.current_worker = None
        self.progress_dialog = None

        layout = QVBoxLayout()
        self.setLayout(layout)

        # --- Controls ---
        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.save_btn = QPushButton("Save Changes")
        self.delete_btn = QPushButton("Delete Selected")
        self.add_btn = QPushButton("Add Source")
        self.reindex_button = QPushButton("Reindex Selected")

        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.reindex_button)
        layout.addLayout(btn_layout)

        # --- Table ---
        self.model = QSqlTableModel(self, db.db)
        self.model.setTable("sources")
        self.model.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit)
        self.model.select()

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.resizeColumnsToContents()
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        # --- Signals ---
        self.add_btn.clicked.connect(self.add_source)
        self.refresh_btn.clicked.connect(self.refresh)
        self.save_btn.clicked.connect(self.save_changes)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.reindex_button.clicked.connect(self.index_source)

    def add_source(self):
        dlg = AddSourceDialog(self.db, self)
        dlg.sig_source_added.connect(self.sig_source_added)
        if dlg.exec():
            self.model.select()  # Refresh view after insertion
            self.table.resizeColumnsToContents()

    def refresh(self):
        self.model.select()

    def save_changes(self):
        if not self.model.submitAll():
            QMessageBox.critical(self, "Error", self.model.lastError().text())
        else:
            QMessageBox.information(self, "Saved", "All changes saved successfully.")

    def delete_selected(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Select at least one source to delete.")
            return

        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {len(selected)} source(s) and their related documents?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        for index in selected:
            source_id = self.model.data(self.model.index(index.row(), 0))
            q = self.db.db.exec(f"DELETE FROM vectors WHERE source_id = {source_id}")
            self.model.removeRow(index.row())

            filename = self.model.data(self.model.index(index.row(), 1))
            filepath = DATA_DIR.joinpath(filename)
            import os
            os.remove(filepath)
            self.sig_source_removed.emit(filepath)

        if not self.model.submitAll():
            QMessageBox.critical(self, "Error", self.model.lastError().text())
        else:
            self.db.db.exec("VACUUM")
            QMessageBox.information(self, "Deleted", "Sources deleted successfully.")
            self.model.select()

    def index_source(self):
        index = self.table.selectionModel().currentIndex()
        if not index:
            QMessageBox.warning(self, "No Selection", "Select at least one source to reindex.")
            return
        source_id = self.model.data(self.model.index(index.row(), 0))
        filename = self.model.data(self.model.index(index.row(), 1))
        language = self.model.data(self.model.index(index.row(), 7))
        destination = DATA_DIR.joinpath(filename)
        self.sig_source_added.emit({"doc_id": source_id, "path": destination.as_posix(), "lang": language})

    def closeEvent(self, event):
        super().closeEvent(event)