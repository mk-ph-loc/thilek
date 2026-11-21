import unicodedata
def norm(s):
    """Πεζά, χωρίς τόνους/διαλυτικά, τελικό ς → σ (για αναζήτηση)."""
    s = unicodedata.normalize('NFD', s or '').lower().replace('ς', 'σ')
    return ''.join(ch for ch in s if not unicodedata.combining(ch))
