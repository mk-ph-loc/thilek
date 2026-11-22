"""Πρόοδος λύσεων εκπαιδευτικού: ποια ερωτήματα/θέματα έχουν λύση (.md), status, Word/PDF, εκκρεμή και σειρά παρτίδας. Εξαγωγή lyseis_progress.xlsx."""
import datetime, io, pathlib
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from urllib.parse import quote
from . import config, qsol
from .main_auth import auth
from .review import db, same_origin

router = APIRouter()
FILENAME = 'lyseis_progress.xlsx'
MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
STATUS = {'': 'χωρίς λύση', 'draft': 'πρόχειρη', 'reviewed': 'ελεγμένη', 'error': 'σφάλμα'}
HARD = ('problem', 'development')            # ευρετικό: πολύπλοκα ερωτήματα με σχήμα προτείνονται για Opus


def model_hint(qtype, has_image):
    return 'Opus' if (qtype in HARD and has_image) else 'Sonnet'


def collect(c, course=None):
    """-> (questions, items). questions: ένα dict ανά ερώτημα της βάσης· items: σύνοψη ανά θέμα με σειρά παρτίδας για τα εκκρεμή."""
    sols = {}
    for r in c.execute('SELECT * FROM qsolution'):
        d = qsol.row_dict(r); sols[(d['item_id'], d['qcode'])] = d
    words = {}
    for r in c.execute('SELECT item_id,kind,status FROM wordsrc'): words.setdefault(r['item_id'], {})[r['kind']] = r['status']
    where, args = ('WHERE i.course_code=?', [course]) if course else ('', [])
    qs = []
    for r in c.execute(f"""SELECT q.item_id,q.code,q.points,q.qtype,q.has_image,i.course_code,i.source,i.position,i.iep_yli,i.statement_path,i.solution_path
                           FROM question q JOIN item i ON i.id=q.item_id {where}""", args):
        s = sols.get((r['item_id'], r['code'])); w = words.get(r['item_id'], {})
        mt = s['mtime'] if s and s.get('mtime') else None
        qs.append({'course': r['course_code'], 'item': r['item_id'], 'source': r['source'] or '', 'topic': r['position'], 'yli': r['iep_yli'] or '', 'code': r['code'], 'points': r['points'],
                   'qtype': r['qtype'] or '', 'image': bool(r['has_image']), 'pdf': bool(r['statement_path']), 'pdf_sol': bool(r['solution_path']),
                   'word': w.get('statement', ''), 'word_sol': w.get('solution', ''), 'has_md': bool(s), 'status': (s['status'] or 'draft') if s else '',
                   'quiz': len([x for x in s['quiz'] if not x['err']]) if s else 0, 'warn': len(s['warn']) if s else 0,
                   'file': s['relpath'] if s else '', 'mtime': datetime.datetime.fromtimestamp(mt).strftime('%d/%m/%Y') if mt else '', 'hint': model_hint(r['qtype'], r['has_image'])})
    def ik(x):
        try: return (0, int(x['item']), x['code'])
        except ValueError: return (1, 0, x['item'] + x['code'])
    qs.sort(key=ik)
    items = {}
    for q in qs:
        it = items.setdefault(q['item'], {'course': q['course'], 'item': q['item'], 'source': q['source'], 'topic': q['topic'], 'yli': q['yli'], 'n': 0, 'done': 0, 'reviewed': 0, 'draft': 0,
                                          'pdf': q['pdf'], 'pdf_sol': q['pdf_sol'], 'word': q['word'], 'word_sol': q['word_sol'], 'hint': 'Sonnet', 'missing': [], 'rank': ''})
        it['n'] += 1
        if q['has_md']:
            it['done'] += 1; it[q['status'] if q['status'] in ('reviewed', 'draft') else 'draft'] += 1
        else:
            it['missing'].append(q['code'])
            if q['hint'] == 'Opus': it['hint'] = 'Opus'
    todo = [i for i in items.values() if i['missing'] and (i['pdf'] or i['word'] or i['source'] != 'TTDD')]
    todo.sort(key=lambda i: (-i['done'], int(i['item']) if i['item'].isdigit() else 10 ** 9))   # πρώτα όσα έχουν ήδη ξεκινήσει
    for n, i in enumerate(todo, 1): i['rank'] = n
    return qs, list(items.values())


def summary(qs, items):
    n = len(qs); done = sum(1 for q in qs if q['has_md']); rev = sum(1 for q in qs if q['status'] == 'reviewed')
    return {'questions': n, 'done': done, 'reviewed': rev, 'draft': sum(1 for q in qs if q['status'] == 'draft'), 'error': sum(1 for q in qs if q['status'] == 'error'),
            'items': len(items), 'items_done': sum(1 for i in items if not i['missing']), 'pending_items': sum(1 for i in items if i['missing']), 'warn': sum(1 for q in qs if q['warn'])}


def next_batch(items, n=5):
    return [i for i in sorted((i for i in items if i['rank']), key=lambda i: i['rank'])][:max(1, min(int(n), 50))]


