"""Κοινά στοιχεία διεπαφής (0.18.0): CSS (σταθερό μενού, χρώματα ρόλων πεδίων, tooltips, πλαίσια), εργαλειοθήκες (έως 3, κοινές για τον server)."""
import json, pathlib
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from .main_auth import auth
from .uikit_css import UI_CSS
from .review import db, page, html, same_origin, fld

router = APIRouter()
E = html.escape
STATIC = pathlib.Path(__file__).parent / 'static'


@router.get('/static/ui.js', include_in_schema=False)
def ui_js(): return Response((STATIC / 'ui.js').read_text(encoding='utf-8'), media_type='application/javascript')

# ---------- εργαλειοθήκες ----------
CATALOG = {
    'search': ('🔎', 'Αναζήτηση', '/search', 'Ψάχνει σε βιβλίο και ερωτήματα (χωρίς τόνους, με ακριβείς φράσεις).'),
    'review': ('📋', 'Θέματα', '/review', 'Λίστα θεμάτων ΙΕΠ και έλεγχος συνδέσεων με το βιβλίο.'),
    'browse': ('❓', 'Ερωτήματα', '/browse', 'Φίλτρα ερωτημάτων και μπάρα ενεργειών για τα επιλεγμένα.'),
    'fav': ('★', 'Αγαπημένα', '/browse?fav=1', 'Μόνο τα ερωτήματα που έχεις σημειώσει με αστέρι.'),
    'coverage': ('📖', 'Ύλη/σελίδα', '/coverage', 'Ποια θέματα καλύπτονται μέχρι μια σελίδα του βιβλίου.'),
    'tags': ('🏷', 'Ετικέτες', '/tags', 'Μαζική ετικέτα ή αφαίρεση σε ερωτήματα και θέματα.'),
    'saved': ('💾', 'Αποθηκευμένα', '/saved', 'Διαγωνίσματα, quiz και συλλογές που έχεις φτιάξει.'),
    'merge': ('🧩', 'Συγχώνευση PDF', '/tools/merge', 'Ένα PDF από θέματα ή ερωτήματα, με προεπισκόπηση.'),
    'htmlx': ('🌐', 'Εξαγωγή HTML', '/tools/html', 'Αυτόνομο HTML από επιλεγμένα θέματα.'),
    'exams': ('📝', 'Διαγωνίσματα', '/exams', 'Παραγωγή διαγωνισμάτων Θέματα Α–Θ.'),
    'quizzes': ('🎯', 'Quiz', '/quizzes', 'Quiz με παιχνίδι, εκτύπωση και εξαγωγές.'),
    'lyseis': ('✍', 'Λύσεις', '/lyseis', 'Λύσεις εκπαιδευτικού και εξαγωγές Reveal/HTML μαθητή/Moodle.'),
    'docs': ('📄', 'Έγγραφα MD', '/docs', 'Έγγραφα Markdown, Word και HTML.'),
    'files': ('📂', 'File browser', '/fb', 'Αρχεία του server: προβολή, upload, λήψη, κάδος.'),
    'trash': ('🗑', 'Κάδος αρχείων', '/fb/trash', 'Επαναφορά ή οριστική διαγραφή αρχείων.'),
    'manual': ('📘', 'Οδηγίες', '/manual', 'Το εγχειρίδιο χρήσης.'),
    'toolbox': ('⚙', 'Ρύθμιση εργαλειοθηκών', '/toolbox', 'Διάλεξε τι περιέχει κάθε εργαλειοθήκη.'),
    'selall': ('☑', 'Επιλογή όλων', 'js:selall', 'Τσεκάρει όλα τα τετράγωνα επιλογής γραμμών της σελίδας.'),
    'selnone': ('☐', 'Καμία επιλογή', 'js:selnone', 'Αφαιρεί κάθε επιλογή γραμμών.'),
    'invert': ('⇄', 'Αντιστροφή επιλογής', 'js:invert', 'Αλλάζει τις επιλεγμένες γραμμές με τις μη επιλεγμένες.'),
    'top': ('⬆', 'Πάνω', 'js:top', 'Κύλιση στην αρχή της σελίδας.'),
    'bottom': ('⬇', 'Κάτω', 'js:bottom', 'Κύλιση στο τέλος της σελίδας.'),
    'print': ('🖨', 'Εκτύπωση', 'js:print', 'Εκτύπωση της σελίδας (Ctrl+P).'),
    'reload': ('↻', 'Ανανέωση', 'js:reload', 'Ξαναφορτώνει τη σελίδα.'),
}
DEFAULTS = {1: ('Βασικά', ['search', 'browse', 'lyseis', 'docs', 'files', 'selall', 'selnone', 'top'], 1),
            2: ('Επιλογή και εξαγωγή', ['selall', 'selnone', 'invert', 'exams', 'quizzes', 'merge', 'htmlx', 'print'], 1),
            3: ('Δική μου', [], 0)}

