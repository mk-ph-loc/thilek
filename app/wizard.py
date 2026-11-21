"""Wizard εξαγωγών (0.21.0): /wizard. Κάθε συνταγή (πίνακας wizard_recipe) κρατά ολόκληρη την κατάσταση των 6 βημάτων και ξανατρέχει.
Οι υπάρχουσες εξαγωγές (λύσεις, έγγραφα, PDF) καλούνται από εδώ· νέο: Excel και Markdown με προσαρμοσμένες μονάδες."""
import datetime, json, pathlib, re
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from . import config, settings, wizmodel as M, wizexam
from .main_auth import auth
from .review import db, page, html, same_origin, fld, chk, TYPE_OPTS
from .library import select_questions, filters_of, chapter_opts, lsol_opts
from .solstyle import UNITS, STYLES

router = APIRouter()
E = html.escape
VIS = {'show': 'ναι', 'hidden': 'κρυφό', 'append': 'στο τέλος'}
STEPS = ((1, 'Επιλογή'), (2, 'Οργάνωση'), (3, 'Βαθμοί'), (4, 'Τύπος αναφοράς'), (5, 'Περιεχόμενο'), (6, 'Έλεγχος και εξαγωγή'))
CSS = ("<style>.wsteps{display:flex;flex-wrap:wrap;gap:.4rem;list-style:none;padding:0;margin:.4rem 0 1rem}.wsteps li a,.wsteps li span{display:block;padding:.3rem .8rem;border:1px solid var(--border);border-radius:999px;text-decoration:none}"
       ".wsteps li.on span{background:var(--accent,#2563eb);color:#fff;border-color:transparent}.wsteps li.done a{opacity:.85}.wnav{display:flex;gap:.6rem;margin:1rem 0;align-items:center}"
       ".wsum{font-size:1.1rem;margin:.5rem 0}.wsum.bad b{color:#dc2626}.wprev{width:100%;height:560px;border:1px solid var(--border);border-radius:8px;background:#fff}.inselect tr.insel{opacity:.55}</style>")


def now(): return datetime.datetime.now().isoformat(timespec='seconds')


def get_recipe(c, rid):
    r = c.execute('SELECT * FROM wizard_recipe WHERE id=?', (rid,)).fetchone()
    if not r: raise HTTPException(404, 'Δεν υπάρχει αυτή η συνταγή.')
    return r['name'], M.load_state(r['state'])


def save_state(c, rid, st, name=None):
    if name: c.execute('UPDATE wizard_recipe SET name=?,state=?,updated=? WHERE id=?', (name.strip()[:120] or 'Συνταγή', json.dumps(st, ensure_ascii=False), now(), rid))
    else: c.execute('UPDATE wizard_recipe SET state=?,updated=? WHERE id=?', (json.dumps(st, ensure_ascii=False), now(), rid))
    c.commit()


def stepnav(rid, cur):
    li = ''.join((f"<li class=on><span>{n}. {E(t)}</span></li>" if n == cur else f"<li class='{'done' if n < cur else ''}'><a href='/wizard/{rid}/{n}'>{n}. {E(t)}</a></li>") for n, t in STEPS)
    return f"<ol class=wsteps>{li}</ol>"


def nav(rid, step, nxt=True):
    prev = f"<a class=btn href='/wizard/{rid}/{step - 1}'>← Πίσω</a>" if step > 1 else '<span></span>'
    return f"<div class=wnav>{prev}<button class=primary name=go value=next>{'Αποθήκευση και επόμενο →' if nxt else 'Αποθήκευση'}</button></div>"


def shell(rid, name, step, inner, post=True):
    body = f"{CSS}<h2>Wizard εξαγωγών · {E(name)}</h2>{stepnav(rid, step)}"
    return page(f'Wizard {step}', body + (f"<form method=post action='/wizard/{rid}/{step}'>{inner}</form>" if post else inner))


def safe_prefix(p): return bool(re.match(r'^[A-Za-z0-9_./-]{0,60}$', p)) and '..' not in p and not p.startswith('/')


def safe_qs(q): return q if re.match(r'^[A-Za-z0-9_=&%.,+*~-]*$', q or '') else ''


# ---------- λίστα συνταγών ----------
@router.get('/wizard', response_class=HTMLResponse, dependencies=[Depends(auth)])
def wizard_home():
    c = db(); rows = c.execute('SELECT id,name,state,updated FROM wizard_recipe ORDER BY updated DESC,id DESC').fetchall(); c.close()
    trs = ''.join(f"<tr><td><a href='/wizard/{r['id']}/1'>{E(r['name'])}</a></td><td>{len(M.load_state(r['state'])['members'])}</td><td>{E(dict(M.FORMATS).get(M.load_state(r['state'])['format'], ''))}</td><td>{E(r['updated'] or '')}</td>"
                  f"<td><a class=btn href='/wizard/{r['id']}/6'>Εξαγωγή</a> <form method=post action='/wizard/{r['id']}/copy' style='display:inline'><button>Αντίγραφο</button></form> "
                  f"<form method=post action='/wizard/{r['id']}/delete' style='display:inline'><button class=danger>Διαγραφή</button></form></td></tr>" for r in rows)
    body = (f"{CSS}<h2>Wizard εξαγωγών</h2><p>Ο οδηγός σε φέρνει βήμα-βήμα από την επιλογή ερωτημάτων μέχρι το αρχείο. Κάθε εξαγωγή αποθηκεύεται ως <b>συνταγή</b> που ξανατρέχεις όποτε αλλάξουν οι λύσεις.</p>"
            "<form method=post action=/wizard/new class=filters><label class=f><span>Όνομα νέας συνταγής</span><input class=r-txt name=name size=30 value='Νέα συνταγή' required></label><button class=primary>Νέα συνταγή</button></form>"
            f"<h3>Οι συνταγές μου ({len(rows)})</h3>" + (f"<table><tr><th>Όνομα</th><th>Ερωτήματα</th><th>Μορφή</th><th>Τελευταία αλλαγή</th><th></th></tr>{trs}</table>" if rows else '<p><i>Καμία συνταγή ακόμα.</i></p>'))
    return page('Wizard εξαγωγών', body)


