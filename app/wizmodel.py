"""Ενιαίο μοντέλο εξαγωγών του wizard (0.21.0): κατάσταση συνταγής, στοιχεία με μονάδες, προσαρμογή βαθμών, ό,τι δεν επιλέχθηκε,
και οι renderers που δεν υπήρχαν (Excel, Markdown με μονάδες). Καθαρή λογική: το HTML/routes είναι στο wizard.py."""
import datetime, io, json, re, zipfile

FORMATS = (('excel', 'Excel (πίνακας ερωτημάτων με συνδέσμους σε αρχεία)'), ('md', 'Markdown έγγραφο (/docs, από εκεί και Word)'),
           ('htmldoc', 'Έγγραφο HTML για εκτύπωση (εικόνες ερωτημάτων)'), ('reveal', 'Reveal.js (λύσεις εκπαιδευτικού)'), ('student', 'HTML μαθητή (λύσεις εκπαιδευτικού)'),
           ('pptx', 'PowerPoint .pptx (λύσεις εκπαιδευτικού, μέσω Pandoc)'), ('moodle', 'Moodle XML (quiz από λύσεις εκπαιδευτικού)'), ('merge', 'PDF συγχώνευσης θεμάτων'), ('exam', 'Διαγώνισμα/τεστ Word (πρότυπο σχολείου)'),
           ('gform', 'Google Form (script Apps Script από λύσεις εκπαιδευτικού)'), ('h5p', 'H5P Question Set (δεδομένα JSON + οδηγίες)'))
FORMAT_KEYS = tuple(k for k, _ in FORMATS)
NEEDS_SOL = ('reveal', 'student', 'pptx', 'moodle', 'gform', 'h5p')                  # θέλουν αρχείο λύσης εκπαιδευτικού
POINTS_HONORED = ('excel', 'md', 'exam')                             # οι υπόλοιπες παίρνουν μονάδες από τα αρχεία/βάση
UNSEL = (('omit', 'Να μην εμφανιστούν καθόλου'), ('hide', 'Κρυφά (μπαίνουν στο αρχείο αλλά δεν φαίνονται)'),
         ('append', 'Στο τέλος, μη εμφανιζόμενα'), ('manual', 'Θα διαλέξω εγώ ποια θα εμφανιστούν'))
ORDERS = (('item', 'Θέμα και ερώτημα'), ('points', 'Μονάδες (φθίνουσα)'), ('qtype', 'Τύπος ερωτήματος'), ('manual', 'Χειροκίνητη σειρά (↑↓)'))
CRITERIA = (('q', 'Λέξεις-κλειδιά'), ('qtype', 'Τύπος ερωτήματος'), ('chapter', 'Κεφάλαιο'), ('image', 'Εικόνα'), ('position', 'Θέση θέματος (2 ή 4)'), ('fav', 'Αγαπημένα'),
            ('yli', 'Ενότητα ΙΕΠ'), ('section', 'Υποενότητα βιβλίου'), ('tag', 'Ετικέτες'), ('lsol', 'Λύση εκπαιδευτικού (με/χωρίς)'), ('src', 'Πηγή θέματος (ΙΕΠ/πανελλήνιες/δικά μου)'), ('word', 'Word ΙΕΠ (με/χωρίς)'), ('upto', 'Ύλη μέχρι σελίδα βιβλίου'))
CRITERIA_KEYS = tuple(k for k, _ in CRITERIA)

DEFAULT = {'criteria': {}, 'members': [], 'mode': 'merge', 'gran': 'item', 'order': 'item', 'points': {}, 'target': None, 'unsel': 'omit', 'manual_sel': [],
           'format': 'excel', 'title': 'Αναφορά ασκήσεων', 'style': 'kids', 'sx': [], 'hide': True, 'frag': False, 'mdmode': 'image', 'numbering': 'new',
           'link_prefix': 'pdf/', 'bundle': False, 'store': 'download', 'preview': True,
           'x_school': '', 'x_class': '', 'x_date': '', 'x_dur': '', 'x_sub': '', 'x_notes': '', 'x_course': '', 'x_tpl': 'default', 'x_ver': 'student', 'x_grp': 'item', 'x_mode': 'image',
           'cmp': False, 'm_cat': 'single', 'm_tags': True, 'g_name': 'required', 'g_img': 'default'}


def key(item, code): return f'{item}|{code}'
def unkey(k): a, _, b = str(k).partition('|'); return a, b


