"""0.32: σελίδες παρουσιάσεων (/decks): λίστα, συνταγή → πηγή → επεξεργαστής διαφανειών, προεπισκόπηση, εξαγωγές (Reveal, εκτύπωση/PDF, PowerPoint, deck.md), δημοσίευση.
HTML από strings, χωρίς inline JS (φόρμες και κουμπιά), same_origin σε κάθε POST. Η προεπισκόπηση σερβίρεται σε sandboxed iframe με αυστηρό CSP."""
import html, io, json, pathlib, re, zipfile
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from . import config, deck as D, deckexport as DX, deckmd, decktpl as T, embed as EM, settings, wizmodel as M
from .library import select_questions
from .main_auth import auth
from .review import chk, db, fld, page, same_origin
from .solstyle import STYLES, UNITS, PRESETS
from .wizard import CSS as WCSS, criteria_on, disp, filter_form, filters_from_qs, safe_qs, step_filters

router = APIRouter()
E = html.escape
CSS = (WCSS + "<style>.dks{display:grid;grid-template-columns:minmax(220px,300px) 1fr;gap:1rem;align-items:start}.dks ol{list-style:none;margin:0;padding:0}.dks li{border:1px solid var(--border);border-radius:8px;margin:.25rem 0;padding:.3rem .5rem}"
       ".dks li.cur{border-color:var(--accent,#2563eb);box-shadow:0 0 0 2px var(--accent,#2563eb) inset}.dks li.hid{opacity:.5}.dks li form{display:inline}.dks li .t{display:block;font-weight:600;text-decoration:none}"
       ".dks li small{opacity:.8}.dks textarea{width:100%;font-family:ui-monospace,Consolas,monospace}.dkprev{width:100%;height:420px;border:1px solid var(--border);border-radius:8px;background:#fff}"
       ".dkbtn button{padding:.1rem .4rem}.dktb button{padding:.15rem .5rem}.warnb{color:#b45309}</style>")


def fv(f, k, default=''):
    v = f.get(k); return v.strip() if isinstance(v, str) else default


def raw(f, k):
    v = f.get(k); return v.replace('\r\n', '\n') if isinstance(v, str) else ''


def inp(name, val='', size=30): return f"<input class=r-txt name={name} size={size} value='{E(val or '')}'>"
def ta(name, val='', rows=6): return f"<textarea class=r-txt name={name} rows={rows}>{E(val or '')}</textarea>"
def sel(name, options): return f"<select class=r-list name={name}>{options}</select>"


def opt(v, t, cur): return f"<option value='{E(str(v))}'{' selected' if str(cur) == str(v) else ''}>{E(t)}</option>"
def ck(name, on, label): return chk(label, f"<input type=checkbox class=r-opt name={name} value=1{' checked' if on else ''}>")


def get_deck(c, did):
    d = D.get(c, did)
    if not d: raise HTTPException(404, 'Δεν υπάρχει αυτή η παρουσίαση.')
    return d


def domains(): return EM.hosts(settings.get('embed_domains'))


def csp_html(body, status=200, headers=None, frames=()):
    """HTML με αυστηρό CSP. frames: επιτρεπτά domains για frame-src (κενό = καθόλου iframe)."""
    h = HTMLResponse(body, status_code=status, headers=headers or {})
    h.headers['Content-Security-Policy'] = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; font-src data:; frame-src " + EM.csp_frames(frames)
    h.headers['X-Content-Type-Options'] = 'nosniff'
    return h


# ---------- λίστα ----------
@router.get('/decks', response_class=HTMLResponse, dependencies=[Depends(auth)])
def decks_home(msg: str = ''):
    c = db(); rows = c.execute('SELECT d.*,(SELECT count(*) FROM deck_slide s WHERE s.deck_id=d.id) n FROM deck d ORDER BY d.kind,d.updated DESC,d.id DESC').fetchall(); c.close()
    kind = {0: 'παρουσίαση', 1: 'πρότυπο', 2: 'βιβλιοθήκη διαφανειών'}
    trs = ''.join(f"<tr><td><a href='/decks/{r['id']}'>{E(r['name'])}</a></td><td>{E(kind.get(r['kind'], ''))}</td><td>{E(T.RECIPE_LABEL.get(r['recipe'], ''))}</td><td>{r['n']}</td><td>{E(r['updated'] or '')}</td>"
                  f"<td><form method=post action='/decks/{r['id']}/copy' style='display:inline'><button>Αντίγραφο</button></form> "
                  f"<form method=post action='/decks/{r['id']}/delete' style='display:inline'><button class=danger>Διαγραφή</button></form></td></tr>" for r in rows)
    tpl = ''.join(opt(r['id'], r['name'], '') for r in rows if r['kind'] == 1); none_opt = "<option value=''>— καμία —</option>"
    rec = ''.join(f"<label class='f chk'><input type=radio class=r-opt name=recipe value={k} {'checked' if k == 'solutions' else ''}>{E(t)} <small>— {E(d)}</small></label>" for k, t, _, d in T.RECIPES)
    body = (f"{CSS}<h2>Παρουσιάσεις</h2><p>Φτιάχνεις παρουσιάσεις (Reveal.js, PDF από τον browser, PowerPoint) από <b>συνταγές</b>: λύσεις ασκήσεων, επανάληψη κεφαλαίου, quiz, διόρθωση διαγωνίσματος ή ελεύθερα. "
            "Κάθε διαφάνεια είναι Markdown που τη διορθώνεις στον επεξεργαστή.</p>" + (f"<div class='adm adm-info'><p>{E(msg)}</p></div>" if msg else '')
            + f"<form method=post action=/decks/new><fieldset><legend>Νέα παρουσίαση</legend>{fld('Όνομα', inp('name', 'Νέα παρουσίαση', 34))}"
              f"<div>{rec}</div>{fld('Ή από πρότυπο (δικό σου)', sel('tpl', none_opt + tpl))}<button class=primary>Δημιουργία →</button></fieldset></form>"
            + f"<h3>Οι παρουσιάσεις μου ({len(rows)})</h3>" + (f"<table><tr><th>Όνομα</th><th>Είδος</th><th>Συνταγή</th><th>Διαφάνειες</th><th>Τελευταία αλλαγή</th><th></th></tr>{trs}</table>" if rows else '<p><i>Καμία ακόμα.</i></p>')
            + "<form method=post action=/decks/import enctype=multipart/form-data><fieldset><legend>Εισαγωγή από deck.md</legend>"
              "<p><small>Αρχείο που εξήχθη από εδώ ή γράφτηκε με το χέρι: διαφάνειες χωρισμένες με γραμμή <code>---</code>, τίτλος <code># …</code>, σημειώσεις μετά από <code>Note:</code>.</small></p>"
              f"{fld('Αρχείο .md', '<input type=file class=r-file name=file accept=.md,.markdown,.txt>')}<button>Εισαγωγή</button></fieldset></form>")
    return page('Παρουσιάσεις', body)