@router.post('/wizard/new', dependencies=[Depends(auth)])
async def wizard_new(request: Request):
    same_origin(request); f = await request.form(); c = db()
    rid = c.execute('INSERT INTO wizard_recipe(name,state,created,updated) VALUES(?,?,?,?)', ((str(f.get('name') or 'Νέα συνταγή').strip()[:120] or 'Νέα συνταγή'), json.dumps(M.new_state()), now(), now())).lastrowid
    c.commit(); c.close(); return RedirectResponse(f'/wizard/{rid}/1', status_code=303)


@router.post('/wizard/{rid}/delete', dependencies=[Depends(auth)])
def wizard_delete(request: Request, rid: int):
    same_origin(request); c = db(); c.execute('DELETE FROM wizard_recipe WHERE id=?', (rid,)); c.commit(); c.close(); return RedirectResponse('/wizard', status_code=303)


@router.post('/wizard/{rid}/copy', dependencies=[Depends(auth)])
def wizard_copy(request: Request, rid: int):
    same_origin(request); c = db(); name, st = get_recipe(c, rid)
    n = c.execute('INSERT INTO wizard_recipe(name,state,created,updated) VALUES(?,?,?,?)', (name[:100] + ' (αντίγραφο)', json.dumps(st, ensure_ascii=False), now(), now())).lastrowid
    c.commit(); c.close(); return RedirectResponse(f'/wizard/{n}/1', status_code=303)


# ---------- βήματα ----------
def criteria_on():
    on = settings.get('wiz_criteria').split(',')
    return [k for k in M.CRITERIA_KEYS if k in on]


def filter_form(c, rid, f, on):
    sel = lambda opts, cur: ''.join(f"<option value='{v}'{' selected' if cur == v else ''}>{t}</option>" for v, t in opts)
    qt = f['qtype'][0] if f.get('qtype') else ''; ctl = []
    def add(k, label, html_):
        if k in on: ctl.append(fld(label, html_))
    add('q', 'Λέξεις-κλειδιά', f"<input class=r-txt name=q value='{E(f.get('q', ''))}' size=16>")
    add('qtype', 'Τύπος', f"<select class=r-list name=qtype><option value=''>— όλοι —</option>{TYPE_OPTS(qt)}</select>")
    add('chapter', 'Κεφάλαιο', f"<select class=r-list name=chapter>{chapter_opts(c, f.get('chapter', ''))}</select>")
    add('image', 'Εικόνα', f"<select class=r-list name=image>{sel((('', '— όλα —'), ('1', 'με εικόνα'), ('0', 'χωρίς εικόνα')), f.get('image', ''))}</select>")
    add('position', 'Θέμα', f"<select class=r-list name=position>{sel((('', '— όλα —'), ('2', 'Θέμα 2'), ('4', 'Θέμα 4')), str(f.get('position', '')))}</select>")
    add('fav', 'Αγαπημένα', f"<select class=r-list name=fav>{sel((('', '— όλα —'), ('1', 'μόνο αγαπημένα')), f.get('fav', ''))}</select>")
    add('yli', 'Ενότητα ΙΕΠ', f"<input class=r-txt name=yli value='{E(f.get('yli', ''))}' size=5>")
    add('section', 'Υποενότητα', f"<input class=r-txt name=section value='{E(f.get('section', ''))}' size=6>")
    add('tag', 'Ετικέτες', f"<input class=r-txt name=tag value='{E(f.get('tag', ''))}' size=14>")
    add('lsol', 'Λύση εκπαιδευτικού', f"<select class=r-list name=lsol>{lsol_opts(f.get('lsol', ''))}</select>")
    add('upto', 'Ύλη από–μέχρι σελίδα', f"<input class=r-txt name=frm value='{E(f.get('frm', ''))}' size=4> – <input class=r-txt name=upto value='{E(f.get('upto', ''))}' size=4>")
    return f"<form method=get action='/wizard/{rid}/1' class=filters>{''.join(ctl)}<button>Εμφάνιση</button></form><p><small>Ποια κριτήρια φαίνονται ρυθμίζεται στις <a href='/settings'>Ρυθμίσεις</a>.</small></p>"


def step_filters(request, on):
    p = request.query_params; f = filters_of(p)
    for k in [x for x in M.CRITERIA_KEYS if x not in on and x in f]: f[k] = [] if k == 'qtype' else ''
    f['upto'] = (p.get('upto') or '').strip() if 'upto' in on and (p.get('upto') or '').strip().isdigit() else ''
    f['frm'] = (p.get('frm') or '').strip() if f['upto'] and (p.get('frm') or '').strip().isdigit() else ''
    return f


def filters_from_qs(qs, on):
    """Φίλτρα από query string (όπως στο step_filters) για την «Προσθήκη ΟΛΩΝ»."""
    from urllib.parse import parse_qsl
    p = dict(parse_qsl(qs)); f = filters_of(p)
    for k in [x for x in M.CRITERIA_KEYS if x not in on and x in f]: f[k] = [] if k == 'qtype' else ''
    f['upto'] = p.get('upto', '') if 'upto' in on and p.get('upto', '').isdigit() else ''
    f['frm'] = p.get('frm', '') if f['upto'] and p.get('frm', '').isdigit() else ''
    return f


