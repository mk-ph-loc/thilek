"""Αγαπημένα ερωτήματα και περιήγηση ένα-ένα (επόμενο/προηγούμενο) πάνω στα φιλτραρισμένα ερωτήματα."""
import datetime, json
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from .main_auth import auth
from .review import db, page, html, same_origin, TYPES, TYPE_OPTS, fld
from .library import select_questions, star, chapter_opts, action_bar, FILTER_KEYS, lsol_opts, src_opts

router = APIRouter()
E = html.escape

def filters_from(params):
    f = {k: (params.get(k) or '').strip() for k in FILTER_KEYS}
    f['qtype'] = [f['qtype']] if f['qtype'] else []
    f['tagmode'] = f['tagmode'] or 'any'
    return f

def keep(params, extra=None):
    d = {k: params.get(k) for k in FILTER_KEYS if params.get(k)}
    d.update(extra or {}); return urlencode(d)

def qrow(c, qid):
    r = c.execute("""SELECT q.id qid,q.item_id,q.code,q.points,q.qtype,q.has_image,q.text,q.geo,q.sol_geo,i.iep_yli,i.position,
        (SELECT group_concat(tag,', ') FROM question_tag t WHERE t.item_id=q.item_id AND t.qcode=q.code) tags,
        EXISTS (SELECT 1 FROM question_fav v WHERE v.item_id=q.item_id AND v.qcode=q.code) fav,
        EXISTS (SELECT 1 FROM qsolution s WHERE s.item_id=q.item_id AND s.qcode=q.code) has_sol FROM question q JOIN item i ON i.id=q.item_id WHERE q.id=?""", (qid,)).fetchone()
    if not r: raise HTTPException(404)
    return r

@router.post('/fav/{qid}', dependencies=[Depends(auth)])
def fav_toggle(qid: int, request: Request):
    same_origin(request); c = db(); r = qrow(c, qid)
    if r['fav']: c.execute('DELETE FROM question_fav WHERE item_id=? AND qcode=?', (r['item_id'], r['code'])); on = False
    else: c.execute('INSERT OR IGNORE INTO question_fav(item_id,qcode,added) VALUES(?,?,?)', (r['item_id'], r['code'], datetime.datetime.now().isoformat(timespec='seconds'))); on = True
    c.commit(); c.close(); return JSONResponse({'fav': on})

@router.get('/q/start', dependencies=[Depends(auth)])
def start(request: Request):
    c = db(); rows = select_questions(c, filters_from(request.query_params), 0); c.close()
    if not rows: return RedirectResponse('/browse?' + keep(request.query_params) + '&none=1', status_code=303)
    return RedirectResponse(f"/q/{rows[0]['qid']}?" + keep(request.query_params), status_code=303)

