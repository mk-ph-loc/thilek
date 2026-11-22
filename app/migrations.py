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

def _v4(c):
    """0.25.0: σύγκριση απαντήσεων με το ΙΕΠ (δεδομένα χρήστη λόγω χειροκίνητων αλλαγών, διατηρούνται στο rebuild)."""
    c.execute("CREATE TABLE IF NOT EXISTS iepcmp(item_id TEXT NOT NULL, qcode TEXT NOT NULL, qn INTEGER NOT NULL, kind TEXT, mine TEXT, iep TEXT, auto TEXT, status TEXT, manual INTEGER NOT NULL DEFAULT 0, note TEXT, updated TEXT, PRIMARY KEY(item_id,qcode,qn))")

def _v5(c):
    """0.26.0: τίτλος/έτος/σημείωση για δικά μου θέματα και πανελλήνιες (δεδομένα χρήστη)."""
    c.execute("CREATE TABLE IF NOT EXISTS ownitem(item_id TEXT PRIMARY KEY, title TEXT, year TEXT, note TEXT)")

def _v6(c):
    """0.27.0: κείμενο/εξισώσεις/εικόνες των Word του ΙΕΠ (παράγωγος πίνακας, ξαναχτίζεται από τα αρχεία)."""
    c.execute("CREATE TABLE IF NOT EXISTS wordsrc(item_id TEXT NOT NULL, kind TEXT NOT NULL, relpath TEXT, sha TEXT, mtime REAL, n_par INTEGER, n_eq INTEGER, n_img INTEGER, n_q INTEGER, pts INTEGER, status TEXT, warn TEXT, text TEXT, images TEXT, PRIMARY KEY(item_id,kind))")

DECK = """CREATE TABLE IF NOT EXISTS deck(id INTEGER PRIMARY KEY, name TEXT NOT NULL, title TEXT, subtitle TEXT, recipe TEXT NOT NULL DEFAULT 'free', state TEXT NOT NULL DEFAULT '{}',
  style TEXT NOT NULL DEFAULT 'calm', opts TEXT NOT NULL DEFAULT '{}', kind INTEGER NOT NULL DEFAULT 0, course_code TEXT, note TEXT, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS deck_slide(id INTEGER PRIMARY KEY, deck_id INTEGER NOT NULL, pos INTEGER NOT NULL, layout TEXT NOT NULL DEFAULT 'content', title TEXT, body TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
  opts TEXT NOT NULL DEFAULT '{}', down INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0, src_item TEXT, src_qcode TEXT, src_unit TEXT, src_part INTEGER, src_sha TEXT, gen_sha TEXT, linked INTEGER NOT NULL DEFAULT 0, updated TEXT);
CREATE INDEX IF NOT EXISTS ix_dslide ON deck_slide(deck_id,pos);"""

def _v7(c):
    """0.32.0: παρουσιάσεις (deck) και διαφάνειες (deck_slide)· δεδομένα χρήστη, διατηρούνται στο rebuild. Χωρίς ξένα κλειδιά, όπως οι άλλοι πίνακες χρήστη."""
    c.executescript(DECK)

MIGRATIONS = [(1, _v1), (2, _v2), (3, _v3), (4, _v4), (5, _v5), (6, _v6), (7, _v7)]
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
