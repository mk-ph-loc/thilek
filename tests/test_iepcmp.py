"""0.25.0: σύγκριση των απαντήσεων των λύσεών μου με τη λύση ΙΕΠ, με χειροκίνητες κρίσεις."""
import io, os, sqlite3
import openpyxl
from tests.test_docs import cl, A, H  # noqa: F401
from tests.test_wizard import new, post
from tests.test_publish import with_solutions
from app import iepcmp


def setup(cl):
    with_solutions(cl); c = sqlite3.connect(os.environ['THILEK_DB'])
    c.execute("UPDATE question SET sol_text='α–Σ. Το ρεύμα είναι I = 2 A' WHERE item_id='1' AND code='2.1'")
    c.execute("UPDATE question SET sol_text='β' WHERE item_id='1' AND code='2.2'"); c.commit(); c.close()
    assert cl.post('/compare/refresh', auth=A, headers=H, follow_redirects=False).status_code == 303


def rows():
    c = sqlite3.connect(os.environ['THILEK_DB']); c.row_factory = sqlite3.Row
    return {(r['qcode'], r['kind']): dict(r) for r in c.execute('SELECT * FROM iepcmp')}


def test_statuses_per_type(cl):
    setup(cl); r = rows()
    assert r[('2.1', 'true_false')]['status'] == 'agrees' and r[('2.1', 'true_false')]['iep'] == 'α: Σωστό' and r[('2.1', 'true_false')]['mine'] == 'Σωστό'
    assert r[('2.1', 'mcq')]['status'] == 'differs' and r[('2.1', 'mcq')]['iep'] == 'α' and r[('2.1', 'mcq')]['mine'].startswith('β')
    assert r[('2.1', 'numeric')]['status'] == 'agrees' and 'στο τέλος' in r[('2.1', 'numeric')]['iep'] and r[('2.1', 'numeric')]['mine'] == '2 A'
    assert r[('2.2', 'mcq')]['status'] == 'agrees' and r[('2.2', 'numeric')]['status'] == 'check' and r[('2.2', 'true_false')]['status'] == 'na' and 'part' in r[('2.2', 'true_false')]['note']
    assert {r[k]['status'] for k in r if k[1] in ('short', 'fill', 'matching')} == {'na'}


def test_numeric_in_middle_is_check_and_tolerance():
    q = {'n': 1, 'type': 'numeric', 'answer': 2.0, 'tolerance': 0.0, 'unit': 'A', 'err': []}; r = {'quiz': [q]}
    assert iepcmp.compare_row(r, '2 A' + ' ' * 300 + 'τέλος')[0]['auto'] == 'check'
    assert iepcmp.compare_row(r, 'x ' * 50 + 'I = 2,00 A')[0]['auto'] == 'agrees'              # κόμμα και σχετική ανοχή
    assert iepcmp.compare_row(r, 'I = 3 A')[0]['auto'] == 'check'


def test_part_field_pairs_true_false_with_letter():
    tf = lambda n, a, part='': {'n': n, 'type': 'true_false', 'answer': a, 'err': [], **({'part': part} if part else {})}
    r = {'quiz': [tf(1, True, 'β'), tf(2, False, 'α')]}; out = iepcmp.compare_row(r, 'α–Λ, β–Σ')
    assert [d['auto'] for d in out] == ['agrees', 'agrees']
    assert [d['auto'] for d in iepcmp.compare_row({'quiz': [tf(1, True), tf(2, True)]}, 'α–Λ, β–Σ')] == ['differs', 'agrees']          # αντιστοίχιση με τη σειρά
    assert iepcmp.compare_row({'quiz': [tf(1, True)]}, 'α–Σ β–Σ')[0]['auto'] == 'na'                                                  # διαφορετικό πλήθος: δεν μαντεύει


def test_qsol_keeps_part_field():
    from app.qsol import check_item
    assert check_item({'type': 'true_false', 'stem': 'x', 'answer': True, 'part': 'β'}, 1)['part'] == 'β'
    assert check_item({'type': 'true_false', 'stem': 'x', 'answer': True, 'part': 'zz'}, 1)['part'] == ''


