"""0.38: δημοσίευση στο GitHub Pages. Η φόρμα /ghpages ετοιμάζει αυτόνομες σελίδες (site, εξάσκηση/flashcards quiz, λύσεις εκπαιδευτικού, παρουσιάσεις)
και τις γράφει σε ΕΝΑ commit στο repo (GitHub Git Data API, fine-grained token) κάτω από <φάκελος>/<slug>/, με σελίδα ευρετηρίου <φάκελος>/index.html.
Εφεδρικά: zip + script push για τον Windows σταθμό. Πάντα προεπισκόπηση πριν την εφαρμογή. Το Pages είναι ΔΗΜΟΣΙΟ: υλικό ΙΕΠ/βιβλίου δεν επιτρέπεται (αποκλεισμοί και επιβεβαιώσεις).
Δεν υπάρχουν νέοι πίνακες: ρυθμίσεις και κατάλογος δημοσιεύσεων στον πίνακα `setting` (κλειδιά gh_*)· το token δεν εμφανίζεται ποτέ."""
import base64, datetime, hashlib, html, io, json, re, urllib.error, urllib.request, zipfile
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from .main_auth import auth
from .review import db, page, same_origin
from . import config, deck as D, deckexport as DX, embed as EM, practice, settings, site as S, solexport as X, solstyle as SS

E = html.escape
router = APIRouter()
API = 'https://api.github.com'
KINDS = {'site': 'Site', 'practice': 'Εξάσκηση quiz', 'cards': 'Flashcards quiz', 'deck': 'Παρουσίαση', 'solutions': 'Λύσεις εκπαιδευτικού'}
RESERVED = {'index', 'assets', 'manifest'}
MAX_FILES, MAX_BYTES = 250, 40 * 1024 * 1024
ALLOWED_EXT = {'.html', '.json', '.txt', '.css', '.js', '.png', '.jpg', '.jpeg', '.svg', '.pdf'}
IEP_RE = re.compile(r'04_TRAPEZA|/crop/\d|thilek://(?:statement|solution)|(?<![\w])orig/', re.I)


class GhError(Exception):
    def __init__(self, status, msg): super().__init__(msg); self.status = status; self.msg = msg


# ---------- ρυθμίσεις (πίνακας setting, κλειδιά gh_*) ----------
def _get(c, k, d=''):
    r = c.execute('SELECT v FROM setting WHERE k=?', (k,)).fetchone(); return r[0] if r else d


def _set(c, k, v):
    if v in (None, ''): c.execute('DELETE FROM setting WHERE k=?', (k,))
    else: c.execute('INSERT INTO setting(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v', (k, v))


def load_cfg(c):
    try: man = json.loads(_get(c, 'gh_manifest', '[]'))
    except ValueError: man = []
    return {'repo': _get(c, 'gh_repo'), 'branch': _get(c, 'gh_branch', 'main') or 'main', 'dir': _get(c, 'gh_dir', 'thilek') or 'thilek', 'token': _get(c, 'gh_token'), 'manifest': [m for m in man if isinstance(m, dict) and m.get('slug')]}


def ok_repo(r): return bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100}', r or ''))
def ok_branch(b): return bool(re.fullmatch(r'[A-Za-z0-9_./-]{1,60}', b or '')) and '..' not in b
def ok_dir(d): return bool(re.fullmatch(r'[A-Za-z0-9_-]{1,40}', d or ''))
def ok_slug(s): return bool(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,47}', s or '')) and s not in RESERVED


def pages_url(cfg, slug=''):
    owner, name = cfg['repo'].split('/', 1) if '/' in (cfg['repo'] or '') else ('', '')
    base = f'https://{owner}.github.io/' + ('' if name.lower() == f'{owner}.github.io'.lower() else name + '/')
    return base + cfg['dir'] + '/' + (slug + '/' if slug else '')


# ---------- πελάτης GitHub ----------
def _http(method, url, token, body=None):
    """-> (status, json). Ξεχωριστή συνάρτηση ώστε τα τεστ να βάζουν ψεύτικο GitHub."""
    data = json.dumps(body).encode('utf-8') if body is not None else None
    rq = urllib.request.Request(url, data=data, method=method, headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'thilek', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(rq, timeout=25) as r: raw = r.read(); return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b'{}')
        except ValueError: return e.code, {}
    except (urllib.error.URLError, OSError, TimeoutError) as e: raise GhError(0, 'Δεν υπάρχει σύνδεση με το api.github.com από τον server (' + type(e).__name__ + ').')


