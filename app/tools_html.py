"""Εξαγωγή θεμάτων σε αυτόνομο HTML: οι σελίδες των PDF ως εικόνες (διατηρούν τύπους και σχήματα), με τα μεταδεδομένα του θέματος."""
import base64, datetime, subprocess, tempfile, pathlib
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from .main_auth import auth
from .review import db, page, html, same_origin, TYPES
from .tools_merge import picker, safe_path, book_pages

router = APIRouter()
MAX_ITEMS = 60; MAX_PAGES = 400
CSS = """body{font:16px/1.45 system-ui,sans-serif;max-width:900px;margin:1rem auto;padding:0 1rem;color:#222}h1{font-size:1.4rem}h2{border-bottom:2px solid #1f3a5f;padding-bottom:.2rem;margin-top:2rem}
img{max-width:100%;border:1px solid #ccc;margin:.4rem 0;display:block}table{border-collapse:collapse;margin:.4rem 0}td,th{border:1px solid #ccc;padding:.2rem .5rem;text-align:left}
details{margin:.6rem 0}summary{cursor:pointer;font-weight:bold}.meta{color:#555;font-size:.9em}section.item{break-before:page}section.item:first-of-type{break-before:auto}@media print{details{display:block}summary{display:none}}"""

def render(path, first, last, dpi):
    """Σελίδες first..last (1-based) του PDF ως JPEG data-URIs."""
    out = []
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(['pdftoppm', '-jpeg', '-jpegopt', 'quality=75', '-r', str(dpi), '-f', str(first), '-l', str(last), path, str(pathlib.Path(d) / 'p')], check=True, capture_output=True, timeout=120)
        for f in sorted(pathlib.Path(d).glob('p*.jpg')): out.append('data:image/jpeg;base64,' + base64.b64encode(f.read_bytes()).decode())
    return out

def runs(pages):
    r = []
    for p in pages:
        if r and p == r[-1][1] + 1: r[-1][1] = p
        else: r.append([p, p])
    return r

def imgs(path, pdf_pages, dpi, alt):
    """pdf_pages: ταξινομημένες 1-based σελίδες PDF (ή None = όλο το αρχείο)."""
    if pdf_pages is None:
        n = int(next((ln.split()[1] for ln in subprocess.run(['pdfinfo', path], capture_output=True, text=True).stdout.splitlines() if ln.startswith('Pages:')), '0'))
        pdf_pages = list(range(1, n + 1))
    tags = []; k = 0
    for a, b in runs(pdf_pages):
        for src in render(path, a, b, dpi):
            k += 1; tags.append(f"<img alt='{html.escape(alt)} – σελίδα {k}' src='{src}'>")
    return ''.join(tags), len(tags)

@router.get('/tools/html', response_class=HTMLResponse, dependencies=[Depends(auth)])
def html_form(yli: str = '', position: str = ''):
    flt, tbl = picker(db(), yli, position)
    body = f"""<h2>Εξαγωγή HTML</h2>{flt}
<form method='post' action='/tools/html'>
<fieldset><legend>Περιεχόμενο</legend>
Τίτλος: <input name=title value='Θέματα Τράπεζας Θεμάτων' size=36><br>
<label><input type=checkbox name=sol value=1> λύσεις</label>
<label><input type=checkbox name=open_sol value=1> εμφάνιση λύσης ανοιχτή (αλλιώς κρύβεται σε «Λύση» με κλικ)</label><br>
<label><input type=checkbox name=book value=1> σελίδες βιβλίου των συνδεδεμένων υποενοτήτων</label> · μέγιστες σελίδες ανά υποενότητα: <input name=cap value=4 size=3><br>
<label><input type=checkbox name=meta value=1 checked> πίνακας ερωτημάτων (μονάδες, τύπος) και συνδέσεις βιβλίου</label><br>
Ανάλυση εικόνων (dpi): <input name=dpi value=100 size=4> (80–150· μεγαλύτερο = πιο καθαρό, πιο βαρύ αρχείο)</fieldset>
<p><button>Δημιουργία HTML</button> · επιλεγμένα θέματα: <span id=count>0</span> (έως {MAX_ITEMS})</p>{tbl}</form>"""
    return page('Εξαγωγή HTML', body)

