"""0.23: διαγώνισμα/τεστ σε Word με πρότυπο σχολείου.
Το πρότυπο είναι ένα απλό .docx με πεδία {{ΤΙΤΛΟΣ}}, {{ΣΧΟΛΕΙΟ}}… και ένα σημείο {{ΕΡΩΤΗΜΑΤΑ}} (δική του παράγραφος) όπου μπαίνουν τα ερωτήματα.
Δεν υπάρχει πρότυπο στον φάκελο; Χρησιμοποιείται το ενσωματωμένο."""
import io, pathlib, re, zipfile
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, Inches
from . import config, mdgen, mddoc
from .exams import LETTERS
from .mdgen import q_block
from . import wizmodel as M

DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
MARK = '{{ΕΡΩΤΗΜΑΤΑ}}'
FIELDS = (('ΤΙΤΛΟΣ', 'Τίτλος'), ('ΥΠΟΤΙΤΛΟΣ', 'Υπότιτλος'), ('ΣΧΟΛΕΙΟ', 'Σχολείο'), ('ΜΑΘΗΜΑ', 'Μάθημα'), ('ΤΑΞΗ', 'Τάξη/τμήμα'), ('ΗΜΕΡΟΜΗΝΙΑ', 'Ημερομηνία'),
          ('ΔΙΑΡΚΕΙΑ', 'Διάρκεια'), ('ΟΔΗΓΙΕΣ', 'Οδηγίες'), ('ΜΟΝΑΔΕΣ', 'Σύνολο μονάδων'), ('ΕΚΔΟΣΗ', 'Έκδοση (μαθητή/καθηγητή)'))
GROUPS = (('item', 'ΘΕΜΑ Α, Β, Γ… = ένα ανά θέμα ΙΕΠ'), ('qtype', 'ΘΕΜΑ Α, Β, Γ… = ανά τύπο ερωτήματος'), ('none', 'Χωρίς ΘΕΜΑΤΑ (απλή αρίθμηση 1, 2, 3…)'))
VERSIONS = (('student', 'Μαθητή'), ('teacher', 'Καθηγητή (με λύσεις ΙΕΠ)'), ('both', 'Και οι δύο (zip)'))
EXKEYS = ('x_school', 'x_class', 'x_date', 'x_dur', 'x_sub', 'x_notes', 'x_course')
MAX_TPL = 5 * 1024 * 1024


def tpl_dir(root=None): return pathlib.Path(root or config.load()['data_root']) / '_templates' / 'exam'


def tpl_name_ok(n): return bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,60}\.docx', n)) and '..' not in n


def list_templates():
    d = tpl_dir(); return sorted(p.name for p in d.iterdir() if p.is_file() and tpl_name_ok(p.name)) if d.is_dir() else []


def default_template():
    """Ενσωματωμένο πρότυπο: επικεφαλίδα σχολείου, τίτλος, πίνακας στοιχείων, οδηγίες, ονοματεπώνυμο, σημείο ερωτημάτων."""
    doc = Document()
    for s in doc.sections: s.left_margin = s.right_margin = Inches(0.9); s.top_margin = s.bottom_margin = Inches(0.8)
    n = doc.styles['Normal']; n.font.name = 'Calibri'; n.font.size = Pt(11)
    p = doc.add_paragraph('{{ΣΧΟΛΕΙΟ}}'); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph('{{ΤΙΤΛΟΣ}}'); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.runs[0].bold = True; p.runs[0].font.size = Pt(16)
    p = doc.add_paragraph('{{ΥΠΟΤΙΤΛΟΣ}}'); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t = doc.add_table(rows=2, cols=4); t.style = 'Table Grid'
    for i, (a, b) in enumerate((('Μάθημα: {{ΜΑΘΗΜΑ}}', 'Τάξη: {{ΤΑΞΗ}}'), ('Ημερομηνία: {{ΗΜΕΡΟΜΗΝΙΑ}}', 'Διάρκεια: {{ΔΙΑΡΚΕΙΑ}}'))):
        t.cell(i, 0).merge(t.cell(i, 1)).text = a; t.cell(i, 2).merge(t.cell(i, 3)).text = b
    doc.add_paragraph('Ονοματεπώνυμο: ______________________________   Σύνολο μονάδων: {{ΜΟΝΑΔΕΣ}}   Βαθμός: ________')
    doc.add_paragraph('{{ΟΔΗΓΙΕΣ}}')
    doc.add_paragraph(MARK)
    sec = doc.sections[0]; sec.footer.paragraphs[0].text = '{{ΣΧΟΛΕΙΟ}} · {{ΤΙΤΛΟΣ}} · {{ΕΚΔΟΣΗ}}'
    b = io.BytesIO(); doc.save(b); return b.getvalue()


