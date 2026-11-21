"""Ενότητες, σειρά, στυλ και έτοιμες διατάξεις των εξαγωγών λύσεων (Reveal.js, HTML μαθητή, Markdown/Word)."""
from .textnorm import norm

# (κλειδί, τίτλος, εικονίδιο). Η λύση εκπαιδευτικού σπάει στις υποενότητες ### του αρχείου.
UNITS = (('statement', 'Εκφώνηση', '✏️'), ('iep', 'Ενδεικτική λύση ΙΕΠ', '📘'), ('goal', 'Στόχος και προαπαιτούμενα', '🎯'), ('guide', 'Καθοδήγηση', '💡'),
         ('full', 'Πλήρης λύση', '✅'), ('errors', 'Συνήθη λάθη και έλεγχος', '⚠️'), ('ext', 'Επέκταση', '🚀'), ('quiz', 'Quiz', '❓'))
KEYS = tuple(u[0] for u in UNITS)
LABEL = {u[0]: u[1] for u in UNITS}
ICON = {u[0]: u[2] for u in UNITS}
TEACHER = ('goal', 'guide', 'full', 'errors', 'ext')
LEGACY = {'teacher': TEACHER}                       # παλιό κλειδί «λύση εκπαιδευτικού» = όλες οι υποενότητες με τη σειρά τους
PRESETS = (('class', 'Μάθημα στην τάξη', ('statement', 'goal', 'guide', 'full', 'errors', 'ext', 'quiz')),
           ('sheet', 'Φύλλο μαθητή', ('statement', 'guide', 'quiz')),
           ('solution', 'Μόνο λύση', ('statement', 'full', 'errors')),
           ('all', 'Όλα (με λύση ΙΕΠ)', KEYS))

def include_of(sx):
    """Κλειδιά ενοτήτων με τη σειρά που στάλθηκαν από τη φόρμα, χωρίς διπλά. Τίποτα έγκυρο = όλα με την προεπιλεγμένη σειρά."""
    out = []
    for x in sx or []:
        for k in LEGACY.get(x, (x,)):
            if k in KEYS and k not in out: out.append(k)
    return out or list(KEYS)

def classify(title):
    t = norm(title or '')
    for pre, key in (('στοχ', 'goal'), ('καθοδηγ', 'guide'), ('πληρη', 'full'), ('λυση', 'full'), ('συνηθη', 'errors'), ('λαθη', 'errors'), ('επεκτασ', 'ext')):
        if t.startswith(pre): return key
    return ''

def teacher_units(parts):
    """Μέρη της λύσης εκπαιδευτικού [{title, body}] -> {κλειδί: [κείμενα]}. Άγνωστος ή κενός τίτλος ανήκει στην προηγούμενη υποενότητα (πρώτη: «Στόχος»)."""
    out, prev = {}, ''
    for p in parts or []:
        k = classify(p.get('title')) or prev or 'goal'; prev = k
        out.setdefault(k, []).append(p['body'])
    return out

# ---------- στυλ ----------
UCOL = {'statement': '#2563eb', 'iep': '#64748b', 'goal': '#9333ea', 'guide': '#d97706', 'full': '#16a34a', 'errors': '#dc2626', 'ext': '#0891b2', 'quiz': '#db2777'}
UCOL_DARK = {'statement': '#7aa7ff', 'iep': '#a3b0c2', 'goal': '#c79bff', 'guide': '#fbbf4a', 'full': '#58d68d', 'errors': '#ff8a8a', 'ext': '#5ed3ec', 'quiz': '#ff8fc4'}
FONT = "system-ui,'Segoe UI',Roboto,'Noto Sans',Arial,sans-serif"
STYLES = {
    'kids': dict(label='Μαθητικό πολύχρωμο', base='white', bg='#fff7e0', fg='#1f2937', card='#ffffff', head='#1e3a8a', accent='#2563eb', cols=UCOL, icons=True, rad='18px', tint=.14, ok='#15803d', bad='#b91c1c', size=1.06,
                 doc={1: '1E3A8A', 2: '7C3AED', 3: 'EA580C', 4: '0F766E'}),
    'calm': dict(label='Ήρεμο φωτεινό', base='white', bg='#f4f6f9', fg='#243040', card='#ffffff', head='#2b4a6f', accent='#3b6ea5', cols={k: '#3b6ea5' for k in KEYS}, icons=False, rad='10px', tint=.08, ok='#15803d', bad='#b91c1c', size=1.0,
                 doc={1: '2B4A6F', 2: '3B6EA5', 3: '3B6EA5', 4: '5A7A9A'}),
    'dark': dict(label='Σκοτεινό', base='black', bg='#12161d', fg='#e6e9ef', card='#1b212b', head='#9fc4ff', accent='#6ea8ff', cols=UCOL_DARK, icons=True, rad='14px', tint=.14, ok='#58d68d', bad='#ff8a8a', size=1.0,
                 doc={1: '2B4A6F', 2: '3B6EA5', 3: '3B6EA5', 4: '5A7A9A'}),
    'print': dict(label='Εκτύπωση ασπρόμαυρο', base='white', bg='#ffffff', fg='#000000', card='#ffffff', head='#000000', accent='#000000', cols={k: '#000000' for k in KEYS}, icons=False, rad='4px', tint=0, ok='#000000', bad='#000000', size=1.0,
                  doc={1: '000000', 2: '000000', 3: '000000', 4: '000000'}),
}