class Gh:
    def __init__(self, cfg): self.repo, self.branch, self.token = cfg['repo'], cfg['branch'], cfg['token']

    def call(self, method, path, body=None, ok=(200, 201)):
        st, d = _http(method, f'{API}/repos/{self.repo}{path}', self.token, body)
        if st in ok: return d
        msg = {401: 'Το token δεν είναι έγκυρο ή έληξε.', 403: 'Το token δεν έχει δικαίωμα (χρειάζεται Contents: Read and write στο repo) ή έχει ξεπεραστεί το όριο.', 404: 'Δεν βρέθηκε το repo/branch ή το token δεν το βλέπει.', 409: 'Σύγκρουση στο repo (κενό repo;).', 422: 'Το GitHub απέρριψε το αίτημα.'}.get(st, f'Σφάλμα GitHub ({st}).')
        raise GhError(st, msg)


def blob_sha(data): return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def commit_files(cfg, add, remove_prefixes, message, gh=None):
    """Ένα commit: προσθήκη/ενημέρωση `add` {διαδρομή: bytes} και διαγραφή των αρχείων κάτω από `remove_prefixes` που δεν υπάρχουν στο add. -> (sha ή None αν δεν άλλαξε τίποτα, αριθμός αλλαγών)."""
    gh = gh or Gh(cfg)
    for attempt in (1, 2):
        ref = gh.call('GET', f"/git/ref/heads/{quote(cfg['branch'], safe='/')}"); head = ref['object']['sha']
        tree = gh.call('GET', f'/git/commits/{head}')['tree']['sha']; ex = gh.call('GET', f'/git/trees/{tree}?recursive=1')
        if ex.get('truncated'): raise GhError(0, 'Το repo έχει πολλά αρχεία για αυτή τη μέθοδο.')
        have = {t['path']: t['sha'] for t in ex.get('tree', []) if t.get('type') == 'blob'}; entries = []
        for p, data in add.items():
            if have.get(p) == blob_sha(data): continue
            b = gh.call('POST', '/git/blobs', {'content': base64.b64encode(data).decode('ascii'), 'encoding': 'base64'}); entries.append({'path': p, 'mode': '100644', 'type': 'blob', 'sha': b['sha']})
        for p in have:
            if p not in add and any(p.startswith(pre) for pre in remove_prefixes): entries.append({'path': p, 'mode': '100644', 'type': 'blob', 'sha': None})
        if not entries: return None, 0
        t = gh.call('POST', '/git/trees', {'base_tree': tree, 'tree': entries}); cm = gh.call('POST', '/git/commits', {'message': message, 'tree': t['sha'], 'parents': [head]})
        try: gh.call('PATCH', f"/git/refs/heads/{quote(cfg['branch'], safe='/')}", {'sha': cm['sha'], 'force': False}); return cm['sha'], len(entries)
        except GhError as e:
            if e.status != 422 or attempt == 2: raise


# ---------- ευρετήριο και κατάλογος ----------
def index_html(cfg, entries):
    rows = ''.join(f"<li><a href='{E(m['slug'], quote=True)}/'>{E(m.get('title') or m['slug'])}</a> <small>{E(KINDS.get(m.get('kind'), m.get('kind') or ''))} · {E(m.get('updated', ''))}</small></li>" for m in sorted(entries, key=lambda m: (m.get('title') or m['slug']).lower()))
    css = "body{font:17px/1.6 'Segoe UI',Arial,sans-serif;max-width:720px;margin:0 auto;padding:1.2rem;color:#1d2433;background:#f4f6fa}li{margin:.5rem 0}small{color:#5b6679}a{color:#1f3a68}"
    return (f"<!doctype html><html lang='el'><meta charset='utf-8'><meta name=viewport content='width=device-width,initial-scale=1'><title>Υλικό μαθημάτων</title><style>{css}</style><body><h1>Υλικό μαθημάτων</h1>"
            f"<ul>{rows or '<li>Δεν υπάρχει ακόμη υλικό.</li>'}</ul><p><small>Δημιουργήθηκε από το TH-ILEK.</small></p></body></html>").encode('utf-8')


