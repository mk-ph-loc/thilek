"""0.34: σελίδες του site builder (/sites): λίστα, επεξεργαστής (δέντρο σελίδων/μενού, φόρμα σελίδας με εργαλειοθήκη μπλοκ, ζωντανή προεπισκόπηση), προεπισκόπηση όλου του site και εξαγωγή zip.
HTML από strings, χωρίς inline JS (φόρμες/κουμπιά + static/site.js), same_origin σε κάθε POST. Η προεπισκόπηση σερβίρεται σε sandboxed iframe με αυστηρό CSP.
Δεν υπάρχει δημοσίευση στο /p/ (0.35): μόνο προεπισκόπηση και zip."""
import html, pathlib
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from . import config, deck as D, deckexport as DX, deckmd, embed as EM, settings, site as S
from .deckui import CSS, ck, csp_html, fv, inp, opt, raw, sel, ta
from .main_auth import auth
from .review import db, fld, page, same_origin
from .wizard import disp

router = APIRouter()
E = html.escape
CSS2 = CSS + "<style>.sts{display:grid;grid-template-columns:minmax(240px,320px) 1fr;gap:1rem;align-items:start}.sts ol{list-style:none;margin:0;padding:0}.sts li{border:1px solid var(--border);border-radius:8px;margin:.2rem 0;padding:.25rem .5rem}.sts li.cur{border-color:var(--accent,#2563eb);box-shadow:0 0 0 2px var(--accent,#2563eb) inset}.sts li.hid{opacity:.5}.sts li form{display:inline}.sts li .t{font-weight:600;text-decoration:none}.sts li small{opacity:.75}.sts textarea{width:100%;font-family:ui-monospace,Consolas,monospace}</style>"
TOOLS = (('callout_note', 'Σημείωση', 'Πλαίσιο σημείωσης'), ('callout_tip', 'Συμβουλή', 'Πλαίσιο συμβουλής'), ('callout_warning', 'Προσοχή', 'Πλαίσιο προσοχής'), ('math', '$x$', 'Τύπος μέσα στη γραμμή'), ('mathblock', '$$', 'Τύπος σε δική του γραμμή'),
         ('bullets', '• Λίστα', 'Λίστα'), ('image', 'Εικόνα', 'Εικόνα από /files/…'), ('link', 'Σύνδεσμος', 'Σύνδεσμος https'), ('pagelink', 'Σύνδεσμος σελίδας', 'Σύνδεσμος σε άλλη σελίδα του site (thilek://page/slug)'),
         ('code', 'Κώδικας', 'Μπλοκ κώδικα'), ('cols', '2 στήλες', 'Δύο στήλες'), ('quizyaml', 'Quiz (YAML)', 'Ερώτηση με απάντηση που ανοίγει'), ('quizref', 'Quiz από «Quiz»', 'Στιγμιότυπο quiz με αριθμό'),
         ('deckref', 'Παρουσίαση', 'Κάρτα προς στιγμιότυπο παρουσίασης με αριθμό'), ('file', 'Αρχείο', 'Εικόνα ή αρχείο από το data_root (pdf, png, jpg, svg, txt, json)'), ('embed', 'Embed', 'Ενσωμάτωση (μόνο επιτρεπτά domains)'),
         ('yt', 'YouTube', 'Βίντεο YouTube'), ('gg', 'GeoGebra', 'GeoGebra'), ('cj', 'Κύκλωμα', 'CircuitJS/Falstad'))
TOOLBAR = "<div class='bar dktb' role=toolbar aria-label='Εργαλειοθήκη μπλοκ'>" + ''.join(f"<button type=button data-blk={k} title='{E(t)}'>{E(l)}</button>" for k, l, t in TOOLS) + "</div>"
JS = (pathlib.Path(__file__).parent / 'static' / 'site.js').read_text(encoding='utf-8')


def domains(): return EM.hosts(settings.get('embed_domains'))
def get_site(c, sid):
    s = S.get(c, sid)
    if not s: raise HTTPException(404, 'Δεν υπάρχει αυτό το site.')
    return s


@router.get('/static/site.js', include_in_schema=False)
def site_js(): return Response(JS, media_type='application/javascript')