def new_state(): return json.loads(json.dumps(DEFAULT))


def load_state(raw):
    """JSON της βάσης -> κατάσταση με προεπιλογές και έγκυρους τύπους (ανθεκτικό σε χαλασμένα δεδομένα)."""
    st = new_state()
    try: d = json.loads(raw or '{}')
    except ValueError: d = {}
    if not isinstance(d, dict): d = {}
    for k, v in d.items():
        if k in st and type(v) is type(st[k]) or (k == 'target' and (v is None or isinstance(v, (int, float)))): st[k] = v
    st['members'] = [list(m) for m in st['members'] if isinstance(m, (list, tuple)) and len(m) == 2]
    st['points'] = {k: v for k, v in st['points'].items() if isinstance(v, (int, float))}
    if st['format'] not in FORMAT_KEYS: st['format'] = 'excel'
    if st['unsel'] not in dict(UNSEL): st['unsel'] = 'omit'
    if st['order'] not in dict(ORDERS): st['order'] = 'item'
    if st['mode'] not in ('merge', 'each'): st['mode'] = 'merge'
    if st['gran'] not in ('item', 'question'): st['gran'] = 'item'
    if st['x_ver'] not in ('student', 'teacher', 'both'): st['x_ver'] = 'student'
    if st['x_grp'] not in ('item', 'qtype', 'none'): st['x_grp'] = 'item'
    if st['x_mode'] not in ('image', 'text', 'both'): st['x_mode'] = 'image'
    if st['m_cat'] not in ('single', 'item', 'qtype'): st['m_cat'] = 'single'
    if st['g_name'] not in ('required', 'optional', 'none'): st['g_name'] = 'required'
    if st['g_img'] not in ('default', 'text', 'images'): st['g_img'] = 'default'
    for k in ('x_school', 'x_class', 'x_date', 'x_dur', 'x_sub', 'x_notes', 'x_course', 'x_tpl'): st[k] = st[k][:300]
    if st['store'] not in ('download', 'server', 'publish'): st['store'] = 'download'
    return st


def num(s):
    """Δεκαδικός με κόμμα ή τελεία -> float ή None."""
    try: return float(str(s).replace(',', '.').strip())
    except ValueError: return None


def fmt_pts(x):
    x = float(x or 0); return str(int(x)) if x == int(x) else f'{x:g}'


def scale_points(pts, target, step=1.0):
    """Αναλογική προσαρμογή {κλειδί: μονάδες} ώστε το άθροισμα να γίνει target, με στρογγυλοποίηση σε πολλαπλάσια του step
    (μέθοδος μεγαλύτερου υπολοίπου: το άθροισμα βγαίνει ακριβές όταν το target είναι πολλαπλάσιο του step)."""
    tot = sum(pts.values())
    if not pts or tot <= 0 or target is None or target <= 0 or step <= 0: return dict(pts)
    units = round(target / step); raw = {k: v * units / tot for k, v in pts.items()}
    fl = {k: int(x) for k, x in raw.items()}; rest = units - sum(fl.values())
    for k in sorted(raw, key=lambda k: (raw[k] - fl[k]), reverse=True)[:max(rest, 0)]: fl[k] += 1
    return {k: round(n * step, 6) for k, n in fl.items()}


ROW_SQL = """SELECT q.id qid,q.item_id,q.code,q.points,q.qtype,q.has_image,q.geo IS NOT NULL has_geo,q.sol_geo IS NOT NULL has_geo_sol,i.iep_yli,i.position,i.course_code,i.statement_path,i.solution_path,
    EXISTS (SELECT 1 FROM qsolution s WHERE s.item_id=q.item_id AND s.qcode=q.code) has_sol,
    (SELECT s.status FROM qsolution s WHERE s.item_id=q.item_id AND s.qcode=q.code) sol_status,
    (SELECT s.relpath FROM qsolution s WHERE s.item_id=q.item_id AND s.qcode=q.code) sol_rel,
    (SELECT s.quiz FROM qsolution s WHERE s.item_id=q.item_id AND s.qcode=q.code) sol_quiz
    FROM question q JOIN item i ON i.id=q.item_id WHERE q.item_id=? AND q.code=?"""


def sort_key(item, code):
    from . import qsol
    return qsol.sort_key(item, code)


