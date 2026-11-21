"""Παραγωγός διαγωνισμάτων: σύνθεση από ερωτήματα της βάσης (εικόνες κομμένες από τα PDF του ΙΕΠ)."""
import datetime, json, random
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from .main_auth import auth
from .review import db, page, html, same_origin, TYPES, TYPE_OPTS
from .tools_merge import safe_path
from . import crops

router = APIRouter()
LETTERS = 'ΑΒΓΔΕΖΗΘ'; MAX_GROUPS = len(LETTERS)

def get_exam(c, eid):
    e = c.execute('SELECT * FROM exam WHERE id=?', (eid,)).fetchone()
    if not e: raise HTTPException(404)
    return e

def exam_rows(c, eid):
    return c.execute("""SELECT eq.grp,eq.pos,eq.item_id,eq.qcode,q.id qid,q.points,q.qtype,q.has_image,q.geo,q.sol_geo,i.iep_yli,i.position,i.solution_path
        FROM exam_question eq LEFT JOIN question q ON q.item_id=eq.item_id AND q.code=eq.qcode LEFT JOIN item i ON i.id=eq.item_id
        WHERE eq.exam_id=? ORDER BY eq.grp,eq.pos""", (eid,)).fetchall()

def renumber(c, eid):
    for g, in c.execute('SELECT DISTINCT grp FROM exam_question WHERE exam_id=?', (eid,)).fetchall():
        for n, r in enumerate(c.execute('SELECT item_id,qcode FROM exam_question WHERE exam_id=? AND grp=? ORDER BY pos', (eid, g)).fetchall(), 1):
            c.execute('UPDATE exam_question SET pos=? WHERE exam_id=? AND item_id=? AND qcode=?', (n, eid, r['item_id'], r['qcode']))

def add_questions(c, eid, qids, grp):
    grp = max(1, min(int(grp), MAX_GROUPS)); added = 0
    pos = (c.execute('SELECT max(pos) FROM exam_question WHERE exam_id=? AND grp=?', (eid, grp)).fetchone()[0] or 0)
    for qid in qids:
        q = c.execute('SELECT item_id,code FROM question WHERE id=?', (qid,)).fetchone()
        if not q or c.execute('SELECT 1 FROM exam_question WHERE exam_id=? AND item_id=? AND qcode=?', (eid, q['item_id'], q['code'])).fetchone(): continue
        pos += 1; added += 1
        c.execute('INSERT INTO exam_question(exam_id,grp,pos,item_id,qcode) VALUES(?,?,?,?,?)', (eid, grp, pos, q['item_id'], q['code']))
    return added

def candidates(c, eid, qtypes, yli, section, image, one_per_item):
    w = ['q.geo IS NOT NULL', 'q.points IS NOT NULL', "NOT EXISTS (SELECT 1 FROM exam_question eq WHERE eq.exam_id=? AND eq.item_id=q.item_id AND eq.qcode=q.code)"]; a = [eid]
    if qtypes: w.append('q.qtype IN (%s)' % ','.join('?' * len(qtypes))); a += qtypes
    if image in ('0', '1'): w.append('q.has_image=?'); a.append(int(image))
    if yli: w.append('i.iep_yli LIKE ?'); a.append(yli + '%')
    if section: w.append("q.id IN (SELECT qs.question_id FROM question_section qs JOIN section s ON s.id=qs.section_id WHERE s.code LIKE ? AND qs.origin!='rejected')"); a.append(section + '%')
    rows = c.execute('SELECT q.id,q.item_id,q.points FROM question q JOIN item i ON i.id=q.item_id WHERE ' + ' AND '.join(w), a).fetchall()
    if one_per_item:                                          # όχι δεύτερο ερώτημα από το ίδιο θέμα, ούτε από θέμα που ήδη υπάρχει
        used = {r[0] for r in c.execute('SELECT item_id FROM exam_question WHERE exam_id=?', (eid,))}
        rows = [r for r in rows if r['item_id'] not in used]
    return rows

def pick(rows, n, target, one_per_item, rng):
    best, tries = [], 300 if target else 1
    for _ in range(tries):
        pool = rows[:]; rng.shuffle(pool); acc, s, seen = [], 0, set()
        for r in pool:
            if n and len(acc) >= n: break
            if target and s + r['points'] > target: continue
            if one_per_item and r['item_id'] in seen: continue
            acc.append(r); seen.add(r['item_id']); s += r['points']
        if not best or (target and abs(target - s) < abs(target - sum(x['points'] for x in best))): best = acc
        if target and s == target: break
    return best

