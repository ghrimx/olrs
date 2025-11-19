# Synonym Manager
import json

from PyQt6.QtWidgets import (
    QInputDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QSplitter, QLineEdit, QMessageBox, QWidget
)

from pathlib import Path

class SynonymManager(QWidget):
    def __init__(self, synonym_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Synonyms Manager")

        self.syn_path = synonym_path
        self.synonyms = {}
        self.load_synonyms()

        splitter = QSplitter(self)

        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(splitter)

        # List of words
        word_widget = QWidget()
        splitter.addWidget(word_widget)
        word_widget_layout = QVBoxLayout()
        word_widget.setLayout(word_widget_layout)
        self.word_list = QListWidget()
        self.word_list.itemSelectionChanged.connect(self.on_word_selected)
        word_widget_layout.addWidget(QLabel("Words:"))
        word_widget_layout.addWidget(self.word_list)

        # Synonyms list
        syn_widget = QWidget()
        splitter.addWidget(syn_widget)
        syn_widget_layout = QVBoxLayout()
        syn_widget.setLayout(syn_widget_layout)
        self.syn_list = QListWidget()
        syn_widget_layout.addWidget(QLabel("Synonyms:"))
        syn_widget_layout.addWidget(self.syn_list)

        # Add synonym row
        add_row = QHBoxLayout()
        self.new_syn_input = QLineEdit()
        self.new_syn_input.setPlaceholderText("Add synonym...")
        self.btn_add_syn = QPushButton("Add")
        self.btn_add_syn.clicked.connect(self.add_synonym)
        add_row.addWidget(self.new_syn_input)
        add_row.addWidget(self.btn_add_syn)
        syn_widget_layout.addLayout(add_row)

        self.btn_remove_syn = QPushButton("Remove Selected Synonym")
        self.btn_remove_syn.clicked.connect(self.remove_synonym)
        add_row.addWidget(self.btn_remove_syn)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_add_word = QPushButton("Add Word")
        self.btn_add_word.clicked.connect(self.add_word)
        self.btn_remove_word = QPushButton("Remove Word")
        self.btn_remove_word.clicked.connect(self.remove_word)
        btn_row.addWidget(self.btn_add_word)
        btn_row.addWidget(self.btn_remove_word)
        word_widget_layout.addLayout(btn_row)

        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self.save_synonyms)
        layout.addWidget(self.btn_save)

        self.refresh_word_list()

    # --------------------------------------------------
    # Load / Save
    # --------------------------------------------------
    def load_synonyms(self):
        if self.syn_path.exists():
            with open(self.syn_path, "r", encoding="utf8") as f:
                self.synonyms = json.load(f)
        else:
            self.synonyms = {}

    def save_synonyms(self):
        with open(self.syn_path, "w", encoding="utf8") as f:
            json.dump(self.synonyms, f, indent=4, ensure_ascii=False)
        QMessageBox.information(self, "Saved", "Synonyms saved successfully.")

    # --------------------------------------------------
    # UI Logic
    # --------------------------------------------------
    def refresh_word_list(self):
        self.word_list.clear()
        for w in sorted(self.synonyms.keys()):
            self.word_list.addItem(w)
        self.syn_list.clear()

    def on_word_selected(self):
        items = self.word_list.selectedItems()
        if not items:
            self.syn_list.clear()
            return
        word = items[0].text()
        self.refresh_syn_list(word)

    def refresh_syn_list(self, word):
        self.syn_list.clear()
        for s in sorted(self.synonyms.get(word, [])):
            self.syn_list.addItem(s)

    # --------------------------------------------------
    # Word / Synonym management
    # --------------------------------------------------
    def add_word(self):
        text, ok = QInputDialog.getText(self, "Add Word", "Word:")
        if not ok or not text.strip():
            return
        w = text.strip().lower()
        if w in self.synonyms:
            QMessageBox.warning(self, "Exists", f"'{w}' already exists.")
            return
        self.synonyms[w] = []
        self.refresh_word_list()

    def remove_word(self):
        items = self.word_list.selectedItems()
        if not items:
            return
        w = items[0].text()
        del self.synonyms[w]
        self.refresh_word_list()

    def add_synonym(self):
        items = self.word_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "Select Word", "Select a word first.")
            return
        word = items[0].text()
        syn = self.new_syn_input.text().strip().lower()
        if not syn:
            return
        if syn not in self.synonyms[word]:
            self.synonyms[word].append(syn)
        self.new_syn_input.clear()
        self.refresh_syn_list(word)

    def remove_synonym(self):
        w_items = self.word_list.selectedItems()
        if not w_items:
            return
        word = w_items[0].text()
        s_items = self.syn_list.selectedItems()
        if not s_items:
            return
        syn = s_items[0].text()
        self.synonyms[word].remove(syn)
        self.refresh_syn_list(word)

