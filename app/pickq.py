"""Επιλογή ερωτημάτων από την τράπεζα θεμάτων μέσα σε quiz (με προεπισκόπηση των στοιχείων που θα προκύψουν)
και συγχώνευση ερωτημάτων σε PDF (δεύτερη καρτέλα της Συγχώνευσης) με προεπισκόπηση και αναδιάταξη."""
import datetime, io, json
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from PIL import Image, ImageDraw, ImageFont
from .main_auth import auth
from .review import db, page, html, same_origin, fld, chk
from .library import select_questions, qtable, filter_card, filters_of, FILTER_KEYS, LIMIT
from .exams import crop_bytes
from .quizgen import make_items
from . import crops

router = APIRouter()
E = html.escape
MERGEQ_JS = (__import__('pathlib').Path(__file__).parent / 'static' / 'mergeq.js').read_text(encoding='utf-8')

@router.get('/static/mergeq.js', include_in_schema=False)
def mergeq_js(): return Response(MERGEQ_JS, media_type='application/javascript')

# ---------- quiz: επιλογή από την τράπεζα ----------
def quiz_preview_cell(c, qid, done):
    r = c.execute('SELECT q.item_id,q.code,q.points,q.text,q.qtype,q.sol_text,q.has_image,q.geo IS NOT NULL has_geo FROM question q WHERE q.id=?', (qid,)).fetchone()
    items = make_items(dict(r)); kinds = {'tf': 'Σ/Λ', 'mcq': 'πολλ. επιλ.', 'free': 'ελεύθερη'}
    cnt = {}
    for d in items: cnt[d['kind']] = cnt.get(d['kind'], 0) + 1
    txt = ', '.join(f"{n}× {kinds.get(k, k)}" for k, n in cnt.items()) or '—'
    rev = sum(1 for d in items if d['status'] == 'review')
    return txt + (f" <span class='tag auto'>{rev} θέλουν έλεγχο</span>" if rev else '') + (" <span class='tag manual'>ήδη στο quiz</span>" if (r['item_id'], r['code']) in done else '')

@router.get('/quizzes/{zid}/pick', response_class=HTMLResponse, dependencies=[Depends(auth)])
def quiz_pick(zid: int, request: Request, thumbs: int = 0):
    c = db(); z = c.execute('SELECT name FROM quiz WHERE id=?', (zid,)).fetchone()
    if not z: c.close(); raise HTTPException(404)
    f = filters_of(request.query_params); rows = select_questions(c, f)
    done = {(r[0], r[1]) for r in c.execute('SELECT src_item,src_qcode FROM quiz_item WHERE quiz_id=?', (zid,))}
    t = qtable(rows, bool(thumbs))
    # στήλη «τι θα προκύψει»: προστίθεται στο τέλος κάθε γραμμής
    import re
    cells = iter(quiz_preview_cell(c, r['qid'], done) for r in rows)
    t = t.replace('</th></tr>', '</th><th>Στοιχεία quiz που θα προκύψουν</th></tr>', 1)
    t = re.sub(r'</td></tr>', lambda m: f'</td><td>{next(cells)}</td></tr>', t)
    back = f'/quizzes/{zid}/pick?' + request.url.query
    body = (f"<h2>Quiz #{zid}: {E(z['name'])} — προσθήκη από την τράπεζα θεμάτων</h2><p><a href='/quizzes/{zid}'>← πίσω στο quiz</a></p>{filter_card(c, f, f'/quizzes/{zid}/pick', thumbs=thumbs)}"
            f"<form method=post action='/quizzes/{zid}/pick'><input type=hidden name=back value='{E(back)}'><p><button class=primary>Προσθήκη των επιλεγμένων στο quiz</button> · επιλεγμένα: <span id=count>0</span> · {len(rows)} ερωτήματα (έως {LIMIT}). "
            "Κάθε ερώτημα σπάει σε στοιχεία (α., β., γ.) με σωστή απάντηση από τη λύση του ΙΕΠ· όσα έχουν αβέβαιη απάντηση σημειώνονται «θέλει έλεγχο».</p>" + t + "</form>")
    c.close(); return page('Quiz: επιλογή ερωτημάτων', body)