@router.post('/decks/new', dependencies=[Depends(auth)])
async def decks_new(request: Request):
    same_origin(request); f = await request.form(); c = db()
    try:
        name = fv(f, 'name') or 'Νέα παρουσίαση'; tpl = fv(f, 'tpl')
        if tpl.isdigit():
            t = D.get(c, int(tpl))
            if t and t['kind'] == 1:
                n = D.copy_deck(c, t['id'], name, 0); c.commit(); return RedirectResponse(f'/decks/{n}', status_code=303)
        recipe = fv(f, 'recipe') if fv(f, 'recipe') in T.RECIPE_KEYS else 'free'
        course = settings.get('course_active') if settings.get('course_active') not in (None, 'all') else ''
        did = D.create(c, name, recipe, title=name, course=course or '')
        if T.RECIPE_NEEDS[recipe]: c.commit(); return RedirectResponse(f'/decks/{did}/source', status_code=303)
        D.build(c, did); c.commit(); return RedirectResponse(f'/decks/{did}', status_code=303)
    finally: c.close()


@router.post('/decks/import', dependencies=[Depends(auth)])
async def decks_import(request: Request):
    same_origin(request); f = await request.form(); up = f.get('file')
    if not hasattr(up, 'read'): raise HTTPException(422, 'Διάλεξε αρχείο .md.')
    data = await up.read(deckmd.MAX_DECK_MD + 1)
    try: meta, sl = deckmd.parse_deck_md(data.decode('utf-8', 'replace'))
    except ValueError as ex: raise HTTPException(422, str(ex))
    if not sl: raise HTTPException(422, 'Το αρχείο δεν έχει διαφάνειες.')
    c = db()
    try:
        did = D.create(c, str(meta.get('name') or 'Εισαγμένη παρουσίαση'), 'free', str(meta.get('title') or ''), str(meta.get('subtitle') or ''), str(meta.get('style') or 'calm'), meta.get('opts') if isinstance(meta.get('opts'), dict) else {})
        D.replace_slides(c, did, sl); c.commit(); return RedirectResponse(f'/decks/{did}', status_code=303)
    finally: c.close()


@router.post('/decks/{did}/delete', dependencies=[Depends(auth)])
def deck_delete(request: Request, did: int):
    same_origin(request); c = db(); D.delete_deck(c, did); c.commit(); c.close(); return RedirectResponse('/decks', status_code=303)


@router.post('/decks/{did}/copy', dependencies=[Depends(auth)])
def deck_copy(request: Request, did: int):
    same_origin(request); c = db(); n = D.copy_deck(c, did)
    if not n: raise HTTPException(404)
    c.commit(); c.close(); return RedirectResponse(f'/decks/{n}', status_code=303)


@router.post('/decks/{did}/astemplate', dependencies=[Depends(auth)])
def deck_astemplate(request: Request, did: int):
    same_origin(request); c = db(); d = get_deck(c, did); D.copy_deck(c, did, d['name'][:100] + ' (πρότυπο)', 1); c.commit(); c.close()
    return RedirectResponse('/decks?msg=' + 'Αποθηκεύτηκε+ως+πρότυπο.', status_code=303)


