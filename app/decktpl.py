"""0.32: πρότυπα διαφανειών, συνταγές και ασφαλής φόρτωση επιλογών των παρουσιάσεων (deck). Καθαρός κώδικας, χωρίς FastAPI και χωρίς βάση.
Τα ενσωματωμένα πρότυπα/συνταγές ζουν εδώ (όχι σε πίνακα): έχουν έκδοση, δοκιμάζονται και δεν μεταφέρονται στο rebuild."""
import json, re

# (κλειδί, ετικέτα, τίτλος-σκελετός, σώμα-σκελετός)
LAYOUTS = (
    ('title', 'Τίτλος παρουσίασης', 'Τίτλος παρουσίασης', 'Υπότιτλος — Τμήμα — Ημερομηνία'),
    ('section', 'Νέα ενότητα', 'Κεφάλαιο 4: Εναλλασσόμενο ρεύμα', ''),
    ('content', 'Κείμενο', 'Τίτλος', 'Κείμενο με **έμφαση** και τύπο $U=I\\cdot R$.'),
    ('bullets', 'Βασικά σημεία (ένα-ένα)', 'Βασικά σημεία', '- πρώτο\n- δεύτερο\n- τρίτο'),
    ('two-col', 'Δύο στήλες', 'Σύγκριση', '::: cols\n**Σειρά**\n- ίδιο I\n|||\n**Παράλληλα**\n- ίδια U\n:::'),
    ('image', 'Εικόνα', 'Σχήμα', '![Κύκλωμα RLC](/files/ΜΑΘΗΜΑ/04_TRAPEZA/orig/images/rlc.png)\n\nΛεζάντα'),
    ('math', 'Τύπος', 'Νόμος του Ohm', '$$I=\\dfrac{U}{R}$$\n\n- $I$ σε A, $U$ σε V, $R$ σε Ω'),
    ('statement', 'Εκφώνηση ερωτήματος', 'Θέμα 17698 · 2.1', 'Εκφώνηση του ερωτήματος.'),
    ('solution-step', 'Βήμα λύσης', 'Λύση (1/3)', 'Ένα βήμα της λύσης με τύπους $..$.'),
    ('quiz', 'Quiz', 'Quiz 1', '::: quiz\ntype: mcq\nstem: Η μονάδα της αντίστασης είναι\noptions: [V, A, Ω]\nanswer: 2\n:::'),
    ('code', 'Κώδικας', 'Πρόγραμμα', '```python\nprint(U / R)\n```'),
    ('summary', 'Ανακεφαλαίωση', 'Ανακεφαλαίωση', '1. πρώτο συμπέρασμα\n2. δεύτερο συμπέρασμα'),
    ('blank', 'Κενή', '', ''),
    ('embed', 'Ενσωμάτωση', 'Προσομοίωση', '::: embed https://www.falstad.com/circuit/circuitjs.html\nΚύκλωμα RC\n:::'),
)
LAYOUT_KEYS = tuple(l[0] for l in LAYOUTS)
LAYOUT_LABEL = {l[0]: l[1] for l in LAYOUTS}
NO_HEADER = ('title', 'section', 'blank')              # χωρίς γραμμή τίτλου διαφάνειας (έχουν δικό τους h1 ή τίποτα)
LAYOUT_UNIT = {'statement': 'statement', 'solution-step': 'full', 'quiz': 'quiz'}      # χρώμα ενότητας (solstyle) ανά διάταξη
BULLET_LAYOUTS = ('bullets',)                          # frag=1 από προεπιλογή στο σκελετό

# (κλειδί, ετικέτα, χρειάζεται πηγή: '' | 'questions' | 'exam', περιγραφή)
RECIPES = (
    ('free', 'Ελεύθερη παρουσίαση', '', 'Διαφάνεια τίτλου και μία κενή διαφάνεια κειμένου.'),
    ('lesson', 'Μάθημα θεωρίας', '', 'Σκελετός: τίτλος, στόχοι, κείμενο, δύο στήλες, τύπος, ανακεφαλαίωση, quiz.'),
    ('solutions', 'Λύση ασκήσεων', 'questions', 'Ανά ερώτημα: ενότητα, εκφώνηση και τα βήματα της λύσης εκπαιδευτικού (κάθετη στοίβα), quiz.'),
    ('review', 'Επανάληψη κεφαλαίου', 'questions', 'Ανά υποενότητα βιβλίου: ενότητα, σημεία προς συμπλήρωση, εκφωνήσεις ερωτημάτων, quiz, ανακεφαλαίωση.'),
    ('quiz', 'Quiz', 'questions', 'Μία διαφάνεια ανά στοιχείο quiz των λύσεων, με απάντηση ένα-ένα ή συγκεντρωμένη στο τέλος.'),
    ('exam', 'Διόρθωση διαγωνίσματος', 'exam', 'Από ένα διαγώνισμα του /exams: ΘΕΜΑ Α, Β… με εκφώνηση και λύση ανά ερώτημα.'),
)
RECIPE_KEYS = tuple(r[0] for r in RECIPES)
RECIPE_LABEL = {r[0]: r[1] for r in RECIPES}
RECIPE_NEEDS = {r[0]: r[2] for r in RECIPES}