def siblings(c, members):
    """Ερωτήματα των θεμάτων των μελών που δεν είναι στη λίστα: [(item, code)] σε σειρά."""
    have = {tuple(m) for m in members}; out = []
    for it in dict.fromkeys(m[0] for m in members):
        for r in c.execute('SELECT code FROM question WHERE item_id=? ORDER BY id', (it,)):
            if (it, r[0]) not in have: out.append((it, r[0]))
    return out


def ordered(c, st):
    """Μέλη με τη σειρά που ζητά η συνταγή."""
    mem = [tuple(m) for m in dict.fromkeys(tuple(m) for m in st['members'])]
    if st['order'] == 'manual': return mem
    info = {}
    for m in mem:
        r = c.execute('SELECT points,qtype FROM question WHERE item_id=? AND code=?', m).fetchone()
        info[m] = (st['points'].get(key(*m), r['points'] if r else 0) or 0, (r['qtype'] if r else '') or '')
    if st['order'] == 'points': return sorted(mem, key=lambda m: (-info[m][0], sort_key(*m)))
    if st['order'] == 'qtype': return sorted(mem, key=lambda m: (info[m][1], sort_key(*m)))
    return sorted(mem, key=lambda m: sort_key(*m))


def entries(c, st):
    """Η τελική λίστα στοιχείων: dict(item, code, pts, vis in show|hidden|append, row). Το άθροισμα βαθμών μετρά μόνο τα vis=show."""
    main = ordered(c, st); out = []; pts = st['points']
    def mk(m, vis):
        r = c.execute(ROW_SQL, m).fetchone()
        if not r: return None
        r = dict(r); p = pts.get(key(*m), r['points'] or 0)
        return {'item': m[0], 'code': m[1], 'pts': float(p or 0), 'vis': vis, 'row': r}
    sib = siblings(c, main) if st['unsel'] != 'omit' else []
    by_item = {}
    for s in sib: by_item.setdefault(s[0], []).append(s)
    manual = {tuple(unkey(k)) for k in st['manual_sel']}
    tail = []
    for i, m in enumerate(main):
        e = mk(m, 'show')
        if e: out.append(e)
        last = i == len(main) - 1 or main[i + 1][0] != m[0]
        if not last: continue
        for s in by_item.pop(m[0], []):
            if st['unsel'] == 'hide': e = mk(s, 'hidden'); out.append(e) if e else None
            elif st['unsel'] == 'append': e = mk(s, 'append'); tail.append(e) if e else None
            elif st['unsel'] == 'manual' and s in manual: e = mk(s, 'show'); out.append(e) if e else None
    return out + tail


def total(es): return sum(e['pts'] for e in es if e['vis'] == 'show')


