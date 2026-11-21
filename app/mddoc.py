"""Έγγραφα Markdown: δημιουργία από διαγωνίσματα/quiz/επιλογές, επεξεργαστής με ζωντανή προεπισκόπηση, λήψη ως .md, HTML και Word (.docx)."""
import base64, datetime, io, pathlib, re
from urllib.parse import parse_qs, urlparse
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from markdown_it import MarkdownIt
from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from .main_auth import auth
from .review import db, page, html, same_origin, fld
from . import config, crops, mdgen
from .mdmath import protect, restore, math_to_text, PH
from . import omml
from .solstyle import STYLES
from docx.oxml import parse_xml, OxmlElement
from docx.text.paragraph import Paragraph
from .exams import crop_bytes
from .library import expand

router = APIRouter()
E = html.escape
MD_JS = (pathlib.Path(__file__).parent / 'static' / 'md.js').read_text(encoding='utf-8')
CROP = re.compile(r'^/crop/(\d+)\.jpg(\?.*)?$')
MAX_MD = 400_000

@router.get('/static/md.js', include_in_schema=False)
def md_js(): return Response(MD_JS, media_type='application/javascript')

def parser():
    return MarkdownIt('commonmark', {'html': False}).enable('table')

def crop_args(src):
    m = CROP.match(src or '')
    if not m: return None
    q = parse_qs(urlparse(src).query)
    return int(m.group(1)), int((q.get('sol') or ['0'])[0] == '1'), int((q.get('dpi') or ['110'])[0] or 110)

def render_html(c, md_text, embed=False):
    md = parser()
    def image(*a):                                  # (tokens, idx, options, env) ή (self, tokens, idx, options, env)
        tokens, idx = a[-4], a[-3]; t = tokens[idx]; src = t.attrGet('src') or ''; alt = t.content or ''
        ca = crop_args(src)
        if ca and embed:
            r = crop_bytes(c, ca[0], ca[1], ca[2])
            src = 'data:image/jpeg;base64,' + base64.b64encode(r[0]).decode() if r else ''
        elif not ca and not (src.startswith('/preview/') or src.startswith('/files/')): return ''      # μόνο εικόνες του συστήματος
        return f"<img src='{E(src)}' alt='{E(alt)}' loading=lazy style='max-width:100%'>"
    md.renderer.rules['image'] = image
    src, maths = protect(md_text)                   # τύποι $..$/$$..$$ μένουν ακέραιοι (το CommonMark θα έτρωγε \\, \\; κ.λπ.)
    return restore(md.render(src), maths)

# ---------- Word ----------
def files_image(src):
    """/files/<σχετική διαδρομή> -> (bytes, πλάτος σε ίντσες) ή None. Μόνο μέσα στο data_root, μόνο png/jpg (το Word δεν δέχεται svg)."""
    import os
    from PIL import Image
    if not src.startswith('/files/') or '..' in src or not re.match(r'^/files/[A-Za-z0-9_./-]+\.(png|jpe?g)$', src, re.I): return None
    root = os.path.realpath(config.load()['data_root']); p = os.path.realpath(os.path.join(root, src[len('/files/'):]))
    if not p.startswith(root + os.sep) or not os.path.isfile(p): return None
    try:
        data = open(p, 'rb').read(); im = Image.open(io.BytesIO(data)); dpi = (im.info.get('dpi') or (96, 96))[0] or 96
        return data, min(im.size[0] / float(dpi), 6.4)
    except Exception: return None

MO, MP = '{%s}oMath' % omml.M_NS, '{%s}oMathPara' % omml.M_NS
MW = 'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'

