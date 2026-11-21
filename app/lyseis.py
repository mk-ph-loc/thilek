"""Λύσεις εκπαιδευτικού: λίστα (/lyseis), σάρωση φακέλων χωρίς rebuild, σελίδα λύσης (/lysi/ID/ερώτημα) με KaTeX, αντιγραφή, λήψη .md, εξαγωγές."""
import json, os, pathlib
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from urllib.parse import quote
from .main_auth import auth
from .review import db, page, html, same_origin
from .library import action_bar, sol_controls
from . import config, qsol, solexport
from .mdmath import render_md, md_text

router = APIRouter()
E = html.escape
LYSI_JS = (pathlib.Path(__file__).parent / 'static' / 'lysi.js').read_text(encoding='utf-8')
CSS = ("<style>.lysi .lpanel{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:.6rem 1rem;margin-bottom:.8rem;max-width:980px;overflow-x:auto}"
       ".lysi .lpanel table{border-collapse:collapse;width:auto}.lysi .lpanel td,.lysi .lpanel th{border:1px solid var(--border)}.lysi .lpanel tr:nth-child(even) td{background:none}"
       ".lysi hr.slide{border:0;border-top:2px dashed var(--border);margin:1rem 0}.lysi .quiz>li{margin:.6rem 0;padding:.4rem .6rem;border:1px solid var(--border);border-radius:var(--radius)}"
       ".lysi .warn{color:#a15c00}.lysi .err{color:#b00020}.lysi .noimg{color:var(--muted)}.lysi a.broken{color:var(--muted);text-decoration:line-through}.lysi .copy{margin-left:.5rem}"
       ".lysi .lpanel .katex{font-size:1.1em}.lysi .katex-display{overflow-x:auto;overflow-y:hidden}.lysi textarea[hidden]{display:none}</style>")
KATEX = ("<link rel=stylesheet href='/static/vendor/katex/katex.min.css'><script src='/static/vendor/katex/katex.min.js'></script>"
         "<script src='/static/vendor/katex/auto-render.min.js'></script><script src='/static/lysi.js'></script>")

@router.get('/static/lysi.js', include_in_schema=False)
def lysi_js(): return Response(LYSI_JS, media_type='application/javascript')

SOLCTL_JS = (pathlib.Path(__file__).parent / 'static' / 'solctl.js').read_text(encoding='utf-8')

@router.get('/static/solctl.js', include_in_schema=False)
def solctl_js(): return Response(SOLCTL_JS, media_type='application/javascript')

def all_keys(c):
    return sorted(((r[0], r[1]) for r in c.execute('SELECT item_id,qcode FROM qsolution')), key=lambda k: qsol.sort_key(*k))

def lysi_url(item_id, qcode): return f"/lysi/{quote(str(item_id))}/{quote(str(qcode))}"

def status_tag(st):
    cls = {'reviewed': 'manual', 'draft': 'auto', 'error': 'ai'}.get(st, 'auto')
    return f"<span class='tag {cls}'>{E({'reviewed': 'ελεγμένη', 'draft': 'πρόχειρη', 'error': 'σφάλμα'}.get(st, st))}</span>"

