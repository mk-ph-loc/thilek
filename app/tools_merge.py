"""Εργαλείο συγχώνευσης PDF: εκφωνήσεις, λύσεις και σελίδες βιβλίου των συνδεδεμένων υποενοτήτων σε ένα έγγραφο."""
import io, os, re, datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pypdf import PdfReader, PdfWriter
from . import config
from .main_auth import auth
from .review import db, page, html, same_origin, fld

router = APIRouter()
MAX_ITEMS = 300; MAX_PAGES = 2000
RANGE = re.compile(r'^\s*(\d{1,4})\s*(?:-\s*(\d{1,4}))?\s*$')

def parse_ranges(s):
    """«267-273, 280» (τυπωμένες σελίδες) -> [(267,273),(280,280)]"""
    out = []
    for part in re.split(r'[,;]', s or ''):
        if not part.strip(): continue
        m = RANGE.match(part)
        if not m: raise HTTPException(422, f'Μη έγκυρο εύρος σελίδων: {part.strip()[:30]}')
        a = int(m.group(1)); b = int(m.group(2) or a)
        if b < a: a, b = b, a
        out.append((a, b))
    return out

def safe_path(rel):
    root = os.path.realpath(config.load()['data_root']); p = os.path.realpath(os.path.join(root, rel or ''))
    if not rel or not p.startswith(root + os.sep) or not os.path.isfile(p): return None
    return p

def book_pages(c, iid, cap):
    """Τυπωμένες σελίδες του βιβλίου για τις συνδέσεις του θέματος (χωρίς τις απορριμμένες), ενωμένες και ταξινομημένες."""
    pages = set()
    for r in c.execute("""SELECT DISTINCT s.page_from a, s.page_to b FROM question_section qs JOIN question q ON q.id=qs.question_id JOIN section s ON s.id=qs.section_id
                          WHERE q.item_id=? AND qs.origin!='rejected' AND s.level=3""", (iid,)):
        a = r['a']; b = r['b'] or a
        if cap and b - a + 1 > cap: b = a + cap - 1
        pages.update(range(a, b + 1))
    return sorted(pages)

def build(c, ids, sol, book, order, cap, extra, bookmarks):
    w = PdfWriter(); readers = {}
    def reader(path):
        if path not in readers: readers[path] = PdfReader(path)
        return readers[path]
    def add(path, pages, title):      # pages: 0-based list ή None = όλο
        r = reader(path); n = len(r.pages); sel = list(range(n)) if pages is None else [p for p in pages if 0 <= p < n]
        if not sel: return 0
        start = len(w.pages)
        for p in sel: w.add_page(r.pages[p])
        if bookmarks: return w.add_outline_item(title, page_number=start)
        return None
    items = []
    for i in ids:
        it = c.execute('SELECT * FROM item WHERE id=?', (i,)).fetchone()
        if it: items.append(it)
    bk = c.execute('SELECT * FROM book WHERE course_code=?', (items[0]['course_code'],)).fetchone() if items and book else None
    bpath = safe_path(bk['relpath']) if bk else None
    off = bk['pdf_offset'] if bk else 1
    def book_idx(printed): return [p + off - 1 for p in printed]
    def stmt(it): return safe_path(it['statement_path'])
    def solu(it): return safe_path(it['solution_path'])
    if order == 'by_item':
        for it in items:
            if stmt(it): add(stmt(it), None, f"Θέμα {it['id']}")
            if sol and solu(it): add(solu(it), None, f"Λύση {it['id']}")
            if bpath:
                bp = book_pages(c, it['id'], cap)
                if bp: add(bpath, book_idx(bp), f"Βιβλίο για {it['id']} (σελ. {bp[0]}–{bp[-1]})")
    else:
        for it in items:
            if stmt(it): add(stmt(it), None, f"Θέμα {it['id']}")
        if sol:
            for it in items:
                if solu(it): add(solu(it), None, f"Λύση {it['id']}")
        if bpath:
            allp = sorted({p for it in items for p in book_pages(c, it['id'], cap)})
            if allp: add(bpath, book_idx(allp), f"Βιβλίο ({len(allp)} σελίδες)")
    if extra and bk and bpath:
        pp = sorted({p for a, b in extra for p in range(a, b + 1)})
        add(bpath, book_idx(pp), 'Σελίδες βιβλίου (επιλογή)')
    if len(w.pages) == 0: raise HTTPException(422, 'Δεν προέκυψε καμία σελίδα (δεν υπάρχουν αρχεία για τα επιλεγμένα).')
    if len(w.pages) > MAX_PAGES: raise HTTPException(422, f'Πάνω από {MAX_PAGES} σελίδες· επίλεξε λιγότερα θέματα.')
    buf = io.BytesIO(); w.write(buf); return buf.getvalue(), len(w.pages)

