"""0.27: ανάγνωση των Word του ΙΕΠ (<ID>.docx, <ID>_SOLUTION.docx στο orig/): κείμενο, εξισώσεις (OMML→LaTeX), εικόνες, σύγκριση με τα ερωτήματα του PDF.
Παράγωγος πίνακας wordsrc (ξαναχτίζεται από τα αρχεία, δεν είναι δεδομένα χρήστη). Τα αρχεία Word δεν τροποποιούνται ποτέ."""
import datetime, sqlite3, hashlib, html, json, pathlib, re, sys, zipfile
from xml.etree import ElementTree as ET
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from urllib.parse import quote
from .main_auth import auth
from .review import db, page, same_origin
from .library import active_course

router = APIRouter()
E = html.escape
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
M = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
RN = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PR = '{http://schemas.openxmlformats.org/package/2006/relationships}'
MAX_XML = 40 * 1024 * 1024; MAX_IMG = 15 * 1024 * 1024; MAX_IMGS = 60
IMG_EXT = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tif', 'tiff'}
FILE = re.compile(r'^(\d+)(_SOLUTION)?\.docx$')


def _latex(elem):
    try: from .ommllatex import omml_to_latex
    except ImportError: omml_to_latex = None
    if omml_to_latex:
        try: return omml_to_latex(elem).strip()
        except Exception: pass
    return ''.join(t.text or '' for t in elem.iter(M + 't'))       # εφεδρικά: μόνο το κείμενο της εξίσωσης


class Doc:
    def __init__(self, rels): self.rels = rels; self.eq = 0; self.imgs = []; self.warn = []

    def para(self, p):
        out = []
        def walk(e):
            for ch in e:
                t = ch.tag
                if t == W + 'r': run(ch)
                elif t in (W + 'hyperlink', W + 'ins', W + 'smartTag', W + 'sdt', W + 'sdtContent', W + 'fldSimple'): walk(ch)
                elif t == M + 'oMathPara':
                    self.eq += 1; out.append(' $$' + ' '.join(_latex(x) for x in ch.findall(M + 'oMath')) + '$$ ')
                elif t == M + 'oMath': self.eq += 1; out.append(' $' + _latex(ch) + '$ ')
        def run(r):
            for x in r:
                if x.tag == W + 't': out.append(x.text or '')
                elif x.tag in (W + 'tab',): out.append(' ')
                elif x.tag in (W + 'br', W + 'cr'): out.append(' ')
                elif x.tag in (W + 'drawing', W + 'pict'):
                    for b in x.iter(A + 'blip'):
                        rid = b.get(RN + 'embed') or b.get(RN + 'link'); tgt = self.rels.get(rid or '')
                        if tgt: self.imgs.append(tgt); out.append(f' [εικόνα {len(self.imgs)}] ')
        walk(p)
        return re.sub(r'[ \t]+', ' ', ''.join(out)).strip()

    def block(self, e, lines):
        for ch in e:
            if ch.tag == W + 'p':
                s = self.para(ch)
                if s: lines.append(s)
            elif ch.tag == W + 'tbl':
                for tr in ch.iter(W + 'tr'):
                    cells = []
                    for tc in tr.findall(W + 'tc'):
                        sub = []; self.block(tc, sub); cells.append(' '.join(sub))
                    if any(cells): lines.append(' | '.join(cells))
            elif ch.tag in (W + 'sdt', W + 'sdtContent'): self.block(ch, lines)
            elif ch.tag == M + 'oMathPara': self.eq += 1; lines.append('$$' + ' '.join(_latex(x) for x in ch.findall(M + 'oMath')) + '$$')


