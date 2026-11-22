"""0.26: μαθήματα (ενεργό μάθημα) και θέματα με πηγή: Τράπεζα ΙΕΠ (TTDD), Πανελλήνιες (PAN), Δικά μου (OWN).
Τα θέματα PAN/OWN γράφονται στους πίνακες item/question (source=PAN|OWN) με αριθμητικό ID (PAN 800001+, OWN 900001+), ώστε να δουλεύουν οι λύσεις <ID>.<θέμα>-<υπ>.md,
οι εξαγωγές και ο wizard όπως τα θέματα ΙΕΠ. Δεν έχουν PDF· εμφανίζονται ως κείμενο (Markdown/LaTeX)."""
import html, re
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from urllib.parse import quote
from .main_auth import auth
from .review import db, page, same_origin, fld
from .library import TYPES, TYPE_OPTS, active_course, SRC

router = APIRouter()
E = html.escape
BASE = {'PAN': 800000, 'OWN': 900000}
LABEL = {k: v for k, v in SRC if k}
CODE = re.compile(r'^\d{1,3}(\.\d{1,3}){0,2}$')


def next_id(c, src):
    lo = BASE[src]; r = c.execute('SELECT max(CAST(id AS INTEGER)) FROM item WHERE source=? AND CAST(id AS INTEGER)>?', (src, lo)).fetchone()[0]
    return str((r or lo) + 1)


def set_active(c, code):
    c.execute('INSERT OR REPLACE INTO setting(k,v) VALUES(?,?)', ('course_active', code)); c.commit()


@router.get('/courses', response_class=HTMLResponse, dependencies=[Depends(auth)])
def courses_page(msg: str = ''):
    c = db(); act = active_course(c); rows = ''
    for r in c.execute('SELECT code,title_el,grade FROM course ORDER BY code'):
        n = {s: c.execute('SELECT count(*) FROM item WHERE course_code=? AND source=?', (r['code'], s)).fetchone()[0] for s in LABEL}
        q = c.execute('SELECT count(*) FROM question x JOIN item i ON i.id=x.item_id WHERE i.course_code=?', (r['code'],)).fetchone()[0]
        on = r['code'] == act
        rows += (f"<tr{' class=cur' if on else ''}><td><b>{E(r['title_el'])}</b><br><small>{E(r['code'])} {E(r['grade'] or '')}</small></td><td>{n['TTDD']}</td><td>{n['PAN']}</td><td>{n['OWN']}</td><td>{q}</td>"
                 f"<td>{'<b>ενεργό</b>' if on else ''}<form method=post action=/courses/select style='display:inline'><input type=hidden name=code value='{E(r['code'])}'><button>{'Ενεργό' if on else 'Επιλογή'}</button></form></td></tr>")
    c.close(); note = f"<div class='adm adm-success'><p class=adm-t>{E(msg)}</p></div>" if msg else ''
    body = (f"{note}<h2>Μαθήματα</h2><p>Το <b>ενεργό μάθημα</b> φιλτράρει τα ερωτήματα στη λίστα, την περιήγηση και τον wizard. "
            "<form method=post action=/courses/select style='display:inline'><input type=hidden name=code value=''><button>Όλα τα μαθήματα</button></form> "
            f"Ενεργό τώρα: <b>{E(act or 'όλα')}</b>.</p><div class=scroll><table><tr><th>Μάθημα</th><th>Θέματα ΙΕΠ</th><th>Πανελλήνιες</th><th>Δικά μου</th><th>Ερωτήματα</th><th></th></tr>{rows or '<tr><td colspan=6>Κανένα μάθημα· τρέξε rebuild.</td></tr>'}</table></div>"
            "<p><a class=btn href='/own'>Πανελλήνιες και δικά μου θέματα</a></p>"
            "<p><small>Νέο μάθημα προστίθεται στο αρχείο <code>courses.json</code> στη ρίζα δεδομένων και μετά rebuild (δες Οδηγίες §31).</small></p>")
    return page('Μαθήματα', body)


