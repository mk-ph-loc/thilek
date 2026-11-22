"""Ρυθμίσεις χρήστη (0.20.0): σελίδα /settings, πίνακας setting(k,v) της βάσης (διατηρείται στο rebuild)."""
import re
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from .main_auth import auth
from .review import db, page, html, same_origin

router = APIRouter()
DRIVE_URL = 'https://drive.google.com/drive/folders/1o8IbCBlgcnncuotnccop6HO717sFMwfA?usp=sharing'
# είδη εργαλείων για tooltip hover (κλειδί, ετικέτα): το κλειδί αντιστοιχεί στη συνάρτηση kindOf() του static/ui.js
TIP_KINDS = (('hdr', 'Σύνδεσμοι του μενού'), ('btn', 'Κουμπιά'), ('danger', 'Κουμπιά κινδύνου (διαγραφή, κάδος)'), ('sel', 'Τσεκ επιλογής γραμμών πινάκων'),
             ('opt', 'Ρυθμίσεις ναι/όχι και επιλογές (checkbox, radio)'), ('list', 'Λίστες επιλογής'), ('txt', 'Πεδία κειμένου'), ('file', 'Επιλογή αρχείου'), ('sum', 'Πτυσσόμενα (summary)'))
START_PAGES = (('/review', 'Θέματα'), ('/search', 'Αναζήτηση'), ('/browse', 'Ερωτήματα'), ('/coverage', 'Ύλη/σελίδα'), ('/tags', 'Ετικέτες'), ('/saved', 'Αποθηκευμένα'),
               ('/exams', 'Διαγωνίσματα'), ('/quizzes', 'Quiz'), ('/wizard', 'Wizard εξαγωγών'), ('/lyseis', 'Λύσεις'), ('/docs', 'Έγγραφα MD'), ('/fb', 'Αρχεία'), ('/sync', 'Συγχρονισμός Drive και εντολές'),
               ('/manual', 'Οδηγίες'), ('/settings', 'Ρυθμίσεις'))
DEFAULTS = {'diagram_mode': 'svg', 'help_default': 'open', 'help_show': 'on', 'help_mode': 'remember', 'start_page': '/review',
            'drive_url': DRIVE_URL, 'rclone_remote': 'gdrive:TH-ILEK'}
DEFAULTS['gform_images'] = 'text'
DEFAULTS['course_active'] = ''
DEFAULTS['embed_domains'] = 'youtube.com,youtube-nocookie.com,geogebra.org,falstad.com'
DEFAULTS['wiz_criteria'] = 'q,qtype,chapter,image,position,fav,yli,section,tag,lsol,src,upto'
DEFAULTS.update({'tip_' + k: 'on' for k, _ in TIP_KINDS})
CHOICES = {'gform_images': ('text', 'images'), 'diagram_mode': ('svg', 'local'), 'help_default': ('open', 'closed'), 'help_show': ('on', 'off'), 'help_mode': ('remember', 'open', 'closed'),
           'start_page': tuple(u for u, _ in START_PAGES)}