def page1(c, rid, name, st, request):
    on = criteria_on(); f = step_filters(request, on); has = bool(request.url.query)
    rows = select_questions(c, f, 300) if has else []
    inn = {tuple(m) for m in st['members']}
    rt = ''.join(f"<tr class='{'insel' if (r['item_id'], r['code']) in inn else ''}'><td><input type=checkbox name=qids value={r['qid']}></td><td><a href='/review/{E(r['item_id'])}'>{E(r['item_id'])}</a></td><td>{E(r['code'])}</td><td>{r['points'] or ''}</td>"
                 f"<td>{E(r['qtype'] or '')}</td><td>{'✎' if r['has_sol'] else ''}</td><td>{E(r['tags'] or '')}</td></tr>" for r in rows)
    res = (f"<h3>Αποτελέσματα ({len(rows)}{'+' if len(rows) >= 300 else ''})</h3><div class=bar><button name=action value=add>Προσθήκη επιλεγμένων</button> <button name=action value=addall>Προσθήκη ΟΛΩΝ των αποτελεσμάτων</button> "
           f"<small>Αχνές γραμμές = ήδη στη λίστα. Επιλέγοντας όλο το θέμα, πρόσθεσε όλα του τα ερωτήματα.</small></div><table class=inselect><tr><th><input type=checkbox data-all=qids></th><th>Θέμα</th><th>Ερώτημα</th><th>Μον.</th><th>Τύπος</th><th>Λύση</th><th>Ετικέτες</th></tr>{rt}</table>"
           ) if has else '<p><i>Διάλεξε κριτήρια και πάτα «Εμφάνιση» (ή πάτα Εμφάνιση χωρίς κριτήρια για όλα).</i></p>'
    cur = ''.join(f"<tr><td><input type=checkbox name=rm value='{E(M.key(*m))}'></td><td>{E(m[0])}</td><td>{E(m[1])}</td></tr>" for m in map(tuple, st['members']))
    selected = (f"<h3>Η λίστα μου ({len(st['members'])})</h3>" + (f"<table><tr><th></th><th>Θέμα</th><th>Ερώτημα</th></tr>{cur}</table><div class=bar><button name=action value=remove class=danger>Αφαίρεση επιλεγμένων</button> <button name=action value=clear class=danger>Καθαρισμός λίστας</button></div>" if cur else '<p><i>Άδεια.</i></p>'))
    form = f"<input type=hidden name=qs value='{E(safe_qs(request.url.query))}'>{res}{selected}<div class=wnav><span></span>{'<a class=btn href=/wizard/%d/2>Επόμενο →</a>' % rid if st['members'] else '<span>Πρόσθεσε τουλάχιστον ένα ερώτημα.</span>'}</div>"
    return page('Wizard 1', f"{CSS}<h2>Wizard εξαγωγών · {E(name)}</h2>{stepnav(rid, 1)}<h3>1. Επιλογή θεμάτων ή ερωτημάτων</h3>{filter_form(c, rid, f, on)}<form method=post action='/wizard/{rid}/1'>{form}</form>")


def page2(c, rid, name, st):
    rd = lambda k, opts, cur: ''.join(f"<label class='f chk'><input type=radio class=r-opt name={k} value={v} {'checked' if cur == v else ''}>{E(t)}</label>" for v, t in opts)
    mem = ''
    if st['order'] == 'manual':
        mem = '<h4>Σειρά</h4><table>' + ''.join(f"<tr><td>{n}</td><td>{E(m[0])} · {E(m[1])}</td><td><button name=move value='up:{E(M.key(*m))}'>↑</button> <button name=move value='down:{E(M.key(*m))}'>↓</button></td></tr>" for n, m in enumerate(map(tuple, st['members']), 1)) + '</table>'
    sib = ''
    if st['unsel'] == 'manual':
        sl = M.siblings(c, [tuple(m) for m in st['members']]); chosen = set(st['manual_sel'])
        sib = '<h4>Τα υπόλοιπα υποερωτήματα των θεμάτων σου: τσέκαρε όσα θα εμφανιστούν</h4>' + ('<table>' + ''.join(f"<tr><td><input type=checkbox class=r-sel name=manual_sel value='{E(M.key(*s))}' {'checked' if M.key(*s) in chosen else ''}></td><td>{E(s[0])} · {E(s[1])}</td></tr>" for s in sl) + '</table>' if sl else '<p><i>Δεν υπάρχουν άλλα υποερωτήματα.</i></p>')
    inner = (f"<h3>2. Οργάνωση</h3><fieldset><legend>Αποτέλεσμα</legend>{rd('mode', (('merge', 'Συγχώνευση: ένα αρχείο για όλα'), ('each', 'Ένα-ένα: ξεχωριστή σελίδα ανά θέμα ή ερώτημα + index + zip (Reveal.js και HTML μαθητή)')), st['mode'])}{fld('Ένα-ένα ανά', '<select class=r-list name=gran>' + opt('item', 'θέμα', st['gran']) + opt('question', 'ερώτημα', st['gran']) + '</select>')}</fieldset>"
             f"<fieldset><legend>Σειρά ερωτημάτων</legend>{rd('order', M.ORDERS, st['order'])}{mem}</fieldset>"
             f"<fieldset><legend>Τα υπόλοιπα υποερωτήματα των θεμάτων που διάλεξες</legend>{rd('unsel', M.UNSEL, st['unsel'])}{sib}</fieldset>" + nav(rid, 2))
    return shell(rid, name, 2, inner)


