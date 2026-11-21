"""0.22: δημοσίευση στατικών ιστοσελίδων από τον server (εσωτερικό δίκτυο) με κωδικό μαθητή.
Αρχεία: <data_root>/_publish/<slug>/ (+ meta.json). Δεν χρειάζεται νέο πίνακα βάσης· ο κωδικός μαθητή (hash) μπαίνει στον πίνακα setting.
Οι σελίδες σερβίρονται με sandbox CSP (αδιαφανές origin): τα scripts τους δεν μπορούν να φτάσουν στο υπόλοιπο API."""
import base64, hashlib, hmac, html, json, os, pathlib, re, secrets, shutil, time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from . import config
from .main_auth import auth
from .review import db, page, same_origin

router = APIRouter()
E = html.escape
MIME = {'.html': 'text/html; charset=utf-8', '.json': 'application/json', '.txt': 'text/plain; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.pdf': 'application/pdf'}
ALLOWED = set(MIME)
basic = HTTPBasic(auto_error=False)
CSP = "default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; font-src data:; media-src data:; sandbox allow-scripts allow-popups"


def base():
    d = pathlib.Path(config.load()['data_root']) / '_publish'; return d


def make_hash(pw, salt=None):
    salt = salt or secrets.token_hex(8); h = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt.encode(), 60000).hex(); return f'{salt}${h}'


def check_hash(pw, stored):
    try: salt, _ = stored.split('$', 1)
    except ValueError: return False
    return hmac.compare_digest(make_hash(pw, salt), stored)


def get_pw_hash():
    c = db()
    try:
        r = c.execute("SELECT v FROM setting WHERE k='student_pw'").fetchone(); return r['v'] if r else ''
    except Exception: return ''
    finally: c.close()


