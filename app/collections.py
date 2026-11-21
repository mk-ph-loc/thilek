"""Αποθηκευμένες συλλογές (επιλογές/έγγραφα) με τα κριτήρια και τις ρυθμίσεις τους, και σύνθετο έγγραφο από ερωτήματα."""
import base64, datetime, json, os, pathlib
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from .main_auth import auth
from .review import db, page, html, same_origin
from . import config, crops
from .tools_merge import safe_path
from .library import select_questions, qtable, action_bar, expand, safe_back
from .exams import LETTERS

router = APIRouter()
MAX_Q = 300
DOC_CSS = """@page{size:A4;margin:14mm}body{font:15px/1.4 'Segoe UI',Arial,sans-serif;margin:0 auto;max-width:820px;padding:0 .5rem}h1{font-size:1.3rem;border-bottom:2px solid #000;padding-bottom:.3rem}
h2{font-size:1.05rem;margin:1rem 0 .3rem;border-bottom:1px solid #888}.q{display:flex;gap:.5rem;break-inside:avoid;margin:.5rem 0}.lab{font-weight:bold;min-width:2.4rem}.src{font-size:.8em;color:#555}
img{max-width:100%;height:auto}.pb{break-before:page}.meta{color:#555;font-size:.9em}"""

def create_collection(c, name, members, criteria, options, kind='selection'):
    cid = c.execute('INSERT INTO collection(name,kind,criteria,options,created) VALUES(?,?,?,?,?)', (name.strip()[:200] or 'Συλλογή', kind, criteria if isinstance(criteria, str) else json.dumps(criteria, ensure_ascii=False),
                    json.dumps(options, ensure_ascii=False), datetime.datetime.now().isoformat(timespec='seconds'))).lastrowid
    for n, (it, code) in enumerate(members, 1): c.execute('INSERT INTO collection_member(collection_id,pos,item_id,qcode) VALUES(?,?,?,?)', (cid, n, it, code))
    return cid

def member_rows(c, cid):
    ms = c.execute('SELECT item_id,qcode FROM collection_member WHERE collection_id=? ORDER BY pos', (cid,)).fetchall()
    ids = [m['item_id'] for m in ms if m['qcode'] is None]; out = []
    for m in ms:
        if m['qcode'] is None: continue
        r = c.execute("""SELECT q.id qid,q.item_id,q.code,q.points,q.qtype,q.has_image,q.text,q.geo IS NOT NULL has_geo,q.sol_geo,i.iep_yli,i.position,i.course_code,i.solution_path,
            (SELECT group_concat(tag,', ') FROM question_tag t WHERE t.item_id=q.item_id AND t.qcode=q.code) tags FROM question q JOIN item i ON i.id=q.item_id WHERE q.item_id=? AND q.code=?""", (m['item_id'], m['qcode'])).fetchone()
        if r: out.append(dict(r))
    for it in ids:
        for r in c.execute("""SELECT q.id qid,q.item_id,q.code,q.points,q.qtype,q.has_image,q.text,q.geo IS NOT NULL has_geo,q.sol_geo,i.iep_yli,i.position,i.course_code,i.solution_path,
            (SELECT group_concat(tag,', ') FROM question_tag t WHERE t.item_id=q.item_id AND t.qcode=q.code) tags FROM question q JOIN item i ON i.id=q.item_id WHERE q.item_id=? ORDER BY q.id""", (it,)): out.append(dict(r))
    seen = set(); res = []
    for r in out:
        if r['qid'] not in seen: seen.add(r['qid']); res.append(r)
    return res

def question_info(c, members):
    out = []
    for it, code in members:
        r = c.execute("""SELECT q.id qid,q.item_id,q.code,q.points,q.geo,q.sol_geo,i.iep_yli,i.solution_path,i.statement_path,i.course_code FROM question q JOIN item i ON i.id=q.item_id WHERE q.item_id=? AND q.code=?""", (it, code)).fetchone()
        if r: out.append(dict(r))
    return out