def load_template(name):
    if not name or name == 'default': return Document(io.BytesIO(default_template()))
    if not tpl_name_ok(name): raise ValueError('Άκυρο όνομα προτύπου.')
    p = tpl_dir() / name
    if not p.is_file() or p.is_symlink(): raise ValueError(f'Το πρότυπο «{name}» δεν βρέθηκε στον φάκελο προτύπων.')
    return Document(str(p))


def check_template(data):
    """Έλεγχος ανεβασμένου προτύπου -> (ok, μήνυμα, πεδία που βρέθηκαν, υπάρχει σημείο ερωτημάτων)."""
    if len(data) > MAX_TPL: return False, 'Το αρχείο είναι πολύ μεγάλο (όριο 5 MB).', [], False
    try: doc = Document(io.BytesIO(data))
    except Exception: return False, 'Δεν είναι έγκυρο αρχείο Word (.docx). Αν είναι .dotx ή .doc, άνοιξέ το στο Word και αποθήκευσε ως «Έγγραφο Word (*.docx)».', [], False
    txt = '\n'.join(all_text(doc)); found = [k for k, _ in FIELDS if '{{' + k + '}}' in txt]
    return True, '', found, MARK in txt


def paragraphs(doc):
    """Όλες οι παράγραφοι: σώμα, πίνακες (και ένθετοι), κεφαλίδες/υποσέλιδα."""
    def in_tables(tables):
        for t in tables:
            for row in t.rows:
                for cell in row.cells:
                    yield from cell.paragraphs; yield from in_tables(cell.tables)
    yield from doc.paragraphs; yield from in_tables(doc.tables)
    for s in doc.sections:
        for part in (s.header, s.footer, s.first_page_header, s.first_page_footer):
            try: yield from part.paragraphs; yield from in_tables(part.tables)
            except Exception: pass


def all_text(doc): return [p.text for p in paragraphs(doc)]


def set_par_text(p, text):
    if p.runs:
        p.runs[0].text = text
        for r in p.runs[1:]: r.text = ''
    else: p.add_run(text)


def fill_fields(doc, vals):
    """Αντικαθιστά {{ΠΕΔΙΟ}} σε κάθε παράγραφο. Αν το πεδίο σπάει σε πολλά runs του Word, η παράγραφος παίρνει τη μορφή του πρώτου run."""
    sub = lambda t: re.sub(r'\{\{([^{}]+)\}\}', lambda m: vals.get(m.group(1).strip(), m.group(0)), t)
    for p in paragraphs(doc):
        if '{{' not in p.text or MARK in p.text: continue
        for r in p.runs:
            if '{{' in r.text: r.text = sub(r.text)
        if re.search(r'\{\{[^{}]+\}\}', p.text):                 # πεδίο σπασμένο σε runs
            new = sub(p.text)
            if new != p.text: set_par_text(p, new)