def read_docx(path):
    """-> dict(text, n_par, n_eq, images=[(όνομα, bytes)], warn). Σηκώνει ValueError για μη έγκυρο/επικίνδυνο αρχείο."""
    try: z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as ex: raise ValueError('δεν είναι έγκυρο αρχείο docx (' + str(ex)[:60] + ')')
    with z:
        names = {i.filename: i for i in z.infolist()}
        if 'word/document.xml' not in names: raise ValueError('λείπει το word/document.xml (δεν είναι docx;)')
        def raw(n):
            i = names[n]
            if i.file_size > MAX_XML: raise ValueError(f'πολύ μεγάλο εσωτερικό αρχείο {n}')
            d = z.read(n)
            if b'<!DOCTYPE' in d[:2000].upper() or b'<!ENTITY' in d.upper(): raise ValueError('απορρίφθηκε: το XML περιέχει DOCTYPE/ENTITY')
            return d
        try:
            rels = {}
            if 'word/_rels/document.xml.rels' in names:
                for r in ET.fromstring(raw('word/_rels/document.xml.rels')).iter(PR + 'Relationship'):
                    if r.get('Id') and r.get('Target'): rels[r.get('Id')] = r.get('Target')
            root = ET.fromstring(raw('word/document.xml'))
        except ET.ParseError as ex: raise ValueError('σπασμένο XML: ' + str(ex)[:60])
        body = root.find(W + 'body')
        if body is None: raise ValueError('το έγγραφο δεν έχει σώμα')
        d = Doc(rels); lines = []; d.block(body, lines)
        imgs = []
        for tgt in d.imgs[:MAX_IMGS]:
            p = tgt.lstrip('/') if tgt.startswith('/') else str(pathlib.PurePosixPath('word') / tgt)
            p = str(pathlib.PurePosixPath(p)); parts = [x for x in p.split('/') if x not in ('', '.')]
            if '..' in parts: d.warn.append(f'εικόνα που παραλείφθηκε (μη ασφαλής διαδρομή): {tgt[:60]}'); continue
            p = '/'.join(parts); ext = p.rsplit('.', 1)[-1].lower() if '.' in p else ''
            if p in names and ext in IMG_EXT and names[p].file_size <= MAX_IMG: imgs.append((f'{len(imgs) + 1}.{ext}', z.read(p)))
            else: d.warn.append(f'εικόνα που παραλείφθηκε: {tgt[:60]}')
        if len(d.imgs) > MAX_IMGS: d.warn.append(f'πάνω από {MAX_IMGS} εικόνες· κρατήθηκαν οι πρώτες')
    return {'text': '\n'.join(lines), 'n_par': len(lines), 'n_eq': d.eq, 'images': imgs, 'warn': d.warn}


def _split(text):
    """Διαχωρισμός ερωτημάτων με τον κανόνα του ingest (ίδιος με του PDF). -> [{code, points, text}] ή None αν δεν φορτώνεται το tools/ingest."""
    try:
        tools = str(pathlib.Path(__file__).resolve().parent.parent / 'tools')
        if tools not in sys.path: sys.path.insert(0, tools)
        import ingest
        return ingest.split_questions(text)
    except Exception: return None


def compare(word_qs, db_qs):
    """word_qs: [{code, points}], db_qs: {code: points από το PDF}. -> λίστα προειδοποιήσεων."""
    w = []; wc = {q['code']: q['points'] for q in word_qs}
    miss = [k for k in db_qs if k not in wc]; extra = [k for k in wc if k not in db_qs]
    if len(wc) != len(db_qs): w.append(f'πλήθος ερωτημάτων: Word {len(wc)}, PDF {len(db_qs)}')
    if miss: w.append('ερωτήματα του PDF που δεν βρέθηκαν στο Word: ' + ', '.join(miss[:12]))
    if extra: w.append('ερωτήματα του Word που δεν υπάρχουν στο PDF: ' + ', '.join(extra[:12]))
    for k in db_qs:
        if k in wc and wc[k] != db_qs[k] and (wc[k] is not None or db_qs[k] is not None): w.append(f'μονάδες {k}: PDF {db_qs[k]}, Word {wc[k]}')
    return w


def scan(c, data_root, course=None):
    """Ανεξάρτητο από το row_factory της σύνδεσης (το thilek-rebuild δίνει σύνδεση με απλές πλειάδες)."""
    old = c.row_factory; c.row_factory = sqlite3.Row
    try: return _scan(c, data_root, course)
    finally: c.row_factory = old