@router.get('/q/{qid}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def view(qid: int, request: Request, sol: int = 0):
    P = request.query_params; c = db(); r = qrow(c, qid); f = filters_from(P)
    ids = [x['qid'] for x in select_questions(c, f, 0)]; n = len(ids)
    pos = ids.index(qid) if qid in ids else -1
    qs = lambda extra=None: keep(P, extra)
    sol_q = {'sol': 1} if sol else None
    nav = ''
    if pos >= 0:
        nav = ((f"<a rel=prev href='/q/{ids[pos - 1]}?{qs(sol_q)}'>← προηγούμενο</a> ") if pos > 0 else '') + f"<b>{pos + 1} / {n}</b>" + ((f" <a rel=next href='/q/{ids[pos + 1]}?{qs(sol_q)}'>επόμενο →</a>") if pos < n - 1 else '')
    else:
        nav = f"<i>Το ερώτημα δεν ταιριάζει στα τρέχοντα φίλτρα ({n} αποτελέσματα).</i>" + (f" <a href='/q/{ids[0]}?{qs()}'>πρώτο αποτέλεσμα</a>" if ids else '')
    sel = "<option value=''>— όλοι —</option>" + TYPE_OPTS(f['qtype'][0] if f['qtype'] else '')
    img = ''.join(f"<option value='{v}'{' selected' if f['image'] == v else ''}>{t}</option>" for v, t in (('', '— όλα —'), ('1', 'με εικόνα'), ('0', 'χωρίς εικόνα')))
    pos_o = ''.join(f"<option value='{v}'{' selected' if f['position'] == v else ''}>{t}</option>" for v, t in (('', '— όλα —'), ('2', 'Θέμα 2'), ('4', 'Θέμα 4')))
    favo = f"<option value=''>— όλα —</option><option value=1{' selected' if f['fav'] == '1' else ''}>μόνο αγαπημένα</option>"
    flt = ("<form method=get action='/q/start' class=filters>" + fld('Τύπος', f"<select name=qtype>{sel}</select>") + fld('Κεφάλαιο', f"<select name=chapter>{chapter_opts(c, f['chapter'])}</select>")
           + fld('Εικόνα', f"<select name=image>{img}</select>") + fld('Θέμα', f"<select name=position>{pos_o}</select>") + fld('Αγαπημένα', f"<select name=fav>{favo}</select>")
           + fld('Λύση εκπαιδευτικού', f"<select name=lsol>{lsol_opts(f['lsol'])}</select>") + fld('Πηγή', f"<select name=src>{src_opts(f['src'])}</select>") + fld('Ενότητα ΙΕΠ', f"<input name=yli value='{E(f['yli'])}' size=5>") + fld('Υποενότητα', f"<input name=section value='{E(f['section'])}' size=6>") + fld('Ετικέτες', f"<input name=tag value='{E(f['tag'])}' size=14>")
           + fld('Λέξεις', f"<input name=q value='{E(f['q'])}' size=14>") + f"<input type=hidden name=tagmode value='{E(f['tagmode'])}'><button>Εφαρμογή φίλτρων</button> <a href='/browse?{qs()}'>λίστα</a></form>")
    has_sol = bool(r['sol_geo'])
    solt = (f"<a href='/q/{qid}?{qs({} if sol else {'sol': 1})}'>{'απόκρυψη λύσης' if sol else 'εμφάνιση λύσης'}</a>" if has_sol else '<small>δεν υπάρχει εικόνα λύσης για το ερώτημα</small>')
    qimg = f"<img src='/crop/{qid}.jpg?dpi=110' alt='ερώτημα'>" if r['geo'] else f"<pre style='white-space:pre-wrap'>{E(r['text'] or '')}</pre><i>(χωρίς εικόνα PDF)</i>"
    simg = f"<div><h4>Λύση</h4><img src='/crop/{qid}.jpg?sol=1&dpi=110' alt='λύση'></div>" if (sol and has_sol) else ''
    tg = ' '.join(f"<a href='/browse?{urlencode({'tag': t.strip()})}'>{E(t.strip())}</a>" for t in (r['tags'] or '').split(',') if t.strip())
    secs = ', '.join(f"{E(s['code'])}" for s in c.execute("SELECT s.code FROM question_section qs JOIN section s ON s.id=qs.section_id WHERE qs.question_id=? AND qs.origin!='rejected' ORDER BY s.code", (qid,)))
    lsol_a = f"<a href='/lysi/{E(r['item_id'])}/{E(r['code'])}'>προβολή</a>" if r['has_sol'] else '—'
    meta = (f"<p>{star(qid, r['fav'])} Θέμα <a href='/review/{E(r['item_id'])}'>{E(r['item_id'])}</a> · ερώτημα <b>{E(r['code'])}</b> · {r['points'] if r['points'] is not None else '—'} μον. · {E(TYPES.get(r['qtype'], '') or 'χωρίς τύπο')} · "
            f"{'με εικόνα' if r['has_image'] else 'χωρίς εικόνα'} · ΙΕΠ: {E(r['iep_yli'] or '')} · υποενότητες: {secs or '—'} · ετικέτες: {tg or '—'} · {solt} · λύση εκπαιδευτικού: {lsol_a}</p>")
    cols = "grid-template-columns:1fr 1fr" if simg else "grid-template-columns:1fr"
    acts = f"<details><summary>Ενέργειες για αυτό το ερώτημα</summary><form method=post action='/select/act'><input type=hidden name=qids value={qid}>{action_bar(c, {'type': 'one', 'qid': qid}, f'/q/{qid}?{qs(sol_q)}')}</form></details>"
    body = f"<h2>Περιήγηση ερωτημάτων</h2>{flt}<div class=bar>{nav}</div>{meta}<div class='cols qv' style='{cols}'><div>{qimg}</div>{simg}</div>{acts}"
    c.close(); return page(f'Ερώτημα {r["code"]}', body)