def compose(c, members, opts, embed=False, filename=None):
    qs = question_info(c, members)
    if not qs: raise HTTPException(422, 'Δεν βρέθηκαν ερωτήματα.')
    if len(qs) > MAX_Q: raise HTTPException(422, f'Πάνω από {MAX_Q} ερωτήματα.')
    E = html.escape; title = opts.get('title') or 'Σύνθετο έγγραφο'
    def src(r, sol=False):
        if not embed: return f"/crop/{r['qid']}.jpg{'?sol=1' if sol else ''}"
        geo, path = (r['sol_geo'], r['solution_path']) if sol else (r['geo'], r['statement_path'])
        p = safe_path(path)
        return 'data:image/jpeg;base64,' + base64.b64encode(crops.render(p, geo, 110)).decode() if geo and p else ''
    groups = {}
    for r in qs:
        key = ('.'.join((r['iep_yli'] or '—').split()[0].split('.')[:2]) if r['iep_yli'] else '—') if opts.get('group') == 'unit' else ''
        groups.setdefault(key, []).append(r)
    out = [f"<h1>{E(title)}</h1><p class=meta>{len(qs)} ερωτήματα · {sum(r['points'] or 0 for r in qs)} μονάδες · {datetime.date.today():%d/%m/%Y}</p>"]; n = 0; order = []
    for key in sorted(groups):
        if key: out.append(f"<h2>Ενότητα {E(key)}</h2>")
        for r in groups[key]:
            n += 1; order.append((n, r)); lab = f"{n}." if opts.get('numbering', 'new') == 'new' else ''
            s = src(r); img = f"<img src='{s}' style='width:{crops.width_pt(r['geo']):.0f}pt'>" if r['geo'] and s else '<i>[χωρίς εικόνα]</i>'
            note = '' if opts.get('numbering', 'new') == 'new' else f"<div class=src>θέμα {E(r['item_id'])} ερ. {E(r['code'])}</div>"
            out.append(f"<div class=q><span class=lab>{lab}</span><div>{note}{img}</div></div>")
    if opts.get('solutions'):
        out.append("<div class=pb></div><h2>Απαντήσεις</h2>")
        for n, r in order:
            s = src(r, True) if r['sol_geo'] else ''
            body = f"<img src='{s}' style='width:{crops.width_pt(r['sol_geo']):.0f}pt'>" if s else (f"<a href='/files/{E(r['solution_path'])}' target=_blank>λύση (PDF) θέμα {E(r['item_id'])}</a>" if r['solution_path'] and not embed else '<i>χωρίς λύση</i>')
            out.append(f"<div class=q><span class=lab>{n}.</span><div class=src>θέμα {E(r['item_id'])} ερ. {E(r['code'])}<br>{body}</div></div>")
    doc = f"<!doctype html><html lang='el'><meta charset='utf-8'><title>{E(title)}</title><style>{DOC_CSS}</style><body>{''.join(out)}</body></html>"
    h = {'Content-Security-Policy': "default-src 'self'; style-src 'unsafe-inline'; img-src 'self' data:"}
    if filename: h['Content-Disposition'] = f'attachment; filename="{filename}"'
    return HTMLResponse(doc, headers=h) if not filename else Response(doc, media_type='text/html; charset=utf-8', headers=h)

def jload(s, d):
    try: return json.loads(s) if s else d
    except ValueError: return d

def summary(c, cid, limit=6):
    ms = c.execute('SELECT item_id,qcode FROM collection_member WHERE collection_id=? ORDER BY pos', (cid,)).fetchall()
    items = [m['item_id'] for m in ms if m['qcode'] is None]; qs = [f"{m['item_id']}:{m['qcode']}" for m in ms if m['qcode'] is not None]
    parts = []
    if items: parts.append(f"θέματα ({len(items)}): " + ', '.join(items[:limit]) + ('…' if len(items) > limit else ''))
    if qs: parts.append(f"ερωτήματα ({len(qs)}): " + ', '.join(qs[:limit]) + ('…' if len(qs) > limit else ''))
    return '; '.join(parts) or '—'

def crit_text(crit):
    if not crit: return 'χωρίς κριτήρια (χειροκίνητη επιλογή)'
    f = crit.get('filters', {}); names = {'upto': 'ύλη μέχρι σελ.', 'frm': 'από σελ.', 'mode': 'τρόπος', 'cap': 'όριο υποενότητας', 'qtype': 'τύπος', 'image': 'εικόνα', 'yli': 'ενότητα ΙΕΠ', 'section': 'υποενότητα', 'position': 'θέμα', 'tag': 'ετικέτες', 'tagmode': 'ετικέτες (λογική)', 'q': 'λέξεις'}
    kv = [f"{names[k]}={', '.join(v) if isinstance(v, list) else v}" for k, v in f.items() if v and k in names and not (k == 'frm' and v == '0')]
    return f"{crit.get('type', '')}: " + ('; '.join(kv) or 'όλα')