def manifest_bytes(entries): return json.dumps(sorted(entries, key=lambda m: m['slug']), ensure_ascii=False, indent=1).encode('utf-8')


def now(): return datetime.datetime.now().strftime('%Y-%m-%d %H:%M')


# ---------- κατασκευή περιεχομένου ----------
class Item:
    def __init__(self, kind, ref, slug, title): self.kind, self.ref, self.slug, self.title = kind, ref, slug, title; self.files = {}; self.warn = []; self.block = []; self.iep = 0

    @property
    def size(self): return sum(len(v) for v in self.files.values())


def guard(item, text, where):
    if IEP_RE.search(text or ''): item.block.append(f'{where}: περιέχει αναφορά σε αρχεία/εικόνες του ΙΕΠ ή του βιβλίου (04_TRAPEZA, orig/, /crop/) — δεν επιτρέπεται σε δημόσιο site.')


def build_item(c, kind, ref, slug, title, f):
    it = Item(kind, ref, slug, title)
    if kind == 'site':
        sid = int(ref); s = S.get(c, sid)
        if not s: it.block.append('Δεν υπάρχει αυτό το site.'); return it
        for p in S.pages(c, sid): guard(it, p['body'], f"σελίδα «{p['title']}»")
        if it.block: return it
        try: it.files, model = S.build_files(c, sid, settings_domains())
        except ValueError as e: it.block.append(str(e)); return it
        if any(n.startswith('file-') for n in it.files): it.warn.append('Το site περιέχει αρχεία (μπλοκ file): βεβαιώσου ότι είναι δικά σου.')
        if s['opts']['quiz_answers'] == 'show': it.warn.append('Τα quiz δείχνουν απαντήσεις στον πηγαίο κώδικα — φαίνονται σε όλο τον κόσμο.')
        it.title = it.title or model['title']
    elif kind in ('practice', 'cards'):
        qid = int(ref); z = c.execute('SELECT * FROM quiz WHERE id=?', (qid,)).fetchone()
        if not z: it.block.append('Δεν υπάρχει αυτό το quiz.'); return it
        its = c.execute('SELECT src_item,stem FROM quiz_item WHERE quiz_id=?', (qid,)).fetchall()
        it.iep = sum(1 for r in its if r['src_item'])
        for r in its: guard(it, r['stem'], 'στοιχείο quiz')
        try: _, h = practice.build(c, qid, kind)
        except HTTPException as e: it.block.append(str(e.detail)); return it
        it.files = {'index.html': h.encode('utf-8')}; it.title = it.title or f"{z['name']} — {practice.KINDS[kind]}"
        if it.iep: it.warn.append(f'{it.iep} από {len(its)} στοιχεία προέρχονται από θέματα ΙΕΠ (src) — χρειάζεται δικαίωμα δημοσίευσης.')
        it.warn.append('Οι σωστές απαντήσεις φαίνονται στον κώδικα της σελίδας (δημόσια).')
    elif kind == 'deck':
        did = int(ref); d = D.get(c, did)
        if not d: it.block.append('Δεν υπάρχει αυτή η παρουσίαση.'); return it
        sl = D.slides(c, did)
        for s in sl: guard(it, (s.get('body') or '') + ' ' + (s.get('notes') or ''), f"διαφάνεια «{s.get('title') or s.get('pos')}»")
        if it.block: return it
        try: h = DX.reveal(d, sl, config.load()['data_root'], publish=True, domains=settings_domains())
        except HTTPException as e: it.block.append(str(e.detail)); return it
        it.files = {'index.html': h.encode('utf-8')}; it.title = it.title or d.get('title') or d['name']
        n = h.count('data:image')
        if n: it.warn.append(f'Ενσωματώνονται {n} εικόνες στις διαφάνειες — βεβαιώσου ότι δεν είναι του ΙΕΠ/βιβλίου.')
    elif kind == 'solutions':
        keys = [tuple(k.split('|', 1)) for k in f.getlist('sol_keys') if '|' in k][:60]; rows = X.load(c, keys)
        if not rows: it.block.append('Διάλεξε τουλάχιστον μία λύση εκπαιδευτικού.'); return it
        inc = list(SS.TEACHER) + ['quiz']                                              # ΟΧΙ «Εκφώνηση» και «Ενδεικτική λύση ΙΕΠ»: είναι υλικό ΙΕΠ
        from .solhtml import student_html
        h = student_html(rows, it.title or 'Λύσεις', inc, SS.style_of(''), config.load()['data_root'], f.get('sol_hide') == '1')
        if f.get('sol_img') != '1': h = re.sub(r'<img\b[^>]*>', '<i>[σχήμα παραλείπεται]</i>', h)
        else: it.warn.append('Οι εικόνες των λύσεων περιλαμβάνονται· προέρχονται από σχήματα του ΙΕΠ — χρειάζεται δικαίωμα δημοσίευσης.'); it.iep += 1
        it.files = {'index.html': h.encode('utf-8')}; it.title = it.title or 'Λύσεις εκπαιδευτικού'
        it.warn.append('Οι Εκφωνήσεις και οι ενδεικτικές λύσεις ΙΕΠ ΔΕΝ περιλαμβάνονται· οι απαντήσεις των quiz φαίνονται στον κώδικα.')
        if any(r.get('status') == 'draft' for r in rows): it.warn.append('Περιλαμβάνονται λύσεις σε κατάσταση draft.')
        if len(rows) > 1: it.warn.append(f'{len(rows)} λύσεις σε μία σελίδα.')
    if len(it.files) > MAX_FILES: it.block.append(f'Πολλά αρχεία ({len(it.files)} > {MAX_FILES}).')
    if it.size > MAX_BYTES: it.block.append(f'Μέγεθος {it.size // 1048576} MB > {MAX_BYTES // 1048576} MB.')
    bad = [n for n in it.files if '/' in n or n.startswith('.') or '.' not in n or '.' + n.rsplit('.', 1)[1].lower() not in ALLOWED_EXT]
    if bad: it.block.append('Μη επιτρεπτά ονόματα/τύποι αρχείων: ' + ', '.join(bad[:5]))
    return it