def page3(c, rid, name, st):
    es = M.entries(c, st); t = M.total(es); tg = st['target']; bad = tg and abs(t - tg) > 1e-6
    rows = ''.join(f"<tr><td>{E(e['item'])}</td><td>{E(e['code'])}</td><td>{M.fmt_pts(e['row']['points'] or 0)}</td><td><input type=hidden name=pk value='{E(M.key(e['item'], e['code']))}'><input class=r-txt name=pv size=5 value='{M.fmt_pts(e['pts'])}'></td><td>{'' if e['vis'] == 'show' else '<i>' + {'hidden': 'κρυφό', 'append': 'στο τέλος'}[e['vis']] + ' (δεν μετρά)</i>'}</td></tr>" for e in es)
    inner = (f"<h3>3. Βαθμοί</h3><p class='wsum{' bad' if bad else ''}'>Άθροισμα μονάδων (ορατά): <b>{M.fmt_pts(t)}</b>{f' · στόχος {M.fmt_pts(tg)}' if tg else ''}{' ⚠ δεν ταιριάζει' if bad else ''}</p>"
             f"<div class=bar>Στόχος <input class=r-txt name=target size=5 value='{M.fmt_pts(tg) if tg else ''}' placeholder='π.χ. 20'> βήμα στρογγυλοποίησης <select class=r-list name=rstep><option value=1>1</option><option value=0.5>0,5</option><option value=0.25>0,25</option></select> "
             "<button name=action value=scale>Αναλογική προσαρμογή στον στόχο</button> <button name=action value=reset>Επαναφορά αρχικών μονάδων</button></div>"
             f"<table><tr><th>Θέμα</th><th>Ερώτημα</th><th>Αρχικές</th><th>Μονάδες (αλλάζεις με το χέρι)</th><th></th></tr>{rows}</table>"
             "<p><small>Το άθροισμα υπολογίζεται πριν βγει η αναφορά. Τις προσαρμοσμένες μονάδες εφαρμόζουν το Excel και το Markdown· οι άλλες μορφές χρησιμοποιούν τις μονάδες των αρχείων.</small></p>" + nav(rid, 3))
    return shell(rid, name, 3, inner)


def page4(rid, name, st):
    r = ''.join(f"<label class='f chk'><input type=radio class=r-opt name=format value={k} {'checked' if st['format'] == k else ''}>{E(t)}</label>" for k, t in M.FORMATS)
    note = ("<p><small>Σύντομα: μορφές HTML/Reveal ανά θέμα με κεντρικό index και zip (0.22), διαγώνισμα/τεστ με πρότυπο σχολείου (0.23), Moodle με κατηγορίες, Google Form και H5P (0.24).</small></p>")
    return shell(rid, name, 4, f"<h3>4. Τύπος αναφοράς</h3><fieldset><legend>Μορφή</legend>{r}</fieldset>{note}" + nav(rid, 4))


def opt(v, t, cur): return f"<option value={v}{' selected' if cur == v else ''}>{t}</option>"
def ck(name, on, label): return chk(label, f"<input type=checkbox class=r-opt name={name} value=1{' checked' if on else ''}>")


def page5(rid, name, st):
    sty = ''.join(opt(k, E(v['label']), st['style']) for k, v in STYLES.items())
    sx = st['sx'] or [u[0] for u in UNITS]
    units = ''.join(f"<label class='f chk'><input type=checkbox class=r-opt name=sx value={k} {'checked' if k in sx else ''}>{ic} {E(t)}</label>" for k, t, ic in UNITS)
    mdm = ''.join(opt(v, t, st['mdmode']) for v, t in (('image', 'εικόνες'), ('text', 'κείμενο'), ('both', 'και τα δύο')))
    num = opt('new', 'νέα (1,2,3)', st['numbering']) + opt('source', 'πηγή (θέμα/ερώτημα)', st['numbering'])
    store = opt('download', 'λήψη στον υπολογιστή', st['store']) + opt('server', 'αποθήκευση στον server (07_EXAGOGES/wizard)', st['store']) + opt('publish', 'δημοσίευση στον server για μαθητές (/p/, με κωδικό μαθητή)', st['store'])
    from . import wizexam
    tpls = opt('default', 'ενσωματωμένο πρότυπο', st['x_tpl']) + ''.join(opt(n, E(n), st['x_tpl']) for n in wizexam.list_templates())
    if st['x_tpl'] != 'default' and st['x_tpl'] not in wizexam.list_templates(): tpls += opt(st['x_tpl'], E(st['x_tpl']) + ' (λείπει)', st['x_tpl'])
    xg = ''.join(opt(k, E(t), st['x_grp']) for k, t in wizexam.GROUPS); xv = ''.join(opt(k, E(t), st['x_ver']) for k, t in wizexam.VERSIONS)
    xm = ''.join(opt(v, t, st['x_mode']) for v, t in (('image', 'εικόνες'), ('text', 'κείμενο'), ('both', 'και τα δύο')))
    tx = lambda k, lab, sz=24: fld(lab, f"<input class=r-txt name={k} size={sz} value='{E(st[k])}'>")
    exam = (f"<fieldset><legend>Διαγώνισμα/τεστ Word</legend>{fld('Πρότυπο', f'<select class=r-list name=x_tpl>{tpls}</select>')} <a class=btn href='/wizard-templates'>Πρότυπα σχολείου και οδηγός</a>"
            f"{tx('x_school', 'Σχολείο', 34)}{tx('x_course', 'Μάθημα')}{tx('x_class', 'Τάξη/τμήμα', 12)}{tx('x_date', 'Ημερομηνία', 12)}{tx('x_dur', 'Διάρκεια', 10)}{tx('x_sub', 'Υπότιτλος', 30)}{tx('x_notes', 'Οδηγίες', 60)}"
            f"{fld('Ομαδοποίηση', f'<select class=r-list name=x_grp>{xg}</select>')}{fld('Ερωτήματα ως', f'<select class=r-list name=x_mode>{xm}</select>')}{fld('Έκδοση', f'<select class=r-list name=x_ver>{xv}</select>')}</fieldset>")
    prefix = fld('Πρόθεμα συνδέσμων αρχείων', f"<input class=r-txt name=link_prefix size=14 value='{E(st['link_prefix'])}'>")
    inner = (f"<h3>5. Περιεχόμενο και επιλογές <small>(μορφή: {E(dict(M.FORMATS)[st['format']])})</small></h3>" + fld('Τίτλος', f"<input class=r-txt name=title size=40 value='{E(st['title'])}'>")
             + exam + f"<fieldset><legend>Excel</legend>{prefix}{ck('bundle', st['bundle'], 'Επισύναψη των PDF και των λύσεων στο zip (στις θέσεις των συνδέσμων)')}</fieldset>"
             + f"<fieldset><legend>Markdown / Word</legend>{fld('Εικόνες ή κείμενο', f'<select class=r-list name=mdmode>{mdm}</select>')}{fld('Αρίθμηση', f'<select class=r-list name=numbering>{num}</select>')}</fieldset>"
             + f"<fieldset><legend>Λύσεις εκπαιδευτικού (Reveal, HTML μαθητή, Moodle)</legend>{fld('Στυλ', f'<select class=r-list name=style>{sty}</select>')}<p>Ενότητες που περιλαμβάνονται:</p>{units}{ck('hide', st['hide'], 'Κρυφές λύσεις με κλικ (HTML μαθητή)')}</fieldset>"
             + f"<fieldset><legend>Αποθήκευση και προεπισκόπηση</legend>{ck('preview', st['preview'], 'Προεπισκόπηση πριν την εξαγωγή (όπου γίνεται)')}{fld('Πού', f'<select class=r-list name=store>{store}</select>')}</fieldset>" + nav(rid, 5))
    return shell(rid, name, 5, inner)


