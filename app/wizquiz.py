"""0.24: εξαγωγές quiz από τον wizard: Moodle XML (κατηγορίες, ετικέτες), script Google Form (Apps Script) και δεδομένα H5P (Question Set JSON).
Πηγή: τα μπλοκ quiz των λύσεων εκπαιδευτικού. Δεν δοκιμάστηκαν σε πραγματικό Moodle, Google Forms ή H5P."""
import html, io, json, pathlib, re, zipfile
from . import config, solexport as X, settings
from .mdmath import protect, restore, math_to_text
from .exams import crop_bytes

M_CATS = (('single', 'Μία κατηγορία (ο τίτλος)'), ('item', 'Υποκατηγορία ανά θέμα ΙΕΠ'), ('qtype', 'Υποκατηγορία ανά τύπο στοιχείου'))
G_NAMES = (('required', 'Ονοματεπώνυμο υποχρεωτικό'), ('optional', 'Ονοματεπώνυμο προαιρετικό'), ('none', 'Χωρίς πεδίο ονόματος'))
G_IMGS = (('default', 'Όπως στις Ρυθμίσεις'), ('text', 'Τύποι ως κείμενο Unicode, εικόνες από φάκελο Drive'), ('images', 'Όλα τα ερωτήματα ως εικόνες (εικόνα ΙΕΠ ανά ερώτημα)'))
QFORMATS = ('moodle', 'gform', 'h5p')


def plain(s):
    """Κείμενο Markdown με τύπους LaTeX -> απλό κείμενο Unicode (για Google Form και H5P)."""
    p, maths = protect(s or ''); return restore(p, maths, math_to_text).strip()


def gather(c, es):
    """-> (rows με λύση σε σειρά εμφάνισης, ερωτήματα χωρίς λύση ή χωρίς έγκυρα στοιχεία quiz)."""
    keys = [(e['item'], e['code']) for e in es if e['vis'] in ('show', 'append')]
    rows = X.load(c, keys); have = {(r['item_id'], r['qcode']) for r in rows}; bad = [f'{i}/{q}' for i, q in keys if (i, q) not in have]
    good = []
    for r in rows:
        if [q for q in r['quiz'] if not q['err']]: good.append(r)
        else: bad.append(f"{r['item_id']}/{r['qcode']}")
    return good, bad


def qitems(rows):
    for r in rows:
        for q in r['quiz']:
            if not q['err']: yield r, q


def img_mode(st):
    v = st.get('g_img', 'default'); return v if v in ('text', 'images') else settings.get('gform_images')


# ---------- Moodle ----------
def moodle(c, st, es):
    rows, bad = gather(c, es)
    if not rows: return None
    xml, skipped, n = X.moodle_xml(rows, st['title'], config.load()['data_root'], st.get('m_cat', 'single'), bool(st.get('m_tags', True)))
    return (xml.encode('utf-8'), f"{slug(st['title'])}.xml", 'application/xml; charset=utf-8') if n else None


def slug(s): return re.sub(r'[^\w-]+', '_', s, flags=re.U).strip('_')[:50] or 'quiz'


# ---------- Google Form (Apps Script) ----------
def js(s): return json.dumps(s, ensure_ascii=False)