def add_text(par, content, maths, bold, em, made):
    """Κείμενο με placeholders τύπων -> runs και εξισώσεις Word (OMML). Τύπος που δεν μετατρέπεται γράφεται ως αναγνώσιμο κείμενο.
    $$..$$ μπαίνει σε δική του παράγραφο (η υπόλοιπη πρόταση συνεχίζει σε νέα). Επιστρέφει την τρέχουσα παράγραφο."""
    def run(txt):
        r = par.add_run(txt); r.bold = bool(bold) or None; r.italic = bool(em) or None
    if not maths: run(content); return par
    parts = PH.split(content)
    for k, part in enumerate(parts):
        if k % 2 == 0:
            if part: run(part)
            continue
        m = maths[int(part)] if int(part) < len(maths) else ''
        disp = m.startswith('$$'); x = omml.latex_to_omml(m[2:-2].strip() if disp else m[1:-1], disp)
        if x is None: run(math_to_text(m)); continue
        el = parse_xml(x.replace('<m:oMath', f'<m:oMath {MW}', 1) if not disp else x.replace('<m:oMathPara>', f'<m:oMathPara {MW}>', 1))
        if not disp: par._p.append(el); continue
        mp = OxmlElement('w:p'); par._p.addnext(mp); mp.append(el)
        nxt = OxmlElement('w:p'); mp.addnext(nxt); np_ = Paragraph(nxt, par._parent)
        try: np_.style = par.style
        except Exception: pass
        made.append(np_); par = np_
    return par

def add_inline(doc, par, children, c, base_bold=False, maths=None):
    """maths: τα math spans που προστάτευσε το md_to_docx· γράφονται ως εξισώσεις Word (OMML), με εφεδρεία αναγνώσιμο κείμενο."""
    bold = em = 0; made = []
    for ch in children or []:
        t = ch.type
        if t == 'strong_open': bold += 1
        elif t == 'strong_close': bold -= 1
        elif t == 'em_open': em += 1
        elif t == 'em_close': em -= 1
        elif t in ('text',): par = add_text(par, ch.content, maths, bold or base_bold, em, made)
        elif t == 'code_inline':
            r = par.add_run(ch.content); r.font.name = 'Consolas'
        elif t == 'softbreak': par.add_run(' ')
        elif t == 'hardbreak': par.add_run().add_break()
        elif t == 'image':
            ca = crop_args(ch.attrGet('src') or ''); got = crop_bytes(c, ca[0], ca[1], ca[2]) if ca else None
            fi = None if got else files_image(ch.attrGet('src') or '')
            if got:
                w = min(crops.width_pt(got[1]) / 72.0, 6.4)
                par.add_run().add_picture(io.BytesIO(got[0]), width=Inches(w))
            elif fi: par.add_run().add_picture(io.BytesIO(fi[0]), width=Inches(fi[1]))
            else: par.add_run('[εικόνα]')
        elif t in ('link_open', 'link_close'): pass
    for p in made:                                   # άδειες παράγραφοι που περίσσεψαν μετά από τελευταίο $$..$$
        if not p.runs and not p._p.findall(MO) and not p._p.findall(MP) and p._p.getparent() is not None: p._p.getparent().remove(p._p)

def cell_len(kids):
    return sum(6 if ch.type == 'text' and PH.search(ch.content) else len(ch.content) for ch in kids or [] if ch.type in ('text', 'code_inline')) + 2

def table_widths(tb, cells, nc, total=6.6):
    """Πίνακας σε πλήρες πλάτος σελίδας, στήλες ανάλογες του περιεχομένου (ελάχιστο 12%, μέγιστο 70%)."""
    w = [max((cell_len(r[ci][0]) if ci < len(r) else 0) for r in cells) for ci in range(nc)]; s = sum(w) or 1
    fr = [min(max(x / s, 0.12), 0.7) for x in w]; fs = sum(fr); tb.autofit = False
    pr = tb._tbl.tblPr; tw = pr.find(qn('w:tblW'))
    if tw is None: tw = OxmlElement('w:tblW'); pr.append(tw)
    tw.set(qn('w:type'), 'dxa'); tw.set(qn('w:w'), str(int(total * 1440)))
    for ci in range(nc):
        for row in tb.rows: row.cells[ci].width = Inches(total * fr[ci] / fs)
        tb.columns[ci].width = Inches(total * fr[ci] / fs)