@router.post('/courses/select', dependencies=[Depends(auth)])
async def courses_select(request: Request):
    same_origin(request); f = await request.form(); code = str(f.get('code') or ''); c = db()
    if code and not c.execute('SELECT 1 FROM course WHERE code=?', (code,)).fetchone(): c.close(); raise HTTPException(422, 'Άγνωστο μάθημα')
    set_active(c, code); c.close()
    return RedirectResponse('/courses?msg=' + quote('Ενεργό μάθημα: ' + (code or 'όλα')), status_code=303)


@router.get('/own', response_class=HTMLResponse, dependencies=[Depends(auth)])
def own_list(src: str = '', msg: str = ''):
    c = db(); ac = active_course(c); w = "i.source IN ('PAN','OWN')"; a = []
    if src in ('PAN', 'OWN'): w = 'i.source=?'; a = [src]
    if ac: w += ' AND i.course_code=?'; a.append(ac)
    rows = c.execute(f"SELECT i.id,i.source,i.course_code,o.title,o.year,(SELECT count(*) FROM question WHERE item_id=i.id) nq,(SELECT sum(points) FROM question WHERE item_id=i.id) pts FROM item i LEFT JOIN ownitem o ON o.item_id=i.id WHERE {w} ORDER BY i.source,CAST(i.id AS INTEGER)", a).fetchall(); c.close()
    tr = ''.join(f"<tr><td><a href='/own/{E(r['id'])}'>{E(r['id'])}</a></td><td>{E(LABEL[r['source']])}</td><td>{E(r['course_code'] or '')}</td><td>{E(r['title'] or '')}</td><td>{E(r['year'] or '')}</td><td>{r['nq']}</td><td>{r['pts'] or 0}</td><td><a href='/review/{E(r['id'])}'>έλεγχος</a></td></tr>" for r in rows)
    note = f"<div class='adm adm-success'><p class=adm-t>{E(msg)}</p></div>" if msg else ''
    body = (f"{note}<h2>Πανελλήνιες και δικά μου θέματα</h2><p>Θέματα χωρίς PDF: γράφονται σε Markdown/LaTeX και χρησιμοποιούνται σε λίστες, wizard, εξαγωγές και λύσεις όπως τα θέματα της τράπεζας. "
            f"<a class=btn href='/own/new?source=OWN'>+ Δικό μου θέμα</a> <a class=btn href='/own/new?source=PAN'>+ Θέμα πανελληνίων</a> · <a href='/own'>όλα</a> · <a href='/own?src=PAN'>πανελλήνιες</a> · <a href='/own?src=OWN'>δικά μου</a>"
            + (f" · ενεργό μάθημα: <b>{E(ac)}</b>" if ac else '') + f"</p><div class=scroll><table><tr><th>ID</th><th>Πηγή</th><th>Μάθημα</th><th>Τίτλος</th><th>Έτος</th><th>Ερωτήματα</th><th>Μονάδες</th><th></th></tr>{tr or '<tr><td colspan=8>Κανένα θέμα.</td></tr>'}</table></div>")
    return page('Δικά μου θέματα', body)