def gform(c, st, es):
    """-> (zip bytes, όνομα) ή None. Περιέχει create_form.gs, images/ και README.txt."""
    rows, bad = gather(c, es)
    if not rows: return None
    root = pathlib.Path(config.load()['data_root']); mode = img_mode(st); files = {}; manual = []; lines = []; n = 0
    def add_image(name, data): files['images/' + name] = data
    for r in rows:
        if mode == 'images':
            qid = c.execute('SELECT id FROM question WHERE item_id=? AND code=?', (r['item_id'], r['qcode'])).fetchone()
            got = crop_bytes(c, qid[0], 0, 130) if qid else None
            if got: nm = f"q{r['item_id']}_{r['qcode']}.jpg"; add_image(nm, got[0]); lines.append(f"  addImage_(form, {js(nm)}, {js('Ερώτημα ' + r['qcode'])});")
        for q in r['quiz']:
            if q['err']: continue
            n += 1; t = q['type']; label = f"{r['item_id']}/{r['qcode']}#{q['n']}"; pts = q.get('points', 1)
            title = plain(q['stem']) if mode != 'images' else f"Ερώτημα {r['qcode']} — στοιχείο {q['n']}"
            if mode != 'images' and t == 'fill': title = re.sub(r'_{3,}', '______', title)
            if q.get('image'):
                src = root / r['base'] / q['image']
                try:
                    if src.resolve().is_relative_to(root.resolve()) and src.is_file():
                        nm = f"{r['item_id']}_{r['qcode']}_{src.name}"; add_image(nm, src.read_bytes()); lines.append(f"  addImage_(form, {js(nm)}, 'Σχήμα');")
                except OSError: pass
            fb = plain(q.get('feedback', ''))
            if t in ('mcq', 'true_false'):
                opts = q['options'] if t == 'mcq' else ['Σωστό', 'Λάθος']; ok = q['answer'] if t == 'mcq' else (0 if q['answer'] else 1)
                lines.append(f"  mcq_(form, {js(title)}, {js([plain(o) for o in opts])}, {ok}, {pts:g}, {js(fb)});")
            elif t == 'matching':
                rights = [plain(b) for _, b in q['pairs']]
                for a, b in q['pairs']:
                    lines.append(f"  mcq_(form, {js(title + ' → ' + plain(a))}, {js(rights)}, {rights.index(plain(b))}, {pts / len(q['pairs']):g}, {js(fb)});")
            else:
                ans = q['answer'] if isinstance(q['answer'], list) else [q['answer']]
                lines.append(f"  text_(form, {js(title)}, {pts:g}, {'true' if t == 'numeric' else 'false'}, {js(fb)});")
                manual.append(f"{label} ({'αριθμός' if t == 'numeric' else 'κείμενο'}, {pts:g} μον.): " + ' | '.join(str(a) + (f" {q.get('unit')}" if t == 'numeric' and q.get('unit') else '') for a in ans) + (f"  (ανοχή ±{q['tolerance']:g})" if t == 'numeric' and q.get('tolerance') else ''))
    name_line = {'required': "  form.addTextItem().setTitle('Ονοματεπώνυμο').setRequired(true);", 'optional': "  form.addTextItem().setTitle('Ονοματεπώνυμο').setRequired(false);", 'none': ''}[st.get('g_name', 'required')]
    gs = f"""// TH-ILEK: δημιουργία Google Form (quiz). Δεν δοκιμάστηκε σε πραγματικό Google Forms.
// Οδηγίες: script.google.com → Νέο έργο → επικόλληση → Αποθήκευση → Εκτέλεση της createForm → Έγκριση αδειών. Το σύνδεσμο της φόρμας δείχνει το Ιστορικό εκτέλεσης (Logger).
var TITLE = {js(st['title'] or 'Quiz')};
var IMAGE_FOLDER_ID = '';   // ΣΥΜΠΛΗΡΩΣΕ: το ID του φακέλου Drive όπου ανέβασες τα αρχεία του φακέλου images/ (αν υπάρχουν εικόνες)

function createForm() {{
  var form = FormApp.create(TITLE);
  form.setIsQuiz(true);
  form.setShuffleQuestions(false);
{name_line}
{chr(10).join(lines)}
  Logger.log('Επεξεργασία: ' + form.getEditUrl());
  Logger.log('Για τους μαθητές: ' + form.getPublishedUrl());
  Logger.log('Στοιχεία με απαντήσεις που βάζεις ΧΕΙΡΟΚΙΝΗΤΑ (Απαντήσεις → κλειδί): δες το README.txt');
}}

function mcq_(form, title, choices, correct, points, feedback) {{
  var it = form.addMultipleChoiceItem();
  it.setTitle(title).setPoints(points).setRequired(false);
  it.setChoices(choices.map(function (c, i) {{ return it.createChoice(c, i === correct); }}));
  if (feedback) it.setFeedbackForCorrect(FormApp.createFeedback().setText(feedback).build()).setFeedbackForIncorrect(FormApp.createFeedback().setText(feedback).build());
}}

function text_(form, title, points, isNumber, feedback) {{
  var it = form.addTextItem();
  it.setTitle(title).setPoints(points).setRequired(false);
  if (isNumber) it.setValidation(FormApp.createTextValidation().requireNumber().build());
  if (feedback) it.setFeedbackForCorrect(FormApp.createFeedback().setText(feedback).build());
}}

function addImage_(form, name, title) {{
  if (!IMAGE_FOLDER_ID) {{ Logger.log('Παραλείφθηκε η εικόνα ' + name + ' (δεν ορίστηκε IMAGE_FOLDER_ID)'); return; }}
  var files = DriveApp.getFolderById(IMAGE_FOLDER_ID).getFilesByName(name);
  if (!files.hasNext()) {{ Logger.log('Λείπει η εικόνα στον φάκελο: ' + name); return; }}
  form.addImageItem().setImage(files.next().getBlob()).setTitle(title);
}}
"""
    readme = ("Google Form από το TH-ILEK\n===========================\n\n1. Άνοιξε https://script.google.com → Νέο έργο, σβήσε ό,τι υπάρχει, επικόλλησε όλο το create_form.gs και αποθήκευσε.\n"
              + ("2. Ανέβασε τα αρχεία του φακέλου images/ σε έναν φάκελο του Google Drive, αντίγραψε το ID του (το τελευταίο κομμάτι του συνδέσμου του φακέλου) και βάλ' το στη γραμμή IMAGE_FOLDER_ID του script.\n" if any(k.startswith('images/') for k in files) else "2. Δεν υπάρχουν εικόνες· τίποτα να ανεβάσεις.\n")
              + "3. Επίλεξε τη συνάρτηση createForm και πάτα Εκτέλεση. Την πρώτη φορά ζητά άδειες (Forms και Drive).\n4. Άνοιξε το Ιστορικό εκτέλεσης: εκεί είναι ο σύνδεσμος επεξεργασίας και ο σύνδεσμος για τους μαθητές.\n\n"
              "Όρια: το Apps Script δεν μπορεί να ορίσει σωστή απάντηση σε ερωτήσεις κειμένου/αριθμού. Αυτές φτιάχνονται με μονάδες αλλά θέλουν να βάλεις εσύ το κλειδί (Φόρμα → Ερώτηση → Απαντήσεις):\n"
              + ('\n'.join('  - ' + m for m in manual) if manual else '  (καμία)') + '\n'
              + (f"\nΔεν περιλαμβάνονται (χωρίς έγκυρα στοιχεία quiz): {', '.join(bad)}\n" if bad else '')
              + "\nΟι τύποι έχουν γίνει κείμενο Unicode (π.χ. U² / R)· ελέγξε τους. Μην ανεβάσεις το script ή τις απαντήσεις σε μαθητές.\n")
    files['create_form.gs'] = gs.encode('utf-8'); files['README.txt'] = readme.encode('utf-8')
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        for k, v in files.items(): z.writestr(k, v)
    return b.getvalue(), f"{slug(st['title'])}_gform.zip", n


