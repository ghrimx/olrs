from pathlib import Path
from enum import StrEnum

DATA_DIR = Path("./data/")
DATA_DIR.mkdir(exist_ok=True)
INDEX_DIR = Path("./indexdir")
DB_FILE = Path("./database.db")
SYNONYM_FILE = Path("./synonyms.json")


class EULanguage(StrEnum):
    ENGLISH = "en"       
    FRENCH = "fr"
    DUTCH = "nl"
    GERMAN = "de"
    BULGARIAN = "bg"
    CROATIAN = "hr"
    CZECH = "cs"
    DANISH = "da"
    ESTONIAN = "et"
    FINNISH = "fi"
    GREEK = "el"
    HUNGARIAN = "hu"
    IRISH = "ga"
    ITALIAN = "it"
    LATVIAN = "lv"
    LITHUANIAN = "lt"
    MALTESE = "mt"
    POLISH = "pl"
    PORTUGUESE = "pt"
    ROMANIAN = "ro"
    SLOVAK = "sk"
    SLOVENE = "sl"
    SPANISH = "es"
    SWEDISH = "sv"
