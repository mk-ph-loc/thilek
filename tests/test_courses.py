"""0.26.0: ενεργό μάθημα, πηγές θεμάτων (ΙΕΠ/πανελλήνιες/δικά μου), θέματα χωρίς PDF, rebuild, ρύθμιση embed."""
import io, json, os, pathlib, sqlite3
import openpyxl
from tests.test_docs import cl, A, H  # noqa: F401
from tests.test_wizard import seed, new, post
from app import settings, library


def own(cl, src='OWN', course='C', qs=(('2.1', '5', 'problem', 'Υπολόγισε το $I$.'), ('2.2', '5', 'fill', 'Συμπλήρωσε.')), item='', **kw):
    d = {'item': item, 'course': course, 'source': src, 'title': 'Δοκιμή', 'year': '2025', 'note': '', **kw}
    for i, (c_, p, t, x) in enumerate(qs): d.update({f'qc_{i}': c_, f'qp_{i}': p, f'qt_{i}': t, f'qx_{i}': x})
    return cl.post('/own/save', data=d, auth=A, headers=H, follow_redirects=False)


def db():
    c = sqlite3.connect(os.environ['THILEK_DB']); c.row_factory = sqlite3.Row; return c


def test_create_own_and_pan_ids_and_lists(cl):
    assert own(cl).status_code == 303 and own(cl).status_code == 303 and own(cl, 'PAN').status_code == 303
    ids = [r[0] for r in db().execute("SELECT id FROM item WHERE source!='TTDD' ORDER BY source,id")]; assert ids == ['900001', '900002', '800001']
    r = db().execute("SELECT * FROM question WHERE item_id='900001' AND code='2.1'").fetchone(); assert r['points'] == 5 and r['qtype'] == 'problem' and r['text'] == 'Υπολόγισε το $I$.'
    t = cl.get('/own', auth=A).text; assert '900001' in t and 'Πανελλήνιες' in t and 'Δοκιμή' in t
    assert '800001' not in cl.get('/own?src=OWN', auth=A).text and cl.get('/own/900001', auth=A).status_code == 200 and cl.get('/own/new?source=PAN', auth=A).status_code == 200
    assert cl.get('/own/1', auth=A).status_code == 404                                         # θέμα ΙΕΠ δεν επεξεργάζεται από εδώ


def test_edit_update_delete_question_and_validation(cl):
    own(cl); assert own(cl, item='900001', qs=(('2.1', '6', 'problem', 'Νέο κείμενο'),)).status_code == 303
    qs = {r['code']: r for r in db().execute("SELECT * FROM question WHERE item_id='900001'")}; assert set(qs) == {'2.1'} and qs['2.1']['points'] == 6 and qs['2.1']['text'] == 'Νέο κείμενο'
    for bad in (dict(qs=(('x', '5', '', 'a'),)), dict(qs=(('2.1', 'x', '', 'a'),)), dict(qs=(('2.1', '5', 'zzz', 'a'),)), dict(qs=(('2.1', '5', '', 'a'), ('2.1', '5', '', 'b'))), dict(src='XX'), dict(course='NOPE')):
        assert own(cl, item='900001', **bad).status_code == 422
    assert own(cl, item='1').status_code == 422                                                 # δεν αλλάζει θέμα ΙΕΠ
    assert db().execute("SELECT source FROM item WHERE id='1'").fetchone()[0] == 'TTDD'
    assert cl.post('/own/900001/delete', data={'confirm': 'ναι'}, auth=A, headers=H).status_code == 422
    assert cl.post('/own/900001/delete', data={'confirm': 'ΔΙΑΓΡΑΦΗ'}, auth=A, headers=H, follow_redirects=False).status_code == 303
    assert not db().execute("SELECT 1 FROM item WHERE id='900001'").fetchone() and not db().execute("SELECT 1 FROM question WHERE item_id='900001'").fetchone()
    assert cl.post('/own/1/delete', data={'confirm': 'ΔΙΑΓΡΑΦΗ'}, auth=A, headers=H).status_code == 404


def test_security_auth_and_origin(cl):
    assert cl.get('/own').status_code == 401 and cl.get('/courses').status_code == 401
    ev = {'origin': 'http://evil.example', 'host': 'testserver'}
    assert cl.post('/own/save', data={}, auth=A, headers=ev).status_code == 403 and cl.post('/courses/select', data={'code': ''}, auth=A, headers=ev).status_code == 403
    assert cl.post('/own/1/delete', data={'confirm': 'ΔΙΑΓΡΑΦΗ'}, auth=A, headers=ev).status_code == 403
    assert own(cl, title="<script>x</script>").status_code == 303 and '<script>x' not in cl.get('/own/900001', auth=A).text and '<script>x' not in cl.get('/own', auth=A).text and '&lt;script&gt;x' in cl.get('/own', auth=A).text


def test_source_filter_and_active_course(cl):
    seed(2); own(cl); own(cl, 'PAN')
    c = db(); f = lambda **k: {r['item_id'] for r in library.select_questions(c, {'qtype': [], **k})}
    assert f() == {'1', '900001', '800001'} and f(src='OWN') == {'900001'} and f(src='PAN') == {'800001'} and f(src='TTDD') == {'1'} and f(src='zz') == {'1', '900001', '800001'}
    c.execute("INSERT INTO course VALUES('D','Άλλο','','TTDD')"); c.commit(); own(cl, course='D'); assert len(f()) == 4
    assert cl.post('/courses/select', data={'code': 'D'}, auth=A, headers=H, follow_redirects=False).status_code == 303
    assert f() == {'900002'} and 'ενεργό' in cl.get('/courses', auth=A).text
    assert cl.post('/courses/select', data={'code': 'NOPE'}, auth=A, headers=H).status_code == 422 and f() == {'900002'}
    assert cl.post('/courses/select', data={'code': ''}, auth=A, headers=H, follow_redirects=False).status_code == 303 and len(f()) == 4
    c.execute("INSERT OR REPLACE INTO setting VALUES('course_active','GONE')"); c.commit(); assert len(f()) == 4              # άγνωστο ενεργό μάθημα αγνοείται
    assert '900001' in cl.get('/browse?src=OWN', auth=A).text and '800001' not in cl.get('/browse?src=OWN', auth=A).text