def xlsx_bytes(c, course=None):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    qs, items = collect(c, course); sm = summary(qs, items)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'Σύνοψη'
    ws.append(['TH-ILEK: πρόοδος λύσεων εκπαιδευτικού']); ws['A1'].font = Font(bold=True, size=13)
    ws.append(['Δημιουργήθηκε', datetime.datetime.now().strftime('%d/%m/%Y %H:%M')]); ws.append(['Μάθημα', course or 'όλα'])
    for k, lab in (('questions', 'Ερωτήματα'), ('done', 'Με λύση (.md)'), ('reviewed', 'Ελεγμένες'), ('draft', 'Πρόχειρες'), ('error', 'Με σφάλμα'), ('warn', 'Με προειδοποιήσεις'), ('items', 'Θέματα'), ('items_done', 'Θέματα πλήρη'), ('pending_items', 'Θέματα εκκρεμή')):
        ws.append([lab, sm[k]])
    ws.append([]); ws.append(['Οδηγία για παρτίδα: πάρε από το φύλλο «Θέματα» τα εκκρεμή με τη μικρότερη «Σειρά παρτίδας» και φτιάξε μόνο τα ερωτήματα της στήλης «Λείπουν». Ό,τι έχει ήδη λύση (.md) δεν ξαναγράφεται.'])
    ws.column_dimensions['A'].width = 34; ws.column_dimensions['B'].width = 22
    ti = wb.create_sheet('Θέματα')
    head = ['Μάθημα', 'Θέμα ID', 'Πηγή', 'Θέση', 'Ενότητα ΙΕΠ', 'Ερωτήματα', 'Με λύση', 'Ελεγμένες', 'Πρόχειρες', 'Λείπουν', 'PDF', 'PDF λύσης', 'Word', 'Word λύσης', 'Προτεινόμενο μοντέλο', 'Σειρά παρτίδας']
    ti.append(head)
    for i in sorted(items, key=lambda i: (i['course'], int(i['item']) if i['item'].isdigit() else 10 ** 9)):
        ti.append([i['course'], i['item'], i['source'], i['topic'], i['yli'], i['n'], i['done'], i['reviewed'], i['draft'], ', '.join(i['missing']), 'ναι' if i['pdf'] else '', 'ναι' if i['pdf_sol'] else '',
                   i['word'], i['word_sol'], i['hint'] if i['missing'] else '', i['rank']])
    tq = wb.create_sheet('Ερωτήματα')
    tq.append(['Μάθημα', 'Θέμα ID', 'Ερώτημα', 'Μονάδες', 'Τύπος', 'Σχήμα', 'Έχει λύση', 'Status', 'Στοιχεία quiz', 'Προειδοποιήσεις', 'Αρχείο λύσης', 'Τελευταία αλλαγή', 'Προτεινόμενο μοντέλο'])
    for q in qs:
        tq.append([q['course'], q['item'], q['code'], q['points'], q['qtype'], 'ναι' if q['image'] else '', 'ναι' if q['has_md'] else 'όχι', STATUS.get(q['status'], q['status']), q['quiz'], q['warn'], q['file'], q['mtime'], '' if q['has_md'] else q['hint']])
    for sh, widths in ((ti, (16, 10, 7, 6, 20, 10, 9, 10, 10, 24, 6, 9, 10, 10, 12, 10)), (tq, (16, 10, 9, 8, 13, 7, 10, 12, 10, 12, 40, 14, 12))):
        for cell in sh[1]: cell.font = Font(bold=True, color='FFFFFF'); cell.fill = PatternFill('solid', fgColor='1E3A8A'); cell.alignment = Alignment(wrap_text=True, vertical='center')
        for k, w in enumerate(widths, 1): sh.column_dimensions[openpyxl.utils.get_column_letter(k)].width = w
        sh.freeze_panes = 'A2'; sh.auto_filter.ref = sh.dimensions
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


@router.get('/lyseis/progress.xlsx', dependencies=[Depends(auth)])
def progress_download(course: str = ''):
    c = db()
    try: data = xlsx_bytes(c, course or None)
    finally: c.close()
    return Response(data, media_type=MIME, headers={'Content-Disposition': f'attachment; filename="{FILENAME}"'})


@router.post('/lyseis/progress/save', dependencies=[Depends(auth)])
def progress_save(request: Request):
    """Γράφει ένα αρχείο ανά μάθημα στο <μάθημα>/07_EXAGOGES/lyseis_progress.xlsx (πάντα αντικαθιστά το προηγούμενο)."""
    same_origin(request); c = db(); root = pathlib.Path(config.load()['data_root']); out = []
    try:
        for (code,) in c.execute('SELECT code FROM course ORDER BY code').fetchall():
            d = root / code / '07_EXAGOGES'; d.mkdir(parents=True, exist_ok=True); p = d / FILENAME
            p.write_bytes(xlsx_bytes(c, code)); out.append(f'{code}/07_EXAGOGES/{FILENAME}')
    finally: c.close()
    return RedirectResponse('/lyseis?msg=' + quote('Αποθηκεύτηκε: ' + ', '.join(out) + ' (ο φάκελος 07_EXAGOGES δεν συγχρονίζεται με το Drive· κατέβασέ το από εδώ και βάλ’ το στο Drive αν το θες εκεί)'), status_code=303)