def checks(es, st):
    """Προειδοποιήσεις πριν την εξαγωγή (λίστα κειμένων)."""
    w = []; shown = [e for e in es if e['vis'] == 'show']
    if not shown: w.append('Δεν υπάρχει κανένα ερώτημα για εμφάνιση.')
    t = total(es)
    if st['target'] and abs(t - st['target']) > 1e-6: w.append(f'Το άθροισμα μονάδων είναι {fmt_pts(t)} και ο στόχος {fmt_pts(st["target"])}. Πήγαινε στο βήμα «Βαθμοί».')
    if st['format'] in NEEDS_SOL:
        miss = [f"{e['item']}/{e['code']}" for e in shown if not e['row']['has_sol']]
        if miss: w.append(f"{len(miss)} ερωτήματα δεν έχουν αρχείο λύσης εκπαιδευτικού και θα παραλειφθούν: {', '.join(miss[:12])}{'…' if len(miss) > 12 else ''}.")
    if st['format'] not in POINTS_HONORED and any(abs(e['pts'] - (e['row']['points'] or 0)) > 1e-9 for e in shown):
        w.append('Αυτή η μορφή δεν εφαρμόζει τις προσαρμοσμένες μονάδες· χρησιμοποιεί τις μονάδες των αρχείων/βάσης (Excel και Markdown τις εφαρμόζουν).')
    if st['format'] == 'merge' and any(e['vis'] != 'show' for e in es): w.append('Το PDF συγχώνευσης περιέχει ολόκληρα θέματα· οι ρυθμίσεις «κρυφά/στο τέλος» δεν εφαρμόζονται.')
    if st['format'] in ('reveal', 'student', 'moodle') and any(e['vis'] == 'hidden' for e in es): w.append('Στις λύσεις εκπαιδευτικού τα «κρυφά» δεν εμφανίζονται (παραλείπονται)· τα «στο τέλος» μπαίνουν στο τέλος.')
    if st['format'] in ('moodle', 'gform', 'h5p'):
        import json as _j
        def nq(e):
            try: return len([q for q in _j.loads(e['row'].get('sol_quiz') or '[]') if not q.get('err')])
            except ValueError: return 0
        noq = [f"{e['item']}/{e['code']}" for e in shown if e['row']['has_sol'] and not nq(e)]
        if noq: w.append(f"{len(noq)} ερωτήματα έχουν λύση αλλά κανένα έγκυρο στοιχείο quiz και θα παραλειφθούν: {', '.join(noq[:10])}{'…' if len(noq) > 10 else ''}.")
        if st['format'] == 'gform': w.append('Google Form: οι ερωτήσεις κειμένου/αριθμού δεν παίρνουν αυτόματο κλειδί από το Apps Script· θα τις βρεις στο README του zip.')
    if st['format'] == 'exam':
        from . import wizexam
        if st['x_tpl'] != 'default' and st['x_tpl'] not in wizexam.list_templates(): w.append(f"Το πρότυπο «{st['x_tpl']}» δεν υπάρχει πια στον φάκελο προτύπων· θα εμφανιστεί σφάλμα. Διάλεξε άλλο ή το ενσωματωμένο.")
        if st['x_ver'] in ('teacher', 'both'):
            no = [f"{e['item']}/{e['code']}" for e in shown if not e['row'].get('has_geo_sol')]
            if no: w.append(f"Έκδοση καθηγητή: {len(no)} ερωτήματα δεν έχουν εικόνα λύσης ΙΕΠ ({', '.join(no[:8])}).")
        if not st['x_school'] and not st['x_notes']: w.append('Δεν έχεις συμπληρώσει σχολείο ή οδηγίες· τα αντίστοιχα πεδία του προτύπου θα μείνουν κενά.')
    if st['mode'] == 'each' and st['format'] not in ('reveal', 'student'): w.append('Το «ένα-ένα» ισχύει μόνο για Reveal.js και HTML μαθητή· σε αυτή τη μορφή θα βγει ένα αρχείο.')
    if st['store'] == 'publish' and st['format'] not in ('reveal', 'student', 'htmldoc'): w.append('Η δημοσίευση αφορά σελίδες HTML (Reveal.js, HTML μαθητή, HTML εκτύπωσης)· αυτή η μορφή δεν μπορεί να δημοσιευτεί.')
    return w


# ---------- renderers ----------
README = """Οδηγίες θέσης αρχείων
=====================
Ο πίνακας (xlsx) έχει συνδέσμους προς αρχεία με ΣΧΕΤΙΚΕΣ διαδρομές. Για να ανοίγουν, κράτα αυτή τη δομή (ο φάκελος του xlsx είναι η ρίζα):

  {prefix}<ID>.pdf              εκφώνηση ΙΕΠ
  {prefix}<ID>_SOLUTION.pdf     λύση ΙΕΠ
  lyseis/<ID>.<θέμα>-<υπ>.md    λύση εκπαιδευτικού

Αν έβαλες την επιλογή «επισύναψη αρχείων», το zip περιέχει ήδη τα PDF και τις λύσεις στις παραπάνω θέσεις.
Αλλιώς αντίγραψε τα PDF από τον φάκελο <ΜΑΘΗΜΑ>/04_TRAPEZA/orig/ του server στον φάκελο «{prefix}».
Το βιβλίο δεν επισυνάπτεται (μεγάλο αρχείο): αν το θέλεις δίπλα στο xlsx, βάλ' το ως book/<όνομα>.pdf.
Οι σύνδεσμοι δουλεύουν σε Excel και LibreOffice όταν το xlsx ανοίγει από τον δίσκο (όχι από προεπισκόπηση του browser).
"""


def book_pages(c, qid):
    r = [dict(x) for x in c.execute("SELECT s.code,s.page_from a,s.page_to b FROM question_section qs JOIN section s ON s.id=qs.section_id WHERE qs.question_id=? AND qs.origin!='rejected' AND s.level=3 ORDER BY s.page_from", (qid,))]
    if not r: r = [dict(x) for x in c.execute("SELECT s.code,s.page_from a,s.page_to b FROM question_section qs JOIN section s ON s.id=qs.section_id WHERE qs.question_id=? AND qs.origin!='rejected' ORDER BY s.page_from", (qid,))]
    return '; '.join(f"{x['code']} (σελ. {x['a']}–{x['b']})" if x['b'] and x['b'] != x['a'] else f"{x['code']} (σελ. {x['a']})" for x in r)