@router.post('/tools/html', dependencies=[Depends(auth)])
def html_do(request: Request, ids: list[str] = Form([]), title: str = Form('Θέματα'), sol: str = Form(''), open_sol: str = Form(''),
            book: str = Form(''), cap: int = Form(4), meta: str = Form(''), dpi: int = Form(100)):
    same_origin(request)
    ids = sorted({i for i in ids if i.isdigit()}, key=int)
    if not ids: raise HTTPException(422, 'Δεν επιλέχθηκε θέμα.')
    if len(ids) > MAX_ITEMS: raise HTTPException(422, f'Πάνω από {MAX_ITEMS} θέματα ανά εξαγωγή HTML.')
    dpi = max(80, min(dpi, 150)); cap = max(0, min(cap, 50)); total = 0; secs = []
    c = db()
    try:
        for i in ids:
            it = c.execute('SELECT * FROM item WHERE id=?', (i,)).fetchone()
            if not it: continue
            bk = c.execute('SELECT * FROM book WHERE course_code=?', (it['course_code'],)).fetchone()
            part = [f"<section class=item><h2>Θέμα {html.escape(i)}</h2><p class=meta>Θέμα {it['position'] or '—'} · ενότητα ΙΕΠ: {html.escape(it['iep_yli'] or '—')}</p>"]
            if meta:
                qrows = ''.join(f"<tr><td>{html.escape(q['code'])}</td><td>{q['points'] if q['points'] is not None else ''}</td><td>{html.escape(TYPES.get(q['qtype'], ''))}</td><td>{'ναι' if q['has_image'] else ''}</td></tr>" for q in c.execute('SELECT * FROM question WHERE item_id=? ORDER BY id', (i,)))
                if qrows: part.append(f"<table><tr><th>Ερώτημα</th><th>Μονάδες</th><th>Τύπος</th><th>Σχήμα</th></tr>{qrows}</table>")
                secl = c.execute("""SELECT DISTINCT s.code,s.title_el,s.page_from,s.page_to FROM question_section qs JOIN question q ON q.id=qs.question_id JOIN section s ON s.id=qs.section_id WHERE q.item_id=? AND qs.origin!='rejected' AND s.level=3 ORDER BY s.id""", (i,)).fetchall()
                if secl: part.append("<p class=meta>Βιβλίο: " + '; '.join(f"{html.escape(s['code'])} {html.escape(s['title_el'] or '')} (σελ. {s['page_from']}–{s['page_to'] or s['page_from']})" for s in secl) + '</p>')
            sp = safe_path(it['statement_path'])
            if sp:
                t, n = imgs(sp, None, dpi, f'Θέμα {i}'); total += n; part.append(f"<h3>Εκφώνηση</h3>{t}")
            else: part.append('<p><i>Δεν υπάρχει αρχείο εκφώνησης.</i></p>')
            lp = safe_path(it['solution_path']) if sol else None
            if lp:
                t, n = imgs(lp, None, dpi, f'Λύση {i}'); total += n
                part.append(f"<details{' open' if open_sol else ''}><summary>Λύση</summary>{t}</details>")
            bpath = safe_path(bk['relpath']) if (book and bk) else None
            if bpath:
                bp = book_pages(c, i, cap)
                if bp:
                    t, n = imgs(bpath, [p + bk['pdf_offset'] for p in bp], dpi, 'Βιβλίο'); total += n
                    part.append(f"<details><summary>Βιβλίο (σελ. {bp[0]}–{bp[-1]})</summary>{t}</details>")
            if total > MAX_PAGES: raise HTTPException(422, f'Πάνω από {MAX_PAGES} σελίδες· επίλεξε λιγότερα θέματα ή αφαίρεσε το βιβλίο.')
            part.append('</section>'); secs.append(''.join(part))
    finally: c.close()
    if not secs: raise HTTPException(422, 'Δεν βρέθηκαν τα επιλεγμένα θέματα.')
    doc = f"<!doctype html><html lang='el'><meta charset='utf-8'><meta name=viewport content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{CSS}</style><h1>{html.escape(title)}</h1><p class=meta>{len(secs)} θέματα · {total} σελίδες · {datetime.date.today():%d/%m/%Y}</p>{''.join(secs)}</html>"
    name = f"thilek-themata-{datetime.date.today():%Y%m%d}-{len(secs)}.html"
    return Response(doc, media_type='text/html; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{name}"'})