@router.post('/quizzes/{zid}/pick', dependencies=[Depends(auth)])
def quiz_pick_do(zid: int, request: Request, qids: list[int] = Form([]), back: str = Form('')):
    same_origin(request); c = db()
    if not c.execute('SELECT 1 FROM quiz WHERE id=?', (zid,)).fetchone(): c.close(); raise HTTPException(404)
    members = []
    for q in dict.fromkeys(qids):
        r = c.execute('SELECT item_id,code FROM question WHERE id=?', (q,)).fetchone()
        if r: members.append((r[0], r[1]))
    if not members: c.close(); raise HTTPException(422, 'Δεν επιλέχθηκε ερώτημα.')
    from .quizzes import add_from_questions
    n, bad = add_from_questions(c, zid, members); c.commit(); c.close()
    return RedirectResponse(f'/quizzes/{zid}?msg=Προστέθηκαν {n} στοιχεία από {len(members)} ερωτήματα' + (f' ({bad} θέλουν έλεγχο).' if bad else '.'), status_code=303)

# ---------- συγχώνευση ερωτημάτων ----------
MAXQ = 150; DPI = 150; PW, PH, MG = 1240, 1754, 110      # A4 στα 150 dpi

def tabs(cur):
    return ("<div class=tabs>" + ''.join(f"<a class='tab{' on' if k == cur else ''}' href='{h}'>{t}</a>" for k, h, t in (('items', '/tools/merge', 'Συγχώνευση εγγράφων (ολόκληρα θέματα)'), ('questions', '/tools/merge?tab=questions', 'Συγχώνευση ερωτημάτων (με προεπισκόπηση)'))) + "</div>")

def questions_tab(request):
    c = db(); f = filters_of(request.query_params); thumbs = 1 if request.query_params.get('thumbs') else 0
    rows = select_questions(c, f)
    body = (f"<h2>Συγχώνευση PDF</h2>{tabs('questions')}<p>Διάλεξε ερωτήματα από όλη την τράπεζα (με φίλτρα), δες προεπισκόπηση, άλλαξε σειρά και φτιάξε ένα PDF από τις εικόνες των ερωτημάτων.</p>"
            + filter_card(c, f, '/tools/merge', {'tab': 'questions'}, thumbs)
            + f"<form method=post action='/tools/merge/preview'><p><button class=primary>Προεπισκόπηση →</button> · επιλεγμένα: <span id=count>0</span> · {len(rows)} ερωτήματα (έως {LIMIT}, το PDF έως {MAXQ})</p>" + qtable(rows, bool(thumbs)) + "</form>")
    c.close(); return page('Συγχώνευση ερωτημάτων', body)

def qinfo(c, qid):
    return c.execute('SELECT q.id,q.item_id,q.code,q.points,q.geo,q.sol_geo FROM question q WHERE q.id=?', (qid,)).fetchone()

@router.post('/tools/merge/preview', response_class=HTMLResponse, dependencies=[Depends(auth)])
def preview(request: Request, qids: list[int] = Form([])):
    same_origin(request); qids = list(dict.fromkeys(qids)); c = db()
    if not qids: c.close(); raise HTTPException(422, 'Δεν επιλέχθηκε ερώτημα.')
    if len(qids) > MAXQ: c.close(); raise HTTPException(422, f'Πάνω από {MAXQ} ερωτήματα.')
    lis = []
    for q in qids:
        r = qinfo(c, q)
        if not r: continue
        body = f"<img loading=lazy src='/crop/{q}.jpg?dpi=80' alt=''>" if r['geo'] else '<i>χωρίς εικόνα PDF — θα παραλειφθεί</i>'
        sol = ' <small>(έχει λύση)</small>' if r['sol_geo'] else ''
        lis.append(f"<li class=pq data-q='{q}'><input type=hidden name=qids value={q}><div class=pqh><span class=pqn></span> <small>θέμα {E(r['item_id'])} ερ. {E(r['code'])}{sol}</small> "
                   f"<button type=button data-act=up>↑</button><button type=button data-act=down>↓</button><button type=button data-act=del>✖ αφαίρεση</button></div>{body}</li>")
    c.close()
    opts = ("<fieldset class=bar2><legend>Επιλογές PDF</legend>"
            "<div>Διάταξη: <label><input type=radio name=layout value=flow checked> συνεχής (πολλά ερωτήματα ανά σελίδα)</label> <label><input type=radio name=layout value=page> ένα ερώτημα ανά σελίδα</label></div>"
            "<div>Λύσεις: <label><input type=radio name=sols value=none checked> καμία</label> <label><input type=radio name=sols value=after> μετά από κάθε ερώτημα</label> <label><input type=radio name=sols value=end> στο τέλος</label></div>"
            "<div><label><input type=checkbox name=numbers value=1 checked> αρίθμηση 1., 2., 3. στο περιθώριο</label></div>"
            "<button class=primary formtarget=_blank name=dl value=0>Προβολή PDF (νέα καρτέλα)</button> <button name=dl value=1>Λήψη PDF</button></fieldset>")
    body = (f"<h2>Προεπισκόπηση συγχώνευσης ερωτημάτων</h2>{tabs('questions')}<p><a href='/tools/merge?tab=questions'>← πίσω στην επιλογή</a> · <span id=pqcount>{len(lis)}</span> ερωτήματα. Η σειρά εδώ είναι η σειρά στο PDF.</p>"
            f"<form method=post action='/tools/merge/questions'>{opts}<ol class=pqlist>{''.join(lis)}</ol></form><script src='/static/mergeq.js'></script>")
    return page('Προεπισκόπηση συγχώνευσης', body)

