# index_worker.py
from PyQt6.QtCore import QThread, pyqtSignal
from pathlib import Path

from db_manager import DbManager


class IndexWorker(QThread):
    progress = pyqtSignal(object, int, int)      
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, source_id: int, pdf_path: Path, language: str, parent=None):
        super().__init__(parent)
        self.source_id = source_id
        self.pdf_path = pdf_path
        self.language = language

    def run(self):
        try:
            db = DbManager.instance()

            records = extract_pdf_text(self.pdf_path, self.language)
            total = len(records)
            
            embeddings = model.encode([t for _, t, _ in records])

            for i, ((page, text, lemma), emb) in enumerate(zip(records, embeddings)):
                db.insert_vector(self.source_id, page, text, lemma, np_to_blob(emb), self.language)
                self.progress.emit(self.pdf_path, i + 1, total)

            self.finished.emit(total)
        except Exception as e:
            self.error.emit(str(e))
