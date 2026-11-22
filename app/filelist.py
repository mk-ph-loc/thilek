"""Αρχεία που χρησιμοποιήθηκαν ή σχετίζονται με μια εξαγωγή (βήμα 6 του wizard): λίστα, άνοιγμα/λήψη, zip επιλεγμένων και merge των επιλεγμένων PDF."""
import io, os, re, zipfile, datetime, pathlib
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from . import config, wizmodel as M
from .main_auth import auth
from .review import db, html, same_origin

router = APIRouter()
E = html.escape
MAX_FILES = 400                       # πλήθος αρχείων ανά zip/merge
MAX_ZIP = 500 * 1024 * 1024           # συνολικό μέγεθος αρχείων σε ένα zip (πριν τη συμπίεση)
KIND = {'stmt': 'Εκφώνηση ΙΕΠ', 'sol': 'Λύση ΙΕΠ', 'md': 'Λύση εκπαιδευτικού', 'wstmt': 'Εκφώνηση Word', 'wsol': 'Λύση Word', 'book': 'Σχολικό βιβλίο'}
FOLDER = {'stmt': 'pdf', 'sol': 'pdf', 'md': 'lyseis', 'wstmt': 'word', 'wsol': 'word', 'book': 'book'}
USED = ('stmt', 'sol', 'md')          # τα υπόλοιπα είναι «σχετικά» (δεν μπαίνουν στο αρχείο εξαγωγής)


def human(n):
    n = float(n or 0)
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or u == 'GB': return f'{int(n)} {u}' if u == 'B' else f'{n:.1f} {u}'
        n /= 1024


def collect(c, es, root=None):
    """Λίστα αρχείων για τις εγγραφές `es` του wizard, με τη σειρά των θεμάτων: [{key, kind, item, label, arc, rel, exists, size}].
    Το `rel` είναι διαδρομή σχετική με το data_root, ήδη επιλυμένη και ασφαλής (δεν βγαίνει από τον data_root). Τα αρχεία που λείπουν έχουν exists=False."""
    root = root or config.load()['data_root']; out = []; seen = set(); courses = []
    base = pathlib.Path(root).resolve()
    def add(kind, item, course, rel, name, label):
        if not rel: return
        p = M._src(root, course, rel, name); arc = f'{FOLDER[kind]}/{name}'
        key = p.relative_to(base).as_posix() if p else f'?{kind}:{item}:{name}'
        if (key, arc) in seen: return
        seen.add((key, arc))
        out.append({'key': key, 'kind': kind, 'item': item, 'label': label, 'arc': arc, 'rel': key if p else '', 'exists': bool(p), 'size': p.stat().st_size if p else 0})
    done_items = set(); done_md = set()
    for e in es:
        r = e['row']; iid = e['item']; course = r['course_code']
        if course and course not in courses: courses.append(course)
        if iid not in done_items:
            done_items.add(iid)
            add('stmt', iid, course, r['statement_path'], f'{iid}.pdf', f'Θέμα {iid}')
            add('sol', iid, course, r['solution_path'], f'{iid}_SOLUTION.pdf', f'Λύση ΙΕΠ {iid}')
            for w in c.execute('SELECT kind,relpath FROM wordsrc WHERE item_id=? ORDER BY kind DESC', (iid,)):
                add('wstmt' if w['kind'] == 'statement' else 'wsol', iid, course, w['relpath'], pathlib.PurePosixPath(w['relpath']).name, f"{'Εκφώνηση' if w['kind'] == 'statement' else 'Λύση'} Word {iid}")
        if r['sol_rel'] and (iid, e['code']) not in done_md:
            done_md.add((iid, e['code'])); add('md', iid, course, r['sol_rel'], pathlib.PurePosixPath(r['sol_rel']).name, f"Λύση εκπαιδευτικού {iid} · {e['code']}")
    for cc in courses:
        b = c.execute('SELECT title_el,relpath FROM book WHERE course_code=?', (cc,)).fetchone()
        if b and b['relpath']: add('book', '', cc, b['relpath'], pathlib.PurePosixPath(b['relpath']).name, b['title_el'] or 'Σχολικό βιβλίο')
    return out


def section(rid, c, es):
    """HTML της ενότητας για το βήμα 6 (μέσα στη φόρμα του wizard· τα κουμπιά χρησιμοποιούν formaction)."""
    fl = collect(c, es)
    if not fl: return "<h3>Αρχεία που χρησιμοποιήθηκαν ή σχετίζονται</h3><p><small>Δεν βρέθηκαν αρχεία για τα επιλεγμένα ερωτήματα.</small></p>"
    rows = []
    for f in fl:
        if f['exists']:
            q = quote(f['rel'], safe='/')
            box = f"<input type=checkbox name=f value='{E(f['key'])}'{' checked' if f['kind'] != 'book' else ''}>"
            links = f"<a href='/fb/raw?p={q}' target=_blank rel=noopener>άνοιγμα</a> · <a href='/fb/raw?p={q}&dl=1'>λήψη</a>"
            name = f"<code>{E(f['rel'])}</code>"; sz = human(f['size'])
        else:
            box = ''; links = '<small>λείπει από τον server</small>'; name = f"<code>{E(f['arc'])}</code>"; sz = '—'
        dim = '' if f['exists'] else ' style=opacity:.6'
        rows.append(f"<tr{dim}><td>{box}</td><td>{E(f['label'])}</td><td>{E(KIND[f['kind']])}</td><td>{'χρησιμοποιείται' if f['kind'] in USED else 'σχετικό'}</td><td>{name}</td><td>{sz}</td><td>{links}</td></tr>")
    have = [f for f in fl if f['exists']]; miss = len(fl) - len(have)
    tot = sum(f['size'] for f in have); pre = sum(1 for f in have if f['kind'] != 'book')
    return (f"<h3>Αρχεία που χρησιμοποιήθηκαν ή σχετίζονται</h3><p><small>{len(have)} αρχεία ({human(tot)})" + (f" · {miss} λείπουν" if miss else '') + ". Το βιβλίο δεν είναι προεπιλεγμένο (είναι μεγάλο)."
            "</small></p><table><tr><th><input type=checkbox data-all='f' title='όλα'></th><th>Αρχείο</th><th>Είδος</th><th>Ρόλος</th><th>Διαδρομή</th><th>Μέγεθος</th><th></th></tr>" + ''.join(rows) + "</table>"
            f"<p><button formaction='/wizard/{rid}/files/zip'>⬇ Λήψη επιλεγμένων (zip)</button> <button formaction='/wizard/{rid}/files/merge'>⬇ Συγχώνευση επιλεγμένων PDF</button> "
            f"<small>επιλεγμένα: <span id=count>{pre}</span></small></p>")