@router.get('/sites', response_class=HTMLResponse, dependencies=[Depends(auth)])
def sites_home(msg: str = ''):
    c = db(); rs = c.execute('SELECT s.*,(SELECT count(*) FROM site_page p WHERE p.site_id=s.id) n FROM site s ORDER BY s.updated DESC,s.id DESC').fetchall(); c.close()
    trs = ''.join(f"<tr><td><a href='/sites/{r['id']}'>{E(r['name'])}</a></td><td>{r['n']}</td><td>{E(S.THEMES[S.theme_of(r['theme'])][0])}</td><td>{E(r['updated'] or '')}</td>"
                  f"<td><form method=post action='/sites/{r['id']}/copy' style='display:inline'><button>Αντίγραφο</button></form> <form method=post action='/sites/{r['id']}/delete' style='display:inline'><button class=danger>Διαγραφή</button></form></td></tr>" for r in rs)
    body = (f"{CSS2}<h2>Site μαθήματος</h2><p>Φτιάχνεις ένα μικρό site με <b>σελίδες και μενού</b>: κείμενο Markdown, quiz και παρουσιάσεις που ήδη έχεις, αρχεία. Βγαίνει ως zip με αυτόνομες σελίδες HTML (που ανοίγουν και χωρίς δίκτυο). "
            "<small>Δημοσίευση στους μαθητές (/p/), αναζήτηση και διαδραστικά έρχονται αργότερα.</small></p>" + (f"<div class='adm adm-info'><p>{E(msg)}</p></div>" if msg else '')
            + f"<form method=post action=/sites/new><fieldset><legend>Νέο site</legend>{fld('Όνομα', inp('name', 'Νέο site', 34))}<button class=primary>Δημιουργία →</button></fieldset></form>"
            + f"<h3>Τα site μου ({len(rs)})</h3>" + (f"<table><tr><th>Όνομα</th><th>Σελίδες</th><th>Θέμα</th><th>Τελευταία αλλαγή</th><th></th></tr>{trs}</table>" if rs else '<p><i>Κανένα ακόμα.</i></p>'))
    return page('Site', body)


@router.post('/sites/new', dependencies=[Depends(auth)])
async def site_new(request: Request):
    same_origin(request); f = await request.form(); c = db()
    try:
        course = settings.get('course_active') if settings.get('course_active') not in (None, 'all') else ''
        sid = S.create(c, fv(f, 'name') or 'Νέο site', course=course or ''); c.commit(); return RedirectResponse(f'/sites/{sid}', status_code=303)
    finally: c.close()


@router.post('/sites/{sid}/delete', dependencies=[Depends(auth)])
def site_delete(request: Request, sid: int):
    same_origin(request); c = db(); S.delete_site(c, sid); c.commit(); c.close(); return RedirectResponse('/sites', status_code=303)


@router.post('/sites/{sid}/copy', dependencies=[Depends(auth)])
def site_copy(request: Request, sid: int):
    same_origin(request); c = db(); n = S.copy_site(c, sid)
    if not n: raise HTTPException(404)
    c.commit(); c.close(); return RedirectResponse(f'/sites/{n}', status_code=303)


def tree_html(c, s, cur):
    sid = s['id']; rs = S.rows(c, sid); od = S.order(rs); li = []
    for p, d in od:
        b = ''.join(f"<button name=act value={a} title='{t}'>{ic}</button>" for a, t, ic in (('up', 'Πάνω', '↑'), ('down', 'Κάτω', '↓'), ('in', 'Μέσα (υποσελίδα της προηγούμενης)', '→'), ('out', 'Έξω (ένα επίπεδο πάνω)', '←'), ('hide', 'Απόκρυψη/εμφάνιση', '👁')))
        n = len(S.descendants(rs, p['id'])); conf = f" title='Διαγράφει και {n} υποσελίδες'" if n else " title='Διαγραφή'"
        b += f"<button name=act value=delete class=danger{conf}>🗑</button>"
        home = ' <small title="Αρχική σελίδα">⌂</small>' if s['opts']['home'] == p['id'] else ''
        li.append(f"<li class='{'cur' if cur and p['id'] == cur['id'] else ''}{' hid' if p['hidden'] else ''}' style='margin-left:{d * 14}px'><a class=t href='/sites/{sid}?p={p['id']}'>{'▸ ' if p['kind'] == 'section' else ''}{E(p['title'] or '(χωρίς τίτλο)')}</a>{home} <small>{E(p['slug'])}</small>"
                  f"<form method=post action='/sites/{sid}/page/{p['id']}' class=dkbtn>{b}</form></li>")
    return f"<ol>{''.join(li)}</ol>", od