def style_of(name, default='calm'):
    """Αποδέχεται και τις παλιές τιμές θέματος Reveal (white/black)."""
    n = {'white': 'calm', 'black': 'dark'}.get(name or '', name or '')
    return n if n in STYLES else default

def mix(a, b, t):
    """Χρώμα a σε ποσοστό t πάνω στο b (#rrggbb)."""
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]; pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{round(x * t + y * (1 - t)):02x}' for x, y in zip(pa, pb))

def vars_css(style):
    """:root και χρώματα ανά ενότητα (.u-<κλειδί>{--u,--ut}). Κοινά για Reveal και HTML μαθητή."""
    s = STYLES[style]
    root = f":root{{--bg:{s['bg']};--fg:{s['fg']};--card:{s['card']};--head:{s['head']};--accent:{s['accent']};--rad:{s['rad']};--ok:{s['ok']};--bad:{s['bad']};--font:{FONT}}}"
    units = ''.join(f".u-{k}{{--u:{s['cols'][k]};--ut:{mix(s['cols'][k], s['card'], s['tint'])}}}" for k in KEYS)
    return root + units

def reveal_css(style):
    s = STYLES[style]
    return (f"{vars_css(style)}.reveal{{font-size:{round(26 * s['size'])}px}}"
            f":root{{--r-background-color:{s['bg']};--r-main-color:{s['fg']};--r-heading-color:{s['head']};--r-link-color:{s['accent']};--r-main-font:{FONT};--r-heading-font:{FONT};--r-main-font-size:{round(26 * s['size'])}px;--r-heading-text-transform:none}}"
            "body,.reveal-viewport{background:var(--bg)}"
            ".reveal .slides section:not(.stack){height:100%;overflow-y:auto;text-align:left;box-sizing:border-box;padding:.3em .6em}.reveal h1{font-size:1.9em}.reveal h2{font-size:1.2em;margin:0}.reveal h3{font-size:1.05em}"
            ".reveal .u{background:var(--ut,transparent)}.reveal .hd{display:flex;align-items:center;gap:.5em;border-bottom:4px solid var(--u,var(--accent));padding-bottom:.25em;margin-bottom:.5em}"
            ".reveal .hd h2{flex:1;color:var(--u,var(--head))}.reveal .hd .who{font-size:.6em;opacity:.75}.reveal .badge{display:inline-flex;align-items:center;justify-content:center;width:1.7em;height:1.7em;border-radius:50%;background:var(--card);font-size:.95em;box-shadow:0 0 0 2px var(--u)}"
            ".reveal img{max-height:420px;background:#fff}.reveal table{font-size:.8em;margin:.4em 0}.reveal td,.reveal th{border:1px solid currentColor;padding:.2em .5em}.reveal .ans{color:var(--ok)}.reveal small{font-size:.65em;opacity:.8}"
            ".reveal ul,.reveal ol{display:block;margin-left:1.2em}.reveal p{margin:.4em 0}.reveal pre{font-size:.6em;width:100%}.reveal .noimg{opacity:.6}.reveal .toc{font-size:.7em;columns:2}"
            f".reveal .u-title h1{{color:var(--accent)}}.reveal .toc li{{margin:.15em 0}}"
            + (".reveal .u{border-radius:var(--rad);padding:.5em .9em!important}" if s['tint'] else ''))