def font(size):
    try: return ImageFont.load_default(size=size)
    except TypeError: return ImageFont.load_default()

def to_img(c, qid, sol):
    got = crop_bytes(c, qid, sol, DPI)
    if not got: return None
    im = Image.open(io.BytesIO(got[0])).convert('RGB'); cw = PW - 2 * MG
    w = min(im.width, cw)
    if w < im.width: im = im.resize((w, max(1, int(im.height * w / im.width))), Image.LANCZOS)
    mh = PH - 2 * MG
    if im.height > mh: im = im.resize((max(1, int(im.width * mh / im.height)), mh), Image.LANCZOS)
    return im

def build_questions(c, qids, layout, sols, numbers):
    """Επιστρέφει (pdf_bytes, σελίδες, παραλείφθηκαν)."""
    pages = []; state = {'img': None, 'draw': None, 'y': MG}; skipped = 0; f = font(34)
    def newpage():
        im = Image.new('RGB', (PW, PH), 'white'); state.update(img=im, draw=ImageDraw.Draw(im), y=MG); pages.append(im)
    def place(im, label=None, bar=False):
        if state['img'] is None or state['y'] + im.height > PH - MG: newpage()
        y = state['y']; state['img'].paste(im, (MG, y))
        if label and numbers: state['draw'].text((MG - 72, y + 4), label, fill='black', font=f)
        if bar: state['draw'].rectangle([MG - 14, y, MG - 8, y + im.height], fill=(120, 120, 120))
        state['y'] = y + im.height + 36
    solq = []
    for n, q in enumerate(qids, 1):
        im = to_img(c, q, 0)
        if im is None: skipped += 1; continue
        if layout == 'page': newpage()
        place(im, f'{n}.')
        if sols != 'none':
            s = to_img(c, q, 1)
            if s is not None:
                if sols == 'after': place(s, None, True)
                else: solq.append((n, s))
    if solq:
        newpage()
        for n, s in solq: place(s, f'{n}.', True)
    if not pages: return None, 0, skipped
    buf = io.BytesIO(); pages[0].save(buf, 'PDF', resolution=float(DPI), save_all=True, append_images=pages[1:]); return buf.getvalue(), len(pages), skipped

@router.post('/tools/merge/questions', dependencies=[Depends(auth)])
def merge_questions(request: Request, qids: list[int] = Form([]), layout: str = Form('flow'), sols: str = Form('none'), numbers: str = Form(''), dl: str = Form('0')):
    same_origin(request); qids = list(dict.fromkeys(qids))
    if not qids: raise HTTPException(422, 'Δεν επιλέχθηκε ερώτημα.')
    if len(qids) > MAXQ: raise HTTPException(422, f'Πάνω από {MAXQ} ερωτήματα.')
    c = db()
    try: data, n, skipped = build_questions(c, qids, 'page' if layout == 'page' else 'flow', sols if sols in ('after', 'end') else 'none', bool(numbers))
    finally: c.close()
    if not data: raise HTTPException(422, 'Κανένα από τα ερωτήματα δεν έχει εικόνα PDF.')
    name = f"thilek-ereotimata-{datetime.date.today():%Y%m%d}-{len(qids)}.pdf"
    return Response(data, media_type='application/pdf', headers={'Content-Disposition': f'{"attachment" if dl == "1" else "inline"}; filename="{name}"', 'X-Pages': str(n), 'X-Skipped': str(skipped)})