def ensure_styles(doc):
    """Πρότυπα σχολείου συχνά δεν έχουν όλα τα στυλ που χρειάζεται ο μετατροπέας· τα προσθέτουμε όπου λείπουν."""
    names = {s.name for s in doc.styles}
    for n in ['Heading 1', 'Heading 2', 'Heading 3', 'Heading 4', 'List Bullet', 'List Bullet 2', 'List Bullet 3', 'List Number', 'List Number 2', 'List Number 3', 'Quote']:
        if n not in names:
            s = doc.styles.add_style(n, WD_STYLE_TYPE.PARAGRAPH)
            try: s.base_style = doc.styles['Normal']
            except KeyError: pass
            if n.startswith('Heading'): s.font.bold = True; s.font.size = Pt({'1': 16, '2': 14, '3': 12, '4': 11}[n[-1]])
    if 'Table Grid' not in names:
        try:
            s = doc.styles.add_style('Table Grid', WD_STYLE_TYPE.TABLE)
            from docx.oxml import parse_xml
            s.element.append(parse_xml('<w:tblPr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:tblBorders>' + ''.join(f'<w:{e} w:val="single" w:sz="4" w:space="0" w:color="000000"/>' for e in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')) + '</w:tblBorders></w:tblPr>'))
        except Exception: pass


def grouping(es, how):
    """Ορατά ερωτήματα -> [(ετικέτα ομάδας ή None, [entries])]."""
    shown = [e for e in es if e['vis'] == 'show']
    if how == 'none': return [(None, shown)]
    key = (lambda e: e['item']) if how == 'item' else (lambda e: e['row']['qtype'] or '—')
    order, g = [], {}
    for e in shown:
        k = key(e)
        if k not in g: order.append(k); g[k] = []
        g[k].append(e)
    return [(i, g[k]) for i, k in enumerate(order, 1)]


def letter(i): return LETTERS[i - 1] if i - 1 < len(LETTERS) else str(i)


def body_md(c, st, es, teacher):
    """Markdown των ερωτημάτων (μόνο το σώμα, χωρίς επικεφαλίδα εγγράφου)."""
    out = []; mode = st.get('x_mode', 'image') if st.get('x_mode') in ('image', 'text', 'both') else 'image'; n = 0
    for gi, ents in grouping(es, st.get('x_grp', 'item')):
        if gi is not None: out.append(f"## ΘΕΜΑ {letter(gi)} ({M.fmt_pts(sum(e['pts'] for e in ents))} μονάδες)")
        for k, e in enumerate(ents, 1):
            n += 1; r = e['row']
            q = c.execute('SELECT id qid,text,geo FROM question WHERE item_id=? AND code=?', (e['item'], e['code'])).fetchone()
            q = dict(q) if q else {'qid': 0, 'text': '', 'geo': None}
            lab = (f"{letter(gi)}{k}." if gi is not None else f"{n}.") + f" ({M.fmt_pts(e['pts'])} μον.)"
            out.append(q_block(q, lab, mode))
            if teacher and q['qid']:
                s = c.execute('SELECT sol_geo FROM question WHERE id=?', (q['qid'],)).fetchone()
                if s and s['sol_geo']: out.append(f"*Λύση ΙΕΠ:*\n\n![](/crop/{q['qid']}.jpg?sol=1)")
    return '\n\n'.join(out) + '\n'


def values(st, es, teacher):
    tot = M.fmt_pts(M.total(es)); g = lambda k, d='': (st.get(k) or d)
    return {'ΤΙΤΛΟΣ': st['title'] or 'Διαγώνισμα', 'ΥΠΟΤΙΤΛΟΣ': g('x_sub'), 'ΣΧΟΛΕΙΟ': g('x_school'), 'ΜΑΘΗΜΑ': g('x_course'), 'ΤΑΞΗ': g('x_class'), 'ΗΜΕΡΟΜΗΝΙΑ': g('x_date'),
            'ΔΙΑΡΚΕΙΑ': g('x_dur'), 'ΟΔΗΓΙΕΣ': g('x_notes'), 'ΜΟΝΑΔΕΣ': tot, 'ΕΚΔΟΣΗ': 'Καθηγητή (με λύσεις)' if teacher else 'Μαθητή'}


def build_one(c, st, es, teacher):
    doc = load_template(st.get('x_tpl') or 'default'); ensure_styles(doc); vals = values(st, es, teacher)
    marker = next((p for p in doc.paragraphs if MARK in p.text), None)
    fill_fields(doc, vals)
    body = doc.element.body; before = list(body)
    mddoc.md_to_docx(c, body_md(c, st, es, teacher), doc=doc)
    added = [el for el in body if el not in before and not el.tag.endswith('}sectPr')]
    if marker is not None:
        for el in added: marker._p.addprevious(el)
        marker._p.getparent().remove(marker._p)
    b = io.BytesIO(); doc.save(b); return b.getvalue()


def build(c, st, es):
    """-> (bytes, όνομα αρχείου, mimetype)."""
    base = re.sub(r'[^\w-]+', '_', st['title'], flags=re.U).strip('_')[:50] or 'diagonisma'; v = st.get('x_ver', 'student')
    if v == 'student': return build_one(c, st, es, False), f'{base}.docx', DOCX
    if v == 'teacher': return build_one(c, st, es, True), f'{base}_kathigiti.docx', DOCX
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'{base}_mathiti.docx', build_one(c, st, es, False)); z.writestr(f'{base}_kathigiti.docx', build_one(c, st, es, True))
    return b.getvalue(), f'{base}.zip', 'application/zip'