def boxes(c):
    have = {r['slot']: r for r in c.execute('SELECT * FROM toolbox')}
    out = []
    for s in (1, 2, 3):
        if s in have:
            r = have[s]
            try: items = [i for i in json.loads(r['items']) if i in CATALOG]
            except ValueError: items = []
            out.append({'slot': s, 'name': r['name'], 'items': items, 'enabled': bool(r['enabled'])})
        else:
            n, it, en = DEFAULTS[s]; out.append({'slot': s, 'name': n, 'items': it, 'enabled': bool(en)})
    return out

@router.get('/toolbox/api', dependencies=[Depends(auth)])
def tb_api():
    c = db(); b = boxes(c); c.close()
    return JSONResponse({'boxes': b, 'catalog': {k: {'icon': v[0], 'label': v[1], 'go': v[2], 'tip': v[3]} for k, v in CATALOG.items()}})

@router.get('/toolbox', response_class=HTMLResponse, dependencies=[Depends(auth)])
def tb_page(msg: str = ''):
    c = db(); bs = boxes(c); c.close(); out = []
    for b in bs:
        sel = b['items'] + [k for k in CATALOG if k not in b['items']]
        lis = ''.join(f"<li><input type=checkbox class=r-opt name='i{b['slot']}' value='{k}'{' checked' if k in b['items'] else ''}> <span class=t>{CATALOG[k][0]} {E(CATALOG[k][1])}</span>"
                      f"<button type=button class=up title='Μετακίνηση προς τα πάνω'>↑</button><button type=button class=dn title='Μετακίνηση προς τα κάτω'>↓</button></li>" for k in sel)
        out.append(f"<fieldset><legend>Εργαλειοθήκη {b['slot']}</legend><label class='f chk'><input type=checkbox class=r-opt name='on{b['slot']}' value=1{' checked' if b['enabled'] else ''}> εμφανίζεται στο πλωτό παράθυρο</label>"
                   + fld('Όνομα', f"<input name='n{b['slot']}' value='{E(b['name'])}' maxlength=30 size=26>") + f"<p><small>Τσέκαρε τις ενέργειες που θέλεις και βάλε τη σειρά με ↑↓ (έως 24).</small></p><ul class=reorder>{lis}</ul></fieldset>")
    body = (f"<h2>⚙ Ρύθμιση εργαλειοθηκών</h2>" + (f"<p><b>{E(msg)}</b></p>" if msg else '')
            + "<p>Η πλωτή εργαλειοθήκη 🧰 (κάτω δεξιά σε κάθε σελίδα) έχει έως <b>τρεις</b> καρτέλες. Οι ρυθμίσεις είναι κοινές για όλους όσοι συνδέονται στον server και αποθηκεύονται στη βάση (πίνακας <code>toolbox</code>).</p>"
            "<form method=post action='/toolbox/save'>" + ''.join(out) + "<p><button class=primary title='Αποθηκεύει και τις τρεις εργαλειοθήκες'>Αποθήκευση</button> <button name=reset value=1 class=danger title='Επαναφέρει τις αρχικές ρυθμίσεις και των τριών'>Επαναφορά προεπιλογών</button></p></form>")
    return page('Εργαλειοθήκες', body)

@router.post('/toolbox/save', dependencies=[Depends(auth)])
async def tb_save(request: Request):
    same_origin(request); f = await request.form(); c = db()
    if f.get('reset'):
        c.execute('DELETE FROM toolbox'); c.commit(); c.close(); return RedirectResponse('/toolbox?msg=Επαναφέρθηκαν+οι+προεπιλογές.', status_code=303)
    for s in (1, 2, 3):
        items = [i for i in f.getlist(f'i{s}') if i in CATALOG][:24]; seen = []
        for i in items:
            if i not in seen: seen.append(i)
        name = (f.get(f'n{s}') or DEFAULTS[s][0]).strip()[:30] or DEFAULTS[s][0]
        c.execute('INSERT INTO toolbox(slot,name,items,enabled) VALUES(?,?,?,?) ON CONFLICT(slot) DO UPDATE SET name=excluded.name,items=excluded.items,enabled=excluded.enabled', (s, name, json.dumps(seen), 1 if f.get(f'on{s}') else 0))
    c.commit(); c.close()
    return RedirectResponse('/toolbox?msg=Αποθηκεύτηκαν.', status_code=303)
