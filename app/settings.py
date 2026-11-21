"""Ρυθμίσεις χρήστη (0.19.0): σελίδα /settings, πίνακας setting(k,v) της βάσης (διατηρείται στο rebuild)."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from .main_auth import auth
from .review import db, page, html, same_origin

router = APIRouter()
DEFAULTS = {'diagram_mode': 'svg', 'help_default': 'open', 'help_show': 'on'}
CHOICES = {'diagram_mode': ('svg', 'local'), 'help_default': ('open', 'closed'), 'help_show': ('on', 'off')}


def get_all():
    """Όλες οι ρυθμίσεις (με προεπιλογές). Λάθος-ασφαλές: αν λείπει ο πίνακας ή η βάση, επιστρέφει τις προεπιλογές."""
    out = dict(DEFAULTS)
    try:
        c = db()
        try:
            for r in c.execute('SELECT k,v FROM setting'):
                if r['k'] in CHOICES and r['v'] in CHOICES[r['k']]: out[r['k']] = r['v']
        finally: c.close()
    except Exception: pass
    return out


def get(k): return get_all().get(k, DEFAULTS.get(k))


@router.get('/settings', response_class=HTMLResponse, dependencies=[Depends(auth)])
def settings_page(saved: int = 0):
    s = get_all()
    ok = '<div class="adm adm-success"><p class=adm-t>✔ Αποθηκεύτηκε</p></div>' if saved else ''
    def radios(k, opts):
        return ''.join(f"<label class='f chk'><input type=radio class=r-opt name={k} value={v} {'checked' if s[k] == v else ''}>{html.escape(lab)}</label>" for v, lab in opts)
    body = f"""<h2>Ρυθμίσεις</h2>{ok}
<form method=post action=/settings>
<fieldset><legend>Διαγράμματα (Mermaid)</legend>
{radios('diagram_mode', [('svg', 'Έτοιμο SVG (προτείνεται): γρήγορο, δουλεύει και χωρίς JavaScript· αν λείπει το SVG ενός διαγράμματος, χρησιμοποιείται αυτόματα το τοπικό Mermaid'), ('local', 'Τοπικό Mermaid στον browser (static/vendor/mermaid): αποδίδει το διάγραμμα από το κείμενο, χωρίς CDN')])}
<p><small>Τα έτοιμα SVG βρίσκονται στο <code>app/diagrams/</code> και παράγονται από το <code>tools/render_diagrams.py</code>.</small></p></fieldset>
<fieldset><legend>Βοήθεια σελίδας (ℹ)</legend>
{radios('help_show', [('on', 'Εμφάνιση του πλαισίου βοήθειας στις σελίδες'), ('off', 'Απόκρυψη παντού')])}
<p>Όταν ανοίγεις μια σελίδα για πρώτη φορά, η βοήθεια της είναι:</p>
{radios('help_default', [('open', 'ανοιχτή'), ('closed', 'κλειστή')])}
<p><small>Κάθε σελίδα θυμάται τη δική σου επιλογή (άνοιγμα/κλείσιμο) στον browser, και αυτή υπερισχύει της προεπιλογής.</small></p>
<p><button type=button data-act=help-reset title='Σβήνει τις αποθηκευμένες επιλογές ανοίγματος/κλεισίματος από αυτόν τον browser'>Επαναφορά επιλογών help αυτού του browser</button></p></fieldset>
<button class=primary>Αποθήκευση</button></form>
<h3>Πού αποθηκεύονται</h3>
<p>Οι ρυθμίσεις γράφονται στον πίνακα <code>setting</code> της βάσης (κοινές για όλους τους browsers, διατηρούνται στο <code>thilek-rebuild</code>). Η μνήμη ανοίγματος του help ανά σελίδα και η τσεκαρισμένη κατάσταση των λιστών εργασιών των εγχειριδίων μένουν στο <b>localStorage του browser</b> (ανά συσκευή, δεν είναι στον server). Δες το <a href='/manual/db'>εγχειρίδιο βάσης</a>.</p>"""
    return page('Ρυθμίσεις', body)


@router.post('/settings', dependencies=[Depends(auth)])
def settings_save(request: Request, diagram_mode: str = Form('svg'), help_default: str = Form('open'), help_show: str = Form('on')):
    same_origin(request)
    vals = {'diagram_mode': diagram_mode, 'help_default': help_default, 'help_show': help_show}; c = db()
    try:
        for k, v in vals.items():
            if v in CHOICES[k]: c.execute('INSERT OR REPLACE INTO setting(k,v) VALUES(?,?)', (k, v))
        c.commit()
    finally: c.close()
    return RedirectResponse('/settings?saved=1', status_code=303)