def settings_domains(): return EM.hosts(settings.get('embed_domains'))


def parse_selection(c, f):
    """Πεδία φόρμας -> [(kind, ref, slug, title)]. Τιμές sel: site:3, practice:5, cards:5, deck:2, solutions:pack."""
    out, seen = [], set()
    for v in f.getlist('sel'):
        kind, _, ref = str(v).partition(':')
        if kind not in KINDS or not ref or len(out) >= 20: continue
        slug = str(f.get('slug_' + v) or '').strip().lower(); title = str(f.get('title_' + v) or '').strip()[:200]
        if not ok_slug(slug): raise HTTPException(422, f'Το όνομα φακέλου «{slug}» δεν είναι έγκυρο (a-z, 0-9, παύλα, έως 48, όχι index/assets/manifest).')
        if slug in seen: raise HTTPException(422, f'Το όνομα φακέλου «{slug}» χρησιμοποιείται δύο φορές.')
        seen.add(slug); out.append((kind, ref, slug, title))
    if not out: raise HTTPException(422, 'Δεν διάλεξες τίποτα για δημοσίευση.')
    return out


def build_all(c, f):
    items = [build_item(c, k, r, s, t, f) for k, r, s, t in parse_selection(c, f)]
    if sum(i.size for i in items) > 2 * MAX_BYTES: raise HTTPException(422, 'Πολύ μεγάλος συνολικός όγκος για μία δημοσίευση.')
    return items


def tree_files(cfg, items, manifest):
    """Διαδρομές repo -> bytes για τα items + νέο ευρετήριο και manifest."""
    d = cfg['dir']; add = {}
    for it in items:
        for n, data in it.files.items(): add[f'{d}/{it.slug}/{n}'] = data
    add[f'{d}/index.html'] = index_html(cfg, manifest); add[f'{d}/manifest.json'] = manifest_bytes(manifest)
    return add


def new_manifest(cfg, items, via):
    byslug = {m['slug']: m for m in cfg['manifest']}
    for it in items: byslug[it.slug] = {'slug': it.slug, 'title': it.title, 'kind': it.kind, 'updated': now(), 'files': len(it.files), 'bytes': it.size, 'via': via}
    return list(byslug.values())


# ---------- σελίδες ----------
CSS = "<style>.blk{border-left:4px solid #d9534f;padding:.3rem .6rem;background:#fbe3e1;margin:.3rem 0}.wrn{border-left:4px solid #e6a700;padding:.3rem .6rem;background:#fff6dc;margin:.3rem 0}fieldset{margin:.8rem 0}.tok{font-family:monospace}</style>"