def md_to_docx(c, md_text, title=''):
    doc = Document()
    for s in doc.sections: s.left_margin = s.right_margin = Inches(0.9); s.top_margin = s.bottom_margin = Inches(0.8)
    st = doc.styles['Normal']; st.font.name = 'Calibri'; st.font.size = Pt(11); st.element.rPr.rFonts.set(qn('w:eastAsia'), 'Calibri')
    sm = re.search(r'^\[thilek-style\]:\s*#(\w+)\s*$', md_text, re.M)          # αόρατος ορισμός από την εξαγωγή λύσεων: χρώματα επικεφαλίδων
    hcol = STYLES[sm.group(1)]['doc'] if sm and sm.group(1) in STYLES else None
    md_text, maths = protect(md_text, only_tex=True)          # $..$ με \ ^ _ ή γράμματα -> κείμενο· ποσά «$5» μένουν όπως είναι
    toks = parser().parse(md_text); lists = []; quote = 0; i = 0
    cells, row, in_head = None, None, False
    while i < len(toks):
        t = toks[i]; ty = t.type
        if ty == 'heading_open':
            inl = toks[i + 1]; lv = min(int(t.tag[1]), 4); p = doc.add_heading('', level=lv); add_inline(doc, p, inl.children, c, maths=maths); i += 3
            if hcol:
                for r_ in p.runs: r_.font.color.rgb = RGBColor.from_string(hcol[lv])
            continue
        if ty == 'paragraph_open':
            inl = toks[i + 1]
            if inl.content.strip() == '\\newpage': doc.add_page_break(); i += 3; continue
            style = None
            if lists: style = ('List Bullet' if lists[-1] == 'ul' else 'List Number') + (f' {min(len(lists), 3)}' if len(lists) > 1 else '')
            elif quote: style = 'Quote'
            p = doc.add_paragraph(style=style); add_inline(doc, p, inl.children, c, maths=maths); i += 3; continue
        if ty == 'bullet_list_open': lists.append('ul')
        elif ty == 'ordered_list_open': lists.append('ol')
        elif ty in ('bullet_list_close', 'ordered_list_close'): lists.pop()
        elif ty == 'blockquote_open': quote += 1
        elif ty == 'blockquote_close': quote -= 1
        elif ty in ('fence', 'code_block'):
            p = doc.add_paragraph(); r = p.add_run(restore(t.content.rstrip('\n'), maths, lambda m: m)); r.font.name = 'Consolas'; r.font.size = Pt(10)
        elif ty == 'hr': doc.add_paragraph('────────────────────────')
        elif ty == 'table_open': cells = []
        elif ty == 'tr_open': row = []
        elif ty in ('th_open', 'td_open'):
            row.append((toks[i + 1].children, ty == 'th_open')); i += 3; continue
        elif ty == 'tr_close': cells.append(row)
        elif ty == 'table_close':
            if cells and cells[0]:
                nc = max(len(r) for r in cells); tb = doc.add_table(rows=len(cells), cols=nc); tb.style = 'Table Grid'
                for ri, r in enumerate(cells):
                    for ci, (kids, head) in enumerate(r): add_inline(doc, tb.cell(ri, ci).paragraphs[0], kids, c, base_bold=head, maths=maths)
                table_widths(tb, cells, nc)
            cells = None
        i += 1
    buf = io.BytesIO(); doc.save(buf); return buf.getvalue()

# ---------- αποθήκευση ----------
def new_doc(c, name, md_text, source=''):
    now = datetime.datetime.now().isoformat(timespec='seconds')
    return c.execute('INSERT INTO mdoc(name,markdown,source,created,updated) VALUES(?,?,?,?,?)', (name.strip()[:200] or 'Έγγραφο', md_text[:MAX_MD], source, now, now)).lastrowid

def get_doc(c, did):
    d = c.execute('SELECT * FROM mdoc WHERE id=?', (did,)).fetchone()
    if not d: raise HTTPException(404)
    return d

def slug(name, did):
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', '_', (name or 'έγγραφο')).strip(' ._')[:60] or 'έγγραφο'
    return f'{did}-{s}'