# ---------- πηγή (συνταγές με ερωτήματα ή διαγώνισμα) ----------
def source_page(c, d, request):
    did = d['id']; need = T.RECIPE_NEEDS[d['recipe']]; st = d['state']
    head = f"{CSS}<h2>Παρουσίαση · {E(d['name'])} <small>({E(T.RECIPE_LABEL[d['recipe']])})</small></h2><h3>Πηγή περιεχομένου</h3>"
    if need == 'exam':
        exs = c.execute('SELECT id,title FROM exam ORDER BY id DESC').fetchall()
        sel = ''.join(opt(e['id'], f"{e['title']} (#{e['id']})", st.get('exam_id')) for e in exs)
        body = (f"<form method=post action='/decks/{did}/source'><p>Διάλεξε διαγώνισμα από τη σελίδα <a href='/exams'>Διαγωνίσματα</a>.</p>"
                + (fld('Διαγώνισμα', f"<select class=r-list name=exam_id>{sel}</select>") + "<button class=primary name=action value=build>Δημιουργία διαφανειών →</button>" if exs else '<p><i>Δεν υπάρχουν διαγωνίσματα.</i></p>') + '</form>')
        return page('Παρουσίαση: πηγή', head + body)
    on = criteria_on(); f = step_filters(request, on); has = bool(request.url.query)
    rows = select_questions(c, f, 300) if has else []; inn = {tuple(m) for m in st.get('members', [])}
    rt = ''.join(f"<tr class='{'insel' if (r['item_id'], r['code']) in inn else ''}'><td><input type=checkbox class=r-sel name=qids value={r['qid']}></td><td>{E(r['item_id'])}</td><td>{E(r['code'])}</td><td>{r['points'] or ''}</td>"
                 f"<td>{E(r['qtype'] or '')}</td><td>{'✎' if r['has_sol'] else ''}</td></tr>" for r in rows)
    res = (f"<h3>Αποτελέσματα ({len(rows)}{'+' if len(rows) >= 300 else ''})</h3><div class=bar><button name=action value=add>Προσθήκη επιλεγμένων</button> <button name=action value=addall>Προσθήκη ΟΛΩΝ των αποτελεσμάτων</button></div>"
           f"<small>Μόνο ερωτήματα με αρχείο λύσης (✎) δίνουν διαφάνειες λύσης.</small><table class=inselect><tr><th><input type=checkbox data-all=qids></th><th>Θέμα</th><th>Ερώτημα</th><th>Μον.</th><th>Τύπος</th><th>Λύση</th></tr>{rt}</table>"
           ) if has else '<p><i>Διάλεξε κριτήρια και πάτα «Εμφάνιση» (ή «Εμφάνιση» χωρίς κριτήρια για όλα).</i></p>'
    cur = ''.join(f"<tr><td><input type=checkbox class=r-sel name=rm value='{E(M.key(*m))}'></td><td>{E(m[0])}</td><td>{E(m[1])}</td></tr>" for m in map(tuple, st.get('members', [])))
    sel = (f"<h3>Η λίστα μου ({len(st.get('members', []))})</h3>" + (f"<table><tr><th></th><th>Θέμα</th><th>Ερώτημα</th></tr>{cur}</table><div class=bar><button name=action value=remove class=danger>Αφαίρεση επιλεγμένων</button></div>" if cur else '<p><i>Άδεια.</i></p>'))
    inc = set(st.get('sx') or PRESETS[0][2])
    units = ''.join(chk(E(t), f"<input type=checkbox class=r-opt name=sx value={k} {'checked' if k in inc else ''}>") for k, t, _ in UNITS)
    o = d['opts']
    cont = (f"<fieldset><legend>Περιεχόμενο διαφανειών</legend><p>Ενότητες λύσης που γίνονται διαφάνειες (με τη σειρά της λύσης):</p>{units}"
            f"{ck('frag', o['frag'], 'Bullets ένα-ένα')}{fld('Quiz: απαντήσεις', '<select class=r-list name=answers>' + ''.join(opt(k, t, o['answers']) for k, t in T.ANSWERS) + '</select>')}</fieldset>")
    form = (f"<input type=hidden name=qs value='{E(safe_qs(request.url.query))}'><form method=post action='/decks/{did}/source'><input type=hidden name=qs value='{E(safe_qs(request.url.query))}'>{res}{sel}{cont}"
            "<div class=wnav><a class=btn href=/decks>Άκυρο</a><button class=primary name=action value=build>Δημιουργία διαφανειών →</button></div></form>")
    return page('Παρουσίαση: πηγή', head + filter_form(c, did, f, on, action=f'/decks/{did}/source') + form.replace("<input type=hidden name=qs value='" + E(safe_qs(request.url.query)) + "'><form", '<form', 1))


@router.get('/decks/{did}/source', response_class=HTMLResponse, dependencies=[Depends(auth)])
def deck_source(request: Request, did: int):
    c = db()
    try:
        d = get_deck(c, did)
        if not T.RECIPE_NEEDS[d['recipe']]: return RedirectResponse(f'/decks/{did}', status_code=303)
        return source_page(c, d, request)
    finally: c.close()