@router.get('/sites/{sid}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def site_editor(request: Request, sid: int, p: int = 0, msg: str = ''):
    c = db()
    try:
        s = get_site(c, sid); tree, od = tree_html(c, s, None); pg = S.get_page(c, sid, p) or (od[0][0] if od else None)
        tree, od = tree_html(c, s, pg)
        add = (f"<form method=post action='/sites/{sid}/add'>{fld('Νέα σελίδα: τίτλος', inp('title', '', 24))}{fld('Είδος', sel('kind', ''.join(opt(k, t, 'page') for k, t in S.KINDS)))}"
               + ck('child', False, 'Ως υποσελίδα της τρέχουσας') + f"<input type=hidden name=cur value='{pg['id'] if pg else ''}'><button>+ Προσθήκη</button></form>")
        edit = page_form(s, pg, c) if pg else '<p><i>Το site δεν έχει σελίδες· πρόσθεσε μία.</i></p>'
        prev = (f"<iframe class=dkprev id=stprev name=stprev sandbox='allow-scripts allow-popups' src='/sites/{sid}/view/{E(pg['slug'])}'></iframe>" if pg else '')
        body = (f"{CSS2}<h2>Site · {E(s['name'])}</h2><p><a href='/sites'>← Όλα τα site</a> · {len(od)} σελίδες</p>" + (f"<div class='adm adm-info'><p>{E(msg)}</p></div>" if msg else '')
                + f"<div class=sts><div>{tree}{add}</div><div>{edit}<h3>Προεπισκόπηση</h3>{prev}<p><small>Ανανεώνεται καθώς γράφεις (χωρίς αποθήκευση)· οι σύνδεσμοι του μενού δείχνουν τις αποθηκευμένες σελίδες.</small></p></div></div>"
                + settings_panel(s, od) + export_panel(s, c) + "<script src='/static/site.js'></script>")
        return page('Site', body)
    finally: c.close()


def page_form(s, p, c):
    sid = s['id']; ctx = S.Ctx(c, s, config.load()['data_root'], domains(), 'preview'); _, w = S.body_html(ctx, p)
    ws = ''.join(f"<li>{E(x)}</li>" for x in w)
    return ((f"<div class='adm adm-warning'><p class=adm-t>Προσοχή</p><ul>{ws}</ul></div>" if w else '')
            + f"<form method=post id=stform data-sid={sid} data-pid={p['id']} action='/sites/{sid}/page/{p['id']}'><fieldset><legend>Σελίδα «{E(p['title'])}»</legend>"
              f"{fld('Τίτλος', inp('title', p['title'], 50))}{fld('Διεύθυνση (slug, a-z 0-9 -)', inp('slug', p['slug'], 30))}{fld('Είδος', sel('kind', ''.join(opt(k, t, p['kind']) for k, t in S.KINDS)))}"
              f"{TOOLBAR}{fld('Σώμα (Markdown, τύποι $..$, οδηγίες ::: cols | quiz | embed | quiz-ref ID | deck-ref ID | file διαδρομή | callout note|tip|warning|danger)', ta('body', p['body'], 16))}"
              f"{ck('hidden', p['hidden'], 'Κρυφή (δεν μπαίνει στο μενού ούτε στην εξαγωγή)')}<button class=primary name=act value=save>Αποθήκευση σελίδας</button></fieldset></form>")


def settings_panel(s, od):
    sid = s['id']; th = ''.join(opt(k, v[0], s['theme']) for k, v in S.THEMES.items())
    home = "<option value='0'>— η πρώτη σελίδα —</option>" + ''.join(opt(p['id'], p['title'], s['opts']['home']) for p, _ in od if p['kind'] == 'page')
    return (f"<details><summary><b>Ρυθμίσεις site</b></summary><form method=post action='/sites/{sid}/save'><fieldset><legend>Site</legend>{fld('Όνομα', inp('name', s['name'], 34))}{fld('Τίτλος (στο μενού)', inp('title', s['title'], 40))}"
            f"{fld('Θέμα', sel('theme', th))}{fld('Αρχική σελίδα', sel('home', home))}{fld('Υποσέλιδο', inp('footer', s['opts']['footer'], 50))}<button class=primary>Αποθήκευση ρυθμίσεων</button></fieldset></form></details>")


def export_panel(s, c):
    sid = s['id']; ctx = S.Ctx(c, s, config.load()['data_root'], domains(), 'export'); ws = []
    for p, _ in ctx.vis:
        _, w = S.page_html(ctx, p); ws += [f"{p['title']}: {x}" for x in w]
    wl = (f"<div class='adm adm-warning'><p class=adm-t>Προειδοποιήσεις ({len(ws)})</p><ul>{''.join(f'<li>{E(x)}</li>' for x in ws[:30])}</ul></div>" if ws else '')
    return (f"<h3>Προεπισκόπηση και εξαγωγή</h3>{wl}<div class=bar><a class=btn target=_blank href='/sites/{sid}/view/index'>▶ Ολόκληρο το site (νέα καρτέλα)</a> <a class=btn href='/sites/{sid}/export.zip'>⬇ Zip (index.html + σελίδες)</a></div>"
            "<div class='adm adm-info'><p>Τα quiz και οι παρουσιάσεις μπαίνουν ως <b>στιγμιότυπο</b> της ώρας της εξαγωγής (αν αλλάξεις το quiz μετά, ξαναεξάγεις). Οι εικόνες Markdown ενσωματώνονται· τα αρχεία (pdf κ.ά.) μπαίνουν στο zip.</p></div>")


@router.post('/sites/{sid}/save', dependencies=[Depends(auth)])
async def site_save(request: Request, sid: int):
    same_origin(request); f = await request.form(); c = db()
    try:
        get_site(c, sid); home = fv(f, 'home'); S.save_site(c, sid, name=fv(f, 'name'), title=fv(f, 'title'), theme=fv(f, 'theme'), footer=fv(f, 'footer'), home=int(home) if home.isdigit() else 0); c.commit()
        return RedirectResponse(f'/sites/{sid}?msg=Αποθηκεύτηκε.', status_code=303)
    finally: c.close()


@router.post('/sites/{sid}/add', dependencies=[Depends(auth)])
async def site_add(request: Request, sid: int):
    same_origin(request); f = await request.form(); c = db()
    try:
        get_site(c, sid); cur = fv(f, 'cur'); par = int(cur) if cur.isdigit() and fv(f, 'child') == '1' else 0
        pid = S.add_page(c, sid, fv(f, 'title') or 'Νέα σελίδα', fv(f, 'kind') or 'page', par, after=int(cur) if cur.isdigit() and not par else None); c.commit()
        if not pid: return RedirectResponse(f'/sites/{sid}?msg=Δεν+προστέθηκε:+όριο+σελίδων+ή+βάθους+μενού.', status_code=303)
        return RedirectResponse(f'/sites/{sid}?p={pid}', status_code=303)
    finally: c.close()


@router.post('/sites/{sid}/page/{pid}', dependencies=[Depends(auth)])
async def site_page_act(request: Request, sid: int, pid: int):
    same_origin(request); f = await request.form(); act = fv(f, 'act'); c = db()
    try:
        get_site(c, sid); p = S.get_page(c, sid, pid)
        if not p: raise HTTPException(404, 'Δεν υπάρχει αυτή η σελίδα.')
        msg = ''
        if act == 'save': S.update_page(c, sid, pid, title=fv(f, 'title'), slug=fv(f, 'slug'), kind=fv(f, 'kind'), body=raw(f, 'body'), hidden=fv(f, 'hidden') == '1'); msg = 'Αποθηκεύτηκε.'
        elif act in ('up', 'down', 'in', 'out'):
            if not S.move(c, sid, pid, act): msg = 'Δεν γίνεται αυτή η μετακίνηση.'
        elif act == 'hide': S.update_page(c, sid, pid, hidden=not p['hidden'])
        elif act == 'delete':
            n = S.delete_page(c, sid, pid); c.commit(); return RedirectResponse(f'/sites/{sid}?msg=Διαγράφηκαν+{n}+σελίδες.', status_code=303)
        else: raise HTTPException(422, 'Άγνωστη ενέργεια.')
        c.commit(); return RedirectResponse(f'/sites/{sid}?p={pid}' + (f'&msg={msg}' if msg else ''), status_code=303)
    finally: c.close()


def _frames(): return domains()


@router.get('/sites/{sid}/view/{slug}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def site_view(sid: int, slug: str):
    c = db()
    try:
        s = get_site(c, sid); ds = domains(); ctx = S.Ctx(c, s, config.load()['data_root'], ds, 'preview'); p = ctx.home() if slug == 'index' else ctx.slug_of.get(slug)
        if not p:
            return csp_html(f"<!doctype html><meta charset=utf-8><p style='font:14px sans-serif;margin:1em'>{'Δεν υπάρχει εμφανίσιμη σελίδα.' if slug == 'index' else 'Δεν υπάρχει αυτή η σελίδα ή είναι κρυφή.'}</p>", 404, frames=ds)
        h, _ = S.page_html(ctx, p); return csp_html(h, frames=ds)
    finally: c.close()


@router.post('/sites/{sid}/preview/{pid}', response_class=HTMLResponse, dependencies=[Depends(auth)])
async def site_preview(request: Request, sid: int, pid: int):
    """Ζωντανή προεπισκόπηση σελίδας από τα πεδία της φόρμας (ΔΕΝ γράφει στη βάση)."""
    same_origin(request); f = await request.form(); c = db()
    try:
        s = get_site(c, sid); p = S.get_page(c, sid, pid)
        if not p: raise HTTPException(404, 'Δεν υπάρχει αυτή η σελίδα.')
        ds = domains(); ctx = S.Ctx(c, s, config.load()['data_root'], ds, 'preview'); body = raw(f, 'body')[:S.LIM['body']]
        if not any(x['id'] == pid for x, _ in ctx.vis): ctx.vis.append((p, 0))
        kind = fv(f, 'kind') if fv(f, 'kind') in S.KIND_KEYS else p['kind']
        h, w = S.page_html(ctx, p, body=body, title=fv(f, 'title')[:S.LIM['title']] or p['title'], kind=kind, note=' · '.join(w_ for w_ in S.body_html(ctx, p, body)[1])[:600])
        return csp_html(h, frames=ds)
    finally: c.close()


@router.get('/sites/{sid}/deck/{did}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def site_deck(sid: int, did: int):
    c = db()
    try:
        get_site(c, sid); d = D.get(c, did)
        if not d: raise HTTPException(404, 'Δεν υπάρχει αυτή η παρουσίαση.')
        ds = domains(); return csp_html(DX.reveal(d, D.slides(c, did), config.load()['data_root'], domains=ds), frames=ds)
    finally: c.close()


@router.get('/sites/{sid}/file', dependencies=[Depends(auth)])
def site_file(sid: int, p: str = ''):
    c = db()
    try: get_site(c, sid)
    finally: c.close()
    fp, why = S.safe_file(config.load()['data_root'], p)
    if not fp: raise HTTPException(404, why)
    mime = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml', '.txt': 'text/plain; charset=utf-8', '.json': 'application/json'}[fp.suffix.lower()]
    return Response(fp.read_bytes(), media_type=mime, headers={'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; sandbox", 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': disp(fp.name).replace('attachment', 'inline')})


@router.get('/sites/{sid}/export.zip', dependencies=[Depends(auth)])
def site_export(sid: int):
    c = db()
    try:
        get_site(c, sid)
        try: data, fname, _ = S.build_zip(c, sid, domains())
        except ValueError as ex: raise HTTPException(422, str(ex))
        return Response(data, media_type='application/zip', headers={'Content-Disposition': disp(fname)})
    finally: c.close()
