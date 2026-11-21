"""Αναζήτηση πλήρους κειμένου στο βιβλίο και στα ερωτήματα της τράπεζας θεμάτων."""
import html, re, sqlite3, subprocess, tempfile, pathlib
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from .main_auth import auth
from .review import db, page, same_origin, fld, chk, TYPES, TYPE_OPTS
from .library import qtable, action_bar
from .tools_merge import safe_path
from . import config, searchindex as si

router = APIRouter()
E = html.escape
BOOK_LIMIT, Q_LIMIT = 40, 200

def has_index(c):
    try: return c.execute('SELECT count(*) FROM book_page').fetchone()[0] > 0
    except sqlite3.OperationalError: return False

def rows_for(c, qids, qtype='', image=''):
    """Γραμμές ερωτημάτων (ίδιες στήλες με το qtable) με τη σειρά των qids."""
    if not qids: return []
    w, a = ['q.id IN (%s)' % ','.join('?' * len(qids))], list(qids)
    if qtype in TYPES: w.append('q.qtype=?'); a.append(qtype)
    if image in ('0', '1'): w.append('q.has_image=?'); a.append(int(image))
    got = {r['qid']: dict(r) for r in c.execute("""SELECT q.id qid,q.item_id,q.code,q.points,q.qtype,q.has_image,q.text,q.geo IS NOT NULL has_geo,i.iep_yli,i.position,i.course_code,
        (SELECT group_concat(tag,', ') FROM question_tag t WHERE t.item_id=q.item_id AND t.qcode=q.code) tags,
        EXISTS (SELECT 1 FROM question_fav v WHERE v.item_id=q.item_id AND v.qcode=q.code) fav
        FROM question q JOIN item i ON i.id=q.item_id WHERE """ + ' AND '.join(w), a)}
    return [got[i] for i in qids if i in got]

def page_sections(c, bid, p):
    return c.execute("SELECT code,title_el FROM section WHERE book_id=? AND level=3 AND page_from<=? AND COALESCE(page_to,page_from)>=? ORDER BY page_from,code", (bid, p, p)).fetchall()

def page_questions(c, bid, pages):
    """Ερωτήματα (μη απορριμμένες συνδέσεις) που καλύπτουν τις τυπωμένες σελίδες· επιστρέφει λίστα qids."""
    seen, out = set(), []
    for p in pages:
        for r in c.execute("""SELECT DISTINCT q.id FROM question_section qs JOIN question q ON q.id=qs.question_id JOIN section s ON s.id=qs.section_id
            WHERE s.book_id=? AND s.level=3 AND qs.origin!='rejected' AND s.page_from<=? AND COALESCE(s.page_to,s.page_from)>=? ORDER BY CAST(q.item_id AS INTEGER),q.id""", (bid, p, p)):
            if r[0] not in seen: seen.add(r[0]); out.append(r[0])
    return out