@router.get('/lyseis', response_class=HTMLResponse, dependencies=[Depends(auth)])
def lyseis_list(msg: str = ''):
    c = db(); rows = [qsol.row_dict(r) for r in c.execute('SELECT * FROM qsolution')]
    rows.sort(key=lambda r: qsol.sort_key(r['item_id'], r['qcode']))
    trs = []
    for r in rows:
        w = r['warn']; box = f"<input type=checkbox name=qids value={r['question_id']}>" if r['question_id'] else "<span title='χωρίς αντίστοιχο ερώτημα στη βάση'>—</span>"
        wcell = f"<span class=warn title='{E(chr(10).join(w))}'>{len(w)} ⚠</span>" if w else ''
        trs.append(f"<tr><td>{box}</td><td><a href='/review/{E(r['item_id'])}'>{E(r['item_id'])}</a></td><td><a href='{E(lysi_url(r['item_id'], r['qcode']))}'>{E(r['qcode'])}</a></td>"
                   f"<td>{E(r['fm'].get('points', ''))}</td><td>{E(r['fm'].get('qtype', ''))}</td><td>{status_tag(r['status'])}</td><td>{len([q for q in r['quiz'] if not q['err']])}</td><td>{wcell}</td><td><small>{E(r['relpath'])}</small></td></tr>")
    scan = ("<form method=post action='/lyseis/scan' class=filters><button class=primary>Σάρωση φακέλου</button> <small>Ξαναδιαβάζει τα αρχεία <code>&lt;ID&gt;.&lt;θέμα&gt;-&lt;υπ&gt;.md</code> από <code>04_TRAPEZA/orig/</code> (και <code>05_LYSEIS/</code>) χωρίς πλήρες rebuild.</small></form>")
    body = (f"<h2>Λύσεις εκπαιδευτικού</h2>{f'<p><b>{E(msg)}</b></p>' if msg else ''}{scan}"
            f"<form method='post' action='/select/act'>{action_bar(c, {'type': 'lyseis'}, '/lyseis')}<p>{len(rows)} αρχεία λύσεων</p>"
            "<table><tr><th><input type=checkbox data-all='qids' title='όλα'></th><th>Θέμα</th><th>Ερώτημα</th><th>Μον.</th><th>Τύπος</th><th>Status</th><th>Quiz</th><th>Προειδοποιήσεις</th><th>Αρχείο</th></tr>"
            f"{''.join(trs)}</table></form>" + ('' if rows else "<p><i>Δεν βρέθηκαν λύσεις. Βάλε τα αρχεία .md στο <code>&lt;ΜΑΘΗΜΑ&gt;/04_TRAPEZA/orig/</code> και πάτα «Σάρωση φακέλου».</i></p>"))
    c.close(); return page('Λύσεις εκπαιδευτικού', body)

@router.post('/lyseis/scan', dependencies=[Depends(auth)])
def lyseis_scan(request: Request):
    same_origin(request); c = db()
    try: res = qsol.scan(c, config.load()['data_root']); c.commit()
    finally: c.close()
    return RedirectResponse('/lyseis?msg=' + quote(qsol.summary(res)), status_code=303)

@router.post('/lyseis/export', dependencies=[Depends(auth)])
def lyseis_export(request: Request, act: str = Form(...), keys: list[str] = Form([]), sx: list[str] = Form([]), sol_title: str = Form(''), rtheme: str = Form(''), sstyle: str = Form(''), hide: str = Form('')):
    """Εξαγωγή με κλειδιά «ID|ερώτημα» (δουλεύει και για ορφανά αρχεία χωρίς ερώτημα στη βάση)."""
    same_origin(request); ks = [tuple(k.split('|', 1)) for k in keys if '|' in k]
    if not ks: raise HTTPException(422, 'Δεν επιλέχθηκε τίποτα.')
    c = db()
    try: return solexport.export(c, act, ks, sx, sol_title, sstyle or rtheme, bool(hide))
    finally: c.close()

def raw_text(r):
    """Ολόκληρο το αρχείο από τον δίσκο (πηγή αλήθειας), με έλεγχο διαδρομής· αλλιώς ανασύνθεση από τις ενότητες."""
    root = os.path.realpath(config.load()['data_root']); p = os.path.realpath(os.path.join(root, r['relpath']))
    if p.startswith(root + os.sep) and os.path.isfile(p):
        try: return open(p, encoding='utf-8-sig').read()
        except (OSError, UnicodeDecodeError): pass
    return '\n\n---\n'.join(f"## {t}\n{r['sections'].get(k, '')}" for k, t in qsol.TITLES.items())