def form_html(c, item, own, qs, source, course, err=''):
    cs = ''.join(f"<option value='{E(r['code'])}'{' selected' if r['code'] == course else ''}>{E(r['title_el'])} ({E(r['code'])})</option>" for r in c.execute('SELECT code,title_el FROM course ORDER BY code'))
    so = ''.join(f"<option value={k}{' selected' if k == source else ''}>{E(v)}</option>" for k, v in LABEL.items() if k in ('PAN', 'OWN'))
    rows = ''
    for i, q in enumerate(list(qs) + [{} for _ in range(3)]):
        rows += (f"<tr><td><input class=r-txt name=qc_{i} size=6 value='{E(str(q.get('code', '')))}'></td><td><input class=r-txt name=qp_{i} size=4 value='{E(str(q.get('points', '') if q.get('points') is not None else ''))}'></td>"
                 f"<td><select class=r-list name=qt_{i}><option value=''>—</option>{TYPE_OPTS(q.get('qtype') or '')}</select></td><td><textarea class=r-txt name=qx_{i} rows=4 style='width:100%;min-width:260px;box-sizing:border-box'>{E(q.get('text') or '')}</textarea></td></tr>")
    err = f"<div class='adm adm-danger'><p class=adm-t>{E(err)}</p></div>" if err else ''
    dele = (f"<form method=post action='/own/{E(item)}/delete' style='margin-top:1em'><label class=f>Για διαγραφή γράψε ΔΙΑΓΡΑΦΗ <input class=r-txt name=confirm size=10></label> <button class=danger>Διαγραφή θέματος</button></form>" if item else '')
    return (f"{err}<h2>{'Θέμα ' + E(item) if item else 'Νέο θέμα'}</h2><form method=post action='/own/save'><input type=hidden name=item value='{E(item or '')}'>"
            + fld('Μάθημα', f"<select class=r-list name=course>{cs}</select>") + fld('Πηγή', f"<select class=r-list name=source>{so}</select>")
            + fld('Τίτλος', f"<input class=r-txt name=title size=40 value='{E(own.get('title') or '')}'>") + fld('Έτος/ημερομηνία', f"<input class=r-txt name=year size=12 value='{E(own.get('year') or '')}'>")
            + fld('Σημείωση', f"<input class=r-txt name=note size=50 value='{E(own.get('note') or '')}'>")
            + "<p><small>Κάθε γραμμή είναι ένα ερώτημα. Κωδικός της μορφής <code>2.1</code> ή <code>3</code>. Κείμενο σε Markdown με τύπους LaTeX (<code>$U=I\\cdot R$</code>). "
              "Για να σβήσεις ερώτημα άδειασε τον κωδικό και το κείμενο. Άδειες γραμμές αγνοούνται.</small></p>"
            f"<div class=scroll><table><tr><th>Κωδικός</th><th>Μονάδες</th><th>Τύπος</th><th>Κείμενο</th></tr>{rows}</table></div><button class=primary>Αποθήκευση</button> <a href='/own'>Άκυρο</a></form>{dele}")


@router.get('/own/new', response_class=HTMLResponse, dependencies=[Depends(auth)])
def own_new(source: str = 'OWN'):
    c = db(); body = form_html(c, '', {}, [], source if source in ('PAN', 'OWN') else 'OWN', active_course(c)); c.close(); return page('Νέο θέμα', body)


