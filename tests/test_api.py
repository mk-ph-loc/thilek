import pathlib, sqlite3, pytest
from fastapi.testclient import TestClient
SCHEMA = pathlib.Path(__file__).parent.parent / 'app' / 'schema.sql'

@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / 't.db'; root = tmp_path / 'data'; (root / 'C').mkdir(parents=True); (root / 'C' / 'a.pdf').write_bytes(b'%PDF')
    c = sqlite3.connect(db); c.executescript(SCHEMA.read_text(encoding='utf-8'))
    c.execute("INSERT INTO course VALUES('C','Test','B','TTDD')"); c.execute("INSERT INTO book(id,course_code,pdf_offset) VALUES(1,'C',1)")
    c.execute("INSERT INTO section(id,book_id,code,level,title_el,page_from,page_to) VALUES(1,1,'4.1',2,'Ενότητα 4.1',266,292)")
    c.execute("INSERT INTO item(id,course_code,source,position,iep_yli,solution_status) VALUES('1','C','TTDD',2,'4.1 Το ηλεκτρικό πεδίο','ok')")
    c.execute("INSERT INTO question(id,item_id,code,points,text) VALUES(1,'1','2.1',15,'q')"); c.execute("INSERT INTO question_section(question_id,section_id,origin) VALUES(1,1,'iep')")
    c.execute("INSERT INTO section(id,book_id,code,level,title_el,page_from,page_to) VALUES(2,1,'4.1.2',3,'Ένταση',300,310)")
    c.execute("INSERT INTO question_section(question_id,section_id,origin,score) VALUES(1,2,'auto',0.3)")
    c.commit(); c.close()
    monkeypatch.setenv('THILEK_DB', str(db)); monkeypatch.setenv('THILEK_ROOT', str(root)); monkeypatch.setenv('THILEK_PASSWORD', 'pw')
    monkeypatch.setenv('THILEK_CONFIG', str(tmp_path / 'none.yaml'))
    from app.main import app
    return TestClient(app)

A = ('admin', 'pw')
def test_health_open(client): assert client.get('/health').json()['ok'] is True
def test_auth_required(client): assert client.get('/items').status_code == 401
def test_items_filter(client): assert [i['id'] for i in client.get('/items?yli=4.1', auth=A).json()] == ['1']
def test_page_to_items(client):
    r = client.get('/pages/270', auth=A).json(); assert r['sections'][0]['code'] == '4.1' and r['items'][0]['id'] == '1'
def test_page_outside(client): assert client.get('/pages/5', auth=A).json()['items'] == []
def test_files_ok_and_traversal(client):
    assert client.get('/files/C/a.pdf', auth=A).status_code == 200
    assert client.get('/files/..%2F..%2Fetc%2Fpasswd', auth=A).status_code == 404

H = {'origin': 'http://testserver', 'host': 'testserver'}
def test_review_pages(client):
    assert client.get('/review', auth=A).status_code == 200 and '>1<' in client.get('/review', auth=A).text
    r = client.get('/review/1', auth=A); assert r.status_code == 200 and '4.1.2' in r.text and 'confirm:2' in r.text
def test_review_requires_auth(client): assert client.get('/review').status_code == 401
def test_confirm_sets_manual(client):
    r = client.post('/review/1/link', data={'question_id': 1, 'action': 'confirm:2'}, auth=A, headers=H, follow_redirects=False)
    assert r.status_code == 303
    assert {s['origin'] for s in client.get('/items/1', auth=A).json()['questions'][0]['sections']} >= {'manual'}
def test_post_without_same_origin_is_rejected(client):
    assert client.post('/review/1/link', data={'question_id': 1, 'action': 'confirm:2'}, auth=A, headers={'origin': 'http://evil.example', 'host': 'testserver'}).status_code == 403
def test_remove_hides_link_from_api(client):
    client.post('/review/1/link', data={'question_id': 1, 'action': 'remove:2'}, auth=A, headers=H)
    assert all(s['code'] != '4.1.2' for s in client.get('/items/1', auth=A).json()['questions'][0]['sections'])
def test_add_manual_rejects_auto(client):
    client.post('/review/1/link', data={'question_id': 1, 'action': 'add', 'section_id': '1'}, auth=A, headers=H)
    sec = client.get('/items/1', auth=A).json()['questions'][0]['sections']; assert all(s['origin'] != 'auto' for s in sec) and any(s['origin'] == 'manual' for s in sec)

