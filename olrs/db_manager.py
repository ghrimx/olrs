# DbManager.py
import logging
from PyQt6.QtSql import QSqlDatabase, QSqlQuery
from PyQt6.QtCore import QByteArray

from config import DB_FILE

logger = logging.getLogger(__name__)


class DbManager:
    _instance = None

    def __init__(self):
        if DbManager._instance:
            raise RuntimeError("Use DbManager.instance()")
        self.db = QSqlDatabase.addDatabase("QSQLITE")
        self.db.setDatabaseName(str(DB_FILE))
        if not self.db.open():
            raise RuntimeError(f"Database open error: {self.db.lastError().text()}")
        self._create_schema()

    @classmethod
    def instance(cls) -> 'DbManager':
        if cls._instance is None:
            cls._instance = DbManager()
        return cls._instance

    def _create_schema(self):
        q = QSqlQuery(self.db)

        q.exec("""
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT UNIQUE,
                    title TEXT,
                    short_title TEXT,
                    url TEXT,
                    reference TEXT,
                    page_count INTEGER,
                    language TEXT
                );
        """)

        q.exec("""
                CREATE TABLE IF NOT EXISTS vectors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER REFERENCES sources(id),
                    page INTEGER,
                    text TEXT,
                    lemma TEXT,
                    embedding BLOB,
                    language TEXT
                );
        """)

        q.exec("""
                CREATE TABLE IF NOT EXISTS synonyms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_name TEXT
                );
               """)

        q.exec("""
                CREATE TABLE IF NOT EXISTS synonym_terms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    synonym_id INTEGER,
                    term TEXT,
                    FOREIGN KEY (synonym_id) REFERENCES synonyms(id) ON DELETE CASCADE
                );
        """)


    def clear(self):
        q = QSqlQuery(self.db)
        q.exec("DELETE FROM vectors")
        q.exec("DELETE FROM sources")

    # ---------- Source ----------
    def get_source_id(self, filename):
        q = QSqlQuery(self.db)
        q.prepare("SELECT id FROM sources WHERE filename = ?")
        q.addBindValue(filename)
        q.exec()
        if q.next():
            return q.value(0)
        return None

    def insert_source(self, filename, title, short_title, url, reference, page_count, language):
        q = QSqlQuery(self.db)
        q.prepare("""
            INSERT INTO sources (filename, title, short_title, url, reference, page_count, language)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """)
        q.addBindValue(filename)
        q.addBindValue(title)
        q.addBindValue(short_title)
        q.addBindValue(url)
        q.addBindValue(reference)
        q.addBindValue(page_count)
        q.addBindValue(language)
        q.exec()
        return q.lastInsertId()

    # ---------- Document ----------
    def insert_vector(self, source_id, page, text, lemma, embedding: bytes, language):
        q = QSqlQuery(self.db)
        q.prepare("""
            INSERT INTO vectors (source_id, page, text, lemma, embedding, language)
            VALUES (?, ?, ?, ?, ?, ?)
        """)
        q.addBindValue(source_id)
        q.addBindValue(page)
        q.addBindValue(text)
        q.addBindValue(lemma)
        q.addBindValue(QByteArray(embedding))
        q.addBindValue(language)
        q.exec()

        if not q.exec():
            logger.error("❌ Insert failed:", q.lastError().text())


    def all_sources(self):
        q = QSqlQuery(self.db)
        q.exec("SELECT id, filename, title, short_title, reference, page_count, language FROM sources")
        return q