def members_of(es, vis=('show', 'append')):
    return [(e['item'], e['code']) for e in es if e['vis'] in vis]


def produce(c, st, es, preview=False):
    """Εκτελεί την εξαγωγή. Επιστρέφει ('file', bytes, όνομα, mimetype), ('redirect', url) ή ('response', Response)."""
    from . import collections, solexport, tools_merge
    from .mddoc import new_doc
    fm = st['format']; root = config.load()['data_root']; title = st['title'] or 'Αναφορά'
    if not any(e['vis'] == 'show' for e in es): raise HTTPException(422, 'Δεν υπάρχει κανένα ερώτημα για εμφάνιση.')
    if fm == 'excel': return ('file',) + M.excel_bytes(c, es, st, root)
    if fm == 'md':
        txt = M.md_text(c, es, st)
        if preview: return ('file', txt.encode('utf-8'), 'preview.md', 'text/markdown; charset=utf-8')
        did = new_doc(c, title, txt, f'wizard ({len(es)} στοιχεία)'); c.commit(); return ('redirect', f'/docs/{did}')
    if fm == 'htmldoc':
        r = collections.compose(c, members_of(es), {'title': title, 'numbering': st['numbering'], 'group': '', 'solutions': False}); return ('response', r)
    if fm in ('reveal', 'student') and st['mode'] == 'each':
        from . import wizsite
        files, model = wizsite.build_site(c, st, es)
        if not files: raise HTTPException(422, 'Κανένα από τα ερωτήματα δεν έχει αρχείο λύσης (.md). Δες τη σελίδα «Λύσεις».')
        return ('site', files, model)
    if fm in ('reveal', 'student', 'moodle'):
        r = solexport.export(c, {'reveal': 'reveal', 'student': 'html', 'moodle': 'moodle'}[fm], members_of(es), st['sx'], title, st['style'], bool(st['hide'])); return ('response', r)
    if fm == 'exam':
        from . import wizexam
        try: data, fname, mime = wizexam.build(c, st, es)
        except ValueError as ex: raise HTTPException(422, str(ex))
        return ('file', data, fname, mime)
    if fm == 'merge':
        items = sorted({m[0] for m in members_of(es, ('show',))}, key=int); data, n = tools_merge.build(c, items, False, False, 'by_item', 8, [], True)
        return ('file', data, 'thilek-merge.pdf', 'application/pdf')
    raise HTTPException(422, 'Άγνωστη μορφή.')


def disp(fname):
    """Content-Disposition με ελληνικά ονόματα (RFC 5987) και ASCII εφεδρικό όνομα."""
    from urllib.parse import quote
    ascii_ = re.sub(r'[^A-Za-z0-9._-]+', '_', fname) or 'export'
    return f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{quote(fname)}"


def slug(s): return re.sub(r'[^\w-]+', '_', s, flags=re.U).strip('_')[:50] or 'anafora'


def page6(c, rid, name, st):
    es = M.entries(c, st); t = M.total(es); warns = M.checks(es, st); fm = st['format']
    rows = ''.join(f"<tr><td>{E(e['item'])}</td><td>{E(e['code'])}</td><td>{M.fmt_pts(e['pts'])}</td><td>{E(e['row']['qtype'] or '')}</td><td>{'✎' if e['row']['has_sol'] else ''}</td><td>{VIS[e['vis']]}</td></tr>" for e in es)
    wb = ''.join(f"<li>{E(w)}</li>" for w in warns)
    prev = ''
    if st['preview']:
        if fm in ('htmldoc', 'reveal', 'student'): prev = f"<h3>Προεπισκόπηση</h3><iframe class=wprev sandbox='allow-scripts' src='/wizard/{rid}/preview'></iframe>"
        elif fm == 'exam':
            from . import wizexam
            prev = f"<h3>Προεπισκόπηση (σώμα ερωτημάτων, Markdown)</h3><pre>{E(wizexam.body_md(c, st, es, st['x_ver'] != 'student')[:6000])}</pre>"
        elif fm == 'md': prev = f"<h3>Προεπισκόπηση (Markdown)</h3><pre>{E(M.md_text(c, es, st)[:6000])}</pre>"
        else: prev = '<p><small>Για αυτή τη μορφή δεν υπάρχει οπτική προεπισκόπηση· ο πίνακας από κάτω δείχνει τι θα περιέχει.</small></p>'
    bad = bool(st['target']) and abs(t - st['target']) > 1e-6
    tg_txt = f" (στόχος {M.fmt_pts(st['target'])})" if st['target'] else ''
    rn = fld('Όνομα', f"<input class=r-txt name=rname size=30 value='{E(name)}'>")
    inner = (f"<h3>6. Έλεγχος και εξαγωγή</h3><p class='wsum{' bad' if bad else ''}'>Μορφή: <b>{E(dict(M.FORMATS)[fm])}</b> · ορατά ερωτήματα: <b>{sum(1 for e in es if e['vis'] == 'show')}</b> · <b>σύνολο μονάδων {M.fmt_pts(t)}</b>"
             f"{tg_txt}</p>"
             + (f"<div class='adm adm-warning'><p class=adm-t>Προσοχή</p><ul>{wb}</ul></div>" if warns else "<div class='adm adm-success'><p class=adm-t>✔ Κανένα πρόβλημα</p></div>")
             + f"<table><tr><th>Θέμα</th><th>Ερώτημα</th><th>Μον.</th><th>Τύπος</th><th>Λύση</th><th>Εμφάνιση</th></tr>{rows}</table>{prev}"
             + f"<div class=wnav><a class=btn href='/wizard/{rid}/5'>← Πίσω</a><button class=primary formaction='/wizard/{rid}/generate' name=how value=run>Εξαγωγή ({dict(download='λήψη', server='αποθήκευση στον server', publish='δημοσίευση').get(st['store'])})</button> <a class=btn href='/wizard'>Οι συνταγές μου</a></div>"
             f"<fieldset><legend>Όνομα συνταγής</legend>{rn}<button formaction='/wizard/{rid}/6' name=go value=rename>Μετονομασία</button></fieldset>")
    return shell(rid, name, 6, inner)


