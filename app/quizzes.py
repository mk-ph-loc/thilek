"""Quiz από τα ερωτήματα της βάσης: Σωστό/Λάθος, πολλαπλής επιλογής και ελεύθερες, με σωστές απαντήσεις (αυτόματες από τη λύση, με έλεγχο από τον καθηγητή)."""
import datetime, json, pathlib
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from .main_auth import auth
from .review import db, page, html, same_origin, fld, chk
from .quizgen import make_items, LET
from . import crops

router = APIRouter()
QUIZ_JS = (pathlib.Path(__file__).parent / 'static' / 'quiz.js').read_text(encoding='utf-8')
KINDS = {'tf': 'Σωστό/Λάθος', 'mcq': 'Πολλαπλής επιλογής', 'free': 'Ελεύθερη (ανάπτυξη)'}
E = html.escape

@router.get('/static/quiz.js', include_in_schema=False)
def quiz_js(): return Response(QUIZ_JS, media_type='application/javascript')

def get_quiz(c, qid):
    q = c.execute('SELECT * FROM quiz WHERE id=?', (qid,)).fetchone()
    if not q: raise HTTPException(404)
    return q

def next_pos(c, qid): return (c.execute('SELECT max(pos) FROM quiz_item WHERE quiz_id=?', (qid,)).fetchone()[0] or 0) + 1