def _scan(c, data_root, course=None):
    """Σαρώνει τα .docx στο <μάθημα>/04_TRAPEZA/orig/ και ξαναγράφει τον wordsrc. -> {files, ok, warn, errors, messages}."""
    root = pathlib.Path(data_root); res = {'files': 0, 'ok': 0, 'warn': 0, 'errors': 0, 'messages': []}
    codes = [r[0] for r in c.execute('SELECT code FROM course')] if not course else [course]
    if course: c.execute('DELETE FROM wordsrc WHERE item_id IN (SELECT id FROM item WHERE course_code=?)', (course,))
    else: c.execute('DELETE FROM wordsrc')
    now = datetime.datetime.now().isoformat(timespec='seconds')
    for code in codes:
        orig = root / code / '04_TRAPEZA' / 'orig'
        if not orig.is_dir(): continue
        for p in sorted(orig.glob('*.docx')):
            m = FILE.match(p.name)
            if not m: res['messages'].append(f'{code}/{p.name}: όνομα εκτός μορφής <ID>.docx / <ID>_SOLUTION.docx (αγνοήθηκε)'); continue
            iid, kind = m.group(1), ('solution' if m.group(2) else 'statement'); res['files'] += 1
            if not c.execute('SELECT 1 FROM item WHERE id=? AND course_code=?', (iid, code)).fetchone(): res['messages'].append(f'{code}/{p.name}: δεν υπάρχει θέμα {iid} στη βάση'); res['errors'] += 1; continue
            rel = f'{code}/04_TRAPEZA/orig/{p.name}'; sha = hashlib.sha256(p.read_bytes()).hexdigest()
            try: d = read_docx(p)
            except ValueError as ex:
                c.execute('INSERT OR REPLACE INTO wordsrc(item_id,kind,relpath,sha,mtime,status,warn,text,n_par,n_eq,n_img,n_q,pts,images) VALUES(?,?,?,?,?,?,?,?,0,0,0,0,0,?)', (iid, kind, rel, sha, p.stat().st_mtime, 'error', json.dumps([str(ex)], ensure_ascii=False), '', '[]'))
                res['errors'] += 1; res['messages'].append(f'{rel}: {ex}'); continue
            qs = _split(d['text']) or []; warn = list(d['warn'])
            if kind == 'statement':
                dbq = {r['code']: r['points'] for r in c.execute('SELECT code,points FROM question WHERE item_id=?', (iid,))}
                if _split('ΘΕΜΑ 2\n2.1 x') is None: warn.append('δεν έγινε σύγκριση με το PDF (λείπει το tools/ingest.py)')
                else: warn += compare(qs, dbq)
            else:
                st = [r['code'] for r in c.execute('SELECT code FROM question WHERE item_id=?', (iid,))]
                if st and qs and {q['code'] for q in qs} != set(st): warn.append('η λύση Word έχει διαφορετικούς κωδικούς ερωτημάτων από την εκφώνηση')
            if not d['text'].strip(): warn.append('το έγγραφο δεν έχει κείμενο')
            imgs = []; dest = root / code / '04_TRAPEZA' / 'derived' / iid / 'word'
            if d['images']:
                dest.mkdir(parents=True, exist_ok=True)
                for old in dest.glob(kind + '_*'): old.unlink()
                for n, data in d['images']:
                    (dest / f'{kind}_{n}').write_bytes(data); imgs.append(f'{code}/04_TRAPEZA/derived/{iid}/word/{kind}_{n}')
            st = 'warn' if warn else 'ok'; res['ok' if st == 'ok' else 'warn'] += 1
            c.execute('INSERT OR REPLACE INTO wordsrc(item_id,kind,relpath,sha,mtime,n_par,n_eq,n_img,n_q,pts,status,warn,text,images) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (iid, kind, rel, sha, p.stat().st_mtime, d['n_par'], d['n_eq'], len(imgs), len(qs), sum(q['points'] or 0 for q in qs), st, json.dumps(warn, ensure_ascii=False), d['text'], json.dumps(imgs)))
    c.commit(); return res


def summary(res): return f"αρχεία Word {res['files']}: ΟΚ {res['ok']}, με προειδοποιήσεις {res['warn']}, σφάλματα {res['errors']}"


# ---------- σελίδες ----------
def mark(r):
    if not r: return '—'
    return {'ok': '✔', 'warn': '⚠', 'error': '✖'}.get(r['status'], '?')


@router.get('/word', response_class=HTMLResponse, dependencies=[Depends(auth)])
def word_page(status: str = '', msg: str = ''):
    c = db(); ac = active_course(c); items = {}
    for r in c.execute('SELECT w.*,i.course_code FROM wordsrc w JOIN item i ON i.id=w.item_id' + (' WHERE i.course_code=?' if ac else ''), (ac,) if ac else ()): items.setdefault(r['item_id'], {})[r['kind']] = r
    tot = c.execute('SELECT count(*) FROM item' + (' WHERE course_code=?' if ac else ''), (ac,) if ac else ()).fetchone()[0]; c.close()
    rows = ''; n = {'ok': 0, 'warn': 0, 'error': 0}
    for iid in sorted(items, key=lambda x: int(x) if x.isdigit() else 0):
        s, l = items[iid].get('statement'), items[iid].get('solution'); sts = [x['status'] for x in (s, l) if x]; worst = 'error' if 'error' in sts else ('warn' if 'warn' in sts else 'ok'); n[worst] += 1
        if status in n and worst != status: continue
        ws = [w for x in (s, l) if x for w in json.loads(x['warn'] or '[]')]
        cnt = lambda x: f"{x['n_q']} ερωτ., {x['n_eq']} εξισ., {x['n_img']} εικ." if x and x['status'] != 'error' else ''
        rows += (f"<tr class='w-{worst}'><td><a href='/word/{E(iid)}'>{E(iid)}</a></td><td>{mark(s)} {E(cnt(s))}</td><td>{mark(l)} {E(cnt(l))}</td><td>{E(worst)}</td><td>{E('; '.join(ws)[:300])}</td></tr>")
    note = f"<div class='adm adm-success'><p class=adm-t>{E(msg)}</p></div>" if msg else ''
    flt = ' · '.join(f"<a href='/word?status={k}'>{l} ({n[k]})</a>" for k, l in (('ok', 'ΟΚ'), ('warn', 'προειδοποιήσεις'), ('error', 'σφάλματα'))) + " · <a href='/word'>όλα</a>"
    body = (f"{note}<h2>Word του ΙΕΠ</h2><p>Η εφαρμογή διαβάζει τα <code>&lt;ID&gt;.docx</code> και <code>&lt;ID&gt;_SOLUTION.docx</code> του <code>orig/</code>: κείμενο, εξισώσεις (σε LaTeX), εικόνες, και τα συγκρίνει με το PDF (ερωτήματα και μονάδες). "
            f"Θέματα με Word: {len(items)} από {tot}.</p><form method=post action=/word/scan><button class=primary>Σάρωση αρχείων Word</button></form><p>{flt}</p>"
            f"<div class=scroll><table><tr><th>Θέμα</th><th>Εκφώνηση Word</th><th>Λύση Word</th><th>Κατάσταση</th><th>Προειδοποιήσεις</th></tr>{rows or '<tr><td colspan=5>Καμία εγγραφή. Πάτα «Σάρωση».</td></tr>'}</table></div>")
    return page('Word ΙΕΠ', body)


@router.post('/word/scan', dependencies=[Depends(auth)])
def word_scan(request: Request):
    same_origin(request); from . import config
    c = db(); res = scan(c, config.load()['data_root']); c.close()
    return RedirectResponse('/word?msg=' + quote(summary(res) + ('. ' + res['messages'][0] if res['messages'] else '')), status_code=303)


@router.get('/word/{iid}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def word_item(iid: str):
    c = db(); rows = {r['kind']: r for r in c.execute('SELECT * FROM wordsrc WHERE item_id=?', (iid,))}
    dbq = {r['code']: r['points'] for r in c.execute('SELECT code,points FROM question WHERE item_id=?', (iid,))}; c.close()
    if not rows: raise HTTPException(404, 'Δεν υπάρχει Word για αυτό το θέμα· πάτα Σάρωση στη σελίδα Word')
    out = [f"<p><a href='/word'>← Word ΙΕΠ</a> · <a href='/review/{E(iid)}'>θέμα {E(iid)}</a></p><h2>Θέμα {E(iid)}: Word</h2>"]
    for kind, label in (('statement', 'Εκφώνηση'), ('solution', 'Λύση')):
        r = rows.get(kind)
        if not r: out.append(f'<h3>{label}</h3><p>Δεν υπάρχει αρχείο Word.</p>'); continue
        ws = json.loads(r['warn'] or '[]'); imgs = json.loads(r['images'] or '[]')
        out.append(f"<h3>{label} {mark(r)}</h3><p><small>{E(r['relpath'])} · {r['n_par']} παράγραφοι, {r['n_eq']} εξισώσεις, {r['n_img']} εικόνες, {r['n_q']} ερωτήματα</small></p>")
        if ws: out.append("<div class='adm adm-warning'><p class=adm-t>Προειδοποιήσεις</p><ul>" + ''.join(f'<li>{E(w)}</li>' for w in ws) + '</ul></div>')
        qs = _split(r['text'] or '') or []
        if kind == 'statement' and (qs or dbq):
            wq = {q['code']: q['points'] for q in qs}; codes = sorted(set(wq) | set(dbq), key=lambda x: [int(p) if p.isdigit() else 0 for p in x.replace('_', '.').split('.')])
            out.append('<table><tr><th>Ερώτημα</th><th>Μονάδες PDF</th><th>Μονάδες Word</th></tr>' + ''.join(f"<tr><td>{E(k)}</td><td>{'' if dbq.get(k) is None else dbq[k]}</td><td>{'' if wq.get(k) is None else wq[k]}</td></tr>" if k in wq and k in dbq else f"<tr class=w-warn><td>{E(k)}</td><td>{'' if dbq.get(k) is None else dbq[k]}</td><td>{'' if wq.get(k) is None else wq[k]}</td></tr>" for k in codes) + '</table>')
        out.append(f"<details><summary>Κείμενο (με εξισώσεις σε LaTeX)</summary><pre style='white-space:pre-wrap'>{E(r['text'] or '')}</pre></details>")
        if imgs: out.append('<p>' + ' '.join(f"<a href='/files/{E(i)}' target=_blank><img src='/files/{E(i)}' style='max-height:120px' loading=lazy></a>" for i in imgs) + '</p>')
    return page('Word ' + iid, ''.join(out))