@router.post('/decks/{did}/source', dependencies=[Depends(auth)])
async def deck_source_post(request: Request, did: int):
    same_origin(request); f = await request.form(); c = db()
    try:
        d = get_deck(c, did); st = d['state']; o = dict(d['opts']); action = fv(f, 'action'); qs = safe_qs(fv(f, 'qs'))
        mem = [tuple(m) for m in st.get('members', []) if isinstance(m, (list, tuple)) and len(m) == 2]
        if action == 'add':
            for q in f.getlist('qids'):
                if str(q).isdigit():
                    r = c.execute('SELECT item_id,code FROM question WHERE id=?', (int(q),)).fetchone()
                    if r and tuple(r) not in mem: mem.append(tuple(r))
        elif action == 'addall':
            for r in select_questions(c, filters_from_qs(qs, criteria_on()), 2000):
                if (r['item_id'], r['code']) not in mem: mem.append((r['item_id'], r['code']))
        elif action == 'remove':
            rm = {tuple(M.unkey(k)) for k in f.getlist('rm')}; mem = [m for m in mem if m not in rm]
        elif action == 'build':
            if T.RECIPE_NEEDS[d['recipe']] == 'exam':
                eid = fv(f, 'exam_id')
                if not eid.isdigit(): raise HTTPException(422, 'Διάλεξε διαγώνισμα.')
                st['exam_id'] = int(eid)
            else:
                if f.getlist('sx') or 'sx' in f: st['sx'] = [x for x in f.getlist('sx') if x in dict((k, 0) for k, _, _ in UNITS)]
                o['frag'] = fv(f, 'frag') == '1'; o['answers'] = fv(f, 'answers') if fv(f, 'answers') in dict(T.ANSWERS) else o['answers']
                if not mem: raise HTTPException(422, 'Πρόσθεσε τουλάχιστον ένα ερώτημα.')
            st['members'] = [list(m) for m in mem]; D.save_deck(c, did, state=st, opts=o)
            rep = D.build(c, did, rebuild=bool(c.execute('SELECT 1 FROM deck_slide WHERE deck_id=? LIMIT 1', (did,)).fetchone())); c.commit()
            q = ('?msg=' + 'Λείπουν+αρχεία+λύσης+για:+' + ','.join(rep['missing'][:8]).replace(' ', '+')) if rep['missing'] else ''
            return RedirectResponse(f'/decks/{did}{q}', status_code=303)
        st['members'] = [list(m) for m in mem]; D.save_deck(c, did, state=st); c.commit()
        return RedirectResponse(f'/decks/{did}/source' + ('?' + qs if qs else ''), status_code=303)
    finally: c.close()


# ---------- επεξεργαστής ----------
def hash_of(es, sid):
    for h, g in enumerate(DX.stacks(es)):
        for v, s in enumerate(g):
            if s.get('id') == sid: return f'#/{h}/{v}' if v else f'#/{h}'
    return ''