def excel_bytes(c, es, st, root=None):
    """(bytes xlsx ή zip, όνομα αρχείου, mimetype). Με st['bundle'] επισυνάπτονται PDF και λύσεις (όσα υπάρχουν) στις θέσεις των συνδέσμων."""
    import openpyxl, pathlib
    from openpyxl.styles import Font, PatternFill, Alignment
    lp = st.get('link_prefix', '')
    prefix = lp if re.match(r'^[A-Za-z0-9_./-]{0,60}$', lp) and '..' not in lp and not lp.startswith('/') else 'pdf/'
    if prefix and not prefix.endswith('/'): prefix += '/'
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'Ερωτήματα'
    head = ['Α/Α', 'Θέμα ΙΕΠ', 'Ερώτημα', 'Μονάδες', 'Τύπος', 'Εικόνα', 'Ενότητα ΙΕΠ', 'Βιβλίο (υποενότητα, σελίδες)', 'Λύση εκπαιδευτικού', 'Status λύσης', 'Εμφάνιση', 'Εκφώνηση PDF', 'Λύση ΙΕΠ PDF', 'Αρχείο λύσης (.md)']
    ws.append(head)
    for cell in ws[1]: cell.font = Font(bold=True, color='FFFFFF'); cell.fill = PatternFill('solid', fgColor='1E3A8A'); cell.alignment = Alignment(wrap_text=True, vertical='center')
    files = []; n = 0; first = 2
    for e in es:
        r = e['row']; n += 1
        stmt = f"{prefix}{e['item']}.pdf" if r['statement_path'] else ''; sol = f"{prefix}{e['item']}_SOLUTION.pdf" if r['solution_path'] else ''
        md = f"lyseis/{pathlib.PurePosixPath(r['sol_rel']).name}" if r['sol_rel'] else ''
        vis = {'show': 'ναι', 'hidden': 'κρυφό', 'append': 'στο τέλος (μη εμφανιζόμενο)'}[e['vis']]
        ws.append([n, e['item'], e['code'], e['pts'], r['qtype'] or '', 'ναι' if r['has_image'] else '', r['iep_yli'] or '', book_pages(c, r['qid']), 'ναι' if r['has_sol'] else 'όχι', r['sol_status'] or '', vis,
                   stmt and 'Εκφώνηση', sol and 'Λύση ΙΕΠ', md and 'Λύση εκπαιδευτικού'])
        row = ws.max_row
        for col, target in ((12, stmt), (13, sol), (14, md)):
            if target: ws.cell(row, col).hyperlink = target; ws.cell(row, col).font = Font(color='0563C1', underline='single')
        if e['vis'] == 'hidden': ws.row_dimensions[row].hidden = True
        if e['vis'] != 'show':
            for cell in ws[row]: cell.font = Font(italic=True, color='888888')
        if stmt: files.append((r['course_code'], r['statement_path'], stmt))
        if sol: files.append((r['course_code'], r['solution_path'], sol))
        if md: files.append((r['course_code'], r['sol_rel'], md))
    last = ws.max_row
    if st.get('cmp'):
        from . import iepcmp
        cs = wb.create_sheet('Σύγκριση ΙΕΠ'); cs.append(['Θέμα', 'Ερώτημα', 'Στοιχείο', 'Τύπος', 'Η απάντησή μου', 'ΙΕΠ', 'Αυτόματο', 'Κατάσταση', 'Χειροκίνητο', 'Σημείωση'])
        for cell in cs[1]: cell.font = Font(bold=True, color='FFFFFF'); cell.fill = PatternFill('solid', fgColor='1E3A8A')
        for x in iepcmp.for_entries(c, es): cs.append([x['item_id'], x['qcode'], x['qn'], x['kind'], x['mine'], x['iep'], iepcmp.label(x['auto']), iepcmp.label(x['status']), 'ναι' if x['manual'] else '', x['note'] or ''])
        for i, wd in enumerate((8, 10, 9, 12, 28, 26, 14, 14, 12, 60), 1): cs.column_dimensions[openpyxl.utils.get_column_letter(i)].width = wd
        cs.freeze_panes = 'A2'
    ws.append([]); ws.append(['', '', 'Σύνολο (ορατά)', f'=SUMIF(K{first}:K{last},"ναι",D{first}:D{last})'])
    for cell in ws[ws.max_row]: cell.font = Font(bold=True)
    for i, wd in enumerate((6, 11, 9, 9, 14, 8, 12, 40, 12, 11, 22, 16, 16, 24), 1): ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = wd
    ws.freeze_panes = 'A2'; ws.auto_filter.ref = f'A1:N{last}'
    g = wb.create_sheet('Οδηγίες'); g['A1'] = 'Οδηγίες θέσης αρχείων'; g['A1'].font = Font(bold=True, size=13)
    for i, ln in enumerate(README.format(prefix=prefix).splitlines()[3:], 3): g.cell(i, 1, ln)
    g.column_dimensions['A'].width = 110
    m = wb.create_sheet('Στοιχεία'); m.append(['Τίτλος', st['title']]); m.append(['Δημιουργήθηκε', datetime.datetime.now().strftime('%d/%m/%Y %H:%M')]); m.append(['Σύνολο μονάδων (ορατά)', total(es)])
    m.append(['Στόχος μονάδων', st['target'] or '—']); m.append(['Χειρισμός μη επιλεγμένων', dict(UNSEL)[st['unsel']]]); m.column_dimensions['A'].width = 30; m.column_dimensions['B'].width = 50
    buf = io.BytesIO(); wb.save(buf); x = buf.getvalue(); base = re.sub(r'[^\w.-]+', '_', st['title'])[:50] or 'anafora'
    if not st.get('bundle'): return x, f'{base}.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    zb = io.BytesIO(); added = set(); skipped = []
    with zipfile.ZipFile(zb, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'{base}.xlsx', x); z.writestr('README.txt', README.format(prefix=prefix))
        for course, rel, arc in files:
            if arc in added: continue
            added.add(arc); p = _src(root, course, rel, arc)
            if p and p.is_file(): z.write(p, arc)
            else: skipped.append(arc)
        if skipped: z.writestr('LIPOUN.txt', 'Δεν βρέθηκαν στον server:\n' + '\n'.join(skipped) + '\n')
    return zb.getvalue(), f'{base}.zip', 'application/zip'


