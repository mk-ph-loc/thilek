"""0.29.0: πρόοδος λύσεων και lyseis_progress.xlsx."""
import io, json, os, sqlite3
import openpyxl
from app import progress
from tests.test_docs import cl, A, H  # noqa: F401
from tests.test_wizard import seed


def setup():
    seed(); c = sqlite3.connect(os.environ['THILEK_DB'])
    c.execute("UPDATE question SET has_image=1 WHERE id=4")                      # 2.4: πρόβλημα με σχήμα -> Opus
    c.execute("INSERT INTO item(id,course_code,source,position,iep_yli,solution_status,statement_path) VALUES('5','C','TTDD',2,'4.2 y','ok','C/04_TRAPEZA/orig/5.pdf')")
    c.execute("INSERT INTO item(id,course_code,source,position,iep_yli,solution_status) VALUES('9','C','TTDD',2,'4.3 z','ok')")      # χωρίς πηγές
    for i, (it, code) in enumerate((('5', '2.1'), ('9', '2.1')), 10): c.execute("INSERT INTO question(id,item_id,code,points,text,qtype) VALUES(?,?,?,?,?,?)", (i, it, code, 5, 'x', 'mcq'))
    for code, stt, q in (('2.1', 'reviewed', [{'err': None}, {'err': None}]), ('2.2', 'draft', [{'err': 'x'}])):
        c.execute("INSERT INTO qsolution(item_id,qcode,relpath,status,quiz,warn,mtime) VALUES('1',?,?,?,?,?,?)", (code, f'C/05_LYSEIS/1.{code}.md', stt, json.dumps(q), json.dumps(['w'] if stt == 'draft' else []), 1700000000))
    c.commit(); c.row_factory = sqlite3.Row; return c


def test_collect_counts_and_batch_order(cl):
    c = setup(); qs, items = progress.collect(c); sm = progress.summary(qs, items)
    assert sm['questions'] == 6 and sm['done'] == 2 and sm['reviewed'] == 1 and sm['draft'] == 1 and sm['warn'] == 1
    it = {i['item']: i for i in items}
    assert it['1']['done'] == 2 and it['1']['missing'] == ['2.3', '2.4'] and it['1']['hint'] == 'Opus' and it['1']['rank'] == 1       # ξεκίνησε ήδη -> πρώτο
    assert it['5']['rank'] == 2 and it['5']['hint'] == 'Sonnet' and it['9']['rank'] == '' and it['9']['missing'] == ['2.1']          # το 9 δεν έχει αρχείο πηγής
    q = {(x['item'], x['code']): x for x in qs}; assert q[('1', '2.1')]['quiz'] == 2 and q[('1', '2.2')]['quiz'] == 0 and q[('1', '2.2')]['status'] == 'draft' and q[('1', '2.3')]['status'] == ''
    assert [i['item'] for i in progress.next_batch(items, 1)] == ['1'] and [i['item'] for i in progress.next_batch(items, 5)] == ['1', '5']


def test_course_filter_and_empty(cl):
    c = setup(); qs, items = progress.collect(c, 'NOPE'); assert qs == [] and items == [] and progress.summary(qs, items)['questions'] == 0
    assert len(progress.collect(c, 'C')[0]) == 6


def test_xlsx_sheets_and_content(cl):
    setup(); r = cl.get('/lyseis/progress.xlsx', auth=A); assert r.status_code == 200 and 'lyseis_progress.xlsx' in r.headers['content-disposition']
    wb = openpyxl.load_workbook(io.BytesIO(r.content)); assert wb.sheetnames == ['Σύνοψη', 'Θέματα', 'Ερωτήματα']
    th = list(wb['Θέματα'].iter_rows(values_only=True)); h = th[0]; row1 = dict(zip(h, next(x for x in th[1:] if x[1] == '1')))
    assert row1['Με λύση'] == 2 and row1['Λείπουν'] == '2.3, 2.4' and row1['Σειρά παρτίδας'] == 1 and row1['Προτεινόμενο μοντέλο'] == 'Opus'
    qr = list(wb['Ερωτήματα'].iter_rows(values_only=True)); qh = qr[0]; r21 = dict(zip(qh, next(x for x in qr[1:] if x[1] == '1' and x[2] == '2.1')))
    assert r21['Status'] == 'ελεγμένη' and r21['Στοιχεία quiz'] == 2 and r21['Έχει λύση'] == 'ναι' and r21['Αρχείο λύσης'] == 'C/05_LYSEIS/1.2.1.md'
    assert len(wb['Σύνοψη']['A']) > 8 and cl.get('/lyseis/progress.xlsx?course=NOPE', auth=A).status_code == 200


def test_page_shows_progress_and_save_writes_file(cl):
    setup(); h = cl.get('/lyseis', auth=A).text
    assert 'Πρόοδος' in h and '2/6' in h and 'lyseis_progress.xlsx' in h and 'Opus' in h
    r = cl.post('/lyseis/progress/save', auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    p = os.path.join(os.environ['THILEK_ROOT'], 'C', '07_EXAGOGES', 'lyseis_progress.xlsx'); assert os.path.isfile(p) and openpyxl.load_workbook(p).sheetnames[1] == 'Θέματα'
    assert cl.post('/lyseis/progress/save', auth=A, headers={'Origin': 'http://evil.example'}, follow_redirects=False).status_code in (400, 403)
    assert cl.get('/lyseis/progress.xlsx').status_code in (401, 403)