def add_from_questions(c, quiz_id, members):
    """members: [(item_id, qcode)]. Επιστρέφει (προστέθηκαν, χρειάζονται_έλεγχο)."""
    n = bad = 0
    for it, code in members:
        r = c.execute("SELECT q.item_id,q.code,q.points,q.text,q.qtype,q.sol_text,q.has_image,q.geo IS NOT NULL has_geo FROM question q WHERE q.item_id=? AND q.code=?", (it, code)).fetchone()
        if not r: continue
        for d in make_items(dict(r)):
            c.execute('INSERT INTO quiz_item(quiz_id,pos,kind,stem,options,answer,points,feedback,src_item,src_qcode,src_part,use_image,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (quiz_id, next_pos(c, quiz_id), d['kind'], d['stem'], d['options'], d['answer'], d['points'], '', d['src_item'], d['src_qcode'], d['src_part'], d['use_image'], d['status']))
            n += 1; bad += d['status'] == 'review'
    return n, bad

def opts_of(r):
    try: return json.loads(r['options'] or '[]')
    except ValueError: return []

def src_qid(c, r):
    x = c.execute('SELECT id,geo IS NOT NULL g,sol_geo IS NOT NULL s FROM question WHERE item_id=? AND code=?', (r['src_item'], r['src_qcode'])).fetchone() if r['src_item'] else None
    return x

def ans_text(r):
    if r['kind'] == 'mcq' and (r['answer'] or '').isdigit():
        o = opts_of(r); i = int(r['answer']); return f"{LET[i]}. {o[i]}" if i < len(o) else ''
    return r['answer'] or ''

@router.get('/quizzes', response_class=HTMLResponse, dependencies=[Depends(auth)])
def quizzes_list():
    c = db(); rows = c.execute("SELECT z.*,(SELECT count(*) FROM quiz_item WHERE quiz_id=z.id) n,(SELECT count(*) FROM quiz_item WHERE quiz_id=z.id AND status='review') nr,(SELECT sum(points) FROM quiz_item WHERE quiz_id=z.id) pts FROM quiz z ORDER BY z.id DESC").fetchall()
    trs = ''.join(f"<tr><td>{r['id']}</td><td><a href='/quizzes/{r['id']}'>{E(r['name'])}</a></td><td>{r['n']}</td><td>{r['nr'] or 0}</td><td>{r['pts'] or 0}</td><td>{E((r['created'] or '').replace('T', ' '))}</td><td><a href='/quizzes/{r['id']}/play' target=_blank>παιχνίδι</a> · <a href='/quizzes/{r['id']}/print?key=1' target=_blank>εκτύπωση με απαντήσεις</a></td></tr>" for r in rows)
    body = ("<h2>Quiz</h2><form method='post' action='/quizzes/new' class=filters>" + fld('Νέο quiz', "<input name=name size=34 placeholder='όνομα' required>") + "<button>Δημιουργία</button></form>"
            "<p>Quiz φτιάχνεις από τα <a href='/browse'>Ερωτήματα</a> ή την <a href='/coverage'>Ύλη/σελίδα</a> (επιλογή και «Quiz»). Οι ερωτήσεις Σωστό/Λάθος και πολλαπλής επιλογής σπάνε σε επιμέρους στοιχεία με σωστή απάντηση από τη λύση του ΙΕΠ.</p>"
            f"<table><tr><th>#</th><th>Όνομα</th><th>Στοιχεία</th><th>Θέλουν έλεγχο</th><th>Μονάδες</th><th>Δημιουργήθηκε</th><th></th></tr>{trs}</table>")
    return page('Quiz', body)

@router.post('/quizzes/new', dependencies=[Depends(auth)])
def quiz_new(request: Request, name: str = Form(...)):
    same_origin(request); c = db()
    qid = c.execute('INSERT INTO quiz(name,created) VALUES(?,?)', (name.strip()[:200] or 'Quiz', datetime.datetime.now().isoformat(timespec='seconds'))).lastrowid
    c.commit(); c.close(); return RedirectResponse(f'/quizzes/{qid}', status_code=303)

@router.get('/quizzes/{qid}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def quiz_page(qid: int, only: str = '', msg: str = ''):
    c = db(); z = get_quiz(c, qid)
    rows = c.execute('SELECT * FROM quiz_item WHERE quiz_id=? ORDER BY pos', (qid,)).fetchall()
    nrev = sum(1 for r in rows if r['status'] == 'review'); cards = []
    for k, r in enumerate(rows, 1):
        if only == 'review' and r['status'] != 'review': continue
        s = src_qid(c, r); opts = opts_of(r)
        ksel = ''.join(f"<option value={a}{' selected' if a == r['kind'] else ''}>{b}</option>" for a, b in KINDS.items())
        if r['kind'] == 'tf': ans = "<select name=answer>" + ''.join(f"<option value='{v}'{' selected' if r['answer'] == v else ''}>{v or '— (ορίστε)'}</option>" for v in ('', 'Σωστό', 'Λάθος')) + "</select>"
        elif r['kind'] == 'mcq': ans = "<select name=answer><option value=''>— (ορίστε)</option>" + ''.join(f"<option value={i}{' selected' if r['answer'] == str(i) else ''}>{LET[i]}. {E(o[:40])}</option>" for i, o in enumerate(opts) if i < len(LET)) + "</select>"
        else: ans = f"<textarea name=answer rows=3 cols=60>{E(r['answer'])}</textarea>"
        thumbs = ''
        if s and s['g']: thumbs += f"<div><small>Πηγή (εκφώνηση):</small><br><img loading=lazy src='/crop/{s['id']}.jpg?dpi=70' style='max-width:420px'></div>"
        if s and s['s']: thumbs += f"<div><small>Λύση ΙΕΠ:</small><br><img loading=lazy src='/crop/{s['id']}.jpg?sol=1&dpi=70' style='max-width:300px'></div>"
        src = f"θέμα {E(r['src_item'])} ερ. {E(r['src_qcode'])}{' ' + E(r['src_part']) if r['src_part'] else ''}" if r['src_item'] else 'χειροκίνητο'
        badge = "<span class='tag auto'>θέλει έλεγχο</span>" if r['status'] == 'review' else "<span class='tag manual'>ok</span>"
        cards.append(f"""<div class=q><form method='post' action='/quizzes/{qid}/item/{r['id']}'><b>{k}.</b> {badge} · {src} · <select name=kind>{ksel}</select> μονάδες <input name=points value='{r['points']:g}' size=4>
<div class=cols style='grid-template-columns:1fr 1fr'><div>{fld('Εκφώνηση', f"<textarea name=stem rows=4 cols=60>{E(r['stem'])}</textarea>")}{fld('Επιλογές (μία ανά γραμμή, μόνο για πολλαπλής)', f"<textarea name=options rows=3 cols=60>{E(chr(10).join(opts))}</textarea>")}</div>
<div>{fld('Σωστή απάντηση', ans)}{fld('Σχόλιο/εξήγηση (προαιρετικά)', f"<textarea name=feedback rows=2 cols=50>{E(r['feedback'])}</textarea>")}{chk('να εμφανίζεται και η εικόνα της πηγής στο quiz', f"<input type=checkbox name=use_image value=1{' checked' if r['use_image'] else ''}>")}</div></div>
<button name=action value=save>Αποθήκευση (✔ έλεγξα)</button> <button name=action value=up>↑</button><button name=action value=down>↓</button> <button name=action value=delete>✖ διαγραφή</button></form>
<div class=cols style='grid-template-columns:auto auto;justify-content:start;gap:1rem'>{thumbs}</div></div>""")
    meta_name = fld('Όνομα', "<input name=name value='" + E(z['name']) + "' size=36>"); meta_desc = fld('Περιγραφή', "<input name=description value='" + E(z['description'] or '') + "' size=50>")
    body = (f"<h2>Quiz #{qid}: {E(z['name'])}</h2>{f'<p><b>{E(msg)}</b></p>' if msg else ''}<p>{len(rows)} στοιχεία · <b>{nrev}</b> θέλουν έλεγχο · <a href='/quizzes/{qid}/play' target=_blank>παιχνίδι</a> · <a href='/quizzes/{qid}/print' target=_blank>εκτύπωση</a> · <a href='/quizzes/{qid}/print?key=1' target=_blank>με απαντήσεις</a> · <a href='/quizzes/{qid}/json'>JSON</a> · <a href='/quizzes/{qid}/docx'>⬇ Word</a> · <form method='post' action='/docs/from' style='display:inline'><input type=hidden name=kind value=quiz><input type=hidden name=ref value={qid}><button>Μετατροπή σε Markdown</button></form> · "
            f"<a href='/quizzes/{qid}'>όλα</a> · <a href='/quizzes/{qid}?only=review'>μόνο όσα θέλουν έλεγχο</a></p>"
            f"<form method='post' action='/quizzes/{qid}/meta' class=filters>{meta_name}{meta_desc}<button>Αποθήκευση</button></form>"
            f"<p><a class=btn href='/quizzes/{qid}/pick'><b>+ Προσθήκη ερωτημάτων από την τράπεζα θεμάτων</b></a></p><form method='post' action='/quizzes/{qid}/additem' class=filters>{fld('Νέο χειροκίνητο στοιχείο', '<select name=kind>' + ''.join(f'<option value={a}>{b}</option>' for a, b in KINDS.items()) + '</select>')}<button>Προσθήκη</button></form>"
            f"{''.join(cards) or '<p><i>Κενό quiz. Πρόσθεσε ερωτήματα από τη σελίδα Ερωτήματα.</i></p>'}"
            f"<form method='post' action='/quizzes/{qid}/delete' onsubmit=\"return confirm('Διαγραφή quiz;')\"><button>Διαγραφή quiz</button></form>")
    return page(f'Quiz {qid}', body)

@router.post('/quizzes/{qid}/meta', dependencies=[Depends(auth)])
def quiz_meta(qid: int, request: Request, name: str = Form(...), description: str = Form('')):
    same_origin(request); c = db(); get_quiz(c, qid); c.execute('UPDATE quiz SET name=?,description=? WHERE id=?', (name.strip()[:200] or 'Quiz', description.strip()[:500], qid)); c.commit(); c.close()
    return RedirectResponse(f'/quizzes/{qid}', status_code=303)

@router.post('/quizzes/{qid}/additem', dependencies=[Depends(auth)])
def quiz_additem(qid: int, request: Request, kind: str = Form('tf')):
    same_origin(request); c = db(); get_quiz(c, qid)
    if kind not in KINDS: c.close(); raise HTTPException(422)
    c.execute("INSERT INTO quiz_item(quiz_id,pos,kind,stem,options,answer,points,status) VALUES(?,?,?,?,?,?,1,'review')", (qid, next_pos(c, qid), kind, '', '[]', '')); c.commit(); c.close()
    return RedirectResponse(f'/quizzes/{qid}', status_code=303)

@router.post('/quizzes/{qid}/item/{iid}', dependencies=[Depends(auth)])
def quiz_item_save(qid: int, iid: int, request: Request, action: str = Form('save'), kind: str = Form('tf'), stem: str = Form(''), options: str = Form(''), answer: str = Form(''),
                   points: str = Form('1'), feedback: str = Form(''), use_image: str = Form('')):
    same_origin(request); c = db(); get_quiz(c, qid)
    me = c.execute('SELECT pos FROM quiz_item WHERE id=? AND quiz_id=?', (iid, qid)).fetchone()
    if not me: c.close(); raise HTTPException(404)
    if action == 'delete': c.execute('DELETE FROM quiz_item WHERE id=?', (iid,))
    elif action in ('up', 'down'):
        o = c.execute(f"SELECT id,pos FROM quiz_item WHERE quiz_id=? AND pos{'<' if action == 'up' else '>'}? ORDER BY pos {'DESC' if action == 'up' else 'ASC'} LIMIT 1", (qid, me['pos'])).fetchone()
        if o: c.execute('UPDATE quiz_item SET pos=? WHERE id=?', (o['pos'], iid)); c.execute('UPDATE quiz_item SET pos=? WHERE id=?', (me['pos'], o['id']))
    else:
        if kind not in KINDS: c.close(); raise HTTPException(422)
        opts = [x.strip() for x in options.splitlines() if x.strip()][:len(LET)] if kind == 'mcq' else []
        try: pts = max(0.0, min(float(points.replace(',', '.')), 1000.0))
        except ValueError: pts = 1.0
        ans = answer.strip()
        if kind == 'tf' and ans not in ('Σωστό', 'Λάθος'): ans = ''
        if kind == 'mcq' and not (ans.isdigit() and int(ans) < len(opts)): ans = ''
        c.execute("UPDATE quiz_item SET kind=?,stem=?,options=?,answer=?,points=?,feedback=?,use_image=?,status=? WHERE id=?",
                  (kind, stem.strip()[:2000], json.dumps(opts, ensure_ascii=False), ans[:4000], pts, feedback.strip()[:1000], 1 if use_image else 0, 'ok' if (ans and stem.strip()) else 'review', iid))
    c.commit(); c.close(); return RedirectResponse(f'/quizzes/{qid}', status_code=303)

@router.post('/quizzes/{qid}/delete', dependencies=[Depends(auth)])
def quiz_delete(qid: int, request: Request):
    same_origin(request); c = db(); get_quiz(c, qid); c.execute('DELETE FROM quiz_item WHERE quiz_id=?', (qid,)); c.execute('DELETE FROM quiz WHERE id=?', (qid,)); c.commit(); c.close()
    return RedirectResponse('/quizzes', status_code=303)

def item_body(c, r, n, key, embed=False):
    s = src_qid(c, r); opts = opts_of(r)
    img = f"<div><img src='/crop/{s['id']}.jpg' style='max-width:100%'></div>" if r['use_image'] and s and s['g'] else ''
    head = f"<span class=num>{n}.</span> <b>{E(r['stem'])}</b>"
    if r['kind'] == 'tf':
        body = f"<div class=opts><label><input type=radio name=q{r['id']} value='Σωστό'> Σωστό</label> <label><input type=radio name=q{r['id']} value='Λάθος'> Λάθος</label></div>"
    elif r['kind'] == 'mcq':
        body = "<div class=opts>" + ''.join(f"<div><label><input type=radio name=q{r['id']} value='{i}'> {LET[i]}. {E(o)}</label></div>" for i, o in enumerate(opts)) + '</div>'
    else:
        sol = f"<div><img src='/crop/{s['id']}.jpg?sol=1' style='max-width:100%'></div>" if s and s['s'] else ''
        body = f"<details><summary>Απάντηση</summary><div>{E(r['answer'])}</div>{sol}</details>"
    fb = f"<div class=fb hidden>Σωστή απάντηση: <b>{E(ans_text(r))}</b>{' — ' + E(r['feedback']) if r['feedback'] else ''}</div>" if r['kind'] != 'free' else (f"<div class=fb hidden>{E(r['feedback'])}</div>" if r['feedback'] else '')
    return f"<div class='q qi' data-kind='{r['kind']}' data-answer='{E(r['answer'])}' data-points='{r['points']:g}'><div>{head} <small>({r['points']:g} μον.)</small></div>{img}{body}{fb}</div>"

@router.get('/quizzes/{qid}/play', response_class=HTMLResponse, dependencies=[Depends(auth)])
def quiz_play(qid: int):
    c = db(); z = get_quiz(c, qid); rows = c.execute('SELECT * FROM quiz_item WHERE quiz_id=? ORDER BY pos', (qid,)).fetchall()
    if not rows: c.close(); raise HTTPException(404, 'Κενό quiz')
    items = ''.join(item_body(c, r, k, False) for k, r in enumerate(rows, 1)); c.close()
    css = "<style>.qi.ok{outline:3px solid #2e9e5b;border-radius:6px}.qi.bad{outline:3px solid #d9534f;border-radius:6px}.opts label{cursor:pointer}</style>"
    body = (f"{css}<h2>{E(z['name'])}</h2><p>{E(z['description'] or '')}</p><div class=bar><button class=primary id=check>Έλεγχος απαντήσεων</button> <button id=reset>Καθαρισμός</button> <button id=shuffle>Ανακάτεμα</button> <b id=score></b></div>"
            f"<div id=quiz>{items}</div><script src='/static/quiz.js'></script>")
    return page(z['name'], body)

@router.get('/quizzes/{qid}/print', response_class=HTMLResponse, dependencies=[Depends(auth)])
def quiz_print(qid: int, key: int = 0):
    c = db(); z = get_quiz(c, qid); rows = c.execute('SELECT * FROM quiz_item WHERE quiz_id=? ORDER BY pos', (qid,)).fetchall(); out = []
    for k, r in enumerate(rows, 1):
        s = src_qid(c, r); opts = opts_of(r)
        img = f"<div><img src='/crop/{s['id']}.jpg' style='max-width:100%'></div>" if r['use_image'] and s and s['g'] else ''
        if r['kind'] == 'tf': body = f"<div>{'☒' if key and r['answer'] == 'Σωστό' else '☐'} Σωστό &nbsp; {'☒' if key and r['answer'] == 'Λάθος' else '☐'} Λάθος</div>"
        elif r['kind'] == 'mcq': body = ''.join(f"<div>{'☒' if key and r['answer'] == str(i) else '☐'} {LET[i]}. {E(o)}</div>" for i, o in enumerate(opts))
        else: body = f"<div style='min-height:3rem;border-bottom:1px dotted #888'></div>" if not key else f"<div class=ans>{E(r['answer'])}</div>"
        fbk = f"<div class=ans>Σωστή απάντηση: {E(ans_text(r))}{' — ' + E(r['feedback']) if r['feedback'] else ''}</div>" if key and r['kind'] != 'free' else ''
        out.append(f"<div class=q><b>{k}.</b> {E(r['stem'])} <small>({r['points']:g} μον.)</small>{img}{body}{fbk}</div>")
    c.close()
    css = "@page{size:A4;margin:14mm}body{font:15px/1.45 'Segoe UI',Arial,sans-serif;max-width:800px;margin:0 auto;padding:0 .5rem}.q{break-inside:avoid;margin:.7rem 0}.ans{color:#064;font-size:.9em}h1{font-size:1.3rem;border-bottom:2px solid #000}"
    return HTMLResponse(f"<!doctype html><html lang='el'><meta charset='utf-8'><title>{E(z['name'])}</title><style>{css}</style><body><h1>{E(z['name'])}{' – απαντήσεις' if key else ''}</h1>{''.join(out)}</body></html>",
                        headers={'Content-Security-Policy': "default-src 'self'; style-src 'unsafe-inline'; img-src 'self'"})

@router.get('/quizzes/{qid}/json', dependencies=[Depends(auth)])
def quiz_json(qid: int):
    c = db(); z = get_quiz(c, qid); rows = c.execute('SELECT * FROM quiz_item WHERE quiz_id=? ORDER BY pos', (qid,)).fetchall(); c.close()
    items = []
    for r in rows:
        o = opts_of(r); d = {'kind': r['kind'], 'question': r['stem'], 'points': r['points'], 'feedback': r['feedback'] or '', 'source': {'item': r['src_item'], 'question': r['src_qcode'], 'part': r['src_part']}, 'needs_review': r['status'] == 'review'}
        if r['kind'] == 'tf': d['correct'] = r['answer']
        elif r['kind'] == 'mcq': d['options'] = o; d['correct_index'] = int(r['answer']) if (r['answer'] or '').isdigit() else None
        else: d['answer'] = r['answer']
        items.append(d)
    return {'name': z['name'], 'description': z['description'] or '', 'items': items}