@router.get('/saved', response_class=HTMLResponse, dependencies=[Depends(auth)])
def saved():
    c = db(); E = html.escape; rows = []
    for e in c.execute("SELECT e.*,(SELECT count(*) FROM exam_question WHERE exam_id=e.id) n FROM exam e"):
        its = [r[0] for r in c.execute('SELECT DISTINCT item_id FROM exam_question WHERE exam_id=? ORDER BY CAST(item_id AS INTEGER)', (e['id'],))]
        rows.append((e['created'] or '', 'διαγώνισμα', f"<a href='/exams/{e['id']}'>{E(e['title'])}</a>", f"{e['n']} ερωτήματα από θέματα: {', '.join(its[:8])}{'…' if len(its) > 8 else ''}", f"τάξη {E(e['class_name'] or '—')}, {E(e['exam_date'] or '—')}", f"<a href='/exams/{e['id']}/print' target=_blank>εκτύπωση</a>"))
    for z in c.execute("SELECT z.*,(SELECT count(*) FROM quiz_item WHERE quiz_id=z.id) n,(SELECT count(*) FROM quiz_item WHERE quiz_id=z.id AND status='review') nr,(SELECT group_concat(DISTINCT src_item) FROM quiz_item WHERE quiz_id=z.id) its FROM quiz z"):
        rows.append((z['created'] or '', 'quiz', f"<a href='/quizzes/{z['id']}'>{E(z['name'])}</a>", f"{z['n']} στοιχεία από θέματα: {E((z['its'] or '—')[:60])}", f"{z['nr'] or 0} θέλουν έλεγχο", f"<a href='/quizzes/{z['id']}/play' target=_blank>παιχνίδι</a>"))
    for k in c.execute('SELECT * FROM collection'):
        crit = jload(k['criteria'], {}); extra = f"<a href='/files/{E(k['saved_file'])}' target=_blank>αρχείο</a>" if k['saved_file'] else ''
        rows.append((k['created'] or '', 'συλλογή', f"<a href='/collections/{k['id']}'>{E(k['name'])}</a>", E(summary(c, k['id'])), E(crit_text(crit)), extra))
    rows.sort(reverse=True)
    trs = ''.join(f"<tr><td>{E(r[0].replace('T', ' '))}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td><td>{r[5]}</td></tr>" for r in rows)
    return page('Αποθηκευμένα', f"<h2>Αποθηκευμένα: διαγωνίσματα και συλλογές</h2><p>Συλλογές φτιάχνεις από τα Ερωτήματα και την Ύλη μέχρι σελίδα («Αποθήκευση ως συλλογή»)· τα διαγωνίσματα από τη σελίδα Διαγωνίσματα.</p><table><tr><th>Δημιουργήθηκε</th><th>Είδος</th><th>Όνομα</th><th>Περιεχόμενο</th><th>Ρυθμίσεις / κριτήρια</th><th></th></tr>{trs}</table>")

