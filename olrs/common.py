from enum import Enum

class SearchMode(Enum):
    PARTIAL = 'partial'
    WHOLE = 'whole'
    FUZZY = 'fuzzy'