def hid(f, skip=('ack', 'ack_iep')): return ''.join(f"<input type=hidden name='{E(k, quote=True)}' value='{E(str(v), quote=True)}'>" for k, v in f.multi_items() if k not in skip)


@router.get('/ghpages', response_class=HTMLResponse, dependencies=[Depends(auth)])
def gh_page(msg: str = '', err: str = ''):
    c = db(); cfg = load_cfg(c); sites = c.execute('SELECT id,name,title FROM site ORDER BY id').fetchall(); quizzes = c.execute('SELECT id,name FROM quiz WHERE EXISTS (SELECT 1 FROM quiz_item WHERE quiz_id=quiz.id) ORDER BY id').fetchall()
    decks = c.execute('SELECT id,name FROM deck WHERE kind=0 ORDER BY id').fetchall(); sols = c.execute('SELECT item_id,qcode,status FROM qsolution').fetchall(); c.close()
    from . import qsol
    sols = sorted(sols, key=lambda r: qsol.sort_key(r[0], r[1]))
    def row(kind, ref, label, slug):
        v = f'{kind}:{ref}'; return f"<tr><td><input type=checkbox name=sel value='{v}'></td><td>{E(KINDS[kind])}</td><td>{E(label)}</td><td><input name='slug_{v}' value='{E(slug, quote=True)}' size=26></td></tr>"
    rows = [row('site', s['id'], s['title'] or s['name'], S.slugify(s['name'])) for s in sites]
    rows += [row(k, q['id'], q['name'], S.slugify(q['name']) + ('-askisi' if k == 'practice' else '-kartes')) for q in quizzes for k in ('practice', 'cards')]
    rows += [row('deck', d['id'], d['name'], S.slugify(d['name'])) for d in decks]
    pack = (f"<tr><td><input type=checkbox name=sel value='solutions:pack'></td><td>{KINDS['solutions']}</td><td>σελίδα με τις λύσεις που διαλέγεις παρακάτω <br><input name='title_solutions:pack' placeholder='Τίτλος' size=30></td><td><input name='slug_solutions:pack' value='lyseis' size=26></td></tr>") if sols else ''
    solsel = (f"<fieldset><legend>Λύσεις εκπαιδευτικού (για τη γραμμή «Λύσεις»)</legend><select name=sol_keys multiple size=8>" + ''.join(f"<option value='{E(r[0])}|{E(r[1])}'>Θέμα {E(r[0])} · {E(r[1])} ({E(r[2] or '')})</option>" for r in sols)
              + "</select><p><label><input type=checkbox name=sol_hide value=1 checked> κρυφές απαντήσεις με κλικ</label> <label><input type=checkbox name=sol_img value=1> να περιληφθούν οι εικόνες των λύσεων (προέρχονται από σχήματα ΙΕΠ)</label></p><small>Οι «Εκφώνηση» και «Ενδεικτική λύση ΙΕΠ» δεν περιλαμβάνονται ποτέ.</small></fieldset>") if sols else ''
    pubs = ''.join(f"<tr><td><a href='{E(pages_url(cfg, m['slug']), quote=True)}' target=_blank rel=noopener>{E(m.get('title') or m['slug'])}</a></td><td>{E(KINDS.get(m.get('kind'), ''))}</td><td>{E(m.get('updated', ''))}{' (zip)' if m.get('via') == 'zip' else ''}</td><td><code>{E(m['slug'])}</code></td>"
                   f"<td><form method=post action='/ghpages/remove' data-confirm='Κατάργηση από το GitHub Pages;'><input type=hidden name=slug value='{E(m['slug'], quote=True)}'><button class=danger>Κατάργηση</button></form></td></tr>" for m in sorted(cfg['manifest'], key=lambda m: m['slug']))
    ready = bool(cfg['repo'] and cfg['token'])
    clear_cb = "<label class='f chk'><input type=checkbox name=clear_token value=1> διαγραφή token</label>" if cfg['token'] else ''
    tok_ph = 'αποθηκευμένο — άφησέ το κενό για να μείνει' if cfg['token'] else 'github_pat_…'
    body = (CSS + f"<h2>Δημοσίευση στο GitHub Pages</h2>{f'<div class=note>{E(msg)}</div>' if msg else ''}{f'<div class=blk>{E(err)}</div>' if err else ''}"
            "<div class='adm adm-warning'><p class=adm-t>Το GitHub Pages είναι δημόσιο</p><p>Ό,τι ανεβάσεις φαίνεται σε όλο τον κόσμο, <b>χωρίς κωδικό</b>. Δεν επιτρέπεται υλικό του ΙΕΠ ή του βιβλίου (εκφωνήσεις, λύσεις ΙΕΠ, εικόνες/PDF)· οι απαντήσεις των quiz φαίνονται στον κώδικα.</p></div>"
            f"<fieldset><legend>Ρυθμίσεις</legend><form method=post action='/ghpages/settings'><label class=f>Repo (χρήστης/όνομα) <input name=repo value='{E(cfg['repo'], quote=True)}' size=40 placeholder='kathigitisakr/kathigitisakr.github.io'></label> "
            f"<label class=f>Branch <input name=branch value='{E(cfg['branch'], quote=True)}' size=10></label> <label class=f>Φάκελος στο repo <input name=dir value='{E(cfg['dir'], quote=True)}' size=14></label><br>"
            f"<label class=f>Token (fine-grained, μόνο αυτό το repo, Contents: Read and write) <input class=tok type=password name=token size=44 autocomplete=off placeholder='{tok_ph}'></label>"
            f"{clear_cb} <button class=primary>Αποθήκευση</button></form>"
            f"<form method=post action='/ghpages/test' style='margin-top:.5rem'><button{'' if ready else ' disabled'}>Έλεγχος σύνδεσης</button></form>"
            "<p><small>Το token αποθηκεύεται στη βάση του server (όχι στον φάκελο δεδομένων που μοιράζεται) και δεν εμφανίζεται ξανά. Ο server πρέπει να φτάνει στο api.github.com.</small></p></fieldset>"
            f"<form method=post action='/ghpages/preview'><h3>Τι θα δημοσιευτεί</h3><div class=scroll><table><tr><th></th><th>Είδος</th><th>Περιεχόμενο</th><th>Φάκελος (slug)</th></tr>{''.join(rows + [pack]) or '<tr><td colspan=4>Δεν υπάρχει ακόμη περιεχόμενο (site, quiz, παρουσιάσεις, λύσεις).</td></tr>'}</table></div>{solsel}"
            "<label class='f chk'><input type=checkbox name=ack value=1> Επιβεβαιώνω ότι δεν περιέχεται υλικό ΙΕΠ ή βιβλίου που δεν έχω δικαίωμα να δημοσιεύσω και ότι καταλαβαίνω πως είναι δημόσιο.</label><p><button class=primary>Προεπισκόπηση (δεν αλλάζει τίποτα)</button></p></form>"
            f"<h3>Δημοσιευμένα</h3><div class=scroll><table><tr><th>Τίτλος</th><th>Είδος</th><th>Ενημερώθηκε</th><th>Φάκελος</th><th></th></tr>{pubs or '<tr><td colspan=5>Καμία ακόμα.</td></tr>'}</table></div>"
            + (f"<p>Ευρετήριο: <a href='{E(pages_url(cfg), quote=True)}' target=_blank rel=noopener>{E(pages_url(cfg))}</a> <small>(το GitHub θέλει λίγο να ανανεωθεί μετά το commit)</small></p>" if cfg['repo'] and ok_repo(cfg['repo']) else ''))
    return page('GitHub Pages', body)