TRANSITIONS = ('none', 'fade', 'slide', 'convex', 'concave', 'zoom')
RATIOS = {'16:9': (1280, 720), '16:10': (1280, 800), '4:3': (1024, 768)}
ANSWERS = (('inline', 'Η απάντηση εμφανίζεται με το επόμενο βήμα, στην ίδια διαφάνεια'), ('end', 'Οι απαντήσεις μαζεύονται σε διαφάνεια στο τέλος'))
STORES = (('download', 'λήψη'), ('server', 'αποθήκευση στον server (07_EXAGOGES/decks)'), ('publish', 'δημοσίευση για μαθητές'))
SLIDE_CLASSES = ('', 'small', 'center', 'dim')         # επιτρεπτά επιπλέον CSS classes ανά διαφάνεια

LIMITS = dict(body=50_000, notes=20_000, title=200, slides=300, name=120)

DEFAULT_OPTS = {'frag': False, 'transition': 'slide', 'ratio': '16:10', 'numbers': True, 'title_slide': False, 'toc': False, 'answers': 'inline',
                'pdf_notes': False, 'pptx_frag': False, 'helpmd': True, 'store': 'download'}
DEFAULT_SLIDE_OPTS = {'frag': None, 'bg': {}, 'transition': '', 'cls': '', 'base': '', 'ans': None}

RE_COLOR = re.compile(r'^#[0-9a-fA-F]{3,8}$')
RE_BASE = re.compile(r'^[A-Za-z0-9_./-]{0,200}$')
RE_BGIMG = re.compile(r'^/files/[A-Za-z0-9_./-]+\.(?:png|jpe?g)$', re.I)


def _json(raw):
    try:
        d = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def load_opts(raw, deck=True):
    """Ανθεκτική φόρτωση JSON επιλογών: άγνωστα/λάθος κλειδιά ή τιμές αγνοούνται και παίρνουν την προεπιλογή. Χρώμα με regex, εικόνα φόντου μόνο /files/…png|jpg."""
    d = _json(raw); out = json.loads(json.dumps(DEFAULT_OPTS if deck else DEFAULT_SLIDE_OPTS))
    if deck:
        for k in ('frag', 'numbers', 'title_slide', 'toc', 'pdf_notes', 'pptx_frag', 'helpmd'):
            if isinstance(d.get(k), bool): out[k] = d[k]
        if d.get('transition') in TRANSITIONS: out['transition'] = d['transition']
        if d.get('ratio') in RATIOS: out['ratio'] = d['ratio']
        if d.get('answers') in dict(ANSWERS): out['answers'] = d['answers']
        if d.get('store') in dict(STORES): out['store'] = d['store']
        return out
    if isinstance(d.get('frag'), bool): out['frag'] = d['frag']
    if isinstance(d.get('ans'), bool): out['ans'] = d['ans']
    if d.get('transition') in TRANSITIONS: out['transition'] = d['transition']
    if d.get('cls') in SLIDE_CLASSES: out['cls'] = d['cls']
    if isinstance(d.get('base'), str) and RE_BASE.match(d['base']) and '..' not in d['base']: out['base'] = d['base'].strip('/')
    bg = d.get('bg') if isinstance(d.get('bg'), dict) else {}
    if isinstance(bg.get('color'), str) and RE_COLOR.match(bg['color']): out['bg']['color'] = bg['color']
    if isinstance(bg.get('image'), str) and RE_BGIMG.match(bg['image']) and '..' not in bg['image']: out['bg']['image'] = bg['image']
    return out


def dump_opts(opts, deck=True):
    return json.dumps(load_opts(opts, deck), ensure_ascii=False)


def skeleton(layout):
    """(τίτλος, σώμα, opts) του σκελετού μιας διάταξης. Άγνωστη διάταξη = κενή διαφάνεια κειμένου."""
    for k, _, t, b in LAYOUTS:
        if k == layout: return t, b, ({'frag': True} if k in BULLET_LAYOUTS else {})
    return 'Τίτλος', '', {}


def layout_ok(layout): return layout if layout in LAYOUT_KEYS else 'content'