@router.get('/wizard/{rid}/preview', dependencies=[Depends(auth)])
def wizard_preview(rid: int):
    c = db()
    try:
        name, st = get_recipe(c, rid); es = M.entries(c, st); r = produce(c, st, es, preview=True)
    finally: c.close()
    if r[0] == 'response':
        resp = r[1]; h = {k: v for k, v in resp.headers.items() if k.lower() in ('content-type',)}; return Response(resp.body, media_type=h.get('content-type', 'text/html'))
    if r[0] == 'file': return Response(r[1], media_type='text/plain; charset=utf-8')
    if r[0] == 'site': return Response(r[1]['index.html'], media_type='text/html; charset=utf-8')
    raise HTTPException(404)


@router.get('/wizard/{rid}/{step}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def wizard_step(request: Request, rid: int, step: int):
    if step not in range(1, 7): raise HTTPException(404)
    c = db()
    try:
        name, st = get_recipe(c, rid)
        if step == 1: return page1(c, rid, name, st, request)
        if step == 2: return page2(c, rid, name, st)
        if step == 3: return page3(c, rid, name, st)
        if step == 4: return page4(rid, name, st)
        if step == 5: return page5(rid, name, st)
        return page6(c, rid, name, st)
    finally: c.close()


def fv(f, k, default=''):
    v = f.get(k); return v.strip() if isinstance(v, str) else default


@router.post('/wizard/{rid}/generate', dependencies=[Depends(auth)])
def wizard_generate(request: Request, rid: int):
    same_origin(request); c = db()
    try:
        name, st = get_recipe(c, rid); es = M.entries(c, st); r = produce(c, st, es)
        if r[0] == 'redirect': return RedirectResponse(r[1], status_code=303)
        if r[0] == 'site':
            from . import wizsite, publish
            files, model = r[1], r[2]
            if st['store'] == 'publish':
                sl = publish.save_site(st['title'], files, source=f'wizard: {name}')
                return page('Δημοσιεύτηκε', f"<h2>Δημοσιεύτηκε</h2><p>{len(model['pages'])} σελίδες · <a href='/p/{E(sl)}/'>/p/{E(sl)}/</a></p>"
                            + ('' if publish.get_pw_hash() else "<div class='adm adm-warning'><p class=adm-t>Δεν υπάρχει κωδικός μαθητή</p><p>Ορίστε τον στις <a href='/publish'>Δημοσιεύσεις</a>· μέχρι τότε ανοίγει μόνο με κωδικό διαχειριστή.</p></div>")
                            + f"<p><a href='/publish'>Δημοσιεύσεις</a> · <a href='/wizard/{rid}/6'>Πίσω στον wizard</a></p>")
            readme = f"{st['title']}\n\nΑνοίξτε το index.html. Κάθε σελίδα είναι αυτόνομο αρχείο (χωρίς διαδίκτυο). Το data.json έχει τα δεδομένα (ερωτήματα, μονάδες) χωριστά από την παρουσίαση.\n"
            r = ('file', wizsite.zip_bytes(files, readme), f"{slug(st['title'])}.zip", 'application/zip')
        if r[0] == 'response':
            resp = r[1]; ct = resp.headers.get('content-type', 'text/html')
            ext = 'xml' if 'xml' in ct else 'html'; body = resp.body; fname = f"{slug(st['title'])}.{ext}"; mime = ct; headers = {'Content-Disposition': resp.headers.get('content-disposition', f'attachment; filename="{fname}"')}
        else: _, body, fname, mime = r; headers = {'Content-Disposition': disp(fname)}
        if st['store'] == 'publish':
            from . import publish
            if not str(mime).startswith('text/html'): raise HTTPException(422, 'Η δημοσίευση αφορά μόνο σελίδες HTML.')
            s_ = publish.save_site(st['title'], {'index.html': body}, source=f'wizard: {name}')
            return page('Δημοσιεύτηκε', f"<h2>Δημοσιεύτηκε</h2><p><a href='/p/{E(s_)}/'>/p/{E(s_)}/</a></p><p><a href='/publish'>Δημοσιεύσεις</a> · <a href='/wizard/{rid}/6'>Πίσω στον wizard</a></p>")
        if st['store'] == 'server':
            course = next((e['row']['course_code'] for e in es if e['row']['course_code']), '') or 'EXPORTS'
            d = pathlib.Path(config.load()['data_root']) / course / '07_EXAGOGES' / 'wizard'; d.mkdir(parents=True, exist_ok=True)
            out = d / f"{rid}-{slug(fname.rsplit('.', 1)[0])}.{fname.rsplit('.', 1)[-1]}"; out.write_bytes(body)
            return page('Αποθηκεύτηκε', f"<h2>Αποθηκεύτηκε στον server</h2><p><code>{E(str(out.relative_to(config.load()['data_root'])))}</code></p><p><a href='/fb'>Άνοιγμα στα Αρχεία</a> · <a href='/wizard/{rid}/6'>Πίσω στον wizard</a></p>")
        return Response(body, media_type=mime, headers=headers)
    finally: c.close()


@router.post('/wizard/{rid}/{step}', dependencies=[Depends(auth)])
async def wizard_post(request: Request, rid: int, step: int):
    same_origin(request)
    if step not in range(1, 7): raise HTTPException(404)
    f = await request.form(); c = db()
    try:
        name, st = get_recipe(c, rid); go = fv(f, 'go'); back = None
        if step == 1:
            action = fv(f, 'action'); mem = [tuple(m) for m in st['members']]; qs = safe_qs(fv(f, 'qs'))
            if action == 'add':
                for q in f.getlist('qids'):
                    if str(q).isdigit():
                        r = c.execute('SELECT item_id,code FROM question WHERE id=?', (int(q),)).fetchone()
                        if r and (r[0], r[1]) not in mem: mem.append((r[0], r[1]))
            elif action == 'addall':
                fl = filters_from_qs(qs, criteria_on())
                for r in select_questions(c, fl, 300):
                    if (r['item_id'], r['code']) not in mem: mem.append((r['item_id'], r['code']))
            elif action == 'remove':
                rm = {tuple(M.unkey(k)) for k in f.getlist('rm')}; mem = [m for m in mem if m not in rm]
            elif action == 'clear': mem = []
            st['members'] = [list(m) for m in mem]; save_state(c, rid, st)
            return RedirectResponse(f'/wizard/{rid}/1' + (f'?{qs}' if qs else ''), status_code=303)
        if step == 2:
            mv = fv(f, 'move')
            if mv:
                d, _, k = mv.partition(':'); mem = [tuple(m) for m in st['members']]; t = tuple(M.unkey(k))
                if t in mem:
                    i = mem.index(t); j = i - 1 if d == 'up' else i + 1
                    if 0 <= j < len(mem): mem[i], mem[j] = mem[j], mem[i]
                st['members'] = [list(m) for m in mem]; save_state(c, rid, st); return RedirectResponse(f'/wizard/{rid}/2', status_code=303)
            if fv(f, 'mode') in ('merge', 'each'): st['mode'] = fv(f, 'mode')
            if fv(f, 'gran') in ('item', 'question'): st['gran'] = fv(f, 'gran')
            if fv(f, 'order') in dict(M.ORDERS): st['order'] = fv(f, 'order')
            if fv(f, 'unsel') in dict(M.UNSEL): st['unsel'] = fv(f, 'unsel')
            st['manual_sel'] = [k for k in f.getlist('manual_sel') if '|' in str(k)] if st['unsel'] == 'manual' else []
            if st['order'] != 'manual' and fv(f, 'order') == 'manual': pass
        if step == 3:
            action = fv(f, 'action'); keys = f.getlist('pk'); vals = f.getlist('pv')
            for k, v in zip(keys, vals):
                n = M.num(v)
                if n is not None and n >= 0: st['points'][k] = n
            tg = M.num(fv(f, 'target')); st['target'] = tg if tg and tg > 0 else None
            if action == 'reset': st['points'] = {}
            if action == 'scale':
                if not st['target']: save_state(c, rid, st); raise HTTPException(422, 'Γράψε στόχο μονάδων (π.χ. 20).')
                es = [e for e in M.entries(c, st) if e['vis'] == 'show']; step_ = M.num(fv(f, 'rstep')) or 1.0
                st['points'].update(M.scale_points({M.key(e['item'], e['code']): e['pts'] for e in es}, st['target'], step_))
            save_state(c, rid, st)
            if action: return RedirectResponse(f'/wizard/{rid}/3', status_code=303)
        if step == 4 and fv(f, 'format') in M.FORMAT_KEYS: st['format'] = fv(f, 'format')
        if step == 5:
            st['title'] = fv(f, 'title')[:200] or 'Αναφορά ασκήσεων'; lp = fv(f, 'link_prefix')
            st['link_prefix'] = lp if safe_prefix(lp) else 'pdf/'
            st['bundle'] = bool(f.get('bundle')); st['hide'] = bool(f.get('hide')); st['preview'] = bool(f.get('preview'))
            if fv(f, 'mdmode') in ('image', 'text', 'both'): st['mdmode'] = fv(f, 'mdmode')
            if fv(f, 'numbering') in ('new', 'source'): st['numbering'] = fv(f, 'numbering')
            if fv(f, 'style') in STYLES: st['style'] = fv(f, 'style')
            for k in ('x_school', 'x_class', 'x_date', 'x_dur', 'x_sub', 'x_notes', 'x_course'): st[k] = fv(f, k)[:300]
            if fv(f, 'x_grp') in ('item', 'qtype', 'none'): st['x_grp'] = fv(f, 'x_grp')
            if fv(f, 'x_mode') in ('image', 'text', 'both'): st['x_mode'] = fv(f, 'x_mode')
            if fv(f, 'x_ver') in ('student', 'teacher', 'both'): st['x_ver'] = fv(f, 'x_ver')
            if fv(f, 'x_tpl') == 'default' or wizexam.tpl_name_ok(fv(f, 'x_tpl')): st['x_tpl'] = fv(f, 'x_tpl') or 'default'
            if fv(f, 'store') in ('download', 'server', 'publish'): st['store'] = fv(f, 'store')
            keys = {u[0] for u in UNITS}; st['sx'] = [k for k in f.getlist('sx') if k in keys]
        if step == 6 and go == 'rename': save_state(c, rid, st, fv(f, 'rname')); return RedirectResponse(f'/wizard/{rid}/6', status_code=303)
        save_state(c, rid, st)
        return RedirectResponse(f'/wizard/{rid}/{min(step + 1, 6)}' if go == 'next' else f'/wizard/{rid}/{step}', status_code=303)
    finally: c.close()


# ---------- πρότυπα Word σχολείου (0.23) ----------
@router.get('/wizard-templates', response_class=HTMLResponse, dependencies=[Depends(auth)])
def templates_page(msg: str = '', bad: int = 0):
    rows = ''.join(f"<tr><td>{E(n)}</td><td><a href='/wizard-templates/file/{E(n)}'>λήψη</a></td><td><form method=post action='/wizard-templates/{E(n)}/delete' style='display:inline'><button class=danger>Διαγραφή</button></form></td></tr>" for n in wizexam.list_templates())
    fields = ''.join(f"<tr><td><code>{{{{{E(k)}}}}}</code></td><td>{E(t)}</td></tr>" for k, t in wizexam.FIELDS)
    note = (f"<div class='adm adm-{'warning' if bad else 'success'}'><p class=adm-t>{E(msg)}</p></div>" if msg else '')
    body = (f"<h2>Πρότυπα Word σχολείου</h2>{note}<p>Ανεβάζεις το δικό σου διαγώνισμα του σχολείου ως πρότυπο: ο wizard γεμίζει τα πεδία και βάζει τα ερωτήματα στο σημείο που θα του δείξεις.</p>"
            "<ol><li>Άνοιξε το έγγραφο του σχολείου στο Word και αποθήκευσε ως <b>Έγγραφο Word (*.docx)</b>.</li>"
            "<li>Γράψε στη θέση κάθε στοιχείου το πεδίο του πίνακα από κάτω (π.χ. <code>{{ΤΙΤΛΟΣ}}</code>), και σε <b>δική του παράγραφο</b> το <code>{{ΕΡΩΤΗΜΑΤΑ}}</code> εκεί που θα μπουν τα ερωτήματα.</li>"
            "<li>Ανέβασέ το εδώ. Μπορείς να δοκιμάσεις πρώτα το <a href='/wizard-templates/sample.docx'>ενσωματωμένο πρότυπο</a> ως υπόδειγμα.</li></ol>"
            f"<div class=scroll><table><tr><th>Πεδίο</th><th>Τι μπαίνει</th></tr>{fields}<tr><td><code>{{{{ΕΡΩΤΗΜΑΤΑ}}}}</code></td><td>Τα ερωτήματα (ΘΕΜΑ Α, Β… με εικόνες/κείμενο και μονάδες)</td></tr></table></div>"
            "<p><small>Τα πεδία δουλεύουν και σε κεφαλίδα/υποσέλιδο και σε πίνακες. Το <code>{{ΕΡΩΤΗΜΑΤΑ}}</code> πρέπει να είναι στο κυρίως σώμα (όχι μέσα σε πίνακα). Αν ένα πεδίο έχει μορφοποίηση μόνο σε μέρος του, η παράγραφος παίρνει τη μορφή του πρώτου γράμματος.</small></p>"
            "<form method=post action='/wizard-templates/upload' enctype='multipart/form-data'><fieldset><legend>Ανέβασμα προτύπου</legend>"
            "<input type=file name=file accept='.docx' class=r-file> <button class=primary>Ανέβασμα</button></fieldset></form>"
            f"<h3>Διαθέσιμα πρότυπα</h3><div class=scroll><table><tr><th>Όνομα</th><th></th><th></th></tr><tr><td>ενσωματωμένο</td><td><a href='/wizard-templates/sample.docx'>λήψη</a></td><td></td></tr>{rows}</table></div>"
            "<p><a class=btn href='/wizard'>← Wizard</a></p>")
    return page('Πρότυπα Word', body)


@router.get('/wizard-templates/sample.docx', dependencies=[Depends(auth)])
def template_sample():
    return Response(wizexam.default_template(), media_type=wizexam.DOCX, headers={'Content-Disposition': 'attachment; filename="protypo-diagonismatos.docx"'})


@router.get('/wizard-templates/file/{name}', dependencies=[Depends(auth)])
def template_file(name: str):
    p = wizexam.tpl_dir() / name
    if not wizexam.tpl_name_ok(name) or not p.is_file() or p.is_symlink(): raise HTTPException(404)
    return Response(p.read_bytes(), media_type=wizexam.DOCX, headers={'Content-Disposition': f'attachment; filename="{name}"'})


@router.post('/wizard-templates/upload', dependencies=[Depends(auth)])
async def template_upload(request: Request):
    same_origin(request); f = await request.form(); up = f.get('file')
    from urllib.parse import quote
    def back(msg, bad=0): return RedirectResponse(f'/wizard-templates?msg={quote(msg)}&bad={bad}', status_code=303)
    if not hasattr(up, 'read') or not getattr(up, 'filename', ''): return back('Δεν επιλέχθηκε αρχείο.', 1)
    name = re.sub(r'[^A-Za-z0-9_.-]+', '_', pathlib.Path(up.filename).stem).strip('._-')[:50] or 'protypo'; name += '.docx'
    data = await up.read(wizexam.MAX_TPL + 1); ok, msg, found, mark = wizexam.check_template(data)
    if not ok: return back(msg, 1)
    d = wizexam.tpl_dir(); d.mkdir(parents=True, exist_ok=True); (d / name).write_bytes(data)
    out = f"Αποθηκεύτηκε ως «{name}». Πεδία που βρέθηκαν: {', '.join(found) or 'κανένα'}."
    if not mark: out += ' ΠΡΟΣΟΧΗ: λείπει το {{ΕΡΩΤΗΜΑΤΑ}}· τα ερωτήματα θα μπουν στο τέλος του εγγράφου.'
    return back(out, 0 if mark else 1)


@router.post('/wizard-templates/{name}/delete', dependencies=[Depends(auth)])
def template_delete(request: Request, name: str):
    same_origin(request); p = wizexam.tpl_dir() / name
    if not wizexam.tpl_name_ok(name) or not p.is_file(): raise HTTPException(404)
    p.unlink(); return RedirectResponse('/wizard-templates?msg=' + __import__('urllib.parse').parse.quote('Διαγράφηκε.'), status_code=303)
