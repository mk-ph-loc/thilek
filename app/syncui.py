"""Σελίδα /sync (0.20.0): σταθερή λίστα εντολών συντήρησης (rclone από το Google Drive, rebuild) ως εργασία παρασκηνίου.
ΔΕΝ εκτελείται ελεύθερο κείμενο ούτε shell: κάθε ενέργεια είναι από τον πίνακα ACTIONS, τα ορίσματα ως λίστα (χωρίς shell)."""
import json, os, pathlib, shutil, subprocess, sys, tempfile, threading, time
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from . import config, settings
from .main_auth import auth
from .review import page, html, same_origin

router = APIRouter()
E = html.escape
EXCL = ('--exclude', '07_EXAGOGES/**')
TIMEOUT = 3 * 3600
# κλειδί: (ετικέτα, κίνδυνος 0/1/2, περιγραφή)· κίνδυνος 2 = ζητά πληκτρολόγηση SYNC
ACTIONS = {
    'remotes': ('Λίστα remotes του rclone', 0, 'Δείχνει ποια remotes έχει ρυθμισμένα ο rclone (π.χ. gdrive:). Δεν αλλάζει τίποτα.'),
    'ls': ('Φάκελοι του Drive', 0, 'Δείχνει τους φακέλους πρώτου επιπέδου του απομακρυσμένου φακέλου. Μόνο ανάγνωση.'),
    'check': ('Σύγκριση Drive ↔ server', 0, 'Συγκρίνει αρχεία Drive και τοπικά (χωρίς το 07_EXAGOGES). Σύμβολα: = ίδια, + λείπει από τον server, - λείπει από το Drive, * διαφέρουν. Μόνο ανάγνωση.'),
    'copy_dry': ('Αντιγραφή: δοκιμή (dry-run)', 0, 'Δείχνει τι θα κατέβει (νέα/αλλαγμένα), χωρίς να γράψει τίποτα.'),
    'copy': ('Αντιγραφή Drive → server', 1, 'Κατεβάζει νέα και αλλαγμένα αρχεία. ΔΕΝ σβήνει τίποτα στον server.'),
    'sync_dry': ('Συγχρονισμός: δοκιμή (dry-run)', 0, 'Δείχνει τι θα γίνει με πλήρη συγχρονισμό, συμπεριλαμβανομένων των διαγραφών, χωρίς να γράψει τίποτα.'),
    'sync': ('Συγχρονισμός Drive → server (με διαγραφές)', 2, 'Κάνει τον server ίδιο με το Drive: ό,τι δεν υπάρχει στο Drive σβήνεται από τον server (π.χ. λύσεις .md που έγραψες μόνο εκεί). Τρέξε πρώτα τη δοκιμή.'),
    'rebuild': ('Rebuild βάσης', 1, 'Ξαναχτίζει τη βάση από τα αρχεία (όπως το thilek-rebuild). Οι χειροκίνητοι σύνδεσμοι και οι ρυθμίσεις διατηρούνται. Μπορεί να κρατήσει μερικά λεπτά.'),
}
ORDER = ('remotes', 'ls', 'check', 'copy_dry', 'copy', 'sync_dry', 'sync', 'rebuild')
STATE = {'running': False, 'action': '', 'label': '', 'started': 0, 'ended': 0, 'rc': None}
LOCK = threading.Lock()


def log_path():
    d = pathlib.Path(config.load()['db']).parent
    if not (d.is_dir() and os.access(d, os.W_OK)): d = pathlib.Path(tempfile.gettempdir())
    return d / 'thilek-last-job.log'


def build_cmd(action, s=None):
    """Η γραμμή εντολής (λίστα ορισμάτων) μιας ενέργειας. ValueError με ελληνικό μήνυμα όταν λείπει εργαλείο."""
    s = s or settings.get_all(); cfg = config.load(); data = cfg['data_root']; remote = s['rclone_remote']
    if action == 'rebuild':
        tool = pathlib.Path(__file__).resolve().parent.parent / 'tools' / 'rebuild.py'
        if not tool.is_file(): raise ValueError('δεν βρέθηκε το tools/rebuild.py')
        return [sys.executable, str(tool), data, cfg['db']]
    rc = shutil.which('rclone')
    if not rc: raise ValueError('δεν βρέθηκε το rclone στον server (apt install rclone και ρύθμιση remote με: runuser -u thilek -- rclone config)')
    if action == 'remotes': return [rc, 'listremotes']
    if action == 'ls': return [rc, 'lsd', remote]
    if action == 'check': return [rc, 'check', remote, data, *EXCL, '--combined', '-']
    if action == 'copy_dry': return [rc, 'copy', remote, data, *EXCL, '--dry-run', '-v']
    if action == 'copy': return [rc, 'copy', remote, data, *EXCL, '-v']
    if action == 'sync_dry': return [rc, 'sync', remote, data, *EXCL, '--dry-run', '-v']
    if action == 'sync': return [rc, 'sync', remote, data, *EXCL, '-v']
    raise ValueError('άγνωστη ενέργεια')


