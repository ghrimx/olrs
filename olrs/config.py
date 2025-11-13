from pathlib import Path
from enum import Enum, auto

DATA_DIR = Path("./data")
INDEX_DIR = Path("./indexdir")
DB_FILE = Path("./database.db")

class Language(Enum):
    en = auto()
    fr = auto()
    nl = auto()
    de = auto()