def test_manual_override_survives_refresh_and_reset(cl):
    setup(cl); k = '1|2.1|1'
    c = sqlite3.connect(os.environ['THILEK_DB']); assert c.execute("SELECT status FROM iepcmp WHERE item_id='1' AND qcode='2.1' AND qn=1").fetchone()[0] == 'differs'
    assert cl.post('/compare/save', data={'k': [k], f'st_{k}': 'agrees', f'nt_{k}': 'το ΙΕΠ έχει λάθος'}, auth=A, headers=H, follow_redirects=False).status_code == 303
    x = c.execute("SELECT status,manual,note,auto FROM iepcmp WHERE item_id='1' AND qcode='2.1' AND qn=1").fetchone(); assert x == ('agrees', 1, 'το ΙΕΠ έχει λάθος', 'differs')
    assert cl.post('/compare/refresh', auth=A, headers=H, follow_redirects=False).status_code == 303                     # νέος υπολογισμός δεν πατά τη χειροκίνητη κρίση
    assert c.execute("SELECT status,manual,note,auto FROM iepcmp WHERE item_id='1' AND qcode='2.1' AND qn=1").fetchone() == ('agrees', 1, 'το ΙΕΠ έχει λάθος', 'differs')
    assert cl.post('/compare/save', data={'k': [k], f'st_{k}': 'differs', f'nt_{k}': 'το ΙΕΠ έχει λάθος'}, auth=A, headers=H, follow_redirects=False).status_code == 303   # επιστροφή στο αυτόματο
    assert c.execute("SELECT status,manual FROM iepcmp WHERE item_id='1' AND qcode='2.1' AND qn=1").fetchone()[1] == 1                                                  # σημείωση παραμένει: χειροκίνητο
    assert cl.post('/compare/save', data={'k': [k], f'st_{k}': 'differs', f'nt_{k}': ''}, auth=A, headers=H, follow_redirects=False).status_code == 303
    assert c.execute("SELECT status,manual FROM iepcmp WHERE item_id='1' AND qcode='2.1' AND qn=1").fetchone() == ('differs', 0)


def test_save_ignores_bad_input_and_pages_security(cl):
    setup(cl); bad = {'k': ['zzz', '1|2.1|x', '9|9|9', '1|2.1|1'], 'st_1|2.1|1': 'hacked'}
    assert cl.post('/compare/save', data=bad, auth=A, headers=H, follow_redirects=False).status_code == 303 and rows()[('2.1', 'true_false')]['status'] == 'agrees'
    assert cl.get('/compare').status_code == 401 and cl.post('/compare/refresh', auth=A, headers={'origin': 'http://evil.example', 'host': 'testserver'}).status_code == 403
    assert cl.post('/compare/save', data={}, auth=A, headers={'origin': 'http://evil.example', 'host': 'testserver'}).status_code == 403
    t = cl.get('/compare?status=differs', auth=A).text; assert 'Σύγκριση με τη λύση ΙΕΠ' in t and 'διαφέρει' in t and "value='agrees'" not in t.split('<table')[0]
    c = cl.get('/compare.csv', auth=A); assert c.status_code == 200 and 'text/csv' in c.headers['content-type'] and 'διαφέρει' in c.content.decode('utf-8-sig') and cl.get('/compare.csv').status_code == 401


def test_refresh_removes_orphans_but_keeps_manual(cl):
    setup(cl); c = sqlite3.connect(os.environ['THILEK_DB'])
    c.execute("INSERT INTO iepcmp(item_id,qcode,qn,kind,status,manual,auto) VALUES('9','1.1',1,'mcq','differs',0,'differs'),('9','1.2',1,'mcq','agrees',1,'differs')"); c.commit()
    cl.post('/compare/refresh', auth=A, headers=H); left = {r[0] for r in c.execute("SELECT item_id||'/'||qcode FROM iepcmp WHERE item_id='9'")}; assert left == {'9/1.2'}


def test_wizard_warns_and_excel_sheet(cl):
    setup(cl); rid = new(cl, 'C'); post(cl, rid, 1, action='add', qids=['1', '2']); post(cl, rid, 4, format='excel', go='next'); post(cl, rid, 5, title='Σ', cmp='1', link_prefix='pdf/', go='next')
    t = cl.get(f'/wizard/{rid}/6', auth=A).text; assert 'ΔΙΑΦΕΡΕΙ από τη λύση ΙΕΠ' in t and 'θέλουν έλεγχο' in t
    wb = openpyxl.load_workbook(io.BytesIO(cl.post(f'/wizard/{rid}/generate', auth=A, headers=H).content)); ws = wb['Σύγκριση ΙΕΠ']
    vals = [[c.value for c in r] for r in ws.iter_rows(min_row=2)]; assert any(v[7] == 'διαφέρει' for v in vals) and any(v[7] == 'συμφωνεί' for v in vals)
    post(cl, rid, 5, title='Σ', link_prefix='pdf/', go='next'); assert 'ΔΙΑΦΕΡΕΙ' not in cl.get(f'/wizard/{rid}/6', auth=A).text
    assert 'Σύγκριση ΙΕΠ' not in openpyxl.load_workbook(io.BytesIO(cl.post(f'/wizard/{rid}/generate', auth=A, headers=H).content)).sheetnames