def _run(cmd, label):
    lp = log_path(); rc = None
    try:
        with open(lp, 'wb') as fh:
            fh.write(('$ ' + ' '.join(cmd) + '\n\n').encode('utf-8'))
            fh.flush()
            try:
                p = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
                try: rc = p.wait(timeout=TIMEOUT)
                except subprocess.TimeoutExpired:
                    p.kill(); rc = -9; fh.write('\n[διακόπηκε: ξεπεράστηκε το χρονικό όριο]\n'.encode('utf-8'))
            except Exception as e:
                rc = 127; fh.write(f'\n[σφάλμα εκκίνησης: {e}]\n'.encode('utf-8'))
    except Exception as e: rc = 126; STATE['err'] = str(e)
    finally:
        STATE.update(running=False, ended=time.time(), rc=rc)


def start(action, s=None):
    """Ξεκινά εργασία παρασκηνίου (μία κάθε φορά). Επιστρέφει το thread (για τα τεστ)."""
    if action not in ACTIONS: raise HTTPException(422, 'Άγνωστη ενέργεια')
    try: cmd = build_cmd(action, s)
    except ValueError as e: raise HTTPException(422, str(e))
    with LOCK:
        if STATE['running']: raise HTTPException(409, 'Τρέχει ήδη μια εργασία· περίμενε να τελειώσει.')
        STATE.update(running=True, action=action, label=ACTIONS[action][0], started=time.time(), ended=0, rc=None); STATE.pop('err', None)
    t = threading.Thread(target=_run, args=(cmd, ACTIONS[action][0]), daemon=True); t.start(); return t


def tail(n=60000):
    try:
        b = log_path().read_bytes()
        return b[-n:].decode('utf-8', 'replace')
    except OSError: return ''


@router.get('/sync/status', dependencies=[Depends(auth)])
def sync_status():
    return JSONResponse({**{k: v for k, v in STATE.items() if k != 'err'}, 'log': tail()}, headers={'Cache-Control': 'no-store'})


@router.post('/sync/run', dependencies=[Depends(auth)])
def sync_run(request: Request, action: str = Form(...), confirm: str = Form('')):
    same_origin(request)
    if action not in ACTIONS: raise HTTPException(422, 'Άγνωστη ενέργεια')
    if ACTIONS[action][1] == 2 and confirm.strip() != 'SYNC': raise HTTPException(422, 'Η ενέργεια σβήνει αρχεία: πληκτρολόγησε SYNC στο πεδίο επιβεβαίωσης.')
    start(action)
    return RedirectResponse('/sync', status_code=303)


def drive_bar(s=None, link=True):
    s = s or settings.get_all()
    return (f"<p class=drivebar>📁 <a href='{E(s['drive_url'])}' target=_blank rel='noopener noreferrer'>Άνοιγμα του φακέλου στο Google Drive</a> "
            f"(για σύγκριση με τα αρχεία του server){' · <a href=/sync>Συγχρονισμός και εντολές</a>' if link else ''}</p>")


@router.get('/sync', response_class=HTMLResponse, dependencies=[Depends(auth)])
def sync_page():
    s = settings.get_all(); busy = STATE['running']; rows = []
    for k in ORDER:
        lab, risk, desc = ACTIONS[k]
        conf = "<input class=r-txt name=confirm size=8 placeholder='SYNC' autocomplete=off required> " if risk == 2 else ''
        cls = 'danger' if risk == 2 else ('primary' if risk == 1 else '')
        rows.append(f"<div class=syncrow><form method=post action=/sync/run class=filters><input type=hidden name=action value={k}>{conf}"
                    f"<button class='{cls}' {'disabled' if busy else ''}>{E(lab)}</button></form><div>{E(desc)}</div></div>")
    ready = 'γεμάτο' if tail() else 'κενό'
    body = f"""<h2>Συγχρονισμός Drive και εντολές συντήρησης</h2>{drive_bar(s, False)}
<p>Φάκελος rclone: <code>{E(s['rclone_remote'])}</code> → φάκελος δεδομένων του server. Αλλάζουν στις <a href='/settings'>Ρυθμίσεις</a>.</p>
<div class='adm adm-warning'><p class=adm-t>Τι επιτρέπεται</p><p>Μόνο οι παρακάτω έτοιμες εντολές. Δεν υπάρχει πεδίο για ελεύθερες εντολές. Προτεινόμενη σειρά: <b>Σύγκριση → Αντιγραφή (δοκιμή) → Αντιγραφή → Rebuild</b>. Ο φάκελος <code>07_EXAGOGES</code> εξαιρείται πάντα.</p></div>
<div class=synclist>{''.join(rows)}</div>
<h3>Αποτέλεσμα <span id=jobstate></span></h3>
<pre id=joblog class=joblog data-url='/sync/status' data-busy='{1 if busy else 0}'>{E(tail())}</pre>
<script src='/static/sync.js'></script>"""
    return page('Συγχρονισμός', body)
