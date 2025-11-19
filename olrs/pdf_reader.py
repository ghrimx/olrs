from pathlib import Path
import pymupdf.layout
pymupdf.layout.activate()
from pymupdf4llm import to_markdown
from PyQt6.QtCore import QThread, pyqtSignal as Signal
from searcher import SearchManager



def extract_pdf_pages(doc: pymupdf.Document):
    """
    Generator: yields (page_number, text) tuples for each page.
    """
    for page_number in range(doc.page_count):
        text = to_markdown(doc, pages=page_number)
        yield page_number + 1, text


class PDFIndexWorker(QThread):
    """
    QThread worker to index PDFs page by page in the background.
    Emits signals to update GUI progress.
    """
    progress = Signal(str, int, int)  # pdf_path, current_page, total_pages
    finished = Signal(str)  # pdf_path
    error = Signal(str)

    def __init__(self, manager: SearchManager, pdf_paths: list[str], lang: str):
        super().__init__()
        self.manager = manager
        self.pdf_paths = pdf_paths
        self.lang = lang

    def run(self):
        pdf_path: Path
        for pdf_path in self.pdf_paths:
            try:
                doc = pymupdf.open(pdf_path)
                total_pages = doc.page_count
                for page_number, text in extract_pdf_pages(doc):
                    # Optional: detect section heading here or pass None
                    section = None
                    self.manager.add_page(
                        pdf_path=pdf_path,
                        text=text,
                        lang=self.lang,
                        page=page_number,
                        section=section
                    )
                    self.progress.emit(pdf_path.as_posix(), page_number, total_pages)
            except Exception as e:
                self.error.emit(f"Error while indexing {pdf_path}: {e}")
            finally:
                self.finished.emit(pdf_path.as_posix())