def picker(c, yli, position):
    """Φίλτρο + πίνακας επιλογής θεμάτων (κοινός για τα εργαλεία εξαγωγής)."""
    w, a = [], []
    if yli: w.append('i.iep_yli LIKE ?'); a.append(yli + '%')
    if position.isdigit(): w.append('i.position=?'); a.append(int(position))
    rows = c.execute(f"""SELECT i.id,i.position,i.iep_yli,i.solution_path,i.solution_status,
        (SELECT count(*) FROM question q WHERE q.item_id=i.id) nq FROM item i {'WHERE ' + ' AND '.join(w) if w else ''} ORDER BY CAST(i.id AS INTEGER)""", a).fetchall()
    trs = ''.join(f"<tr><td><input type=checkbox name=ids value='{r['id']}'></td><td><a href='/review/{r['id']}'>{r['id']}</a></td><td>{r['position'] or ''}</td><td>{html.escape(r['iep_yli'] or '')}</td><td>{r['nq']}</td><td>{html.escape(r['solution_status'] or '')}</td></tr>" for r in rows)
    pos_sel = "<select name=position><option value=''>—</option><option value=2%s>2</option><option value=4%s>4</option></select>" % (' selected' if position == '2' else '', ' selected' if position == '4' else '')
    flt = "<form method='get' class=filters>" + fld('Ενότητα ΙΕΠ', f"<input name=yli value='{html.escape(yli)}' size=5>") + fld('Θέμα', pos_sel) + "<button>Εμφάνιση</button></form>"
    tbl = f"<table><tr><th><input type=checkbox data-all='ids' title='όλα τα εμφανιζόμενα'></th><th>ID</th><th>Θέμα</th><th>Ενότητα ΙΕΠ</th><th>Ερωτήματα</th><th>Λύση</th></tr>{trs}</table>"
    return flt, tbl

@router.get('/tools/merge', response_class=HTMLResponse, dependencies=[Depends(auth)])
def merge_form(request: Request, yli: str = '', position: str = '', tab: str = ''):
    from . import pickq
    if tab == 'questions': return pickq.questions_tab(request)
    flt, tbl = picker(db(), yli, position)
    body = f"""<h2>Συγχώνευση PDF</h2>{pickq.tabs("items")}{flt}
<form method='post' action='/tools/merge'>
<fieldset><legend>Περιεχόμενο</legend>
<label><input type=checkbox name=sol value=1> λύσεις</label>
<label><input type=checkbox name=book value=1> σελίδες βιβλίου των συνδεδεμένων υποενοτήτων</label>
 · μέγιστες σελίδες ανά υποενότητα: <input name=cap value=8 size=3> (0 = όλες)<br>
Επιπλέον σελίδες βιβλίου (τυπωμένες, π.χ. 267-273, 280): <input name=extra size=24><br>
Σειρά: <label><input type=radio name=order value=by_item checked> ανά θέμα (εκφώνηση, λύση, βιβλίο)</label>
<label><input type=radio name=order value=by_type> όλες οι εκφωνήσεις, μετά οι λύσεις, μετά το βιβλίο</label><br>
<label><input type=checkbox name=bookmarks value=1 checked> σελιδοδείκτες</label></fieldset>
<p><button>Δημιουργία PDF</button> · επιλεγμένα θέματα: <span id=count>0</span> · η σειρά είναι αυτή του πίνακα (αύξων ID)</p>{tbl}</form>"""
    return page('Συγχώνευση PDF', body)

@router.post('/tools/merge', dependencies=[Depends(auth)])
def merge_do(request: Request, ids: list[str] = Form([]), sol: str = Form(''), book: str = Form(''), order: str = Form('by_item'),
             cap: int = Form(8), extra: str = Form(''), bookmarks: str = Form('')):
    same_origin(request)
    ids = [i for i in dict.fromkeys(ids) if i.isdigit()]
    if not ids: raise HTTPException(422, 'Δεν επιλέχθηκε θέμα.')
    if len(ids) > MAX_ITEMS: raise HTTPException(422, f'Πάνω από {MAX_ITEMS} θέματα.')
    ids.sort(key=int)
    c = db()
    try: data, n = build(c, ids, bool(sol), bool(book), order if order in ('by_item', 'by_type') else 'by_item', max(0, min(cap, 200)), parse_ranges(extra), bool(bookmarks))
    finally: c.close()
    name = f"thilek-merge-{datetime.date.today():%Y%m%d}-{len(ids)}themata.pdf"
    return Response(data, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{name}"', 'X-Pages': str(n)})