# ---------- H5P ----------
def hp(s): return '<p>' + html.escape(plain(s)).replace('\n', '<br>') + '</p>'


def h5p(c, st, es):
    """-> (zip bytes, όνομα, πλήθος) ή None. Περιέχει content.json (Question Set), h5p.json (δείγμα) και README.txt με τις οδηγίες εισαγωγής."""
    rows, bad = gather(c, es)
    if not rows: return None
    qs = []; imgs = []; files = {}; root = pathlib.Path(config.load()['data_root'])
    meta = lambda ct, t: {'contentType': ct, 'license': 'U', 'title': (t or ct)[:60]}
    for r, q in qitems(rows):
        t = q['type']; title = f"{r['item_id']}/{r['qcode']}#{q['n']}"; fb = html.escape(plain(q.get('feedback', '')))
        if q.get('image'):
            src = root / r['base'] / q['image']
            try:
                if src.resolve().is_relative_to(root.resolve()) and src.is_file(): nm = f"{r['item_id']}_{r['qcode']}_{src.name}"; files['images/' + nm] = src.read_bytes(); imgs.append(f"{title}: {nm}")
            except OSError: pass
        beh = {'enableRetry': True, 'enableSolutionsButton': True, 'singleAnswer': True}
        def mc(question, opts, ok):
            return {'library': 'H5P.MultiChoice 1.16', 'params': {'question': hp(question), 'answers': [{'text': '<div>' + html.escape(plain(o)) + '</div>', 'correct': i == ok, 'tipsAndFeedback': {'tip': '', 'chosenFeedback': '', 'notChosenFeedback': ''}} for i, o in enumerate(opts)], 'behaviour': beh, 'overallFeedback': [{'from': 0, 'to': 100, 'feedback': fb}] if fb else []}, 'metadata': meta('Multiple Choice', title)}
        if t == 'mcq': qs.append(mc(q['stem'], q['options'], q['answer']))
        elif t == 'true_false': qs.append({'library': 'H5P.TrueFalse 1.8', 'params': {'question': hp(q['stem']), 'correct': 'true' if q['answer'] else 'false', 'behaviour': {'enableRetry': True, 'enableSolutionsButton': True}}, 'metadata': meta('True/False Question', title)})
        elif t == 'matching':
            rights = [b for _, b in q['pairs']]
            for k, (a, b) in enumerate(q['pairs']): qs.append(mc(q['stem'] + ' → ' + a, rights, k))
        else:
            ans = q['answer'] if isinstance(q['answer'], list) else [q['answer']]
            if t == 'fill' and '___' in q['stem']:
                parts = re.split(r'_{3,}', q['stem']); blanks = len(parts) - 1; text = html.escape(plain(parts[0]))
                for k, p in enumerate(parts[1:]):
                    alts = [ans[k]] if blanks > 1 and len(ans) == blanks else ans
                    text += '*' + '/'.join(html.escape(plain(str(a))).replace('/', '') for a in alts) + '*' + html.escape(plain(p))
            else:
                alts = [f"{a:g}" if isinstance(a, float) else str(a) for a in ans]
                text = html.escape(plain(q['stem'])) + ' *' + '/'.join(html.escape(a).replace('/', '') for a in alts) + '*' + (f" {html.escape(q.get('unit') or '')}" if t == 'numeric' else '')
            qs.append({'library': 'H5P.Blanks 1.14', 'params': {'text': '<p>' + html.escape(title) + '</p>', 'questions': ['<p>' + text + '</p>'], 'behaviour': {'caseSensitive': False, 'enableRetry': True, 'enableSolutionsButton': True, 'autoCheck': False}}, 'metadata': meta('Fill in the Blanks', title)})
    if not qs: return None
    content = {'introPage': {'showIntroPage': False}, 'progressType': 'textual', 'passPercentage': 50, 'questions': qs, 'disableBackwardsNavigation': False, 'randomQuestions': False, 'endGame': {'showResultPage': True}}
    h5pjson = {'title': st['title'] or 'Quiz', 'language': 'el', 'mainLibrary': 'H5P.QuestionSet', 'embedTypes': ['div'], 'license': 'U',
               'preloadedDependencies': [{'machineName': 'H5P.QuestionSet', 'majorVersion': 1, 'minorVersion': 20}, {'machineName': 'H5P.MultiChoice', 'majorVersion': 1, 'minorVersion': 16}, {'machineName': 'H5P.TrueFalse', 'majorVersion': 1, 'minorVersion': 8}, {'machineName': 'H5P.Blanks', 'majorVersion': 1, 'minorVersion': 14}]}
    readme = ("H5P Question Set από το TH-ILEK\n==============================\n\nΤο ΔΕΝ είναι έτοιμο αρχείο .h5p· είναι τα δεδομένα (content.json). Δεν έχει δοκιμαστεί σε πραγματικό H5P/Moodle.\n\n"
              "Πώς το χρησιμοποιείς:\n 1. Στο Moodle (ή σε H5P.com/Lumi) φτιάξε ένα Question Set, αποθήκευσέ το και εξήγαγέ το ως .h5p (Λήψη).\n 2. Άνοιξε αυτό το .h5p ως zip (μετονόμασέ το σε .zip).\n"
              " 3. Αντικατάστησε το content/content.json με το content.json αυτού του φακέλου. Αν οι εκδόσεις βιβλιοθηκών στο δικό σου h5p.json διαφέρουν από τις δικές μας (QuestionSet 1.20, MultiChoice 1.16, TrueFalse 1.8, Blanks 1.14), άλλαξε τις εδώ ώστε να ταιριάζουν· το h5p.json του δείγματος είναι μόνο παράδειγμα.\n"
              " 4. Φτιάξε ξανά το zip (το content.json στον φάκελο content/), μετονόμασέ το σε .h5p και ανέβασέ το.\n 5. Ή άλλαξε ένα-ένα τις ερωτήσεις στον editor του H5P χρησιμοποιώντας το content.json ως πηγή.\n\n"
              "Τύποι: Σωστό/Λάθος και Πολλαπλής → H5P.TrueFalse / H5P.MultiChoice· σύντομη, αριθμητική και συμπλήρωση → H5P.Blanks (κενό *απάντηση/εναλλακτική*)· αντιστοίχιση → μία ερώτηση πολλαπλής ανά ζεύγος. Οι τύποι έγιναν κείμενο Unicode.\n"
              + ("Εικόνες που ανήκουν σε στοιχεία (πρόσθεσέ τες χειροκίνητα στον editor):\n" + '\n'.join('  - ' + i for i in imgs) + '\n' if imgs else '')
              + (f"Δεν περιλαμβάνονται (χωρίς έγκυρα στοιχεία quiz): {', '.join(bad)}\n" if bad else ''))
    files['content.json'] = json.dumps(content, ensure_ascii=False, indent=1).encode('utf-8'); files['h5p.json'] = json.dumps(h5pjson, ensure_ascii=False, indent=1).encode('utf-8'); files['README.txt'] = readme.encode('utf-8')
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        for k, v in files.items(): z.writestr(k, v)
    return b.getvalue(), f"{slug(st['title'])}_h5p.zip", len(qs)