@router.get('/docs', response_class=HTMLResponse, dependencies=[Depends(auth)])
def docs_list(msg: str = ''):
    c = db(); rows = c.execute('SELECT id,name,source,created,updated,length(markdown) n FROM mdoc ORDER BY id DESC').fetchall(); dbp = config.load()['db']; c.close()
    trs = ''.join(f"<tr><td><input type=checkbox name=ids value={r['id']} class=selbox></td><td>{r['id']}</td><td><a href='/docs/{r['id']}'>{E(r['name'])}</a></td><td>{E(r['source'] or '')}</td><td>{r['n']}</td><td>{E((r['created'] or '').replace('T', ' '))}</td><td>{E((r['updated'] or '').replace('T', ' '))}</td>"
                  f"<td><small>βάση · mdoc #{r['id']}</small></td><td><a href='/docs/{r['id']}/docx' title='Κατεβάζει το έγγραφο ως Word'>Word</a> · <a href='/docs/{r['id']}/md' title='Κατεβάζει το έγγραφο ως .md'>.md</a></td></tr>" for r in rows)
    bulk = ("<div class=bar><button type=button data-selall='ids' title='Επιλέγει όλα τα έγγραφα της λίστας'>☑ Όλα</button> <button type=button data-selnone='ids' title='Αφαιρεί κάθε επιλογή'>☐ Κανένα</button> "
            "<button name=act value=zipmd title='Ένα zip με ένα αρχείο .md για κάθε επιλεγμένο έγγραφο'>⬇ zip .md</button> <button name=act value=zipdocx title='Ένα zip με ένα Word για κάθε επιλεγμένο έγγραφο'>⬇ zip Word</button> "
            "<button name=act value=savesrv title='Γράφει τα επιλεγμένα ως αρχεία .md στον server (07_EXAGOGES/docs) για να τα βλέπεις στο File browser'>💾 Αντίγραφο στον server</button> "
            "<button name=act value=delete class=danger title='Διαγράφει τα επιλεγμένα από τη βάση. Πρώτα κρατιέται αντίγραφο στον Κάδο και ζητείται επιβεβαίωση'>🗑 Διαγραφή</button> <span>επιλεγμένα: <b id=count>0</b></span></div>")
    body = ("<h2>Έγγραφα Markdown</h2>" + (f"<p><b>{E(msg)}</b></p>" if msg else '')
            + f"<div class=note><b>Πού αποθηκεύονται:</b> τα έγγραφα ζουν <b>μέσα στη βάση SQLite</b>, στον πίνακα <code>mdoc</code> (στήλη <code>markdown</code>), στο αρχείο <code>{E(dbp)}</code>. Δεν είναι αρχεία στον δίσκο. "
              "Για να υπάρχουν και ως αρχεία (και να τα βλέπεις στο <a href='/fb'>File browser</a>) διάλεξέ τα και πάτα «Αντίγραφο στον server». Η βάση παίρνει ημερήσιο backup και το rebuild δεν σβήνει τα έγγραφα.</div>"
            + "<form method='post' action='/docs/new' class=filters>" + fld('Νέο κενό έγγραφο', "<input name=name size=30 placeholder='όνομα' required>") + "<button>Δημιουργία</button></form>"
            "<form method='post' action='/docs/upload' enctype='multipart/form-data' class=filters>" + fld('Εισαγωγή αρχείου .md/.txt', "<input type=file name=file accept='.md,.markdown,.txt' required>") + "<button>Εισαγωγή</button></form>"
            "<p>Έγγραφα δημιουργείς και από τα Διαγωνίσματα, τα Quiz, τις Συλλογές και τη μπάρα ενεργειών των Ερωτημάτων («Μετατροπή σε Markdown»).</p>"
            f"<form method=post action='/docs/bulk'>{bulk}<table><tr><th></th><th>#</th><th>Όνομα</th><th>Προέλευση</th><th>Χαρακτήρες</th><th>Δημιουργία</th><th>Τελευταία αλλαγή</th><th>Θέση αποθήκευσης</th><th></th></tr>{trs}</table></form>")
    return page('Έγγραφα Markdown', body)