def quiz_html(qs):
    out = []
    for q in qs:
        t = q.get('type', ''); head = f"<b>{q['n']}.</b> <span class='tag iep'>{E(qsol.QTYPES.get(t, t or '?'))}</span> <small>{q.get('points', 1):g} μον.</small>"
        if q['err']: out.append(f"<li>{head} <span class=err>σφάλμα: {E('; '.join(q['err']))}</span><div>{md_text(q.get('stem', ''))}</div></li>"); continue
        body = f"<div>{md_text(q['stem'])}</div>" + (f"<div><small>εικόνα: {E(q['image'])}</small></div>" if q.get('image') else '')
        if t == 'mcq': body += '<ol type=a>' + ''.join(f"<li>{md_text(o)}{' ✔' if i == q['answer'] else ''}</li>" for i, o in enumerate(q['options'])) + '</ol>'
        if t == 'matching': body += '<table><tr><th>Α</th><th>Β</th></tr>' + ''.join(f"<tr><td>{md_text(a)}</td><td>{md_text(b)}</td></tr>" for a, b in q['pairs']) + '</table>'
        body += f"<details><summary>Απάντηση</summary><b>{md_text(solexport.answer_text(q))}</b>{'<div>' + md_text(q['feedback']) + '</div>' if q.get('feedback') else ''}</details>"
        out.append(f"<li>{head}{body}</li>")
    return "<ol class=quiz style='list-style:none;padding:0'>" + ''.join(out) + '</ol>'

@router.get('/lysi/{item_id}/{qcode}/md', dependencies=[Depends(auth)])
def lysi_md(item_id: str, qcode: str):
    c = db(); r = qsol.get(c, item_id, qcode); c.close()
    if not r: raise HTTPException(404)
    fn = r['relpath'].rsplit('/', 1)[-1]
    return Response(raw_text(r), media_type='text/markdown; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{fn}"'})

def book_line(fm):
    """Γραμμή «Βιβλίο: σελ. α–β · λύση στη σελ. γ · στυλ …» από τα προαιρετικά πεδία του front matter (αν υπάρχουν)."""
    from .solstyle import STYLES
    a, b, s_ = (fm.get(k) for k in ('book_first_page', 'book_last_page', 'book_solution_page')); st = str(fm.get('style') or '')
    parts = []
    if a or b: parts.append(f"σελίδες βιβλίου <b>{E(a if a else '?')}–{E(b if b else '?')}</b>")
    if s_: parts.append(f"η λύση υπάρχει στη σελίδα <b>{E(s_)}</b> (<a href='/coverage'>Ύλη/σελίδα</a>)")
    if st in STYLES: parts.append(f"στυλ εξαγωγής: <b>{E(STYLES[st]['label'])}</b>")
    return f"<p class=booknote>📖 {' · '.join(parts)}</p>" if parts else ''