def back(msg='', err=''):
    q = '&'.join(f'{k}={quote(v)}' for k, v in (('msg', msg), ('err', err)) if v); return RedirectResponse('/ghpages' + ('?' + q if q else ''), status_code=303)


@router.post('/ghpages/settings', dependencies=[Depends(auth)])
async def gh_settings(request: Request):
    same_origin(request); f = await request.form(); g = lambda k: str(f.get(k) or '').strip()
    repo, branch, d = g('repo'), g('branch') or 'main', g('dir') or 'thilek'
    if repo and not ok_repo(repo): raise HTTPException(422, 'Το repo πρέπει να έχει τη μορφή χρήστης/όνομα.')
    if not ok_branch(branch) or not ok_dir(d): raise HTTPException(422, 'Άκυρο branch ή όνομα φακέλου (γράμματα, ψηφία, _ και -).')
    tok = g('token')
    if tok and not re.fullmatch(r'[A-Za-z0-9_]{20,255}', tok): raise HTTPException(422, 'Το token έχει άγνωστη μορφή.')
    c = db()
    try:
        _set(c, 'gh_repo', repo); _set(c, 'gh_branch', branch); _set(c, 'gh_dir', d)
        if g('clear_token') == '1': _set(c, 'gh_token', '')
        elif tok: _set(c, 'gh_token', tok)
        c.commit()
    finally: c.close()
    return back('Αποθηκεύτηκαν οι ρυθμίσεις.')


