"""Αναβαθμίσεις σχήματος βάσης (migrations). Τρέχουν αυτόματα στην εκκίνηση και στο πρώτο db() ανά διαδρομή βάσης.
Βάση 0.15.x = χωρίς πίνακα schema_version (έκδοση 0). Κάθε βήμα είναι ιδεμπότεντ και δεν αγγίζει δεδομένα χρήστη."""
import sqlite3

QSOLUTION = """CREATE TABLE IF NOT EXISTS qsolution(item_id TEXT NOT NULL, qcode TEXT NOT NULL, question_id INTEGER, iep_id TEXT, sub TEXT, relpath TEXT NOT NULL,
  fm TEXT, sections TEXT, quiz TEXT, status TEXT, warn TEXT, mtime REAL, sha TEXT, PRIMARY KEY(item_id,qcode))"""

def _v1(c):
    """0.16.0: λύσεις εκπαιδευτικού (ξαναχτίζονται από τα αρχεία .md, δεν είναι δεδομένα χρήστη)."""
    c.execute(QSOLUTION)

def _v2(c):
    """0.18.0: εργαλειοθήκες, κάδος αρχείων, ιστορικό, ρυθμίσεις."""
    c.executescript("""CREATE TABLE IF NOT EXISTS toolbox(slot INTEGER PRIMARY KEY CHECK(slot BETWEEN 1 AND 3), name TEXT NOT NULL, items TEXT NOT NULL DEFAULT '[]', enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS trash(id INTEGER PRIMARY KEY, orig_rel TEXT NOT NULL, trash_rel TEXT NOT NULL, kind TEXT, size INTEGER, deleted TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS fileops(id INTEGER PRIMARY KEY, ts TEXT, op TEXT, path TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS setting(k TEXT PRIMARY KEY, v TEXT);
""")

def _v3(c):
    """0.21.0: συνταγές του wizard εξαγωγών (δεδομένα χρήστη, διατηρούνται στο rebuild)."""
    c.execute("CREATE TABLE IF NOT EXISTS wizard_recipe(id INTEGER PRIMARY KEY, name TEXT NOT NULL, state TEXT NOT NULL DEFAULT '{}', created TEXT, updated TEXT)")

MIGRATIONS = [(1, _v1), (2, _v2), (3, _v3)]
LATEST = MIGRATIONS[-1][0]

def tables(c): return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}

def current(c):
    if 'schema_version' not in tables(c): return 0
    r = c.execute('SELECT max(version) FROM schema_version').fetchone()
    return int(r[0] or 0)

def migrate(c: sqlite3.Connection):
    """Φέρνει τη βάση στην LATEST. Επιστρέφει (από, προς). Κενή/ξένη βάση (χωρίς πίνακα item): καμία αλλαγή."""
    if 'item' not in tables(c): return (None, None)
    v = current(c)
    if v >= LATEST: return (v, v)
    c.execute('CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL)')
    for n, fn in MIGRATIONS:
        if n > v: fn(c)
    c.execute('DELETE FROM schema_version'); c.execute('INSERT INTO schema_version(version) VALUES(?)', (LATEST,))
    c.commit(); return (v, LATEST)

def migrate_path(path):
    c = sqlite3.connect(path)
    try: return migrate(c)
    finally: c.close()
