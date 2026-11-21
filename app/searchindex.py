"""Ευρετήριο πλήρους κειμένου (SQLite FTS5): σελίδες βιβλίου + ερωτήματα. Παράγωγα δεδομένα: ξαναχτίζονται από τα PDF/τη βάση."""
import re, subprocess, unicodedata
from .textnorm import norm

TOK = re.compile(r'\w+', re.U)

def norm_map(s):
    """(κανονικοποιημένο κείμενο, λίστα θέσεων στο πρωτότυπο) ώστε τα αποσπάσματα να δείχνουν το αρχικό κείμενο με τόνους."""
    out, idx = [], []
    for i, ch in enumerate(s or ''):
        for n in norm(ch):
            out.append(n); idx.append(i)
    return ''.join(out), idx

def parse_query(q):
    """Όροι: λέξεις (πρόθεμα) και "φράσεις" -> λίστα [('w', 'λέξη')|('p', ['λ1','λ2'])]."""
    terms = []
    for m in re.finditer(r'"([^"]+)"|(\S+)', q or ''):
        if m.group(1) is not None:
            ws = TOK.findall(norm(m.group(1)))
            if ws: terms.append(('p', ws))
        else:
            for w in TOK.findall(norm(m.group(2))): terms.append(('w', w))
    return terms[:12]

def fts_expr(terms):
    parts = []
    for k, v in terms:
        parts.append('"' + ' '.join(v) + '"' if k == 'p' else '"' + v + '"*')
    return ' '.join(parts)

def create(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS book_page(id INTEGER PRIMARY KEY, book_id INTEGER, pdf_page INTEGER, printed INTEGER, text TEXT, norm TEXT, UNIQUE(book_id,pdf_page));
CREATE VIRTUAL TABLE IF NOT EXISTS book_fts USING fts5(norm, content='book_page', content_rowid='id', tokenize='unicode61 remove_diacritics 0');
CREATE VIRTUAL TABLE IF NOT EXISTS q_fts USING fts5(body, tokenize='unicode61 remove_diacritics 0');""")

def index_book(c, bid, pdf, offset):
    create(c)
    out = subprocess.run(['pdftotext', '-layout', str(pdf), '-'], capture_output=True, text=True, timeout=300).stdout
    pages = out.split('\f')
    if pages and not pages[-1].strip(): pages.pop()
    c.execute('DELETE FROM book_page WHERE book_id=?', (bid,))
    for i, t in enumerate(pages, 1):
        t = re.sub(r'[ \t]+', ' ', t).strip()
        c.execute('INSERT INTO book_page(book_id,pdf_page,printed,text,norm) VALUES(?,?,?,?,?)', (bid, i, i - offset, t, norm(t)))
    c.execute("INSERT INTO book_fts(book_fts) VALUES('rebuild')")
    return len(pages)

def index_questions(c):
    create(c)
    c.execute('DELETE FROM q_fts')
    n = 0
    for r in c.execute('SELECT id,text,sol_text FROM question').fetchall():
        c.execute('INSERT INTO q_fts(rowid,body) VALUES(?,?)', (r[0], norm((r[1] or '') + ' ' + (r[2] or '')))); n += 1
    return n

def reindex(c, root):
    """Πλήρης επανευρετηρίαση (βιβλία + ερωτήματα). Επιστρέφει (σελίδες, ερωτήματα)."""
    import os
    npg = 0
    for b in c.execute('SELECT id,relpath,pdf_offset FROM book').fetchall():
        p = os.path.join(root, b[1])
        if os.path.isfile(p): npg += index_book(c, b[0], p, b[2])
    nq = index_questions(c); c.commit(); return npg, nq

def snippet(text, terms, width=110):
    """Απόσπασμα από το αρχικό κείμενο γύρω από την πρώτη εμφάνιση· τα ταιριάσματα σε <mark> (ήδη escaped)."""
    import html
    nt, idx = norm_map(text); words = [w for k, v in terms for w in ([v] if k == 'w' else v)]
    spans = []
    for w in words:
        for m in re.finditer(r'(?<!\w)' + re.escape(w) + r'\w*', nt):
            spans.append((idx[m.start()], idx[m.end() - 1] + 1))
    spans.sort()
    if not spans: return html.escape(' '.join(text.split())[:2 * width])
    a = max(0, spans[0][0] - width); b = min(len(text), spans[0][0] + width)
    merged = []
    for s, e in spans:
        if s >= b: break
        if s < a: continue
        if merged and s <= merged[-1][1]: merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else: merged.append((s, e))
    out, pos = [], a
    for s, e in merged:
        e = min(e, b); out.append(html.escape(text[pos:s])); out.append('<mark>' + html.escape(text[s:e]) + '</mark>'); pos = e
    out.append(html.escape(text[pos:b]))
    s = ' '.join(''.join(out).split())
    return ('… ' if a > 0 else '') + s + (' …' if b < len(text) else '')

def highlight(text, terms):
    """Όλο το κείμενο σελίδας με <mark> σε όλα τα ταιριάσματα."""
    import html
    nt, idx = norm_map(text); words = [w for k, v in terms for w in ([v] if k == 'w' else v)]
    spans = sorted((idx[m.start()], idx[m.end() - 1] + 1) for w in words for m in re.finditer(r'(?<!\w)' + re.escape(w) + r'\w*', nt))
    out, pos = [], 0
    for s, e in spans:
        if s < pos: continue
        out.append(html.escape(text[pos:s])); out.append('<mark>' + html.escape(text[s:e]) + '</mark>'); pos = e
    out.append(html.escape(text[pos:])); return ''.join(out)