def need_ready(cfg):
    if not (ok_repo(cfg['repo']) and cfg['token']): raise HTTPException(422, 'Συμπλήρωσε repo και token στις ρυθμίσεις.')


@router.post('/ghpages/test', dependencies=[Depends(auth)])
def gh_test(request: Request):
    same_origin(request); c = db(); cfg = load_cfg(c); c.close(); need_ready(cfg)
    try:
        d = Gh(cfg).call('GET', ''); push = (d.get('permissions') or {}).get('push')
        Gh(cfg).call('GET', f"/git/ref/heads/{quote(cfg['branch'], safe='/')}")
    except GhError as e: return back(err=e.msg)
    return back(f"Η σύνδεση δουλεύει: {d.get('full_name')}{'' if push else ' — ΠΡΟΣΟΧΗ: το token φαίνεται να μην έχει δικαίωμα εγγραφής'} · {'δημόσιο' if not d.get('private') else 'ιδιωτικό'} repo.")


def check_acks(items, f):
    if f.get('ack') != '1': raise HTTPException(422, 'Χρειάζεται η επιβεβαίωση ότι το περιεχόμενο μπορεί να γίνει δημόσιο.')
    if any(i.iep for i in items) and f.get('ack_iep') != '1': raise HTTPException(422, 'Υπάρχουν στοιχεία που προέρχονται από θέματα/σχήματα ΙΕΠ: χρειάζεται η ρητή επιβεβαίωση δικαιώματος.')
    if any(i.block for i in items): raise HTTPException(422, 'Υπάρχουν στοιχεία που δεν επιτρέπεται να δημοσιευτούν. Δες την προεπισκόπηση.')


@router.post('/ghpages/preview', response_class=HTMLResponse, dependencies=[Depends(auth)])
async def gh_preview(request: Request):
    same_origin(request); f = await request.form(); c = db(); cfg = load_cfg(c)
    try: items = build_all(c, f)
    finally: c.close()
    if f.get('ack') != '1': raise HTTPException(422, 'Χρειάζεται η επιβεβαίωση ότι το περιεχόμενο μπορεί να γίνει δημόσιο.')
    old = {m['slug'] for m in cfg['manifest']}; rows = []
    for i in items:
        w = ''.join(f'<div class=wrn>⚠ {E(x)}</div>' for x in i.warn) + ''.join(f'<div class=blk>⛔ {E(x)}</div>' for x in i.block)
        rows.append(f"<tr><td>{E(KINDS[i.kind])}</td><td>{E(i.title)}</td><td><code>{E(cfg['dir'])}/{E(i.slug)}/</code>{' <b>(αντικαθιστά)</b>' if i.slug in old else ''}</td><td>{len(i.files)}</td><td>{i.size // 1024} KB</td><td>{w or '✔'}</td></tr>")
    blocked = any(i.block for i in items); iep = any(i.iep for i in items); ready = bool(ok_repo(cfg['repo']) and cfg['token'])
    ack2 = "<label class='f chk'><input type=checkbox name=ack_iep value=1> Περιέχονται στοιχεία που προέρχονται από θέματα/σχήματα ΙΕΠ και έχω το δικαίωμα να τα δημοσιεύσω.</label>" if iep else ''
    act = ('' if blocked else f"<form method=post action='/ghpages/apply'>{hid(f)}<input type=hidden name=ack value=1>{ack2}<button class=primary{'' if ready else ' disabled'}>Εφαρμογή στο GitHub (ένα commit)</button> "
           f"<button formaction='/ghpages/zip'>Λήψη zip + script push</button></form>" + ('' if ready else '<p><small>Για εφαρμογή χρειάζονται repo και token στις ρυθμίσεις· το zip δουλεύει χωρίς token.</small></p>'))
    body = (CSS + f"<h2>Προεπισκόπηση δημοσίευσης</h2><div class=note>Δεν έχει αλλάξει τίποτα ακόμη. Στόχος: <b>{E(cfg['repo'] or '—')}</b> · branch {E(cfg['branch'])} · φάκελος {E(cfg['dir'])}</div>"
            f"<div class=scroll><table><tr><th>Είδος</th><th>Τίτλος</th><th>Φάκελος</th><th>Αρχεία</th><th>Μέγεθος</th><th>Έλεγχος</th></tr>{''.join(rows)}</table></div>{act}<p><a class=btn href='/ghpages' data-back>← Πίσω</a></p>")
    return page('Προεπισκόπηση GitHub Pages', body)