def _src(root, course, rel, arc):
    """Διαδρομή αρχείου στον server από τη διαδρομή της βάσης (σχετική με το data_root ή με τον φάκελο του μαθήματος)· ασφαλής έναντι ../."""
    import pathlib
    if not root or not rel: return None
    base = pathlib.Path(root).resolve()
    for cand in (base / rel, base / (course or '') / rel, base / (course or '') / '04_TRAPEZA' / 'orig' / pathlib.PurePosixPath(rel).name, base / (course or '') / '05_LYSEIS' / pathlib.PurePosixPath(rel).name):
        try: p = cand.resolve()
        except OSError: continue
        if base in p.parents and p.is_file(): return p
    return None


def md_text(c, es, st):
    """Markdown με επικεφαλίδα, μονάδες ανά ερώτημα και σύνολο. Τα hidden/append μπαίνουν μέσα σε σχόλιο HTML (δεν φαίνονται)."""
    from .mdgen import q_block
    shown = [e for e in es if e['vis'] == 'show']; out = [f"# {st['title']}", f"Σύνολο: {fmt_pts(total(es))} μονάδες"]
    def block(e, n):
        q = c.execute('SELECT id qid,text,geo FROM question WHERE item_id=? AND code=?', (e['item'], e['code'])).fetchone()
        q = dict(q) if q else {'qid': 0, 'text': '', 'geo': None}
        lab = f"{n}." if st['numbering'] == 'new' else f"Θέμα {e['item']} · {e['code']}"
        return q_block(q, f"{lab} ({fmt_pts(e['pts'])} μον.)", st['mdmode'] if st['mdmode'] in ('image', 'text', 'both') else 'image')
    for n, e in enumerate(shown, 1): out.append(block(e, n))
    rest = [e for e in es if e['vis'] != 'show']
    if rest:
        body = '\n\n'.join(block(e, f"{e['item']}/{e['code']}").replace('--', '- -') for e in rest)
        out.append('<!-- Μη εμφανιζόμενα ερωτήματα (αφαίρεσε τα σχόλια για να εμφανιστούν):\n\n' + body + '\n-->')
    return '\n\n'.join(out) + '\n'