def test_questions_filter_and_type_edit(client):
    assert client.get('/questions?qtype=mcq', auth=A).json() == []
    H = {'Origin': 'http://testserver', 'host': 'testserver'}
    r = client.post('/review/1/meta', data={'question_id': 1, 'qtype': 'mcq', 'has_image': '1'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    q = client.get('/questions?qtype=mcq&has_image=1&section=4.1', auth=A).json(); assert [x['code'] for x in q] == ['2.1']
def test_bad_type_rejected(client):
    H = {'Origin': 'http://testserver'}
    assert client.post('/review/1/meta', data={'question_id': 1, 'qtype': 'xx'}, auth=A, headers=H).status_code == 422
def test_questions_html_page(client): assert client.get('/browse?qtype=development', auth=A).status_code == 200

def test_static_js_and_sortable_markup(client):
    r = client.get('/static/app.js'); assert r.status_code == 200 and 'sort' in r.text
    assert "/static/app.js" in client.get('/review', auth=A).text
def _two_items(client):
    import sqlite3, os
    c = sqlite3.connect(os.environ['THILEK_DB']); c.execute("INSERT INTO item(id,course_code,source,position,iep_yli,solution_status,solution_path,statement_path) VALUES('2','C','TTDD',4,'4.1 x','ok','C/a.pdf','C/a.pdf')"); c.commit(); c.close()
def test_prev_next_and_panes(client):
    _two_items(client)
    h = client.get('/review/1?yli=4.1', auth=A).text
    assert "rel=next href='/review/2?yli=4.1'" in h and 'rel=prev' not in h
    h2 = client.get('/review/2?view=sol,book&bp=267', auth=A).text
    assert 'rel=prev' in h2 and 'Λύση' in h2 and '#page=267' in h2
def test_context_survives_post(client):
    H = {'Origin': 'http://testserver'}
    r = client.post('/review/1/meta', data={'question_id': 1, 'qtype': 'fill', 'ctx': 'view=sol%2Cbook&bp=300&evil=1'}, auth=A, headers=H, follow_redirects=False)
    assert r.headers['location'] == '/review/1?view=sol%2Cbook&bp=300'

def _make_pdf(path, n):
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(n): w.add_blank_page(width=200, height=200)
    w.write(path)
def test_merge_pdf(client, tmp_path):
    import sqlite3, os
    root = tmp_path / 'data'; _make_pdf(str(root / 'C' / 'a.pdf'), 2); _make_pdf(str(root / 'C' / 'b.pdf'), 1); _make_pdf(str(root / 'C' / 'book.pdf'), 400)
    c = sqlite3.connect(os.environ['THILEK_DB'])
    c.execute("UPDATE item SET statement_path='C/a.pdf', solution_path='C/b.pdf' WHERE id='1'"); c.execute("UPDATE book SET relpath='C/book.pdf' WHERE id=1"); c.commit(); c.close()
    H = {'Origin': 'http://testserver'}
    assert client.get('/tools/merge', auth=A).status_code == 200
    r = client.post('/tools/merge', data={'ids': ['1'], 'sol': '1'}, auth=A, headers=H); assert r.status_code == 200 and r.headers['x-pages'] == '3' and r.content[:4] == b'%PDF'
    # βιβλίο: υποενότητα 4.1.2 (σελ. 300–310), cap 3 → 300,301,302 + έξτρα 10-11
    r = client.post('/tools/merge', data={'ids': ['1'], 'book': '1', 'cap': '3', 'extra': '10-11'}, auth=A, headers=H); assert r.headers['x-pages'] == '2 + 3'.replace('2 + 3', '7')
    assert client.post('/tools/merge', data={'ids': ['1'], 'extra': 'abc'}, auth=A, headers=H).status_code == 422
    assert client.post('/tools/merge', data={}, auth=A, headers=H).status_code == 422
    assert client.post('/tools/merge', data={'ids': ['1']}, auth=A).status_code == 403
    assert client.post('/tools/merge', data={'ids': ['999']}, auth=A, headers=H).status_code == 422

def test_html_export(client, tmp_path):
    import sqlite3, os
    root = tmp_path / 'data'; _make_pdf(str(root / 'C' / 'a.pdf'), 2); _make_pdf(str(root / 'C' / 'b.pdf'), 1); _make_pdf(str(root / 'C' / 'book.pdf'), 400)
    c = sqlite3.connect(os.environ['THILEK_DB'])
    c.execute("UPDATE item SET statement_path='C/a.pdf', solution_path='C/b.pdf' WHERE id='1'"); c.execute("UPDATE book SET relpath='C/book.pdf' WHERE id=1"); c.commit(); c.close()
    H = {'Origin': 'http://testserver'}
    assert client.get('/tools/html', auth=A).status_code == 200
    r = client.post('/tools/html', data={'ids': ['1'], 'sol': '1', 'book': '1', 'cap': '2', 'meta': '1', 'title': '<b>x</b>'}, auth=A, headers=H)
    assert r.status_code == 200 and r.text.count('data:image/jpeg;base64,') == 5 and '<b>x</b>' not in r.text and '&lt;b&gt;' in r.text and '<details>' in r.text
    assert client.post('/tools/html', data={'ids': ['1']}, auth=A).status_code == 403
    assert client.post('/tools/html', data={}, auth=A, headers=H).status_code == 422

def _exam_setup(client, tmp_path):
    import sqlite3, os, json
    root = tmp_path / 'data'; _make_pdf(str(root / 'C' / 'a.pdf'), 1)
    geo = json.dumps({'regions': [{'p': 1, 'x0': 10, 'x1': 190, 'y0': 10, 'y1': 100}], 'mask': [1, 10, 10, 30, 20]})
    c = sqlite3.connect(os.environ['THILEK_DB'])
    c.execute("UPDATE item SET statement_path='C/a.pdf' WHERE id='1'"); c.execute("UPDATE question SET geo=?, qtype='mcq' WHERE id=1", (geo,))
    c.execute("INSERT INTO item(id,course_code,source,position,iep_yli) VALUES('2','C','TTDD',2,'4.1 y')")
    c.execute("INSERT INTO question(id,item_id,code,points,text,qtype,geo) VALUES(2,'2','2.1',10,'q2','mcq',?)", (geo,)); c.commit(); c.close()
    H = {'Origin': 'http://testserver'}
    r = client.post('/exams/new', data={'title': 'T <i>', 'class_name': 'B1'}, auth=A, headers=H, follow_redirects=False); assert r.headers['location'] == '/exams/1'
    return H
def test_exam_flow(client, tmp_path):
    H = _exam_setup(client, tmp_path)
    assert client.post('/exams/1/add', data={'qids': ['1', '2', '1'], 'grp': '1'}, auth=A, headers=H, follow_redirects=False).status_code == 303
    assert client.post('/exams/1/add', data={'qids': ['1'], 'grp': '2'}, auth=A, headers=H).status_code == 200      # διπλό: δεν προστίθεται ξανά
    p = client.get('/exams/1', auth=A).text; assert '<h3>Θέμα Α <small>(25 μονάδες)' in p and '<h3>Θέμα Β' not in p and 'T &lt;i&gt;' in p
    client.post('/exams/1/move', data={'item_id': '2', 'qcode': '2.1', 'action': 'up'}, auth=A, headers=H)
    client.post('/exams/1/move', data={'item_id': '1', 'qcode': '2.1', 'action': 'group', 'newgrp': '2'}, auth=A, headers=H)
    pr = client.get('/exams/1/print', auth=A).text; assert 'ΘΕΜΑ Α' in pr and 'ΘΕΜΑ Β' in pr and pr.count('/crop/') == 2
    j = client.get('/crop/1.jpg', auth=A); assert j.status_code == 200 and j.content[:2] == b'\xff\xd8'
    assert client.get('/crop/1.jpg?sol=1', auth=A).status_code == 404
    client.post('/exams/1/move', data={'item_id': '1', 'qcode': '2.1', 'action': 'remove'}, auth=A, headers=H)
    assert 'ΘΕΜΑ Β' not in client.get('/exams/1/print', auth=A).text
def test_exam_generate(client, tmp_path):
    H = _exam_setup(client, tmp_path)
    r = client.post('/exams/1/generate', data={'qtype': ['mcq'], 'target': '10', 'grp': '1', 'seed': '1'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    assert 'ΘΕΜΑ Α' in client.get('/exams/1/print', auth=A).text
    r = client.post('/exams/1/generate', data={'grp': '1'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
def test_exam_requires_origin_and_auth(client, tmp_path):
    _exam_setup(client, tmp_path)
    assert client.post('/exams/new', data={'title': 'x'}, auth=A).status_code == 403
    assert client.get('/exams').status_code == 401 and client.get('/crop/1.jpg').status_code == 401
def test_browse_exam_mode(client, tmp_path):
    _exam_setup(client, tmp_path)
    h = client.get('/browse?exam=1', auth=A).text; assert "action='/select/act'" in h and 'name=qids' in h and 'selected' in h

def test_coverage_by_page(client, tmp_path):
    _exam_setup(client, tmp_path)
    h = client.get('/coverage?upto=320', auth=A).text; assert 'name=qids value=1' in h and 'name=qids value=2' not in h and 'name=ids value=\'1\'' in h
    assert 'name=qids value=1' not in client.get('/coverage?upto=305', auth=A).text             # η υποενότητα 300-307 δεν έχει τελειώσει
    assert 'name=qids value=1' in client.get('/coverage?upto=305&mode=started', auth=A).text
    assert 'name=qids value=1' not in client.get('/coverage?upto=320&frm=305', auth=A).text      # ξεκινά πριν τη σελίδα 305
    assert client.get('/coverage', auth=A).status_code == 200
def test_tags_and_keyword_filters(client, tmp_path):
    H = _exam_setup(client, tmp_path)
    r = client.post('/select/act', data={'act': 'tag', 'qids': ['1', '2'], 'tag': ' Νόμος Ohm , επανάληψη', 'back': '/browse'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303 and r.headers['location'] == '/browse'
    assert 'νόμος ohm' in client.get('/tags', auth=A).text
    h = client.get('/browse?tag=επανάληψη', auth=A).text; assert 'name=qids value=1' in h and 'name=qids value=2' in h
    client.post('/select/act', data={'act': 'untag', 'qids': ['2'], 'tag': 'επανάληψη'}, auth=A, headers=H)
    h = client.get('/browse?tag=επανάληψη', auth=A).text; assert 'name=qids value=2' not in h and 'name=qids value=1' in h
    assert 'name=qids value=1' in client.get('/browse?tag=επανάληψη,νόμος ohm&tagmode=all', auth=A).text
    assert 'name=qids value=2' not in client.get('/browse?tag=επανάληψη,νόμος ohm&tagmode=all', auth=A).text
    assert 'name=qids value=1' in client.get('/browse?q=Q', auth=A).text                           # κείμενο «q» (ανεξάρτητα από πεζά)
    assert 'name=qids value=1' not in client.get('/browse?q=ΑΔΥΝΑΤΟ', auth=A).text
    assert client.post('/select/act', data={'act': 'tag', 'qids': ['1'], 'tag': ''}, auth=A, headers=H).status_code == 422
def test_act_exam_save_doc_merge(client, tmp_path):
    H = _exam_setup(client, tmp_path)
    r = client.post('/select/act', data={'act': 'exam', 'ids': ['1'], 'exam_id': '1', 'grp': '2'}, auth=A, headers=H, follow_redirects=False); assert r.headers['location'] == '/exams/1'
    assert '<h3>Θέμα Β' in client.get('/exams/1', auth=A).text
    crit = '{"type":"coverage","filters":{"upto":"320","mode":"full","cap":"8","frm":"0"}}'
    r = client.post('/select/act', data={'act': 'save', 'qids': ['1'], 'name': 'Μέχρι 320', 'criteria': crit, 'title': 'Έγγραφο', 'solutions': '1'}, auth=A, headers=H, follow_redirects=False); assert r.headers['location'] == '/collections/1'
    page = client.get('/collections/1', auth=A).text; assert 'Μέχρι 320' in page and 'upto' in page and 'name=qids value=1' in page
    s = client.get('/saved', auth=A).text; assert 'Μέχρι 320' in s and 'συλλογή' in s and 'διαγώνισμα' in s
    d = client.get('/collections/1/doc', auth=A).text; assert '/crop/1.jpg' in d and 'Απαντήσεις' in d
    r = client.post('/select/act', data={'act': 'doc', 'qids': ['1', '2'], 'title': 'T', 'numbering': 'source', 'group': 'unit'}, auth=A, headers=H); assert r.status_code == 200 and 'Ενότητα 4.1' in r.text and 'θέμα 1 ερ. 2.1' in r.text
    r = client.post('/select/act', data={'act': 'merge', 'ids': ['1']}, auth=A, headers=H); assert r.status_code == 200 and r.content[:4] == b'%PDF'
    r = client.post('/collections/1/savefile', auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    assert (tmp_path / 'data' / 'C' / '07_EXAGOGES').is_dir() and 'data:image/jpeg;base64' in next((tmp_path / 'data' / 'C' / '07_EXAGOGES').iterdir()).read_text()
    assert 'αρχείο' in client.get('/saved', auth=A).text
    client.post('/collections/1/rerun', auth=A, headers=H); assert 'name=qids value=1' in client.get('/collections/1', auth=A).text
    client.post('/collections/1/rename', data={'name': 'Νέο'}, auth=A, headers=H); assert 'Νέο' in client.get('/saved', auth=A).text
    client.post('/collections/1/delete', auth=A, headers=H); assert 'Νέο' not in client.get('/saved', auth=A).text
def test_act_requires_selection_and_origin(client, tmp_path):
    H = _exam_setup(client, tmp_path)
    assert client.post('/select/act', data={'act': 'doc'}, auth=A, headers=H).status_code == 422
    assert client.post('/select/act', data={'act': 'tag', 'qids': ['1'], 'tag': 'x'}, auth=A).status_code == 403

def test_themes_and_scroll(client):
    assert 'data-theme' in client.get('/static/theme.js').text
    h = client.get('/review', auth=A).text
    assert "id=theme" in h and "/static/theme.js" in h and 'class=scroll' in h
    assert 'class=filters' in h

def test_quizgen_parsing():
    from app.quizgen import split_parts, tf_answers, mcq_answer, make_items
    t = "2.1 Να χαρακτηρίσετε.\nα. Πρώτη.\nβ. Δεύτερη\n   συνέχεια.\nγ. Τρίτη.\n(Μονάδες 15)"
    intro, parts = split_parts(t); assert [p[0] for p in parts] == ['α', 'β', 'γ']
    assert tf_answers("2.1\nα–Σ\nβ – Λ\nγ-Σωστό\nστ – Λάθος") == {'α': 'Σωστό', 'β': 'Λάθος', 'γ': 'Σωστό', 'στ': 'Λάθος'}
    its = make_items({'item_id': '1', 'code': '2.1', 'points': 15, 'text': t, 'qtype': 'true_false', 'sol_text': "2.1\nα–Σ\nβ – Λ"})
    assert [i['answer'] for i in its] == ['Σωστό', 'Λάθος', ''] and [i['status'] for i in its] == ['ok', 'ok', 'review'] and its[1]['stem'] == 'Δεύτερη συνέχεια.' and its[0]['points'] == 5
    m = make_items({'item_id': '1', 'code': '2.2.1', 'points': 5, 'text': "2.2.1 Αν η τάση διπλασιαστεί:\nα. x\nβ. y\nγ. z\nΜονάδες 5", 'qtype': 'mcq', 'sol_text': '2.2.1\nβ'})
    assert m[0]['kind'] == 'mcq' and m[0]['answer'] == '1' and m[0]['stem'] == 'Αν η τάση διπλασιαστεί:'
    f = make_items({'item_id': '1', 'code': '4.1', 'points': 25, 'text': '4.1 Να υπολογίσετε', 'qtype': 'problem', 'sol_text': '4.1\nR = 5 Ω'})
    assert f[0]['kind'] == 'free' and f[0]['answer'] == 'R = 5 Ω' and f[0]['status'] == 'review'
    g = make_items({'item_id': '1', 'code': '2.1', 'points': 5, 'text': "2.1 Σ/Λ\nα. 𝑉𝑉 είναι\nβ. άλλο", 'qtype': 'true_false', 'sol_text': 'α–Σ β–Λ'}); assert g[0]['status'] == 'review' and g[1]['status'] == 'ok'
def test_quiz_flow(client, tmp_path):
    H = _exam_setup(client, tmp_path)
    import sqlite3, os
    c = sqlite3.connect(os.environ['THILEK_DB']); c.execute("UPDATE question SET qtype='true_false', text=?, sol_text=? WHERE id=1", ("2.1 Σ/Λ\nα. Ένα.\nβ. Δύο.\n(Μονάδες 15)", "2.1\nα–Σ\nβ–Λ")); c.commit(); c.close()
    r = client.post('/select/act', data={'act': 'quiz', 'qids': ['1'], 'quiz_name': 'Δοκιμαστικό'}, auth=A, headers=H, follow_redirects=False); assert r.headers['location'] == '/quizzes/1'
    p = client.get('/quizzes/1', auth=A).text; assert 'Δοκιμαστικό' in p and 'Ένα.' in p and 'Σωστό' in p
    j = client.get('/quizzes/1/json', auth=A).json(); assert [i['correct'] for i in j['items']] == ['Σωστό', 'Λάθος'] and j['items'][0]['points'] == 7.5
    play = client.get('/quizzes/1/play', auth=A).text; assert "data-answer='Σωστό'" in play and '/static/quiz.js' in play and client.get('/static/quiz.js').status_code == 200
    assert '☒ Σωστό' in client.get('/quizzes/1/print?key=1', auth=A).text and '☒' not in client.get('/quizzes/1/print', auth=A).text
    iid = j and 1
    r = client.post('/quizzes/1/item/2', data={'action': 'save', 'kind': 'mcq', 'stem': 'Ποιο;', 'options': 'α\nβ\nγ', 'answer': '2', 'points': '3', 'feedback': 'ΟΚ'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    j = client.get('/quizzes/1/json', auth=A).json(); assert j['items'][1]['kind'] == 'mcq' and j['items'][1]['correct_index'] == 2 and j['items'][1]['options'] == ['α', 'β', 'γ']
    client.post('/quizzes/1/item/2', data={'action': 'up'}, auth=A, headers=H); assert client.get('/quizzes/1/json', auth=A).json()['items'][0]['kind'] == 'mcq'
    client.post('/quizzes/1/additem', data={'kind': 'free'}, auth=A, headers=H); assert len(client.get('/quizzes/1/json', auth=A).json()['items']) == 3
    assert 'quiz' in client.get('/saved', auth=A).text and 'Δοκιμαστικό' in client.get('/saved', auth=A).text
    assert client.post('/quizzes/1/item/2', data={'action': 'save', 'kind': 'xx'}, auth=A, headers=H).status_code == 422
    assert client.post('/quizzes/new', data={'name': 'x'}, auth=A).status_code == 403
    client.post('/quizzes/1/delete', auth=A, headers=H); assert client.get('/quizzes/1', auth=A).status_code == 404

def test_markdown_docs_and_word(client, tmp_path):
    H = _exam_setup(client, tmp_path)
    client.post('/exams/1/add', data={'qids': ['1', '2'], 'grp': '1'}, auth=A, headers=H)
    r = client.post('/docs/from', data={'kind': 'exam', 'ref': '1', 'mode': 'both'}, auth=A, headers=H, follow_redirects=False); assert r.headers['location'] == '/docs/1'
    md = client.get('/docs/1/md', auth=A).text; assert '# T <i>' in md and '## ΘΕΜΑ Α' in md and '![](/crop/1.jpg)' in md and '**Α1.**' in md and '**Α2.**' in md
    page = client.get('/docs/1', auth=A).text; assert 'id=md' in page and '/static/md.js' in page and client.get('/static/md.js').status_code == 200
    # ζωντανή προεπισκόπηση: html απενεργοποιημένο, εικόνες μόνο του συστήματος
    h = client.post('/docs/render', data={'md': '# Τίτλος\n\n<script>alert(1)</script>\n\n**έντονο** ![x](/crop/1.jpg) ![y](http://evil/x.png)\n\n| a | b |\n|---|---|\n| 1 | 2 |'}, auth=A, headers=H).text
    assert '<h1>Τίτλος</h1>' in h and '<script>' not in h and '<strong>έντονο</strong>' in h and "src='/crop/1.jpg'" in h and 'evil' not in h and '<table>' in h
    client.post('/docs/1/save', data={'name': 'Νέο όνομα', 'md': "# Έγγραφο\n\nΚείμενο με **έντονο** και *πλάγιο*.\n\n- α\n- β\n\n1. ένα\n2. δύο\n\n\\newpage\n\n| Στήλη | Τιμή |\n|---|---|\n| x | 1 |\n\n![](/crop/1.jpg)\n\n> παράθεση\n"}, auth=A, headers=H, follow_redirects=False)
    r = client.get('/docs/1/docx', auth=A); assert r.status_code == 200 and r.content[:2] == b'PK'
    from docx import Document; import io
    d = Document(io.BytesIO(r.content)); txt = '\n'.join(p.text for p in d.paragraphs)
    assert 'Έγγραφο' in txt and 'έντονο' in txt and 'παράθεση' in txt and len(d.tables) == 1 and len(d.inline_shapes) == 1
    assert any(r.bold for p in d.paragraphs for r in p.runs if r.text == 'έντονο')
    assert client.get('/docs/1/html', auth=A).text.count('data:image/jpeg;base64') == 1
    assert client.get('/exams/1/docx', auth=A).content[:2] == b'PK'
    assert 'Νέο όνομα' in client.get('/docs', auth=A).text
    up = client.post('/docs/upload', files={'file': ('x.md', '# Από αρχείο\n'.encode(), 'text/markdown')}, auth=A, headers=H, follow_redirects=False); assert up.headers['location'] == '/docs/2'
    assert client.post('/docs/render', data={'md': 'x'}, auth=A).status_code == 403
    r = client.post('/select/act', data={'act': 'md', 'qids': ['1'], 'title': 'Από επιλογή', 'mdmode': 'text'}, auth=A, headers=H, follow_redirects=False); assert r.headers['location'] == '/docs/3'
def test_quiz_to_markdown_and_word(client, tmp_path):
    H = _exam_setup(client, tmp_path)
    client.post('/quizzes/new', data={'name': 'Q'}, auth=A, headers=H); client.post('/quizzes/1/additem', data={'kind': 'mcq'}, auth=A, headers=H)
    client.post('/quizzes/1/item/1', data={'action': 'save', 'kind': 'mcq', 'stem': 'Ποιο;', 'options': 'α1\nβ1', 'answer': '1', 'points': '2'}, auth=A, headers=H)
    assert client.get('/quizzes/1/docx', auth=A).content[:2] == b'PK'
    client.post('/docs/from', data={'kind': 'quiz', 'ref': '1'}, auth=A, headers=H); md = client.get('/docs/1/md', auth=A).text
    assert '**1.** Ποιο;' in md and '- β. β1' in md and 'Σωστή απάντηση: β. β1' in md
def test_item_preview_and_hover_js(client, tmp_path):
    _exam_setup(client, tmp_path)
    r = client.get('/preview/1.jpg', auth=A); assert r.status_code == 200 and r.content[:2] == b'\xff\xd8'
    assert client.get('/preview/abc.jpg', auth=A).status_code == 404 and client.get('/preview/1.jpg').status_code == 401
    assert "'/preview/'" in client.get('/static/app.js').text

def _fill_index(tmp_path):
    import os
    from app import searchindex as si
    root = tmp_path / 'data'; _make_pdf(str(root / 'C' / 'book.pdf'), 5)
    c = sqlite3.connect(os.environ['THILEK_DB']); c.execute("UPDATE book SET relpath='C/book.pdf', title_el='Βιβλίο' WHERE id=1"); si.create(c)
    pages = {301: 'Ο νόμος του Ohm συνδέει την τάση με το ηλεκτρικό ρεύμα και την αντίσταση.', 302: 'Η ηλεκτρική ΑΝΤΙΣΤΑΣΗ μετριέται σε Ω. Το ηλεκτρικό ρεύμα είναι ροή φορτίων.', 303: 'Μαγνητικό πεδίο.'}
    for p, t in pages.items(): c.execute('INSERT INTO book_page(book_id,pdf_page,printed,text,norm) VALUES(1,?,?,?,?)', (p + 1, p, t, si.norm(t)))
    c.execute("INSERT INTO book_fts(book_fts) VALUES('rebuild')"); c.execute("UPDATE question SET text='Υπολογίστε την αντίσταση του κυκλώματος', sol_text='νόμος του Ohm' WHERE id=1")
    si.index_questions(c); c.commit(); c.close()

def test_search_query_parsing():
    from app import searchindex as si
    assert si.parse_query('Νόμος "ηλεκτρικό ρεύμα" ΑΝΤΙΣΤ') == [('w', 'νομοσ'), ('p', ['ηλεκτρικο', 'ρευμα']), ('w', 'αντιστ')]
    assert si.fts_expr(si.parse_query('νόμος "α β"')) == '"νομοσ"* "α β"' and si.parse_query('"\' ;') == [] and si.parse_query('') == []

def test_fulltext_search(client, tmp_path):
    H = {'Origin': 'http://testserver'}
    assert 'Χτίσιμο ευρετηρίου' in client.get('/search', auth=A).text        # πριν το ευρετήριο
    _fill_index(tmp_path)
    r = client.get('/search?q=αντιστ', auth=A).text; assert 'σελ. 302' in r and 'σελ. 301' in r and 'σελ. 303' not in r and '<mark>ΑΝΤΙΣΤΑΣΗ</mark>' in r and '<mark>αντίσταση</mark>' in r
    assert 'Ερωτήματα με αυτές τις λέξεις — 1' in r and "name=qids value=1" in r
    r = client.get('/search?q=%22ηλεκτρικό+ρεύμα%22&scope=book', auth=A).text; assert 'σελ. 301' in r and 'σελ. 302' in r and 'Ερωτήματα με αυτές' not in r
    assert 'σελ. 301' not in client.get('/search?q=%22ρεύμα+ηλεκτρικό%22&scope=book', auth=A).text      # η σειρά μετράει στη φράση
    r = client.get('/search?q=αντιστ&scope=book&sort=page', auth=A).text; assert r.index('σελ. 301') < r.index('σελ. 302')
    assert 'Καμία σελίδα' in client.get('/search?q=ξξξ', auth=A).text
    assert client.get('/search?q=%22%27+AND+OR+NEAR%28', auth=A).status_code == 200      # δεν σπάει από σύνταξη FTS
    r = client.get('/search?q=Ohm&qtype=mcq', auth=A).text; assert 'Ερωτήματα με αυτές τις λέξεις — 0' in r     # φίλτρο τύπου (το 1 δεν είναι mcq)
    assert client.get('/search', auth=A, params={'q': '<script>'}).text.count('<script>alert') == 0
    assert client.post('/search/reindex', auth=A).status_code == 403

def test_book_page_view_and_image(client, tmp_path):
    _fill_index(tmp_path)
    r = client.get('/book/1/302?q=ρεύμα', auth=A).text
    assert '<mark>ρεύμα</mark>' in r and 'rel=prev' in r and 'rel=next' in r and '/book/1/302.jpg' in r
    assert 'rel=next' not in client.get('/book/1/303', auth=A).text and client.get('/book/1/999', auth=A).status_code == 404
    j = client.get('/book/1/1.jpg', auth=A); assert j.status_code == 200 and j.content[:2] == b'\xff\xd8'
    assert client.get('/book/1/1.jpg').status_code == 401 and client.get('/book/9/1.jpg', auth=A).status_code == 404

def test_index_book_from_pdf(tmp_path):
    rl = pytest.importorskip('reportlab.pdfgen.canvas')
    from reportlab.pdfbase import pdfmetrics; from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont('DJ', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdf = tmp_path / 'b.pdf'; cv = rl.Canvas(str(pdf))
    for t in ('Εξώφυλλο', 'Ο νόμος του Ohm', 'Το ηλεκτρικό ρεύμα'): cv.setFont('DJ', 14); cv.drawString(60, 700, t); cv.showPage()
    cv.save()
    from app import searchindex as si
    c = sqlite3.connect(':memory:'); c.row_factory = sqlite3.Row; c.execute('CREATE TABLE book(id)')
    assert si.index_book(c, 1, pdf, 1) == 3
    assert [r[0] for r in c.execute("SELECT p.printed FROM book_fts f JOIN book_page p ON p.id=f.rowid WHERE book_fts MATCH '\"νομοσ\"*'")] == [1]

def test_favorites_and_question_browse(client, tmp_path):
    H = _exam_setup(client, tmp_path)
    c = sqlite3.connect(__import__('os').environ['THILEK_DB']); c.execute("INSERT INTO question(id,item_id,code,points,text,qtype) VALUES(3,'1','2.2',10,'q3','true_false')"); c.commit(); c.close()
    assert client.post('/fav/1', auth=A).status_code == 403 and client.post('/fav/1', headers=H).status_code == 401
    assert client.post('/fav/1', auth=A, headers=H).json() == {'fav': True}
    assert "class='star on'" in client.get('/browse', auth=A).text
    r = client.get('/browse?fav=1', auth=A).text; assert 'name=qids value=1>' in r and 'name=qids value=2>' not in r and 'name=qids value=3>' not in r
    assert client.post('/fav/1', auth=A, headers=H).json() == {'fav': False} and 'name=qids value=1>' not in client.get('/browse?fav=1', auth=A).text
    assert client.post('/fav/999', auth=A, headers=H).status_code == 404
    client.post('/fav/2', auth=A, headers=H)
    # περιήγηση με φίλτρα
    r = client.get('/q/start?qtype=mcq', auth=A, follow_redirects=False); assert r.headers['location'] == '/q/1?qtype=mcq'
    p1 = client.get('/q/1?qtype=mcq', auth=A).text; assert '1 / 2' in p1 and "rel=next href='/q/2?qtype=mcq'" in p1 and 'rel=prev' not in p1 and '/crop/1.jpg' in p1
    p2 = client.get('/q/2?qtype=mcq', auth=A).text; assert '2 / 2' in p2 and "rel=prev href='/q/1?qtype=mcq'" in p2 and 'rel=next' not in p2 and "class='star on'" in p2
    assert 'δεν ταιριάζει' in client.get('/q/3?qtype=mcq', auth=A).text and '3 / 3' not in p1
    assert client.get('/q/start?fav=1&qtype=true_false', auth=A, follow_redirects=False).headers['location'].startswith('/browse?')
    assert 'Κανένα ερώτημα' in client.get('/browse?none=1', auth=A).text
    assert client.get('/q/start?chapter=4', auth=A, follow_redirects=False).headers['location'].startswith('/q/')
    assert client.get('/q/999', auth=A).status_code == 404 and client.get('/q/1').status_code == 401
    assert 'Κεφάλαιο 4' in client.get('/browse', auth=A).text
    assert client.get('/q/start?chapter=9', auth=A, follow_redirects=False).headers['location'].startswith('/browse?')

def test_quiz_pick_from_bank(client, tmp_path):
    H = _exam_setup(client, tmp_path)
    c = sqlite3.connect(__import__('os').environ['THILEK_DB']); c.execute("UPDATE question SET qtype='true_false', text=?, sol_text=? WHERE id=1", ("2.1 Σ/Λ\nα. Ένα.\nβ. Δύο.\n(Μονάδες 15)", "2.1\nα–Σ\nβ–Λ")); c.commit(); c.close()
    client.post('/quizzes/new', data={'name': 'Q'}, auth=A, headers=H)
    assert '/quizzes/1/pick' in client.get('/quizzes/1', auth=A).text
    r = client.get('/quizzes/1/pick?qtype=true_false', auth=A).text
    assert 'name=qids value=1>' in r and 'name=qids value=2>' not in r and '2× Σ/Λ' in r and 'Στοιχεία quiz που θα προκύψουν' in r
    assert client.get('/quizzes/9/pick', auth=A).status_code == 404
    assert client.post('/quizzes/1/pick', data={'qids': ['1']}, auth=A).status_code == 403
    assert client.post('/quizzes/1/pick', data={}, auth=A, headers=H).status_code == 422
    r = client.post('/quizzes/1/pick', data={'qids': ['1', '1']}, auth=A, headers=H, follow_redirects=False)
    assert r.status_code == 303 and 'Προστέθηκαν 2 στοιχεία' in __import__('urllib.parse').parse.unquote(r.headers['location'])
    assert 'ήδη στο quiz' in client.get('/quizzes/1/pick', auth=A).text and client.get('/quizzes/1', auth=A).text.count('name=stem') == 2

def test_merge_questions_tab_preview_pdf(client, tmp_path):
    from pypdf import PdfReader; import io
    H = _exam_setup(client, tmp_path)
    page = client.get('/tools/merge', auth=A).text; assert 'class=tabs' in page and 'tab=questions' in page and 'name=ids' in page
    q = client.get('/tools/merge?tab=questions&qtype=mcq&thumbs=1', auth=A).text
    assert 'class=tabs' in q and "action='/tools/merge/preview'" in q and 'name=qids value=1>' in q and '/crop/1.jpg' in q
    p = client.post('/tools/merge/preview', data={'qids': ['2', '1']}, auth=A, headers=H).text
    assert p.index("data-q='2'") < p.index("data-q='1'") and '/static/mergeq.js' in p and 'Προβολή PDF' in p
    assert client.get('/static/mergeq.js').status_code == 200 and 'pqlist' in client.get('/static/mergeq.js').text
    assert client.post('/tools/merge/preview', data={}, auth=A, headers=H).status_code == 422 and client.post('/tools/merge/preview', data={'qids': ['1']}, auth=A).status_code == 403
    c = sqlite3.connect(__import__('os').environ['THILEK_DB']); c.execute("UPDATE item SET statement_path='C/a.pdf' WHERE id='2'"); c.commit(); c.close()
    r = client.post('/tools/merge/questions', data={'qids': ['1', '2'], 'layout': 'flow', 'numbers': '1', 'dl': '0'}, auth=A, headers=H)
    assert r.status_code == 200 and r.headers['content-type'] == 'application/pdf' and r.headers['content-disposition'].startswith('inline') and len(PdfReader(io.BytesIO(r.content)).pages) == 1
    r = client.post('/tools/merge/questions', data={'qids': ['1', '2'], 'layout': 'page', 'dl': '1'}, auth=A, headers=H)
    assert len(PdfReader(io.BytesIO(r.content)).pages) == 2 and r.headers['content-disposition'].startswith('attachment')
    c = sqlite3.connect(__import__('os').environ['THILEK_DB']); c.execute("UPDATE question SET geo=NULL WHERE id=2"); c.commit(); c.close()
    r = client.post('/tools/merge/questions', data={'qids': ['1', '2']}, auth=A, headers=H); assert r.headers['x-skipped'] == '1'
    c = sqlite3.connect(__import__('os').environ['THILEK_DB']); c.execute("UPDATE question SET geo=NULL WHERE id=1"); c.commit(); c.close()
    assert client.post('/tools/merge/questions', data={'qids': ['1', '2']}, auth=A, headers=H).status_code == 422

def test_footer_version_and_manual(client):
    import app as _app
    r = client.get('/review', auth=A).text
    assert f'TH-ILEK v{_app.__version__}' in r and "href='/manual'" in r and "href='/health'" in r
    m = client.get('/manual', auth=A); assert m.status_code == 200
    t = m.text; assert 'Οδηγίες χρήσης' in t and "class=mantoc" in t and "<h2 id=" in t.replace('"', '') and 'Γρήγορη εκκίνηση' in t and '<table>' in t and '<script' not in t.split('<main>')[1].split('</main>')[0].replace("<script src='/static", '')
    raw = client.get('/manual.md', auth=A); assert raw.status_code == 200 and raw.text.startswith('# TH-ILEK') and 'attachment' in raw.headers['content-disposition']
    assert client.get('/manual').status_code == 401 and client.get('/manual.md').status_code == 401
    from app.manual import render
    h, toc = render('## Α β\n\ntext\n\n## Α β\n\n<script>x</script>'); assert toc[0][0] != toc[1][0] and '<script>' not in h
    for need in ('/search', '/browse', '/tools/merge', '/quizzes', '/docs', '/exams', '/coverage', '/tags', '/saved', '/tools/html'):
        assert need in raw.text, need


def test_exam_variants_and_spec(client, tmp_path):
    from app import examvar
    H = _exam_setup(client, tmp_path)
    import sqlite3, os
    c = sqlite3.connect(os.environ['THILEK_DB']); geo = c.execute('SELECT geo FROM question WHERE id=2').fetchone()[0]
    for i in range(3, 7): c.execute("INSERT INTO question(id,item_id,code,points,text,qtype,geo) VALUES(?,?,?,?,?,?,?)", (i, '2', f'2.{i}', 5, 'q', 'true_false' if i % 2 else 'mcq', geo))
    c.commit(); c.close()
    client.post('/exams/1/add', data={'qids': ['1', '2', '3', '4', '5', '6'], 'grp': '1'}, auth=A, headers=H)
    def order(url):
        t = client.get(url, auth=A).text; import re; return re.findall(r"/crop/(\d+)\.jpg", t)
    a = order('/exams/1/print'); assert order('/exams/1/print?v=A') == a and len(a) == 6
    b = order('/exams/1/print?v=B&seed=7'); assert sorted(b) == sorted(a) and b != a and order('/exams/1/print?v=B&seed=7') == b          # ίδιο seed = ίδιο ανακάτεμα
    assert order('/exams/1/print?v=b&seed=7') == b and 'ΕΚΔΟΣΗ Β' in client.get('/exams/1/print?v=B&seed=7', auth=A).text and 'ΕΚΔΟΣΗ' not in client.get('/exams/1/print', auth=A).text
    assert order('/exams/1/print?v=B&seed=8') != b or order('/exams/1/print?v=C&seed=7') != b                                                   # άλλο seed/έκδοση: τυπικά άλλη σειρά
    t = client.get('/exams/1/print?v=B&seed=7&teacher=1', auth=A).text; assert 'Αντιστοίχιση με την έκδοση Α' in t and 'Πίνακας προδιαγραφών' in t
    assert 'ΕΚΔΟΣΗ' not in client.get('/exams/1/print?v=Z', auth=A).text and client.get('/exams/1/print?v=B&seed=<script>', auth=A).status_code == 200 and '<script>' not in client.get('/exams/1/print?v=B&seed=<script>', auth=A).text
    d = client.get('/exams/1/docx?v=B&seed=7', auth=A); assert d.status_code == 200 and 'thilek-exam-1-B.docx' in d.headers['content-disposition'] and d.content[:2] == b'PK'
    s = client.get('/exams/1/spec', auth=A); assert s.status_code == 200 and 'Πολλαπλής επιλογής' in s.text and 'Σωστό/Λάθος' in s.text and '4.1 y' in s.text and '45 μον.' in s.text
    assert 'Εκδόσεις Α/Β' in client.get('/exams/1', auth=A).text


def test_examvar_unit():
    from app import examvar as X
    rows = [{'grp': g, 'pos': k, 'item_id': str(g), 'qcode': str(k), 'points': 5, 'qtype': 'mcq', 'iep_yli': '1.1'} for g in (1, 2) for k in (1, 2, 3)]
    a = X.variant(rows, 1, 'Α'); assert [(r['grp'], r['pos']) for r in a] == [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)] and a[0]['orig'] == 'Α1'
    b = X.variant(rows, 1, 'Β', '3', True); assert len(b) == 6 and {r['orig'] for r in b} == {'Α1', 'Α2', 'Α3', 'Β1', 'Β2', 'Β3'} and [(r['item_id'], r['qcode']) for r in b] != [(r['item_id'], r['qcode']) for r in a]
    assert {r['grp'] for r in b} == {1, 2} and [r['pos'] for r in b if r['grp'] == 1] == [1, 2, 3]
    assert X.variant([], 1, 'Β') == [] and X.variant(rows[:1], 1, 'Β')[0]['orig'] == 'Α1' and X.clean_ver('c') == 'Γ' and X.clean_ver('x') == '' and X.clean_seed('a<b>9') == 'ab9'
    assert 'Σύνολο' in X.spec_html(rows, {'mcq': 'ΠΕ'}) and '30 μον.' in X.spec_html(rows, {'mcq': 'ΠΕ'}) and 'κενό' in X.spec_html([], {})
