"""Προτείνει υποενότητες (και άρα σελίδες) του βιβλίου για κάθε ερώτημα, με TF-IDF πάνω στο κείμενο του βιβλίου.
Ο υποψήφιος χώρος περιορίζεται στην ενότητα που δίνει το ΙΕΠ (π.χ. 4.1 → 4.1.x). Χωρίς εξωτερικές υπηρεσίες.
Αποτέλεσμα: question_section με origin='auto' και score. Οι χειροκίνητες συνδέσεις (origin 'manual') δεν αγγίζονται."""
import math, re, subprocess, unicodedata, collections

TOK = re.compile(r'[a-zα-ω0-9]+')
def norm(s):
    s = unicodedata.normalize('NFD', s.lower())
    s = ''.join(c for c in s if not unicodedata.combining(c)).replace('ς', 'σ')
    return [w[:6] for w in TOK.findall(s) if len(w) >= 3 and not w.isdigit()]

def book_pages(pdf):
    out = subprocess.run(['pdftotext', '-layout', str(pdf), '-'], capture_output=True, text=True).stdout
    return out.split('\f')            # δείκτης 0 = σελίδα PDF 1

def own_text(full, code, next_code):
    """Μόνο το κείμενο της υποενότητας: από τον τίτλο της μέχρι τον τίτλο της επόμενης ή την «Ανακεφαλαίωση»."""
    m = re.search(r'(?m)^\s*' + re.escape(code) + r'\.?\s', full)
    start = m.start() if m else 0
    end = len(full)
    cuts = [r'(?m)^\s*Ανακεφαλαίωση', r'(?m)^\s*Ενότητα\s+\d+\.\d+', r'(?m)^\s*Κεφάλαιο\s+\d+\s*$']
    if next_code: cuts.append(r'(?m)^\s*' + re.escape(next_code) + r'\.?\s')
    for c in cuts:
        m2 = re.search(c, full[start + len(code):])
        if m2: end = min(end, start + len(code) + m2.start())
    return full[start:end]

def suggest(conn, book_id, pdf, offset, min_score=0.08, rel=0.85, only_missing=True):
    pages = book_pages(pdf)
    secs = sorted(conn.execute("SELECT id,code,page_from,page_to FROM section WHERE book_id=? AND level=3", (book_id,)).fetchall(),
                  key=lambda r: [int(x) for x in r[1].split('.')])
    docs = {}
    for i, (sid, code, a, b) in enumerate(secs):
        b = b or a
        full = '\n'.join(pages[p + offset - 1] for p in range(a, b + 1) if 0 <= p + offset - 1 < len(pages))
        txt = own_text(full, code, secs[i + 1][1] if i + 1 < len(secs) else None)
        docs[sid] = collections.Counter(norm(txt))
    n = len(docs); df = collections.Counter(w for d in docs.values() for w in d)
    idf = {w: math.log((n + 1) / (c + 0.5)) for w, c in df.items()}
    def vec(c):
        v = {w: (1 + math.log(f)) * idf[w] for w, f in c.items() if w in idf}
        nrm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / nrm for w, x in v.items()}
    dvec = {sid: vec(c) for sid, c in docs.items()}
    code_of = {sid: code for sid, code, _, _ in secs}
    added = 0
    qs = conn.execute("SELECT x.id, x.text, (SELECT s.code FROM question_section qs JOIN section s ON s.id=qs.section_id WHERE qs.question_id=x.id AND qs.origin='iep' LIMIT 1) FROM question x").fetchall()
    for qid, text, unit in qs:
        if only_missing and conn.execute("SELECT 1 FROM question_section WHERE question_id=? AND origin='manual'", (qid,)).fetchone(): continue
        qv = vec(collections.Counter(norm(text or '')))
        cands = [sid for sid in docs if (not unit or code_of[sid].startswith(unit + '.'))]
        scored = sorted(((sum(qv.get(w, 0) * x for w, x in dvec[sid].items()), sid) for sid in cands), reverse=True)
        if not scored or scored[0][0] < min_score: continue
        top = scored[0][0]
        for sc, sid in scored[:2]:
            if sc >= min_score and sc >= rel * top:
                conn.execute("INSERT OR IGNORE INTO question_section(question_id,section_id,origin,score) VALUES(?,?,'auto',?)", (qid, sid, round(sc, 3))); added += 1
    return added