@router.post('/ghpages/apply', dependencies=[Depends(auth)])
async def gh_apply(request: Request):
    same_origin(request); f = await request.form(); c = db(); cfg = load_cfg(c); need_ready(cfg)
    try:
        items = build_all(c, f); check_acks(items, f); man = new_manifest(cfg, items, 'api'); add = tree_files(cfg, items, man)
        try: sha, n = commit_files(cfg, add, [f"{cfg['dir']}/{i.slug}/" for i in items], 'TH-ILEK: δημοσίευση ' + ', '.join(i.slug for i in items)[:150])
        except GhError as e: return back(err=e.msg)
        _set(c, 'gh_manifest', json.dumps(man, ensure_ascii=False)); c.commit()
    finally: c.close()
    return back('Δεν άλλαξε τίποτα σε σχέση με το GitHub.' if not sha else f"Έγινε commit ({n} αρχεία). Οι σελίδες θα φανούν στο {pages_url(cfg)} σε λίγα λεπτά.")


@router.post('/ghpages/remove', dependencies=[Depends(auth)])
async def gh_remove(request: Request):
    same_origin(request); f = await request.form(); slug = str(f.get('slug') or ''); c = db(); cfg = load_cfg(c); need_ready(cfg)
    try:
        if not ok_slug(slug): raise HTTPException(422, 'Άκυρο όνομα φακέλου.')
        man = [m for m in cfg['manifest'] if m['slug'] != slug]; add = {f"{cfg['dir']}/index.html": index_html(cfg, man), f"{cfg['dir']}/manifest.json": manifest_bytes(man)}
        try: commit_files(cfg, add, [f"{cfg['dir']}/{slug}/"], f'TH-ILEK: κατάργηση {slug}')
        except GhError as e: return back(err=e.msg)
        _set(c, 'gh_manifest', json.dumps(man, ensure_ascii=False)); c.commit()
    finally: c.close()
    return back(f'Καταργήθηκε το «{slug}».')


PS1 = """param([Parameter(Mandatory=$true)][string]$Repo, [string]$Message = "TH-ILEK publish")
$ErrorActionPreference = 'Stop'
if (-not (Test-Path (Join-Path $Repo '.git'))) { throw "No git repo at $Repo" }
Copy-Item -Path (Join-Path $PSScriptRoot '%(d)s') -Destination $Repo -Recurse -Force
git -C $Repo add -- '%(d)s'
git -C $Repo commit -m $Message
git -C $Repo push
"""


@router.post('/ghpages/zip', dependencies=[Depends(auth)])
async def gh_zip(request: Request):
    same_origin(request); f = await request.form(); c = db(); cfg = load_cfg(c)
    try:
        if not ok_dir(cfg['dir']): raise HTTPException(422, 'Άκυρος φάκελος στις ρυθμίσεις.')
        items = build_all(c, f); check_acks(items, f); man = new_manifest(cfg, items, 'zip'); add = tree_files(cfg, items, man)
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
            for p, data in add.items(): z.writestr(p, data)
            z.writestr('publish-ghpages.ps1', PS1 % {'d': cfg['dir']})
            z.writestr('README.txt', f"Δημοσίευση στο GitHub Pages (εφεδρικός τρόπος)\n1. Άνοιξε το PowerShell σε αυτόν τον φάκελο.\n2. .\\publish-ghpages.ps1 -Repo C:\\διαδρομή\\του\\τοπικού\\repo\nΑντιγράφει τον φάκελο {cfg['dir']} στο repo και κάνει git add/commit/push. Η διαγραφή παλιών αρχείων δεν γίνεται αυτόματα.\n")
        _set(c, 'gh_manifest', json.dumps(man, ensure_ascii=False)); c.commit()
    finally: c.close()
    return Response(b.getvalue(), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="thilek-github-pages.zip"'})