@router.get('/lysi/{item_id}/{qcode}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def lysi_page(item_id: str, qcode: str):
    c = db(); r = qsol.get(c, item_id, qcode)
    if not r: c.close(); raise HTTPException(404, 'Δεν υπάρχει λύση εκπαιδευτικού για αυτό το ερώτημα.')
    s = r['sections']; links = qsol.resolver(c, r['course']); md = lambda t: render_md(t, r['base'], links)
    keys = all_keys(c); pos = keys.index((item_id, qcode)) if (item_id, qcode) in keys else -1
    prev_a = f"<a rel=prev href='{E(lysi_url(*keys[pos - 1]))}'>◀ {E(' '.join(keys[pos - 1]))}</a>" if pos > 0 else '<span>◀</span>'
    next_a = f"<a rel=next href='{E(lysi_url(*keys[pos + 1]))}'>{E(' '.join(keys[pos + 1]))} ▶</a>" if 0 <= pos < len(keys) - 1 else '<span>▶</span>'
    q = c.execute('SELECT id,points FROM question WHERE item_id=? AND code=?', (item_id, qcode)).fetchone()
    raw = raw_text(r); E2 = lambda k: E(f"## {qsol.TITLES[k]}\n\n{s.get(k, '')}\n")
    hid = (f"<textarea hidden id=md-all>{E(raw)}</textarea>" + ''.join(f"<textarea hidden id=md-{k}>{E2(k)}</textarea>" for k in qsol.TITLES))
    cp = lambda k, t='Αντιγραφή ενότητας': f"<button type=button class=copy data-copy='md-{k}' title='σε Markdown'>⧉ {t}</button>"
    teacher, prev = [], None
    for i, p in enumerate(s.get('teacher_parts') or []):
        if i: teacher.append("<hr class=slide title='αλλαγή διαφάνειας'>")
        if p['title'] and p['title'] != prev: teacher.append(f"<h3>{E(p['title'])}</h3>")
        prev = p['title']; teacher.append(md(p['body']))
    nq = len(r['quiz'])
    if nq: teacher.append(f"<h3>Quiz ({nq})</h3>{quiz_html(r['quiz'])}")
    tabs = (('statement', 'Εκφώνηση', md(s.get('statement', ''))), ('iep', 'Λύση ΙΕΠ', md(s.get('iep', ''))),
            ('teacher', 'Λύση εκπαιδευτικού', ''.join(teacher)), ('refs', 'Παραπομπές', md(s.get('refs', ''))))
    tabbar = "<div class=tabs>" + ''.join(f"<a class='tab ltab{' on' if i == 0 else ''}' href='#t-{k}' data-tab='{k}'>{t}</a>" for i, (k, t, _) in enumerate(tabs)) + '</div>'
    panels = ''.join(f"<section class=lpanel id='t-{k}' data-panel='{k}'><h3>{t} {cp(k)}</h3>{h or '<p><i>κενή ενότητα</i></p>'}</section>" for k, t, h in tabs)
    w = r['warn']
    warns = (f"<details class=warn{' open' if w else ''}><summary>Προειδοποιήσεις ({len(w)})</summary><ul>" + ''.join(f'<li>{E(x)}</li>' for x in w) + '</ul></details>') if w else ''
    fm = r['fm']; tags = ', '.join(str(t) for t in fm.get('tags') or []) if isinstance(fm.get('tags'), list) else ''
    meta = (f"<p>{status_tag(r['status'])} · θέμα <a href='/review/{E(item_id)}'>{E(item_id)}</a> · ερώτημα <b>{E(qcode)}</b> · {E(fm.get('points', q['points'] if q else '—'))} μον. · τύπος {E(fm.get('qtype', '—'))}"
            + (f" · <a href='/q/{q['id']}'>περιήγηση ερωτήματος</a>" if q else ' · <span class=warn>χωρίς αντίστοιχο ερώτημα στη βάση</span>')
            + (f" · ετικέτες: {E(tags)}" if tags else '') + f" · <small>{E(r['relpath'])}</small></p>" + book_line(fm))
    bar = (f"<div class=bar>{prev_a} <b>{pos + 1}/{len(keys)}</b> {next_a} · {cp('all', 'Αντιγραφή όλου (Markdown)')} · <a href='{E(lysi_url(item_id, qcode))}/md'>⬇ .md</a> · <a href='/lyseis'>όλες οι λύσεις</a> · <small>πλήκτρα ← →</small></div>")
    exp = (f"<details><summary>Εξαγωγή αυτού του ερωτήματος (Reveal.js, Markdown/Word, Moodle XML)</summary><form method=post action='/lyseis/export' class=filters>"
           f"<input type=hidden name=keys value='{E(item_id)}|{E(qcode)}'>{sol_controls(str(fm.get('style') or 'kids'))}</form></details>")
    c.close()
    body = f"{CSS}<div class=lysi><h2>Λύση εκπαιδευτικού · θέμα {E(item_id)} · ερώτημα {E(qcode)}</h2>{bar}{meta}{warns}{exp}{tabbar}{panels}{hid}</div>{KATEX}"
    return page(f'Λύση {item_id} {qcode}', body)