def set_pw(pw):
    c = db()
    try:
        if pw: c.execute("INSERT INTO setting(k,v) VALUES('student_pw',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (make_hash(pw),))
        else: c.execute("DELETE FROM setting WHERE k='student_pw'")
        c.commit()
    finally: c.close()


def student_auth(cred: HTTPBasicCredentials | None = Depends(basic)):
    """Ο μαθητής μπαίνει με τον κωδικό μαθητή· ο διαχειριστής με τον δικό του. Χωρίς κωδικό μαθητή ΔΕΝ ανοίγει σε κανέναν εκτός διαχειριστή."""
    if cred:
        adm = config.load()['admin_password']
        if adm and secrets.compare_digest(cred.password.encode(), adm.encode()): return 'admin'
        h = get_pw_hash()
        if h and check_hash(cred.password, h): return 'student'
    raise HTTPException(401, headers={'WWW-Authenticate': 'Basic realm="TH-ILEK mathites"'})


def slugify(s):
    s = re.sub(r'[^A-Za-z0-9]+', '-', s).strip('-').lower()
    return s[:40] or 'pub'


def uniq_slug(title):
    d = base(); s = slugify(title)
    if not (d / s).exists(): return s
    n = 2
    while (d / f'{s}-{n}').exists(): n += 1
    return f'{s}-{n}'


def save_site(title, files, slug=None, source=''):
    """Γράφει τα αρχεία της δημοσίευσης. Επιτρέπονται μόνο απλά ονόματα αρχείων γνωστών τύπων."""
    d = base(); d.mkdir(parents=True, exist_ok=True); slug = slug or uniq_slug(title); tgt = d / slug
    tmp = d / f'.{slug}.tmp'; shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
    for n, data in files.items():
        if '/' in n or '\\' in n or n.startswith('.') or pathlib.Path(n).suffix.lower() not in ALLOWED: raise HTTPException(422, f'Μη επιτρεπτό όνομα αρχείου: {n}')
        (tmp / n).write_bytes(data)
    (tmp / 'meta.json').write_text(json.dumps({'title': title, 'created': time.strftime('%Y-%m-%d %H:%M'), 'source': source, 'files': len(files)}, ensure_ascii=False), encoding='utf-8')
    shutil.rmtree(tgt, ignore_errors=True); tmp.rename(tgt); return slug


def listing():
    out = []; d = base()
    if d.is_dir():
        for p in sorted(d.iterdir()):
            if p.is_dir() and not p.name.startswith('.') and (p / 'meta.json').is_file():
                try: m = json.loads((p / 'meta.json').read_text(encoding='utf-8'))
                except ValueError: m = {}
                out.append((p.name, m.get('title') or p.name, m.get('created', ''), m.get('source', '')))
    return out


@router.get('/publish', response_class=HTMLResponse, dependencies=[Depends(auth)])
def publish_admin(ok: int = 0):
    rows = ''.join(f"<tr><td><a href='/p/{E(s)}/'>{E(t)}</a></td><td>{E(cr)}</td><td>{E(src)}</td><td><code>/p/{E(s)}/</code></td>"
                   f"<td><form method=post action='/publish/{E(s)}/delete' style='display:inline'><button class=danger>Κατάργηση</button></form></td></tr>" for s, t, cr, src in listing())
    has = bool(get_pw_hash())
    msg = '<div class="adm adm-success"><p class=adm-t>✔ Αποθηκεύτηκε</p></div>' if ok else ''
    warn = '' if has else "<div class='adm adm-warning'><p class=adm-t>Δεν έχει οριστεί κωδικός μαθητή</p><p>Μέχρι να οριστεί, οι δημοσιευμένες σελίδες ανοίγουν μόνο με τον κωδικό διαχειριστή.</p></div>"
    body = (f"<h2>Δημοσιεύσεις</h2>{msg}{warn}<p>Οι μαθητές ανοίγουν <a href='/p/'>/p/</a> (όνομα χρήστη: οτιδήποτε, κωδικός: ο κωδικός μαθητή). "
            "Δημοσιεύονται όσα διαλέξεις στον wizard («Πού: δημοσίευση στον server»). Το δίκτυο θεωρείται εσωτερικό· ο κωδικός μαθητή δεν δίνει πρόσβαση σε τίποτα άλλο.</p>"
            f"<fieldset><legend>Κωδικός μαθητή</legend><form method=post action='/publish/password'><label class=f>Νέος κωδικός (άδειο = αφαίρεση) <input class=r-txt type=text name=pw size=24 autocomplete=off></label> <button class=primary>Αποθήκευση</button></form></fieldset>"
            f"<h3>Δημοσιευμένες σελίδες</h3><div class=scroll><table><tr><th>Τίτλος</th><th>Ημερομηνία</th><th>Πηγή</th><th>Διεύθυνση</th><th></th></tr>{rows or '<tr><td colspan=5>Καμία ακόμα.</td></tr>'}</table></div>")
    return page('Δημοσιεύσεις', body)


@router.post('/publish/password', dependencies=[Depends(auth)])
async def publish_password(request: Request):
    same_origin(request); f = await request.form(); pw = str(f.get('pw') or '').strip()
    if pw and not 4 <= len(pw) <= 64: raise HTTPException(422, 'Ο κωδικός μαθητή πρέπει να έχει 4 έως 64 χαρακτήρες.')
    set_pw(pw); return RedirectResponse('/publish?ok=1', status_code=303)


@router.post('/publish/{slug}/delete', dependencies=[Depends(auth)])
def publish_delete(request: Request, slug: str):
    same_origin(request)
    if not re.fullmatch(r'[a-z0-9-]{1,50}', slug) or not (base() / slug).is_dir(): raise HTTPException(404)
    shutil.rmtree(base() / slug); return RedirectResponse('/publish', status_code=303)


def _send(path: pathlib.Path):
    ext = path.suffix.lower()
    return Response(path.read_bytes(), media_type=MIME.get(ext, 'application/octet-stream'), headers={'Content-Security-Policy': CSP, 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})


@router.get('/p/', response_class=HTMLResponse)
def student_menu(who: str = Depends(student_auth)):
    items = ''.join(f"<li><a href='/p/{E(s)}/'>{E(t)}</a> <small>{E(cr)}</small></li>" for s, t, cr, _ in listing())
    return HTMLResponse(f"<!doctype html><html lang=el><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Υλικό μαθήματος</title>"
                        "<style>body{font:16px/1.6 system-ui,sans-serif;max-width:44rem;margin:2rem auto;padding:0 1rem}li{margin:.6rem 0}small{color:#667}</style>"
                        f"<h1>Υλικό μαθήματος</h1><ul>{items or '<li>Δεν υπάρχει ακόμα δημοσιευμένο υλικό.</li>'}</ul></html>", headers={'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'", 'Cache-Control': 'no-store'})


@router.get('/p/{slug}/{name:path}')
def student_file(slug: str, name: str = '', who: str = Depends(student_auth)):
    if not re.fullmatch(r'[a-z0-9-]{1,50}', slug): raise HTTPException(404)
    name = name or 'index.html'
    if '/' in name or name.startswith('.') or name == 'meta.json' or pathlib.Path(name).suffix.lower() not in ALLOWED: raise HTTPException(404)
    p = base() / slug / name
    if not p.is_file() or p.is_symlink(): raise HTTPException(404)
    return _send(p)
