"""Τύπος ερώτησης και ένδειξη εικόνας/σχήματος, από το κείμενο και τις σελίδες του PDF. Οι τιμές είναι προτάσεις (origin=auto)· διορθώνονται από την οθόνη ελέγχου."""
import re, subprocess, unicodedata

TYPES = {'mcq': 'Πολλαπλής επιλογής', 'true_false': 'Σωστό/Λάθος', 'matching': 'Αντιστοίχισης', 'fill': 'Συμπλήρωσης κενών',
         'problem': 'Προβλήματος (υπολογισμοί)', 'development': 'Ανάπτυξης'}
THEME = re.compile(r'[Θθ][έΕεΈ][Μμ][Αα]\s*(\d)')

def norm(s):
    s = unicodedata.normalize('NFD', s or '').lower().replace('ς', 'σ')
    return ''.join(ch for ch in s if not unicodedata.combining(ch))

OPT = re.compile(r'^[ \t]*([αβγδ])\.[ \t]+\S', re.M)
FILL = re.compile(r'_{3,}|…{2,}|\.{6,}|συμπληρωσ|στο αντιστοιχο κενο')
PROBLEM = re.compile(r'υπολογισ|να βρειτε|να βρεθ|προσδιορισ|να σχεδιασ|δινεται|δινονται|ποια ειναι η τιμη')
FIGURE = re.compile(r'σχημα|εικον[αεη]|διαγραμμα|γραφημα|καμπυλ|παρακατω κυκλωμα|κυκλωμα του|απεικονιζ|φαινεται')

def qtype(text, theme=None):
    n = norm(text)
    if re.search(r'αντιστοιχισ|στηλη α.*στηλη β|στηλη β', n, re.S): return 'matching'
    if 'σωστ' in n and ('λαθοσ' in n or 'λανθασμεν' in n): return 'true_false'
    if FILL.search(n): return 'fill'
    if re.search(r'επιλεξτε|ορθη απαντηση|σωστη απαντηση|σωστη επιλογη', n): return 'mcq'
    if PROBLEM.search(n) or theme == '4': return 'problem'
    if len({m.group(1) for m in OPT.finditer(text or '')}) >= 3: return 'mcq'
    return 'development'

def image_pages(pdf, min_px=2500):
    """Σελίδες (0-based) με ενσωματωμένη εικόνα. Διανυσματικά σχήματα δεν ανιχνεύονται από το poppler."""
    r = subprocess.run(['pdfimages', '-list', str(pdf)], capture_output=True, text=True)
    out = set()
    for ln in r.stdout.splitlines()[2:]:
        p = ln.split()
        try:
            if int(p[3]) * int(p[4]) >= min_px: out.add(int(p[0]) - 1)
        except (IndexError, ValueError): pass
    return out

def _start_pages(qs, pages):
    cur, res = 0, []
    for q in qs:
        key = norm(' '.join((q['text'] or '').split()))[:40]
        found = None
        for i in range(cur, len(pages)):
            if key and key in norm(' '.join(pages[i].split())): found = i; break
        if found is None: found = cur
        res.append(found); cur = found
    return res

def annotate(qs, statement_text, img_pages=()):
    tm = THEME.search(statement_text); theme = tm.group(1) if tm else None
    pages = statement_text.split('\f'); starts = _start_pages(qs, pages)
    for k, q in enumerate(qs):
        q['qtype'] = qtype(q['text'], theme)
        end = starts[k + 1] if k + 1 < len(qs) else len(pages)       # τελευταίο ερώτημα: μέχρι το τέλος
        own = set(range(starts[k], max(end, starts[k] + 1) if k + 1 == len(qs) else end))
        q['has_image'] = int(bool(FIGURE.search(norm(q['text']))) or bool(own & set(img_pages)))
    return qs