def test_own_items_work_in_review_wizard_excel_and_exam(cl):
    own(cl, qs=(('1', '10', 'problem', 'Πρώτο $R=2\\,\\Omega$'), ('2', '10', 'problem', 'Δεύτερο')))
    for p in ('/review/900001', '/browse', '/q/start?src=OWN', '/lyseis', '/compare', '/courses', '/wizard'): assert cl.get(p, auth=A).status_code in (200, 303), p
    rid = new(cl, 'Δικά'); post(cl, rid, 1, action='add', qids=[str(r['id']) for r in db().execute("SELECT id FROM question WHERE item_id='900001'")])
    post(cl, rid, 4, format='excel', go='next'); post(cl, rid, 5, title='Σ', link_prefix='pdf/', go='next')
    wb = openpyxl.load_workbook(io.BytesIO(cl.post(f'/wizard/{rid}/generate', auth=A, headers=H).content)); vals = [[c.value for c in r] for r in wb['Ερωτήματα'].iter_rows()]
    assert any('900001' in str(r) for r in vals)
    post(cl, rid, 4, format='md', go='next'); assert cl.post(f'/wizard/{rid}/generate', auth=A, headers=H).status_code == 200


def test_wizard_source_criterion_and_default_on(cl):
    seed(2); own(cl); rid = new(cl); assert 'name=src' in cl.get(f'/wizard/{rid}/1', auth=A).text
    t = cl.get(f'/wizard/{rid}/1?src=OWN', auth=A).text; assert '900001' in t and 'ερώτημα 1' not in t


def test_settings_embed_domains_and_course_active_validation(cl):
    assert settings.valid('embed_domains', 'youtube.com,geogebra.org') and settings.valid('embed_domains', '') and not settings.valid('embed_domains', 'http://x.com') and not settings.valid('embed_domains', 'a b.com')
    assert not settings.valid('embed_domains', 'evil.com/path') and not settings.valid('embed_domains', '"><script>.com')
    assert settings.valid('course_active', '') and settings.valid('course_active', 'B-ILEK') and not settings.valid('course_active', '../x')
    assert 'youtube.com' in settings.get('embed_domains')
    cl.post('/settings', data={'embed_domains': 'youtube.com, falstad.com'}, auth=A, headers=H); assert 'youtube.com' in settings.get('embed_domains')
    cl.post('/settings', data={'embed_domains': 'bad domain'}, auth=A, headers=H); assert settings.get('embed_domains') != 'bad domain'
    assert 'embed_domains' in cl.get('/settings', auth=A).text


def test_migration_5_and_schema_agree(cl):
    from app import migrations as m
    assert m.LATEST == 5 and db().execute('SELECT version FROM schema_version').fetchone()[0] == 5 and db().execute("SELECT 1 FROM sqlite_master WHERE name='ownitem'").fetchone()
    c = sqlite3.connect(':memory:'); c.execute('CREATE TABLE schema_version(version INTEGER)'); c.execute('INSERT INTO schema_version VALUES(4)'); m._v5(c); m._v5(c)
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name='ownitem'").fetchone()


def test_rebuild_keeps_own_and_pan_items(tmp_path):
    import sys, subprocess, shutil
    root = tmp_path / 'data'; (root / 'EXTRA').mkdir(parents=True); db_path = tmp_path / 'x.db'
    (root / 'courses.json').write_text(json.dumps([{'code': 'EXTRA', 'title': 'Άλλο μάθημα', 'own_only': True}, {'code': '../bad', 'title': 'x', 'own_only': True}, {'code': 'NOKEYS', 'title': 'y'}]), encoding='utf-8')
    here = pathlib.Path(__file__).resolve().parent.parent; sys.path.insert(0, str(here / 'tools'))
    import rebuild
    rebuild.main(str(root), str(db_path)); c = sqlite3.connect(db_path); assert [r[0] for r in c.execute('SELECT code FROM course')] == ['EXTRA']
    c.execute("INSERT INTO item(id,course_code,source,solution_status) VALUES('900001','EXTRA','OWN','own'),('800001','GONE','PAN','own')"); c.execute("INSERT INTO ownitem VALUES('900001','Τίτλος','2025','σημ')")
    c.execute("INSERT INTO question(item_id,code,points,text,qtype,qtype_origin) VALUES('900001','1',7,'κείμενο','problem','manual'),('800001','1',3,'x','problem','manual')"); c.commit(); c.close()
    rebuild.main(str(root), str(db_path)); c = sqlite3.connect(db_path)
    assert c.execute("SELECT course_code,source FROM item WHERE id='900001'").fetchone() == ('EXTRA', 'OWN') and c.execute("SELECT points,text FROM question WHERE item_id='900001'").fetchone() == (7, 'κείμενο')
    assert c.execute("SELECT title FROM ownitem WHERE item_id='900001'").fetchone() == ('Τίτλος',) and not c.execute("SELECT 1 FROM item WHERE id='800001'").fetchone()     # θέμα σε μάθημα που λείπει: όχι μεταφορά