def crop_bytes(c, qid, sol=0, dpi=130):
    """(jpeg, geo) για το ερώτημα qid ή τη λύση του· None αν δεν υπάρχει εικόνα."""
    r = c.execute('SELECT q.geo,q.sol_geo,i.statement_path,i.solution_path FROM question q JOIN item i ON i.id=q.item_id WHERE q.id=?', (qid,)).fetchone()
    if not r: return None
    geo, path = (r['sol_geo'], r['solution_path']) if sol else (r['geo'], r['statement_path'])
    p = safe_path(path)
    if not geo or not p: return None
    return crops.render(p, geo, max(80, min(dpi, 200))), geo

@router.get('/crop/{qid}.jpg', dependencies=[Depends(auth)])
def crop(qid: int, sol: int = 0, dpi: int = 130):
    c = db(); r = crop_bytes(c, qid, sol, dpi); c.close()
    if not r: raise HTTPException(404, 'δεν υπάρχει εικόνα')
    return Response(r[0], media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=300'})

@router.get('/preview/{iid}.jpg', dependencies=[Depends(auth)])
def preview(iid: str, dpi: int = 55):
    """Μικρή εικόνα της πρώτης σελίδας της εκφώνησης (για γρήγορη προεπισκόπηση)."""
    import subprocess, tempfile, pathlib
    if not iid.isdigit(): raise HTTPException(404)
    c = db(); r = c.execute('SELECT statement_path FROM item WHERE id=?', (iid,)).fetchone(); c.close()
    p = safe_path(r['statement_path']) if r else None
    if not p: raise HTTPException(404)
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(['pdftoppm', '-jpeg', '-singlefile', '-r', str(max(30, min(dpi, 110))), '-f', '1', '-l', '1', p, str(pathlib.Path(d) / 'p')], check=True, capture_output=True, timeout=30)
        return Response((pathlib.Path(d) / 'p.jpg').read_bytes(), media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=600'})

@router.get('/exams', response_class=HTMLResponse, dependencies=[Depends(auth)])
def exams_list():
    c = db(); rows = c.execute("SELECT e.*,(SELECT count(*) FROM exam_question WHERE exam_id=e.id) n FROM exam e ORDER BY e.id DESC").fetchall()
    trs = ''.join(f"<tr><td>{r['id']}</td><td><a href='/exams/{r['id']}'>{html.escape(r['title'])}</a></td><td>{html.escape(r['class_name'] or '')}</td><td>{html.escape(r['exam_date'] or '')}</td><td>{r['n']}</td><td><a href='/exams/{r['id']}/print' target=_blank>εκτύπωση</a></td></tr>" for r in rows)
    body = f"""<h2>Διαγωνίσματα</h2><form method='post' action='/exams/new'>Νέο διαγώνισμα: <input name=title placeholder='Τίτλος' size=34 required> <input name=class_name placeholder='Τάξη/τμήμα' size=14> <button>Δημιουργία</button></form>
<table><tr><th>#</th><th>Τίτλος</th><th>Τάξη</th><th>Ημερομηνία</th><th>Ερωτήματα</th><th></th></tr>{trs}</table>"""
    return page('Διαγωνίσματα', body)

@router.post('/exams/new', dependencies=[Depends(auth)])
def exam_new(request: Request, title: str = Form(...), class_name: str = Form('')):
    same_origin(request); c = db()
    eid = c.execute('INSERT INTO exam(title,class_name,created) VALUES(?,?,?)', (title.strip()[:200] or 'Διαγώνισμα', class_name.strip()[:100], datetime.datetime.now().isoformat(timespec='seconds'))).lastrowid
    c.commit(); c.close(); return RedirectResponse(f'/exams/{eid}', status_code=303)

@router.get('/exams/{eid}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def exam_page(eid: int, msg: str = ''):
    c = db(); e = get_exam(c, eid); rows = exam_rows(c, eid)
    groups = {}
    for r in rows: groups.setdefault(r['grp'], []).append(r)
    out = []; total = 0
    for g in sorted(groups):
        sub = sum(r['points'] or 0 for r in groups[g]); total += sub
        lis = []
        for k, r in enumerate(groups[g], 1):
            key = f"<input type=hidden name=item_id value='{html.escape(r['item_id'])}'><input type=hidden name=qcode value='{html.escape(r['qcode'])}'>"
            thumb = f"<img src='/crop/{r['qid']}.jpg?dpi=90' style='max-width:520px;border:1px solid #ccc'>" if r['qid'] and r['geo'] else '<i>χωρίς εικόνα (το ερώτημα άλλαξε ή λείπει)</i>'
            gsel = ''.join(f"<option value={n}{' selected' if n == g else ''}>Θέμα {LETTERS[n - 1]}</option>" for n in range(1, MAX_GROUPS + 1))
            lis.append(f"""<div class=q><form method='post' action='/exams/{eid}/move'>{key}<b>{LETTERS[g - 1]}{k}</b> · <a href='/review/{html.escape(r['item_id'])}'>{html.escape(r['item_id'])}</a> ερ. {html.escape(r['qcode'])} · {r['points'] if r['points'] is not None else '?'} μον. · {html.escape(TYPES.get(r['qtype'], '') or '')} · {html.escape(r['iep_yli'] or '')}
                <button name=action value=up>↑</button><button name=action value=down>↓</button> <select name=newgrp>{gsel}</select><button name=action value=group>μεταφορά</button> <button name=action value=remove>✖ αφαίρεση</button></form><br>{thumb}</div>""")
        out.append(f"<h3>Θέμα {LETTERS[g - 1]} <small>({sub} μονάδες)</small></h3>{''.join(lis)}")
    if not out: out.append('<p><i>Το διαγώνισμα είναι κενό. Πρόσθεσε ερωτήματα από τη «Δημιουργία με κριτήρια» ή από τη σελίδα Ερωτήματα.</i></p>')
    gopt = ''.join(f"<option value={n}>Θέμα {LETTERS[n - 1]}</option>" for n in range(1, MAX_GROUPS + 1))
    types = ''.join(f"<label><input type=checkbox name=qtype value={k}> {v}</label> " for k, v in TYPES.items())
    f = lambda k: html.escape(e[k] or '')
    body = f"""<h2>Διαγώνισμα #{eid}: {f('title')}</h2>{f"<p><b>{html.escape(msg)}</b></p>" if msg else ''}
<p><a href='/exams/{eid}/print' target=_blank>Εκτύπωση/προεπισκόπηση</a> · <a href='/exams/{eid}/print?teacher=1' target=_blank>με απαντήσεις και πηγές (καθηγητή)</a> · <a href='/exams/{eid}/docx'>⬇ Word</a> · <form method='post' action='/docs/from' style='display:inline'><input type=hidden name=kind value=exam><input type=hidden name=ref value={eid}><select name=mode><option value=image>εικόνες</option><option value=text>κείμενο</option><option value=both>και τα δύο</option></select> <button>Μετατροπή σε Markdown</button></form> · <a href='/browse?exam={eid}'>Προσθήκη από τα Ερωτήματα (φίλτρα)</a> · Σύνολο: <b>{total}</b> μονάδες</p>
<details open><summary>Στοιχεία διαγωνίσματος</summary><form method='post' action='/exams/{eid}/meta'>
Τίτλος <input name=title value='{f('title')}' size=36> Υπότιτλος <input name=subtitle value='{f('subtitle')}' size=30><br>
Σχολείο <input name=school value='{f('school')}' size=30> Τάξη/τμήμα <input name=class_name value='{f('class_name')}' size=14> Ημερομηνία <input name=exam_date value='{f('exam_date')}' size=12> Διάρκεια <input name=duration value='{f('duration')}' size=10><br>
Οδηγίες <input name=notes value='{f('notes')}' size=80> <button>Αποθήκευση</button></form></details>
<details><summary>Δημιουργία με κριτήρια (τυχαία επιλογή)</summary><form method='post' action='/exams/{eid}/generate'>
Τύποι: {types} <small>(κανένας = όλοι)</small><br>
Ενότητα ΙΕΠ <input name=yli size=5> Υποενότητα βιβλίου <input name=section size=6> Εικόνα <select name=image><option value=''>—</option><option value=1>με</option><option value=0>χωρίς</option></select><br>
Πλήθος ερωτημάτων <input name=n size=3> Στόχος μονάδων <input name=target size=3> <small>(ένα από τα δύο ή και τα δύο)</small> → σε <select name=grp>{gopt}</select>
<label><input type=checkbox name=one_per_item value=1 checked> όχι δύο ερωτήματα από το ίδιο θέμα ΙΕΠ</label> Seed <input name=seed size=5> <button>Προσθήκη τυχαίων</button></form></details>
{''.join(out)}
<form method='post' action='/exams/{eid}/delete' onsubmit="return confirm('Διαγραφή διαγωνίσματος;')"><button>Διαγραφή διαγωνίσματος</button></form>"""
    return page(f'Διαγώνισμα {eid}', body)

def redirect(eid, msg=''): return RedirectResponse(f'/exams/{eid}' + ('?' + urlencode({'msg': msg}) if msg else ''), status_code=303)

@router.post('/exams/{eid}/meta', dependencies=[Depends(auth)])
def exam_meta(eid: int, request: Request, title: str = Form(...), subtitle: str = Form(''), school: str = Form(''), class_name: str = Form(''), exam_date: str = Form(''), duration: str = Form(''), notes: str = Form('')):
    same_origin(request); c = db(); get_exam(c, eid)
    c.execute('UPDATE exam SET title=?,subtitle=?,school=?,class_name=?,exam_date=?,duration=?,notes=? WHERE id=?', tuple(x.strip()[:300] for x in (title, subtitle, school, class_name, exam_date, duration, notes)) + (eid,))
    c.commit(); c.close(); return redirect(eid, 'Αποθηκεύτηκε.')

@router.post('/exams/{eid}/add', dependencies=[Depends(auth)])
def exam_add(eid: int, request: Request, qids: list[int] = Form([]), grp: int = Form(1)):
    same_origin(request); c = db(); get_exam(c, eid); n = add_questions(c, eid, qids, grp); c.commit(); c.close()
    return redirect(eid, f'Προστέθηκαν {n} ερωτήματα.')

@router.post('/exams/{eid}/move', dependencies=[Depends(auth)])
def exam_move(eid: int, request: Request, item_id: str = Form(...), qcode: str = Form(...), action: str = Form(...), newgrp: int = Form(1)):
    same_origin(request); c = db(); get_exam(c, eid)
    me = c.execute('SELECT grp,pos FROM exam_question WHERE exam_id=? AND item_id=? AND qcode=?', (eid, item_id, qcode)).fetchone()
    if not me: raise HTTPException(404)
    if action == 'remove': c.execute('DELETE FROM exam_question WHERE exam_id=? AND item_id=? AND qcode=?', (eid, item_id, qcode))
    elif action == 'group' and 1 <= newgrp <= MAX_GROUPS:
        nxt = (c.execute('SELECT max(pos) FROM exam_question WHERE exam_id=? AND grp=?', (eid, newgrp)).fetchone()[0] or 0) + 1
        c.execute('UPDATE exam_question SET grp=?,pos=? WHERE exam_id=? AND item_id=? AND qcode=?', (newgrp, nxt, eid, item_id, qcode))
    elif action in ('up', 'down'):
        o = c.execute(f"SELECT item_id,qcode,pos FROM exam_question WHERE exam_id=? AND grp=? AND pos{'<' if action == 'up' else '>'}? ORDER BY pos {'DESC' if action == 'up' else 'ASC'} LIMIT 1", (eid, me['grp'], me['pos'])).fetchone()
        if o:
            c.execute('UPDATE exam_question SET pos=? WHERE exam_id=? AND item_id=? AND qcode=?', (o['pos'], eid, item_id, qcode))
            c.execute('UPDATE exam_question SET pos=? WHERE exam_id=? AND item_id=? AND qcode=?', (me['pos'], eid, o['item_id'], o['qcode']))
    renumber(c, eid); c.commit(); c.close(); return redirect(eid)

@router.post('/exams/{eid}/generate', dependencies=[Depends(auth)])
def exam_generate(eid: int, request: Request, qtype: list[str] = Form([]), yli: str = Form(''), section: str = Form(''), image: str = Form(''), n: str = Form(''), target: str = Form(''),
                  grp: int = Form(1), one_per_item: str = Form(''), seed: str = Form('')):
    same_origin(request); c = db(); get_exam(c, eid)
    N = int(n) if n.isdigit() and int(n) > 0 else None; T = int(target) if target.isdigit() and int(target) > 0 else None
    if not N and not T: return redirect(eid, 'Όρισε πλήθος ερωτημάτων ή στόχο μονάδων.')
    rows = candidates(c, eid, [t for t in qtype if t in TYPES], yli.strip(), section.strip(), image, bool(one_per_item))
    rng = random.Random(int(seed)) if seed.strip().isdigit() else random.Random()
    chosen = pick(rows, N, T, bool(one_per_item), rng); added = add_questions(c, eid, [r['id'] for r in chosen], grp); c.commit(); c.close()
    s = sum(r['points'] for r in chosen)
    return redirect(eid, f'Προστέθηκαν {added} ερωτήματα ({s} μονάδες) από {len(rows)} υποψήφια.' + (' Δεν βρέθηκαν αρκετά.' if (N and added < N) or (T and s < T) else ''))

@router.post('/exams/{eid}/delete', dependencies=[Depends(auth)])
def exam_delete(eid: int, request: Request):
    same_origin(request); c = db(); get_exam(c, eid)
    c.execute('DELETE FROM exam_question WHERE exam_id=?', (eid,)); c.execute('DELETE FROM exam WHERE id=?', (eid,)); c.commit(); c.close()
    return RedirectResponse('/exams', status_code=303)

PRINT_CSS = """@page{size:A4;margin:14mm}body{font:15px/1.4 'Segoe UI',Arial,sans-serif;margin:0 auto;max-width:820px;padding:0 .5rem;color:#000}
.head{text-align:center;border-bottom:2px solid #000;margin-bottom:.8rem;padding-bottom:.4rem}.head h1{font-size:1.35rem;margin:.1rem 0}.meta{display:flex;justify-content:space-between;margin:.4rem 0}
h2{font-size:1.1rem;margin:1.1rem 0 .3rem;border-bottom:1px solid #000}.q{display:flex;gap:.5rem;break-inside:avoid;margin:.5rem 0}.lab{font-weight:bold;min-width:2.2rem}img{max-width:100%;height:auto}
.name{margin:.4rem 0}.src{font-size:.85em}table{border-collapse:collapse}td,th{border:1px solid #888;padding:.15rem .4rem}.pb{break-before:page}.note{font-style:italic;margin:.3rem 0}
@media screen{.tip{background:#fffbe0;padding:.3rem;border:1px solid #cc9}}@media print{.tip{display:none}}"""

@router.get('/exams/{eid}/print', response_class=HTMLResponse, dependencies=[Depends(auth)])
def exam_print(eid: int, teacher: int = 0):
    c = db(); e = get_exam(c, eid); rows = exam_rows(c, eid); c.close()
    total = sum(r['points'] or 0 for r in rows); h = lambda k: html.escape(e[k] or '')
    school_html = f"<div>{h('school')}</div>" if e['school'] else ''; sub_html = f"<div>{h('subtitle')}</div>" if e['subtitle'] else ''
    out = [f"<div class=tip>Εκτύπωση: Ctrl+P → «Αποθήκευση ως PDF» ή εκτυπωτής. Περιθώρια: προεπιλογή.</div><div class=head>{school_html}<h1>{h('title')}</h1>{sub_html}"
           f"<div class=meta><span>Τάξη: {h('class_name')}</span><span>Ημερομηνία: {h('exam_date')}</span><span>Διάρκεια: {h('duration')}</span><span>Σύνολο: {total} μονάδες</span></div></div><div class=name>Ονοματεπώνυμο: ______________________________ Βαθμός: ________</div>"]
    if e['notes']: out.append(f"<div class=note>{h('notes')}</div>")
    groups = {}
    for r in rows: groups.setdefault(r['grp'], []).append(r)
    for g in sorted(groups):
        out.append(f"<h2>ΘΕΜΑ {LETTERS[g - 1]} <small>({sum(r['points'] or 0 for r in groups[g])} μονάδες)</small></h2>")
        for k, r in enumerate(groups[g], 1):
            img = f"<img src='/crop/{r['qid']}.jpg' style='width:{crops.width_pt(r['geo']):.0f}pt'>" if r['qid'] and r['geo'] else '<i>[λείπει το ερώτημα]</i>'
            out.append(f"<div class=q><span class=lab>{LETTERS[g - 1]}{k}.</span><div>{img}</div></div>")
    if teacher:
        out.append("<div class=pb></div><h2>Απαντήσεις και πηγές (μόνο για τον καθηγητή)</h2>")
        for g in sorted(groups):
            for k, r in enumerate(groups[g], 1):
                sol = f"<img src='/crop/{r['qid']}.jpg?sol=1' style='width:{crops.width_pt(r['sol_geo']):.0f}pt'>" if r['qid'] and r['sol_geo'] else (f"<a href='/files/{html.escape(r['solution_path'])}' target=_blank>λύση (PDF)</a>" if r['solution_path'] else '<i>χωρίς λύση</i>')
                out.append(f"<div class=q><span class=lab>{LETTERS[g - 1]}{k}.</span><div class=src>Πηγή: θέμα {html.escape(r['item_id'])} ερ. {html.escape(r['qcode'])} · {r['points'] if r['points'] is not None else '?'} μον. · {html.escape(r['iep_yli'] or '')}<br>{sol}</div></div>")
    return HTMLResponse(f"<!doctype html><html lang='el'><meta charset='utf-8'><title>{h('title')}</title><style>{PRINT_CSS}</style><body>{''.join(out)}</body></html>",
                        headers={'Content-Security-Policy': "default-src 'self'; style-src 'unsafe-inline'; img-src 'self'"})