def _selected(c, rid, keys):
    from .wizard import get_recipe
    name, st = get_recipe(c, rid); es = M.entries(c, st)
    fl = {f['key']: f for f in collect(c, es) if f['exists']}
    keys = list(dict.fromkeys(keys))
    if not keys: raise HTTPException(422, 'Δεν επιλέχθηκε κανένα αρχείο.')
    sel = [fl[k] for k in keys if k in fl]
    if not sel: raise HTTPException(422, 'Τα επιλεγμένα αρχεία δεν ανήκουν σε αυτή την εξαγωγή ή δεν υπάρχουν πια.')
    order = {f['key']: i for i, f in enumerate(fl.values())}
    sel.sort(key=lambda f: order[f['key']])
    if len(sel) > MAX_FILES: raise HTTPException(422, f'Πάνω από {MAX_FILES} αρχεία· επίλεξε λιγότερα.')
    return st, sel


def zip_bytes(sel, root, readme=''):
    base = pathlib.Path(root).resolve(); total = sum(f['size'] for f in sel)
    if total > MAX_ZIP: raise HTTPException(422, f'Τα επιλεγμένα αρχεία ({human(total)}) ξεπερνούν το όριο {human(MAX_ZIP)}· επίλεξε λιγότερα (π.χ. χωρίς το βιβλίο).')
    buf = io.BytesIO(); used = set()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        if readme: z.writestr('README.txt', readme)
        for f in sel:
            arc = f['arc']
            if arc in used:                                   # ίδιο όνομα από άλλον φάκελο: προσθέτουμε το θέμα
                stem, dot, ext = arc.rpartition('.'); arc = f"{stem}_{len(used)}{dot}{ext}"
            used.add(arc); z.write(base / f['rel'], arc)
    return buf.getvalue()


def merge_bytes(sel, root):
    from pypdf import PdfReader, PdfWriter
    from .tools_merge import MAX_PAGES
    base = pathlib.Path(root).resolve(); w = PdfWriter(); n = 0
    pdfs = [f for f in sel if f['rel'].lower().endswith('.pdf')]
    if not pdfs: raise HTTPException(422, 'Στην επιλογή δεν υπάρχει αρχείο PDF.')
    for f in pdfs:
        try:
            r = PdfReader(str(base / f['rel']))
            if r.is_encrypted: raise ValueError('κρυπτογραφημένο')
            start = len(w.pages)
            for p in r.pages:
                w.add_page(p); n += 1
                if n > MAX_PAGES: raise HTTPException(422, f'Πάνω από {MAX_PAGES} σελίδες· επίλεξε λιγότερα αρχεία.')
            w.add_outline_item(title=f['label'], page_number=start)
        except HTTPException: raise
        except Exception as ex: raise HTTPException(422, f"Δεν διαβάστηκε το «{f['label']}» ({f['arc']}): {str(ex)[:80]}")
    buf = io.BytesIO(); w.write(buf); return buf.getvalue(), n


def _name(st, ext):
    from .wizard import slug
    return f"{slug(st['title'])}-arxeia.{ext}"


@router.post('/wizard/{rid}/files/zip', dependencies=[Depends(auth)])
async def files_zip(request: Request, rid: int):
    same_origin(request); form = await request.form(); keys = [str(k) for k in form.getlist('f')]
    c = db()
    try: st, sel = _selected(c, rid, keys)
    finally: c.close()
    root = config.load()['data_root']
    readme = f"{st['title']}\n\nΑρχεία της εξαγωγής ({len(sel)}), σε φακέλους ανά είδος: pdf/ (εκφωνήσεις και λύσεις ΙΕΠ), lyseis/ (λύσεις εκπαιδευτικού), word/ (αρχεία Word ΙΕΠ), book/ (σχολικό βιβλίο).\nΔημιουργήθηκε {datetime.datetime.now():%d/%m/%Y %H:%M}.\n"
    data = zip_bytes(sel, root, readme)
    from .wizard import disp
    return Response(data, media_type='application/zip', headers={'Content-Disposition': disp(_name(st, 'zip'))})


@router.post('/wizard/{rid}/files/merge', dependencies=[Depends(auth)])
async def files_merge(request: Request, rid: int):
    same_origin(request); form = await request.form(); keys = [str(k) for k in form.getlist('f')]
    c = db()
    try: st, sel = _selected(c, rid, keys)
    finally: c.close()
    data, n = merge_bytes(sel, config.load()['data_root'])
    from .wizard import disp
    return Response(data, media_type='application/pdf', headers={'Content-Disposition': disp(_name(st, 'pdf')), 'X-Pages': str(n)})