@router.post('/docs/bulk', dependencies=[Depends(auth)])
def docs_bulk(request: Request, act: str = Form(...), ids: list[int] = Form([]), confirm: str = Form('')):
    same_origin(request)
    if not ids: return RedirectResponse('/docs?msg=' + 'Διάλεξε+πρώτα+έγγραφα+με+τα+τετράγωνα.', status_code=303)
    import zipfile, os, tempfile, json as _json
    c = db(); docs = [d for d in (c.execute('SELECT * FROM mdoc WHERE id=?', (i,)).fetchone() for i in ids) if d]
    if act in ('zipmd', 'zipdocx'):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            for d in docs:
                if act == 'zipmd': z.writestr(slug(d['name'], d['id']) + '.md', d['markdown'])
                else: z.writestr(slug(d['name'], d['id']) + '.docx', md_to_docx(c, d['markdown']))
        c.close(); return Response(buf.getvalue(), media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="thilek-docs-{act[3:]}.zip"'})
    if act == 'savesrv':
        r = c.execute('SELECT code FROM course ORDER BY code LIMIT 1').fetchone(); root = os.path.realpath(config.load()['data_root'])
        if not r: c.close(); return RedirectResponse('/docs?msg=' + 'Δεν+υπάρχει+μάθημα+στη+βάση.', status_code=303)
        d0 = os.path.join(root, r['code'], '07_EXAGOGES', 'docs'); os.makedirs(d0, exist_ok=True); n = 0
        for d in docs:
            path = os.path.realpath(os.path.join(d0, slug(d['name'], d['id']) + '.md'))
            if not path.startswith(root + os.sep): continue
            pathlib.Path(path).write_text(d['markdown'], encoding='utf-8'); n += 1
        c.execute('INSERT INTO fileops(ts,op,path,detail) VALUES(?,?,?,?)', (datetime.datetime.now().isoformat(timespec='seconds'), 'docs→server', f"{r['code']}/07_EXAGOGES/docs", f'{n} αρχεία')); c.commit(); c.close()
        return RedirectResponse('/docs?msg=' + f'Γράφτηκαν+{n}+αρχεία+στο+{r["code"]}/07_EXAGOGES/docs+(File+browser).', status_code=303)
    if act == 'delete':
        if not confirm:
            names = ''.join(f"<li>#{d['id']} {E(d['name'])} ({len(d['markdown'])} χαρ.)</li>" for d in docs); hid = ''.join(f"<input type=hidden name=ids value={d['id']}>" for d in docs); c.close()
            return page('Επιβεβαίωση διαγραφής', "<h2>⚠ Διαγραφή εγγράφων</h2><div class='note warn' style='border-left:5px solid #e69500;padding:.5rem .8rem;background:var(--code)'>Θα διαγραφούν από τη βάση "
                        f"<b>{len(docs)}</b> έγγραφα:<ul>{names}</ul>Πριν τη διαγραφή κρατιέται αντίγραφο .md στον <a href='/fb/trash'>Κάδο</a> (από εκεί «Επαναφορά» τα ξαναβάζει ως νέα έγγραφα).</div>"
                        f"<form method=post action='/docs/bulk'>{hid}<input type=hidden name=act value=delete><label><input type=checkbox name=confirm value=1 required> καταλαβαίνω, διαγραφή</label> <button class=danger>🗑 Διαγραφή</button> <a class=btn href='/docs'>Άκυρο</a></form>")
        root = os.path.realpath(config.load()['data_root']); ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S'); d0 = os.path.join(root, '_kados', ts + '-docs'); os.makedirs(d0, exist_ok=True)
        for d in docs:
            fn = slug(d['name'], d['id']) + '.md'; pathlib.Path(d0, fn).write_text(d['markdown'], encoding='utf-8')
            c.execute('INSERT INTO trash(orig_rel,trash_rel,kind,size,deleted,reason) VALUES(?,?,?,?,?,?)', (f"έγγραφο MD: {d['name']}", f"_kados/{ts}-docs/{fn}", 'mdoc', len(d['markdown'].encode('utf-8')), datetime.datetime.now().isoformat(timespec='seconds'), _json.dumps({'name': d['name'], 'source': d['source']}, ensure_ascii=False)))
            c.execute('DELETE FROM mdoc WHERE id=?', (d['id'],))
        c.commit(); c.close(); return RedirectResponse('/docs?msg=' + f'Διαγράφηκαν+{len(docs)}+έγγραφα+(αντίγραφο+στον+Κάδο).', status_code=303)
    c.close(); raise HTTPException(422)

@router.post('/docs/new', dependencies=[Depends(auth)])
def doc_new(request: Request, name: str = Form(...)):
    same_origin(request); c = db(); did = new_doc(c, name, f'# {name.strip()}\n\n', 'κενό'); c.commit(); c.close(); return RedirectResponse(f'/docs/{did}', status_code=303)

@router.post('/docs/upload', dependencies=[Depends(auth)])
async def doc_upload(request: Request, file: UploadFile = File(...)):
    same_origin(request); raw = await file.read(MAX_MD + 1)
    if len(raw) > MAX_MD: raise HTTPException(413, 'Μεγάλο αρχείο')
    try: text = raw.decode('utf-8-sig')
    except UnicodeDecodeError: raise HTTPException(422, 'Το αρχείο πρέπει να είναι UTF-8')
    c = db(); did = new_doc(c, pathlib.Path(file.filename or 'έγγραφο').stem, text, 'εισαγωγή'); c.commit(); c.close(); return RedirectResponse(f'/docs/{did}', status_code=303)

@router.post('/docs/from', dependencies=[Depends(auth)])
def doc_from(request: Request, kind: str = Form(...), ref: int = Form(0), mode: str = Form('image')):
    """kind: exam|quiz|collection. Μετατρέπει σε Markdown και ανοίγει στον επεξεργαστή."""
    same_origin(request); c = db(); mode = mode if mode in ('image', 'text', 'both') else 'image'
    if kind == 'exam':
        e = c.execute('SELECT title FROM exam WHERE id=?', (ref,)).fetchone()
        if not e: c.close(); raise HTTPException(404)
        md, name, src = mdgen.exam_md(c, ref, mode), e['title'], f'διαγώνισμα #{ref}'
    elif kind == 'quiz':
        z = c.execute('SELECT name FROM quiz WHERE id=?', (ref,)).fetchone()
        if not z: c.close(); raise HTTPException(404)
        md, name, src = mdgen.quiz_md(c, ref), z['name'], f'quiz #{ref}'
    elif kind == 'collection':
        from .collections import member_rows
        k = c.execute('SELECT name FROM collection WHERE id=?', (ref,)).fetchone()
        if not k: c.close(); raise HTTPException(404)
        md, name, src = mdgen.members_md(c, [(r['item_id'], r['code']) for r in member_rows(c, ref)], k['name'], mode), k['name'], f'συλλογή #{ref}'
    else: c.close(); raise HTTPException(422)
    did = new_doc(c, name, md, src); c.commit(); c.close(); return RedirectResponse(f'/docs/{did}', status_code=303)

@router.get('/docs/{did}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def doc_page(did: int, msg: str = ''):
    c = db(); d = get_doc(c, did); c.close()
    bar = ("<div class=mdbar><button type=button data-wrap='**'><b>B</b></button><button type=button data-wrap='*'><i>I</i></button><button type=button data-prefix='## '>Τίτλος</button><button type=button data-prefix='- '>Λίστα</button>"
           "<button type=button data-prefix='> '>Παράθεση</button><button type=button data-insert='\\n\\n\\\\newpage\\n\\n'>Αλλαγή σελίδας</button> <input id=qimg size=6 placeholder='# ερωτήματος'><button type=button id=addimg>+ εικόνα ερωτήματος</button>"
           "<button type=button id=addsol>+ εικόνα λύσης</button></div>")
    name_fld = fld('Όνομα', "<input name=name value='" + E(d['name']) + "' size=40>")
    body = (f"<h2>Έγγραφο #{did}</h2>{f'<p><b>{E(msg)}</b></p>' if msg else ''}<form method='post' action='/docs/{did}/save' id=mdform>"
            f"<div class=filters>{name_fld}<button class=primary>Αποθήκευση (Ctrl+S)</button> "
            f"<a href='/docs/{did}/docx'>⬇ Word (.docx)</a> <a href='/docs/{did}/md'>⬇ Markdown</a> <a href='/docs/{did}/html'>⬇ HTML αυτόνομο</a> <a href='/docs' >Λίστα</a></div>{bar}"
            f"<div class=cols style='grid-template-columns:1fr 1fr'><textarea id=md name=md spellcheck=false style='width:100%;height:72vh;font:14px/1.45 Consolas,monospace'>{E(d['markdown'])}</textarea>"
            f"<div id=preview class=pane style='background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:.6rem;height:72vh'></div></div></form>"
            "<p><small>Εικόνες ερωτημάτων: <code>![](/crop/ΑΡΙΘΜΟΣ.jpg)</code>, λύσεων: <code>![](/crop/ΑΡΙΘΜΟΣ.jpg?sol=1)</code>. Αλλαγή σελίδας στο Word: γραμμή <code>\\newpage</code>. Υποστηρίζονται τίτλοι, έντονα/πλάγια, λίστες, πίνακες, παραθέσεις.</small></p>"
            "<style>#preview table{border-collapse:collapse;width:100%}#preview td,#preview th{border:1px solid var(--border);padding:.25rem .5rem}#preview .katex{font-size:1.12em}</style>"
            "<link rel=stylesheet href='/static/vendor/katex/katex.min.css'><script src='/static/vendor/katex/katex.min.js'></script><script src='/static/vendor/katex/auto-render.min.js'></script>"
            "<script src='/static/md.js'></script>")
    return page(f'Έγγραφο {did}', body)

@router.post('/docs/render', dependencies=[Depends(auth)])
def doc_render(request: Request, md: str = Form('')):
    same_origin(request)
    if len(md) > MAX_MD: raise HTTPException(413)
    c = db(); out = render_html(c, md); c.close(); return HTMLResponse(out)

@router.post('/docs/{did}/save', dependencies=[Depends(auth)])
def doc_save(did: int, request: Request, name: str = Form(...), md: str = Form('')):
    same_origin(request)
    if len(md) > MAX_MD: raise HTTPException(413)
    c = db(); get_doc(c, did); c.execute('UPDATE mdoc SET name=?,markdown=?,updated=? WHERE id=?', (name.strip()[:200] or 'Έγγραφο', md.replace('\r\n', '\n'), datetime.datetime.now().isoformat(timespec='seconds'), did)); c.commit(); c.close()
    return RedirectResponse(f'/docs/{did}?msg=' + 'Αποθηκεύτηκε.', status_code=303)

@router.get('/docs/{did}/md', dependencies=[Depends(auth)])
def doc_md(did: int):
    c = db(); d = get_doc(c, did); c.close(); return Response(d['markdown'], media_type='text/markdown; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="thilek-doc-{did}.md"'})

@router.get('/docs/{did}/html', dependencies=[Depends(auth)])
def doc_html(did: int):
    c = db(); d = get_doc(c, did); body = render_html(c, d['markdown'], embed=True); c.close()
    css = "body{font:15px/1.5 'Segoe UI',Arial,sans-serif;max-width:820px;margin:1rem auto;padding:0 1rem}table{border-collapse:collapse}td,th{border:1px solid #888;padding:.2rem .5rem}blockquote{border-left:3px solid #aaa;margin-left:0;padding-left:.8rem;color:#444}"
    return Response(f"<!doctype html><html lang='el'><meta charset='utf-8'><title>{E(d['name'])}</title><style>{css}</style><body>{body}</body></html>", media_type='text/html; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="thilek-doc-{did}.html"'})

DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
@router.get('/docs/{did}/docx', dependencies=[Depends(auth)])
def doc_docx(did: int):
    c = db(); d = get_doc(c, did); data = md_to_docx(c, d['markdown']); c.close()
    return Response(data, media_type=DOCX, headers={'Content-Disposition': f'attachment; filename="thilek-doc-{did}.docx"'})

@router.get('/exams/{eid}/docx', dependencies=[Depends(auth)])
def exam_docx(eid: int):
    c = db()
    if not c.execute('SELECT 1 FROM exam WHERE id=?', (eid,)).fetchone(): c.close(); raise HTTPException(404)
    data = md_to_docx(c, mdgen.exam_md(c, eid, 'image')); c.close()
    return Response(data, media_type=DOCX, headers={'Content-Disposition': f'attachment; filename="thilek-exam-{eid}.docx"'})

@router.get('/quizzes/{qid}/docx', dependencies=[Depends(auth)])
def quiz_docx(qid: int, key: int = 1):
    c = db()
    if not c.execute('SELECT 1 FROM quiz WHERE id=?', (qid,)).fetchone(): c.close(); raise HTTPException(404)
    data = md_to_docx(c, mdgen.quiz_md(c, qid, bool(key))); c.close()
    return Response(data, media_type=DOCX, headers={'Content-Disposition': f'attachment; filename="thilek-quiz-{qid}.docx"'})