CHOICES.update({'tip_' + k: ('on', 'off') for k, _ in TIP_KINDS})
RE_REMOTE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.-]*:[^\x00-\x1f"\']{0,200}$')


def valid(k, v):
    """Έγκυρη τιμή για το κλειδί; (κείμενα: drive_url πρέπει να είναι σύνδεσμος Google Drive, rclone_remote της μορφής όνομα:διαδρομή.)"""
    if k in CHOICES: return v in CHOICES[k]
    if k == 'wiz_criteria':
        from .wizmodel import CRITERIA_KEYS
        xs = [x for x in v.split(',') if x]
        return bool(xs) and all(x in CRITERIA_KEYS for x in xs)
    if k == 'drive_url': return bool(re.match(r'^https://(drive|docs)\.google\.com/[^\s<>"\']{3,400}$', v))
    if k == 'rclone_remote': return bool(RE_REMOTE.match(v))
    if k == 'course_active': return v == '' or bool(re.match(r'^[A-Za-z0-9_-]{1,40}$', v))
    if k == 'embed_domains': return all(re.match(r'^[a-z0-9]([a-z0-9.-]{1,78})\.[a-z]{2,24}$', d) for d in v.split(',') if d) and len(v) <= 600
    return False


def get_all():
    """Όλες οι ρυθμίσεις (με προεπιλογές). Λάθος-ασφαλές: αν λείπει ο πίνακας ή η βάση, επιστρέφει τις προεπιλογές."""
    out = dict(DEFAULTS)
    try:
        c = db()
        try:
            for r in c.execute('SELECT k,v FROM setting'):
                if r['k'] in DEFAULTS and valid(r['k'], r['v']): out[r['k']] = r['v']
        finally: c.close()
    except Exception: pass
    return out


def get(k): return get_all().get(k, DEFAULTS.get(k))


@router.get('/settings', response_class=HTMLResponse, dependencies=[Depends(auth)])
def settings_page(saved: int = 0):
    s = get_all(); E = html.escape
    ok = '<div class="adm adm-success"><p class=adm-t>✔ Αποθηκεύτηκε</p></div>' if saved else ''
    def radios(k, opts):
        return ''.join(f"<label class='f chk'><input type=radio class=r-opt name={k} value={v} {'checked' if s[k] == v else ''}>{E(lab)}</label>" for v, lab in opts)
    tips = ''.join(f"<label class='f chk'><input type=checkbox class=r-opt name=tip_{k} {'checked' if s['tip_' + k] == 'on' else ''}>{E(lab)}</label>" for k, lab in TIP_KINDS)
    from .wizmodel import CRITERIA
    on = s['wiz_criteria'].split(',')
    wcs = ''.join(f"<label class='f chk'><input type=checkbox class=r-opt name=wc_{k} {'checked' if k in on else ''}>{E(lab)}</label>" for k, lab in CRITERIA)
    start = ''.join(f"<option value='{E(u)}' {'selected' if s['start_page'] == u else ''}>{E(lab)} ({E(u)})</option>" for u, lab in START_PAGES)
    body = f"""<h2>Ρυθμίσεις</h2>{ok}
<form method=post action=/settings>
<input type=hidden name=tips_present value=1>
<fieldset><legend>Αρχική σελίδα</legend>
<p>Η διεύθυνση <code>/</code> (όταν ανοίγεις μόνο το όνομα του server) οδηγεί σε:</p>
<label class=f>Αρχική σελίδα <select name=start_page class=r-list>{start}</select></label>
<p><small>Οι σύνδεσμοι του μενού και οι υπόλοιπες σελίδες δεν αλλάζουν.</small></p></fieldset>
<fieldset><legend>Κριτήρια επιλογής στον wizard εξαγωγών</legend><input type=hidden name=wc_present value=1>
<p>Ποια κριτήρια φαίνονται στο βήμα «Επιλογή» του <a href='/wizard'>wizard</a>:</p>{wcs}</fieldset>
<fieldset><legend>Tooltip στο hover, ανά είδος εργαλείου</legend>
<p>Τσεκαρισμένο = εμφανίζεται μικρό κείμενο βοήθειας όταν περνάς το ποντίκι πάνω από αυτό το είδος.</p>{tips}
<p><small>Ισχύει και στο πληκτρολόγιο (focus). Οι αλλαγές εφαρμόζονται στην επόμενη φόρτωση σελίδας.</small></p></fieldset>
<fieldset><legend>Βοήθεια σελίδας (ℹ)</legend>
{radios('help_show', [('on', 'Εμφάνιση του πλαισίου βοήθειας στις σελίδες'), ('off', 'Απόκρυψη παντού')])}
<p>Όταν ανοίγει μια σελίδα, η βοήθειά της είναι:</p>
{radios('help_mode', [('remember', 'όπως την άφησα (κάθε σελίδα θυμάται τη δική της κατάσταση στον browser)'), ('open', 'ΠΑΝΤΑ ανοιχτή'), ('closed', 'ΠΑΝΤΑ κλειστή')])}
<p>Στην επιλογή «όπως την άφησα», την πρώτη φορά που ανοίγεται μια σελίδα η βοήθεια είναι:</p>
{radios('help_default', [('open', 'ανοιχτή'), ('closed', 'κλειστή')])}
<p><button type=button data-act=help-reset title='Σβήνει τις αποθηκευμένες επιλογές ανοίγματος/κλεισίματος από αυτόν τον browser'>Επαναφορά επιλογών help αυτού του browser</button></p></fieldset>
<fieldset><legend>Διαγράμματα (Mermaid)</legend>
{radios('diagram_mode', [('svg', 'Έτοιμο SVG (προτείνεται): γρήγορο, δουλεύει και χωρίς JavaScript· αν λείπει το SVG ενός διαγράμματος, χρησιμοποιείται αυτόματα το τοπικό Mermaid'), ('local', 'Τοπικό Mermaid στον browser (static/vendor/mermaid)')])}
<p><small>Τα έτοιμα SVG βρίσκονται στο <code>app/diagrams/</code> και παράγονται από το <code>tools/render_diagrams.py</code>.</small></p></fieldset>
<fieldset><legend>Google Form (wizard)</legend>
{radios('gform_images', [('text', 'Τύποι ως κείμενο Unicode και εικόνες από φάκελο Drive (προεπιλογή)'), ('images', 'Όλα τα ερωτήματα ως εικόνες (η εικόνα του ΙΕΠ κάθε ερωτήματος)')])}
<p><small>Ισχύει όταν στο βήμα 5 του wizard η επιλογή είναι «Όπως στις Ρυθμίσεις».</small></p></fieldset>
<fieldset><legend>Google Drive και συγχρονισμός</legend>
<label class=f>Επιτρεπόμενα domains για embed σε παρουσιάσεις/σελίδες (χωρισμένα με κόμμα· ισχύει από 0.33) <input class=r-txt name=embed_domains size=70 value="{E(s['embed_domains'])}"></label>
<label class=f>Σύνδεσμος φακέλου Drive (για σύγκριση) <input class=r-txt name=drive_url size=70 value="{E(s['drive_url'])}"></label>
<label class=f>Απομακρυσμένος φάκελος rclone <input class=r-txt name=rclone_remote size=30 value="{E(s['rclone_remote'])}"></label>
<p><small>Η μορφή του rclone είναι <code>όνομα:διαδρομή</code>, π.χ. <code>gdrive:TH-ILEK</code>. Χρησιμοποιείται από τη σελίδα <a href='/sync'>Συγχρονισμός</a>.</small></p></fieldset>
<button class=primary>Αποθήκευση ρυθμίσεων</button></form>
<h3>Πού αποθηκεύονται</h3>
<p>Οι ρυθμίσεις γράφονται στον πίνακα <code>setting</code> της βάσης (κοινές για όλους τους browsers, διατηρούνται στο <code>thilek-rebuild</code>). Η μνήμη ανοίγματος του help ανά σελίδα και η τσεκαρισμένη κατάσταση των λιστών εργασιών των εγχειριδίων κρατιούνται στο <code>localStorage</code> του browser.</p>"""
    return page('Ρυθμίσεις', body)


@router.post('/settings', dependencies=[Depends(auth)])
async def settings_save(request: Request):
    same_origin(request)
    f = await request.form(); vals = {}
    for k in DEFAULTS:
        if k.startswith('tip_'): continue
        v = f.get(k)
        if isinstance(v, str) and valid(k, v.strip()): vals[k] = v.strip()
    if f.get('wc_present'):
        from .wizmodel import CRITERIA_KEYS
        sel = [k for k in CRITERIA_KEYS if f.get('wc_' + k)]
        if sel: vals['wiz_criteria'] = ','.join(sel)
    if f.get('tips_present'):
        for k, _ in TIP_KINDS: vals['tip_' + k] = 'on' if f.get('tip_' + k) else 'off'
    c = db()
    try:
        for k, v in vals.items(): c.execute('INSERT OR REPLACE INTO setting(k,v) VALUES(?,?)', (k, v))
        c.commit()
    finally: c.close()
    return RedirectResponse('/settings?saved=1', status_code=303)