@router.get('/decks/{did}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def deck_editor(request: Request, did: int, s: int = 0, msg: str = ''):
    c = db()
    try:
        d = get_deck(c, did); sl = D.slides(c, did); stale = D.stale(c, sl); cur = next((x for x in sl if x['id'] == s), sl[0] if sl else None)
        li = []
        for x in sl:
            fl = (' <span class=warnb title="Το αρχείο λύσης άλλαξε από τότε που αντιγράφηκε">⚠ ' + ('λείπει η λύση' if stale[x['id']] == 'missing' else 'η λύση άλλαξε') + '</span>' if x['id'] in stale else '') \
                + (' <span title="Την άλλαξες με το χέρι">✎</span>' if D.edited(x) else '') + (' <small>↓ στοίβα</small>' if x['down'] else '')
            b = ''.join(f"<button name=act value={a} title='{t}'>{ic}</button>" for a, t, ic in (('up', 'Πάνω', '↑'), ('down', 'Κάτω', '↓'), ('copy', 'Αντίγραφο', '⧉'), ('hide', 'Απόκρυψη/εμφάνιση', '👁')))
            b += "<button name=act value=delete class=danger title='Διαγραφή'>🗑</button>"
            li.append(f"<li class='{'cur' if cur and x['id'] == cur['id'] else ''}{' hid' if x['hidden'] else ''}'><a class=t href='/decks/{did}?s={x['id']}'>{x['pos']}. {E(x['title'] or '(χωρίς τίτλο)')}</a>"
                      f"<small>{E(T.LAYOUT_LABEL.get(x['layout'], ''))}</small>{fl}<form method=post action='/decks/{did}/slide/{x['id']}' class=dkbtn>{b}</form></li>")
        lay = ''.join(opt(k, t, '') for k, t, *_ in T.LAYOUTS)
        add = (f"<form method=post action='/decks/{did}/add'>{fld('Νέα διαφάνεια από πρότυπο', f'<select class=r-list name=layout>{lay}</select>')}<input type=hidden name=after value='{cur['id'] if cur else ''}'>"
               "<button>+ Προσθήκη</button></form>")
        edit = slide_form(d, cur, c) if cur else '<p><i>Η παρουσίαση δεν έχει διαφάνειες· πρόσθεσε μία.</i></p>'
        es = DX.effective(d, sl); prev = (f"<iframe class=dkprev id=dkprev name=dkprev sandbox='allow-scripts' src='/decks/{did}/preview{hash_of(es, cur['id']) if cur else ''}'></iframe>"
                f"<p><a class=btn target=_blank href='/decks/{did}/preview{hash_of(es, cur['id']) if cur else ''}'>▶ Ολόκληρη η παρουσίαση (νέα καρτέλα)</a> <small>Εδώ φαίνεται η τρέχουσα διαφάνεια· ανανεώνεται καθώς γράφεις.</small></p>") if es else ''
        body = (f"{CSS}<h2>Παρουσίαση · {E(d['name'])}</h2><p><a href='/decks'>← Όλες οι παρουσιάσεις</a> · {E(T.RECIPE_LABEL.get(d['recipe'], ''))} · {len(sl)} διαφάνειες</p>"
                + (f"<div class='adm adm-info'><p>{E(msg)}</p></div>" if msg else '')
                + f"<div class=dks><div><ol>{''.join(li)}</ol>{add}</div><div>{edit}<h3>Προεπισκόπηση</h3>{prev}</div></div>"
                + settings_panel(d, c) + export_panel(d) + "<script src='/static/deck.js'></script>")
        return page('Παρουσίαση', body)
    finally: c.close()


TOOLBAR = ("<div class='bar dktb' role=toolbar aria-label='Εργαλειοθήκη μπλοκ'>"
           + ''.join(f"<button type=button data-blk={k} title='{E(t)}'>{E(l)}</button>" for k, l, t in (
               ('title', 'Τίτλος', 'Πήγαινε στο πεδίο τίτλου'), ('bullets', '• Bullets', 'Λίστα (ένα-ένα): βάζει και «Bullets ένα-ένα: ναι»'), ('step', 'Βήμα', 'Ομάδα που εμφανίζεται μαζί (::: step)'),
               ('math', '$x$', 'Τύπος μέσα στη γραμμή'), ('mathblock', '$$', 'Τύπος σε δική του γραμμή'), ('image', 'Εικόνα', 'Εικόνα από /files/…'), ('link', 'Σύνδεσμος', 'Σύνδεσμος https'),
               ('code', 'Κώδικας', 'Μπλοκ κώδικα'), ('cols', '2 στήλες', 'Δύο στήλες (::: cols, χωρισμός |||)'), ('quizmcq', 'Quiz ΠΕ', 'Quiz πολλαπλής επιλογής'), ('quiztf', 'Quiz Σ/Λ', 'Quiz Σωστό/Λάθος'),
               ('embed', 'Embed', 'Ενσωμάτωση (μόνο επιτρεπτά domains)'), ('yt', 'YouTube', 'Βίντεο YouTube (nocookie)'), ('gg', 'GeoGebra', 'Υλικό GeoGebra'), ('cj', 'Κύκλωμα', 'CircuitJS/Falstad'),
               ('notes', 'Σημειώσεις', 'Πήγαινε στις σημειώσεις ομιλητή'), ('bg', 'Φόντο', 'Πήγαινε στο χρώμα φόντου'))) + "</div>")


def slide_form(d, s, c):
    o = T.load_opts(s['opts'], deck=False); w = deckmd.warnings(s, domains()); did = d['id']
    lay = ''.join(opt(k, t, s['layout']) for k, t, *_ in T.LAYOUTS)
    fr = ''.join(opt(v, t, {None: '', True: '1', False: '0'}[o['frag']]) for v, t in (('', 'όπως η παρουσίαση'), ('1', 'ναι, ένα-ένα'), ('0', 'όχι')))
    tr = ''.join(opt(v, t, o['transition']) for v, t in [('', 'όπως η παρουσίαση')] + [(x, x) for x in T.TRANSITIONS])
    cl = ''.join(opt(v, t, o['cls']) for v, t in (('', 'κανονικό'), ('small', 'μικρότερη γραμματοσειρά'), ('center', 'κέντρο'), ('dim', 'αχνό')))
    ws = ''.join(f"<li>{E(x)}</li>" for x in w)
    src = f"<p><small>Πηγή: θέμα {E(s['src_item'])} · ερώτημα {E(s['src_qcode'])} · {E(s.get('src_unit') or '')}</small> <button form=rf name=act value=refresh>Ανανέωση από τη λύση</button></p>" if s.get('src_item') else ''
    bgc = inp('bgcolor', o['bg'].get('color', ''), 9); bgi = inp('bgimage', o['bg'].get('image', ''), 40)
    return (f"{src}<form id=rf method=post action='/decks/{did}/slide/{s['id']}'></form>" + (f"<div class='adm adm-warning'><p class=adm-t>Προσοχή</p><ul>{ws}</ul></div>" if w else '')
            + f"<form method=post id=dkform data-did={did} data-sid={s['id']} action='/decks/{did}/slide/{s['id']}'><fieldset><legend>Διαφάνεια {s['pos']}</legend>{fld('Διάταξη', sel('layout', lay))}"
              f"{fld('Τίτλος', inp('title', s['title'], 50))}"
              f"{TOOLBAR}{fld('Σώμα (Markdown, τύποι $..$, οδηγίες ::: cols | quiz | step | embed)', ta('body', s['body'], 12))}"
              f"{fld('Σημειώσεις ομιλητή (Markdown)', ta('notes', s['notes'], 3))}"
              f"{fld('Bullets ένα-ένα', sel('frag', fr))}{fld('Μετάβαση', sel('transition', tr))}{fld('Μορφή', sel('cls', cl))}"
              f"{fld('Φόντο: χρώμα (#rrggbb)', bgc)}{fld('Φόντο: εικόνα (/files/…png|jpg)', bgi)}"
              f"{ck('down', s['down'], 'Κάθετα κάτω από την προηγούμενη (στοίβα)')}{ck('hidden', s['hidden'], 'Κρυφή (δεν εξάγεται)')}"
              "<button class=primary name=act value=save>Αποθήκευση διαφάνειας</button></fieldset></form>")


def settings_panel(d, c):
    o = d['opts']; did = d['id']
    sty = ''.join(opt(k, v['label'], d['style']) for k, v in STYLES.items()); rt = ''.join(opt(k, k, o['ratio']) for k in T.RATIOS); tr = ''.join(opt(k, k, o['transition']) for k in T.TRANSITIONS)
    an = ''.join(opt(k, t, o['answers']) for k, t in T.ANSWERS)
    rebuild = (f"<form method=post action='/decks/{did}/rebuild' style='display:inline'><button title='Ξαναπαράγει τις διαφάνειες της συνταγής· όσες άλλαξες με το χέρι κρατιούνται'>↻ Ξαναχτίσιμο από τη συνταγή</button></form> "
               + (f"<a class=btn href='/decks/{did}/source'>Αλλαγή πηγής</a>" if T.RECIPE_NEEDS[d['recipe']] else '')) if d['recipe'] != 'free' else ''
    nm = inp('name', d['name'], 34); ti = inp('title', d['title'], 40); su = inp('subtitle', d['subtitle'], 40)
    return (f"<details><summary><b>Ρυθμίσεις παρουσίασης</b></summary><form method=post action='/decks/{did}/save'><fieldset><legend>Παρουσίαση</legend>{fld('Όνομα', nm)}"
            f"{fld('Τίτλος', ti)}{fld('Υπότιτλος', su)}"
            f"{fld('Στυλ', sel('style', sty))}{fld('Αναλογία', sel('ratio', rt))}{fld('Μετάβαση', sel('transition', tr))}"
            f"{fld('Quiz: απαντήσεις (στο ξαναχτίσιμο)', sel('answers', an))}"
            f"{ck('numbers', o['numbers'], 'Αρίθμηση διαφανειών')}{ck('frag', o['frag'], 'Bullets ένα-ένα (προεπιλογή)')}{ck('title_slide', o['title_slide'], 'Διαφάνεια τίτλου αυτόματα')}{ck('toc', o['toc'], 'Διαφάνεια περιεχομένων (από τις ενότητες)')}"
            f"{ck('pdf_notes', o['pdf_notes'], 'PDF: σημειώσεις ομιλητή σε ξεχωριστή σελίδα')}{ck('pptx_frag', o['pptx_frag'], 'PowerPoint: bullets ένα-ένα')}{ck('helpmd', o['helpmd'], 'Επισύναψη αρχείου βοήθειας στις λήψεις (zip)')}"
            f"<button class=primary>Αποθήκευση ρυθμίσεων</button></fieldset></form>{rebuild}"
            f"<form method=post action='/decks/{did}/astemplate' style='display:inline'><button>Αποθήκευση ως πρότυπο</button></form></details>")


def export_panel(d):
    did = d['id']
    return (f"<h3>Εξαγωγή</h3><div class=bar><a class=btn href='/decks/{did}/export/reveal'>⬇ Reveal.js (HTML)</a> <a class=btn href='/decks/{did}/export/print' target=_blank>🖨 Εκτύπωση / PDF (από τον browser)</a> "
            f"<a class=btn href='/decks/{did}/export/pptx'>⬇ PowerPoint (.pptx)</a> <a class=btn href='/decks/{did}/export/md'>⬇ deck.md</a></div>"
            f"<form method=post action='/decks/{did}/store' class=bar>{fld('Αποθήκευση στον server ή δημοσίευση (Reveal)', '<select class=r-list name=where><option value=server>αποθήκευση στον server (07_EXAGOGES/decks)</option><option value=publish>δημοσίευση για μαθητές</option></select>')}"
            "<button>Εκτέλεση</button></form>"
            "<div class='adm adm-info'><p class=adm-t>PDF</p><p>Το πάτημα «Εκτύπωση / PDF» ανοίγει τη διάταξη εκτύπωσης του Reveal· πάτα <b>Ctrl+P → «Αποθήκευση ως PDF»</b> (Chrome/Edge, περιθώρια: κανένα, γραφικά φόντου: ναι). "
            "Για πιο προχωρημένο PDF από τον ίδιο τον server υπάρχουν δύο εναλλακτικές που <b>δεν είναι εγκατεστημένες</b>: <b>LibreOffice headless</b> πάνω στο .pptx (~400 MB, εμφάνιση του Pandoc) ή "
            "<b>Pandoc με XeLaTeX/Beamer</b> (~1 GB, χρειάζεται ελληνικές γραμματοσειρές). Δες το <a href='/manual#s34'>εγχειρίδιο §34</a>.</p></div>")


@router.post('/decks/{did}/save', dependencies=[Depends(auth)])
async def deck_save(request: Request, did: int):
    same_origin(request); f = await request.form(); c = db()
    try:
        d = get_deck(c, did); o = dict(d['opts'])
        for k in ('numbers', 'frag', 'title_slide', 'toc', 'pdf_notes', 'pptx_frag', 'helpmd'): o[k] = fv(f, k) == '1'
        for k, ok in (('ratio', T.RATIOS), ('transition', T.TRANSITIONS), ('answers', dict(T.ANSWERS))):
            if fv(f, k) in ok: o[k] = fv(f, k)
        D.save_deck(c, did, name=fv(f, 'name'), title=fv(f, 'title'), subtitle=fv(f, 'subtitle'), style=fv(f, 'style'), opts=o); c.commit()
    finally: c.close()
    return RedirectResponse(f'/decks/{did}', status_code=303)


@router.post('/decks/{did}/add', dependencies=[Depends(auth)])
async def deck_add(request: Request, did: int):
    same_origin(request); f = await request.form(); c = db()
    try:
        get_deck(c, did); after = fv(f, 'after')
        try: sid = D.add_slide(c, did, fv(f, 'layout') or 'content', int(after) if after.isdigit() else None)
        except ValueError as ex: raise HTTPException(422, str(ex))
        c.commit(); return RedirectResponse(f'/decks/{did}?s={sid}', status_code=303)
    finally: c.close()


@router.post('/decks/{did}/slide/{sid}', dependencies=[Depends(auth)])
async def slide_post(request: Request, did: int, sid: int):
    same_origin(request); f = await request.form(); c = db()
    try:
        get_deck(c, did)
        if not D.get_slide(c, did, sid): raise HTTPException(404, 'Δεν υπάρχει αυτή η διαφάνεια.')
        act = fv(f, 'act'); go = sid
        if act == 'save':
            o = {'frag': {'1': True, '0': False}.get(fv(f, 'frag')), 'transition': fv(f, 'transition'), 'cls': fv(f, 'cls'), 'bg': {'color': fv(f, 'bgcolor'), 'image': fv(f, 'bgimage')}}
            cur = D.get_slide(c, did, sid); o['base'] = cur['opts']['base']; o['ans'] = cur['opts']['ans']
            D.update_slide(c, did, sid, layout=fv(f, 'layout'), title=fv(f, 'title'), body=raw(f, 'body'), notes=raw(f, 'notes'), opts=o, down=fv(f, 'down') == '1', hidden=fv(f, 'hidden') == '1')
        elif act in ('up', 'down'): D.move(c, did, sid, -1 if act == 'up' else 1)
        elif act == 'copy':
            try: go = D.copy_slide(c, did, sid) or sid
            except ValueError as ex: raise HTTPException(422, str(ex))
        elif act == 'hide':
            s = D.get_slide(c, did, sid); D.update_slide(c, did, sid, hidden=not s['hidden'])
        elif act == 'delete':
            D.delete_slide(c, did, sid); r = c.execute('SELECT id FROM deck_slide WHERE deck_id=? ORDER BY pos LIMIT 1', (did,)).fetchone(); go = r[0] if r else 0
        elif act == 'refresh':
            if not D.refresh_from_source(c, did, sid): c.commit(); return RedirectResponse(f'/decks/{did}?s={sid}&msg=Η+λύση+δεν+βρέθηκε+ή+η+διαφάνεια+δεν+προέρχεται+από+λύση.', status_code=303)
        c.commit(); return RedirectResponse(f'/decks/{did}' + (f'?s={go}' if go else ''), status_code=303)
    finally: c.close()


@router.post('/decks/{did}/rebuild', dependencies=[Depends(auth)])
def deck_rebuild(request: Request, did: int):
    same_origin(request); c = db()
    try:
        get_deck(c, did)
        try: rep = D.build(c, did, rebuild=True)
        except ValueError as ex: raise HTTPException(422, str(ex))
        c.commit(); msg = f"Ξαναχτίστηκε: {rep['created']} νέες/ανανεωμένες διαφάνειες" + (f", κρατήθηκαν όσες άλλαξες ({len(rep['kept'])}): {', '.join(rep['kept'][:5])}" if rep['kept'] else '') + (f". Λείπουν λύσεις: {', '.join(rep['missing'][:6])}" if rep['missing'] else '')
        from urllib.parse import quote
        return RedirectResponse(f'/decks/{did}?msg=' + quote(msg), status_code=303)
    finally: c.close()


# ---------- προεπισκόπηση και εξαγωγές ----------
@router.get('/decks/{did}/preview', response_class=HTMLResponse, dependencies=[Depends(auth)])
def deck_preview(did: int):
    c = db()
    try:
        d = get_deck(c, did); sl = D.slides(c, did); ds = domains()
        return csp_html(DX.reveal(d, sl, config.load()['data_root'], domains=ds), frames=ds)
    finally: c.close()


@router.post('/decks/{did}/preview/{sid}', response_class=HTMLResponse, dependencies=[Depends(auth)])
async def slide_preview(request: Request, did: int, sid: int):
    """Ζωντανή προεπισκόπηση μιας διαφάνειας από τα πεδία της φόρμας (ΔΕΝ γράφει στη βάση)."""
    same_origin(request); f = await request.form(); c = db()
    try:
        d = get_deck(c, did); cur = D.get_slide(c, did, sid)
        if not cur: raise HTTPException(404, 'Δεν υπάρχει αυτή η διαφάνεια.')
        o = {'frag': {'1': True, '0': False}.get(fv(f, 'frag')), 'transition': fv(f, 'transition'), 'cls': fv(f, 'cls'), 'bg': {'color': fv(f, 'bgcolor'), 'image': fv(f, 'bgimage')}, 'base': cur['opts']['base'], 'ans': cur['opts']['ans']}
        tmp = dict(cur, layout=T.layout_ok(fv(f, 'layout')), title=fv(f, 'title')[:T.LIMITS['title']], body=raw(f, 'body')[:T.LIMITS['body']], notes=raw(f, 'notes')[:T.LIMITS['notes']],
                   opts=T.dump_opts(o, deck=False), down=0, hidden=0)
        d2 = dict(d, opts=dict(d['opts'], title_slide=False, toc=False, numbers=False)); ds = domains()
        page_ = DX.reveal(d2, [tmp], config.load()['data_root'], domains=ds)
        w = deckmd.warnings(tmp, ds)
        if w: page_ = page_.replace('<body>', "<body><div style=\"position:fixed;top:0;left:0;right:0;z-index:99;background:#fff3cd;color:#664d03;font:13px sans-serif;padding:4px 8px\">⚠ " + E(' · '.join(w))[:600] + '</div>', 1)
        return csp_html(page_, frames=ds)
    finally: c.close()


@router.get('/decks/{did}/embed', response_class=HTMLResponse, dependencies=[Depends(auth)])
def deck_embed_test(did: int, u: str = '', ratio: str = '16:9'):
    """Δοκιμή ενός embed σε σελίδα ψηλού επιπέδου (χωρίς sandbox της προεπισκόπησης)· μόνο για επιτρεπτά domains."""
    ds = domains(); src = EM.to_src(u, {}, ds); ok, host, why = EM.check(src, ds)
    if not ok: return csp_html(page_body_msg('Δεν επιτρέπεται: ' + why), 422, frames=ds)
    r = ratio if ratio in EM.RATIOS else '16:9'
    body = (f"<!doctype html><meta charset=utf-8><title>Δοκιμή embed</title><body style='margin:0;font:14px sans-serif'><p style='margin:6px'>Δοκιμή: {E(host)} · <a href='{E(u, quote=True)}' target=_blank rel='noopener noreferrer'>άνοιγμα σε νέα καρτέλα</a></p>"
            f"<div style='aspect-ratio:{EM.RATIOS[r]};width:96vw;margin:0 auto'><iframe src='{E(src, quote=True)}' sandbox='{EM.IFRAME_SANDBOX}' allow='{EM.IFRAME_ALLOW}' allowfullscreen referrerpolicy='strict-origin-when-cross-origin' style='width:100%;height:100%;border:0'></iframe></div>")
    h = csp_html(body, frames=ds); h.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; frame-src " + EM.csp_frames(ds); return h


def page_body_msg(m): return f"<!doctype html><meta charset=utf-8><p style='font:14px sans-serif;margin:1em'>{E(m)}</p>"


DECK_JS = (pathlib.Path(__file__).parent / 'static' / 'deck.js').read_text(encoding='utf-8')


@router.get('/static/deck.js', include_in_schema=False)
def deck_js(): return Response(DECK_JS, media_type='application/javascript')


def with_help(act, data, fname, mime, d):
    """Με opts.helpmd οι λήψεις Reveal/PowerPoint βγαίνουν zip με το αρχείο βοήθειας."""
    if act not in ('reveal', 'pptx') or not d['opts']['helpmd']: return data, fname, mime
    app = pathlib.Path(__file__).parent; b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(fname, data); z.writestr('reveal-help.md' if act == 'reveal' else 'pandoc-help.md', (app / ('manual_reveal.md' if act == 'reveal' else 'manual_pandoc.md')).read_bytes())
    return b.getvalue(), fname.rsplit('.', 1)[0] + '.zip', 'application/zip'


@router.get('/decks/{did}/export/{act}', dependencies=[Depends(auth)])
def deck_export(did: int, act: str):
    c = db()
    try:
        d = get_deck(c, did); sl = D.slides(c, did)
        data, fname, mime = DX.build(d, sl, act)
        if act == 'print': return csp_html(data.decode('utf-8'))
        data, fname, mime = with_help(act, data, fname, mime, d)
        return Response(data, media_type=mime, headers={'Content-Disposition': disp(fname)})
    finally: c.close()


@router.post('/decks/{did}/store', dependencies=[Depends(auth)])
async def deck_store(request: Request, did: int):
    same_origin(request); f = await request.form(); c = db()
    try:
        d = get_deck(c, did); sl = D.slides(c, did); root = config.load()['data_root']; where = fv(f, 'where')
        html_ = DX.reveal(d, sl, root, publish=(where == 'publish')); title = d.get('title') or d['name']
        if where == 'publish':
            from . import publish
            s_ = publish.save_site(title, {'index.html': html_.encode('utf-8')}, source=f"παρουσίαση: {d['name']}")
            return page('Δημοσιεύτηκε', f"<h2>Δημοσιεύτηκε</h2><p><a href='/p/{E(s_)}/'>/p/{E(s_)}/</a></p>"
                        + ('' if publish.get_pw_hash() else "<div class='adm adm-warning'><p class=adm-t>Δεν υπάρχει κωδικός μαθητή</p><p>Ορίστε τον στις <a href='/publish'>Δημοσιεύσεις</a>.</p></div>")
                        + f"<p><a href='/publish'>Δημοσιεύσεις</a> · <a href='/decks/{did}'>Πίσω</a></p>")
        course = d['course_code'] or 'EXPORTS'
        out_dir = pathlib.Path(root) / course / '07_EXAGOGES' / 'decks'; out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{did}-{DX.slug(title)}.html"; out.write_bytes(html_.encode('utf-8'))
        return page('Αποθηκεύτηκε', f"<h2>Αποθηκεύτηκε στον server</h2><p><code>{E(str(out.relative_to(root)))}</code></p><p><a href='/fb'>Αρχεία</a> · <a href='/decks/{did}'>Πίσω</a></p>")
    finally: c.close()