@router.get('/collections/{cid}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def collection_page(cid: int, msg: str = ''):
    c = db(); k = c.execute('SELECT * FROM collection WHERE id=?', (cid,)).fetchone()
    if not k: raise HTTPException(404)
    E = html.escape; crit = jload(k['criteria'], {}); opts = jload(k['options'], {}); rows = member_rows(c, cid)
    cfg = E(json.dumps({'κριτήρια': crit, 'ρυθμίσεις_εγγράφου': opts}, ensure_ascii=False, indent=1))
    file = f"<p>Αποθηκευμένο αρχείο: <a href='/files/{E(k['saved_file'])}' target=_blank>{E(k['saved_file'])}</a></p>" if k['saved_file'] else ''
    rerun = f"<form method='post' action='/collections/{cid}/rerun' style='display:inline'><button>↻ Ξανατρέξιμο κριτηρίων (αντικαθιστά τα μέλη)</button></form> " if crit.get('filters') else ''
    body = f"""<h2>Συλλογή #{cid}: {E(k['name'])}</h2>{f"<p><b>{E(msg)}</b></p>" if msg else ''}{file}
<form method='post' action='/collections/{cid}/rename' style='display:inline'><input name=name value='{E(k['name'])}' size=28><button>Μετονομασία</button></form> {rerun}
<a href='/collections/{cid}/doc' target=_blank>Προβολή/εκτύπωση εγγράφου</a>
<form method='post' action='/docs/from' style='display:inline'><input type=hidden name=kind value=collection><input type=hidden name=ref value={cid}><select name=mode><option value=image>εικόνες</option><option value=text>κείμενο</option><option value=both>και τα δύο</option></select> <button>Μετατροπή σε Markdown</button></form>
<form method='post' action='/collections/{cid}/savefile' style='display:inline'><button>Αποθήκευση εγγράφου ως αρχείο στον server (07_EXAGOGES)</button></form>
<form method='post' action='/collections/{cid}/delete' style='display:inline' onsubmit="return confirm('Διαγραφή συλλογής;')"><button>Διαγραφή</button></form>
<details open><summary>Ρυθμίσεις και κριτήρια</summary><pre>{cfg}</pre></details>
<form method='post' action='/select/act'>{action_bar(c, crit, f'/collections/{cid}')}<h3>Μέλη ({len(rows)} ερωτήματα)</h3>{qtable(rows, True)}</form>"""
    return page(f'Συλλογή {cid}', body)

def doc_for(c, cid):
    k = c.execute('SELECT * FROM collection WHERE id=?', (cid,)).fetchone()
    if not k: raise HTTPException(404)
    return k, [(r['item_id'], r['code']) for r in member_rows(c, cid)], jload(k['options'], {})

@router.get('/collections/{cid}/doc', response_class=HTMLResponse, dependencies=[Depends(auth)])
def collection_doc(cid: int):
    c = db(); k, ms, o = doc_for(c, cid); o.setdefault('title', k['name']); r = compose(c, ms, o); c.close(); return r

@router.post('/collections/{cid}/savefile', dependencies=[Depends(auth)])
def collection_savefile(cid: int, request: Request):
    same_origin(request); c = db(); k, ms, o = doc_for(c, cid); o.setdefault('title', k['name'])
    r = compose(c, ms, o, embed=True, filename='x.html'); qs = question_info(c, ms); course = qs[0]['course_code']
    rel = f"{course}/07_EXAGOGES/doc-{cid}-{datetime.date.today():%Y%m%d}.html"; root = os.path.realpath(config.load()['data_root']); path = os.path.realpath(os.path.join(root, rel))
    if not path.startswith(root + os.sep): raise HTTPException(400)
    try: pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True); pathlib.Path(path).write_bytes(r.body)
    except OSError as ex: c.close(); raise HTTPException(500, f'Δεν ήταν δυνατή η εγγραφή στον server: {ex.strerror}')
    c.execute('UPDATE collection SET saved_file=? WHERE id=?', (rel, cid)); c.commit(); c.close()
    return RedirectResponse(f'/collections/{cid}', status_code=303)

@router.post('/collections/{cid}/rename', dependencies=[Depends(auth)])
def collection_rename(cid: int, request: Request, name: str = Form(...)):
    same_origin(request); c = db(); c.execute('UPDATE collection SET name=? WHERE id=?', (name.strip()[:200] or 'Συλλογή', cid)); c.commit(); c.close(); return RedirectResponse(f'/collections/{cid}', status_code=303)

@router.post('/collections/{cid}/rerun', dependencies=[Depends(auth)])
def collection_rerun(cid: int, request: Request):
    same_origin(request); c = db(); k = c.execute('SELECT * FROM collection WHERE id=?', (cid,)).fetchone()
    if not k: raise HTTPException(404)
    f = jload(k['criteria'], {}).get('filters')
    if not f: c.close(); raise HTTPException(422, 'Η συλλογή δεν έχει κριτήρια.')
    rows = select_questions(c, f, limit=0)
    c.execute('DELETE FROM collection_member WHERE collection_id=?', (cid,))
    for n, r in enumerate(rows, 1): c.execute('INSERT INTO collection_member(collection_id,pos,item_id,qcode) VALUES(?,?,?,?)', (cid, n, r['item_id'], r['code']))
    c.commit(); c.close(); return RedirectResponse(f'/collections/{cid}', status_code=303)

@router.post('/collections/{cid}/delete', dependencies=[Depends(auth)])
def collection_delete(cid: int, request: Request):
    same_origin(request); c = db(); c.execute('DELETE FROM collection_member WHERE collection_id=?', (cid,)); c.execute('DELETE FROM collection WHERE id=?', (cid,)); c.commit(); c.close()
    return RedirectResponse('/saved', status_code=303)