@router.get('/own/{item}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def own_edit(item: str):
    c = db(); i = c.execute("SELECT * FROM item WHERE id=? AND source IN ('PAN','OWN')", (item,)).fetchone()
    if not i: c.close(); raise HTTPException(404, 'Δεν βρέθηκε δικό μου θέμα ή θέμα πανελληνίων με αυτό το ID')
    own = c.execute('SELECT * FROM ownitem WHERE item_id=?', (item,)).fetchone() or {}
    qs = [dict(r) for r in c.execute('SELECT code,points,qtype,text FROM question WHERE item_id=?', (item,))]
    qs.sort(key=lambda q: [int(x) for x in q['code'].split('.') if x.isdigit()])
    body = form_html(c, item, dict(own) if own else {}, qs, i['source'], i['course_code']); c.close(); return page('Θέμα ' + item, body)


@router.post('/own/save', dependencies=[Depends(auth)])
async def own_save(request: Request):
    same_origin(request); f = await request.form(); c = db(); item = str(f.get('item') or '').strip(); src = str(f.get('source') or '')
    course = str(f.get('course') or ''); title = str(f.get('title') or '').strip()[:200]; year = str(f.get('year') or '').strip()[:40]; note = str(f.get('note') or '').strip()[:300]
    def fail(msg): 
        c.close(); raise HTTPException(422, msg)
    if src not in BASE: fail('Άκυρη πηγή')
    if not c.execute('SELECT 1 FROM course WHERE code=?', (course,)).fetchone(): fail('Άγνωστο μάθημα')
    if item:
        i = c.execute("SELECT source FROM item WHERE id=? AND source IN ('PAN','OWN')", (item,)).fetchone()
        if not i: fail('Το θέμα δεν είναι δικό μου/πανελληνίων')
    qs = {}; idx = sorted({int(k.split('_')[1]) for k in f.keys() if re.match(r'^q[cptx]_\d{1,3}$', k)})
    for n in idx:
        code = str(f.get(f'qc_{n}') or '').strip(); text = str(f.get(f'qx_{n}') or '').strip(); pts = str(f.get(f'qp_{n}') or '').strip(); qt = str(f.get(f'qt_{n}') or '').strip()
        if not code and not text: continue
        if not CODE.match(code): fail(f'Άκυρος κωδικός ερωτήματος «{code}» (π.χ. 2.1)')
        if code in qs: fail(f'Διπλός κωδικός ερωτήματος {code}')
        if pts and not pts.isdigit(): fail(f'Οι μονάδες του {code} πρέπει να είναι ακέραιος αριθμός')
        if qt and qt not in TYPES: fail(f'Άκυρος τύπος στο {code}')
        qs[code] = (int(pts) if pts else None, text[:20000], qt or None)
    if not item:
        item = next_id(c, src); c.execute('INSERT INTO item(id,course_code,source,solution_status) VALUES(?,?,?,?)', (item, course, src, 'own'))
    else: c.execute('UPDATE item SET course_code=?,source=? WHERE id=?', (course, src, item))
    c.execute('INSERT OR REPLACE INTO ownitem(item_id,title,year,note) VALUES(?,?,?,?)', (item, title, year, note))
    have = {r['code']: r['id'] for r in c.execute('SELECT id,code FROM question WHERE item_id=?', (item,))}
    for code, (pts, text, qt) in qs.items():
        if code in have: c.execute("UPDATE question SET points=?,text=?,qtype=?,qtype_origin='manual' WHERE id=?", (pts, text, qt, have[code]))
        else: c.execute("INSERT INTO question(item_id,code,points,text,qtype,qtype_origin) VALUES(?,?,?,?,?,'manual')", (item, code, pts, text, qt))
    for code, qid in have.items():
        if code not in qs: c.execute('DELETE FROM question_section WHERE question_id=?', (qid,)); c.execute('DELETE FROM question WHERE id=?', (qid,))
    c.commit(); c.close()
    return RedirectResponse('/own?msg=' + quote(f'Αποθηκεύτηκε το θέμα {item}.'), status_code=303)


@router.post('/own/{item}/delete', dependencies=[Depends(auth)])
async def own_delete(item: str, request: Request):
    same_origin(request); f = await request.form()
    if str(f.get('confirm') or '').strip() != 'ΔΙΑΓΡΑΦΗ': raise HTTPException(422, 'Γράψε ΔΙΑΓΡΑΦΗ για επιβεβαίωση')
    c = db()
    if not c.execute("SELECT 1 FROM item WHERE id=? AND source IN ('PAN','OWN')", (item,)).fetchone(): c.close(); raise HTTPException(404, 'Δεν βρέθηκε')
    for t in ('question_section',): c.execute('DELETE FROM question_section WHERE question_id IN (SELECT id FROM question WHERE item_id=?)', (item,))
    for t in ('question_tag', 'question_fav', 'exam_question', 'iepcmp', 'qsolution'): c.execute(f'DELETE FROM {t} WHERE item_id=?', (item,))
    c.execute('DELETE FROM question WHERE item_id=?', (item,)); c.execute('DELETE FROM ownitem WHERE item_id=?', (item,)); c.execute('DELETE FROM item WHERE id=?', (item,)); c.commit(); c.close()
    return RedirectResponse('/own?msg=' + quote(f'Διαγράφηκε το θέμα {item} (τα αρχεία λύσεων .md δεν διαγράφονται).'), status_code=303)