@router.get('/search', response_class=HTMLResponse, dependencies=[Depends(auth)])
def search(request: Request, q: str = '', scope: str = 'all', qtype: str = '', image: str = '', sort: str = 'rank', msg: str = ''):
    c = db(); terms = si.parse_query(q); sel = "<option value=''>— όλοι —</option>" + TYPE_OPTS(qtype)
    img = ''.join(f"<option value='{v}'{' selected' if image == v else ''}>{t}</option>" for v, t in (('', '— όλα —'), ('1', 'με εικόνα'), ('0', 'χωρίς εικόνα')))
    sc = ''.join(f"<option value={v}{' selected' if scope == v else ''}>{t}</option>" for v, t in (('all', 'βιβλίο και ερωτήματα'), ('book', 'μόνο βιβλίο'), ('questions', 'μόνο ερωτήματα')))
    form = ("<form method=get class=filters>" + fld('Αναζήτηση', f"<input name=q value='{E(q)}' size=34 autofocus placeholder='π.χ. νόμος ohm, \"ηλεκτρικό ρεύμα\", αντιστ'>") + fld('Πού', f"<select name=scope>{sc}</select>")
            + fld('Σειρά βιβλίου', "<select name=sort><option value=rank%s>συνάφεια</option><option value=page%s>σελίδα</option></select>" % ('' if sort == 'page' else ' selected', ' selected' if sort == 'page' else '')) + fld('Τύπος ερωτήματος', f"<select name=qtype>{sel}</select>") + fld('Εικόνα', f"<select name=image>{img}</select>") + "<button class=primary>Αναζήτηση</button></form>"
            "<p><small>Αγνοεί τόνους και κεφαλαία/πεζά· οι λέξεις ταιριάζουν και ως αρχή λέξης (<code>αντιστ</code> βρίσκει «αντίσταση»). Με εισαγωγικά ψάχνεις ακριβή φράση.</small></p>")
    ok = has_index(c); msg_h = f'<p><b>{E(msg)}</b></p>' if msg else ''
    if not ok:
        c.close(); return page('Αναζήτηση', f"<h2>Αναζήτηση</h2>{msg_h}<p>Το ευρετήριο δεν έχει χτιστεί ακόμη.</p><form method=post action='/search/reindex'><button class=primary>Χτίσιμο ευρετηρίου τώρα</button></form>")
    stat = c.execute('SELECT count(*) FROM book_page').fetchone()[0]
    body = f"<h2>Αναζήτηση</h2>{msg_h}{form}"
    if not terms:
        c.close(); return page('Αναζήτηση', body + f"<p>Ευρετήριο: {stat} σελίδες βιβλίου. <form method=post action='/search/reindex' style='display:inline'><button>Ανανέωση ευρετηρίου</button></form></p>")
    expr = si.fts_expr(terms); top_pages = []; bt = qt = lt = ''
    try:
        if scope in ('all', 'book'):
            hits = c.execute("""SELECT p.id,p.book_id,p.printed,p.text FROM book_fts f JOIN book_page p ON p.id=f.rowid WHERE book_fts MATCH ? ORDER BY bm25(book_fts) LIMIT ?""", (expr, BOOK_LIMIT)).fetchall()
            if sort == 'page': hits = sorted(hits, key=lambda h: (h['book_id'], h['printed']))
            trs = []
            for h in hits:
                secs = ', '.join(f"{E(s['code'])} {E(s['title_el'] or '')}" for s in page_sections(c, h['book_id'], h['printed']))
                nq = len(page_questions(c, h['book_id'], [h['printed']])); top_pages.append((h['book_id'], h['printed']))
                trs.append(f"<tr><td><a href='/book/{h['book_id']}/{h['printed']}?q={E(q)}'>σελ. {h['printed']}</a></td><td>{secs}</td><td>{si.snippet(h['text'], terms)}</td><td>{nq}</td></tr>")
            bt = f"<h3>Βιβλίο — {len(hits)} σελίδες{' (έως ' + str(BOOK_LIMIT) + ')' if len(hits) == BOOK_LIMIT else ''}</h3>" + (f"<table><tr><th>Σελίδα</th><th>Ενότητα</th><th>Απόσπασμα</th><th>Ερωτήματα</th></tr>{''.join(trs)}</table>" if trs else '<p>Καμία σελίδα.</p>')
        direct = []
        if scope in ('all', 'questions'):
            ids = [r[0] for r in c.execute('SELECT rowid FROM q_fts WHERE q_fts MATCH ? ORDER BY bm25(q_fts) LIMIT ?', (expr, Q_LIMIT))]
            direct = rows_for(c, ids, qtype, image)
            qt = f"<h3>Ερωτήματα με αυτές τις λέξεις — {len(direct)}</h3>" + (qtable(direct, False) if direct else '<p>Κανένα ερώτημα.</p>')
        if scope in ('all', 'book') and top_pages:
            bid = top_pages[0][0]; have = {r['qid'] for r in direct}
            ids = [i for i in page_questions(c, bid, [p for b, p in top_pages if b == bid][:15]) if i not in have][:Q_LIMIT]
            linked = rows_for(c, ids, qtype, image)
            lt = f"<h3>Ερωτήματα συνδεδεμένα με τις πρώτες σελίδες που βρέθηκαν — {len(linked)}</h3>" + (qtable(linked, False) if linked else '<p>Κανένα.</p>')
    except sqlite3.OperationalError as e:
        c.close(); return page('Αναζήτηση', body + f"<p>Μη έγκυρη αναζήτηση ({E(str(e))}).</p>")
    bar = action_bar(c, {'type': 'search', 'q': q}, '/search?' + request.url.query) if (qt or lt) else ''
    c.close()
    return page('Αναζήτηση: ' + q, body + bt + f"<form method=post action='/select/act'>{bar}{qt}{lt}</form>")

@router.post('/search/reindex', dependencies=[Depends(auth)])
def reindex(request: Request):
    same_origin(request); c = db()
    try: pg, nq = si.reindex(c, config.load()['data_root'])
    finally: c.close()
    return RedirectResponse(f'/search?msg=Ευρετήριο: {pg} σελίδες βιβλίου, {nq} ερωτήματα.', status_code=303)

def book_row(c, bid):
    b = c.execute('SELECT * FROM book WHERE id=?', (bid,)).fetchone()
    if not b: raise HTTPException(404)
    return b

@router.get('/book/{bid}/{printed}.jpg', dependencies=[Depends(auth)])
def book_img(bid: int, printed: int, dpi: int = 90):
    c = db(); b = book_row(c, bid); c.close(); p = safe_path(b['relpath']); n = printed + b['pdf_offset']
    if not p or n < 1: raise HTTPException(404)
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run(['pdftoppm', '-jpeg', '-singlefile', '-r', str(max(40, min(dpi, 150))), '-f', str(n), '-l', str(n), p, str(pathlib.Path(d) / 'p')], capture_output=True, timeout=60)
        f = pathlib.Path(d) / 'p.jpg'
        if r.returncode or not f.exists(): raise HTTPException(404)
        return Response(f.read_bytes(), media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=600'})

@router.get('/book/{bid}/{printed}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def book_page_view(bid: int, printed: int, q: str = ''):
    c = db(); b = book_row(c, bid)
    try: row = c.execute('SELECT text FROM book_page WHERE book_id=? AND printed=?', (bid, printed)).fetchone()
    except sqlite3.OperationalError: row = None
    if not row: c.close(); raise HTTPException(404, 'Η σελίδα δεν υπάρχει στο ευρετήριο')
    terms = si.parse_query(q); lo, hi = c.execute('SELECT min(printed),max(printed) FROM book_page WHERE book_id=?', (bid,)).fetchone()
    qs = '?q=' + E(q) if q else ''
    nav = (f"<a rel=prev href='/book/{bid}/{printed - 1}{qs}'>← προηγούμενη</a> " if printed > lo else '') + f"<b>σελίδα {printed}</b> " + (f" <a rel=next href='/book/{bid}/{printed + 1}{qs}'>επόμενη →</a>" if printed < hi else '')
    secs = ''.join(f"<li>{E(s['code'])} {E(s['title_el'] or '')}</li>" for s in page_sections(c, bid, printed))
    rows = rows_for(c, page_questions(c, bid, [printed]))
    qh = (f"<h3>Ερωτήματα που καλύπτουν τη σελίδα — {len(rows)}</h3><form method=post action='/select/act'>{action_bar(c, {'type': 'bookpage', 'page': printed}, f'/book/{bid}/{printed}{qs}')}{qtable(rows, False)}</form>") if rows else '<p>Κανένα ερώτημα δεν είναι συνδεδεμένο με αυτή τη σελίδα.</p>'
    txt = si.highlight(row['text'], terms) if terms else E(row['text'])
    body = (f"<h2>{E(b['title_el'] or '')}</h2><div class=bar>{nav} · <a href='/search?q={E(q)}'>πίσω στην αναζήτηση</a> · <a target=_blank href='/files/{E(b['relpath'])}#page={printed + b['pdf_offset']}'>↗ PDF</a></div>"
            f"<ul>{secs}</ul><div class=cols style='grid-template-columns:1fr 1fr'><div class=pane style='max-height:82vh;overflow:auto'><img src='/book/{bid}/{printed}.jpg' alt='σελίδα {printed}'></div><div class=pane style='max-height:82vh;overflow:auto'><pre style='white-space:pre-wrap'>{txt}</pre></div></div>{qh}")
    c.close(); return page(f'Βιβλίο σελ. {printed}', body)
