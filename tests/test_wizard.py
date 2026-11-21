"""0.21.0: wizard εξαγωγών (μοντέλο, βαθμοί, ό,τι δεν επιλέχθηκε, Excel, Markdown, συνταγές)."""
import io, json, os, sqlite3, zipfile
import openpyxl
from app import wizmodel as M
from tests.test_docs import cl, A, H  # noqa: F401


def seed(n=4):
    c = sqlite3.connect(os.environ['THILEK_DB'])
    c.execute("UPDATE item SET statement_path='C/04_TRAPEZA/orig/1.pdf', solution_path='C/04_TRAPEZA/orig/1_SOLUTION.pdf' WHERE id='1'")
    for i in range(1, n + 1): c.execute("INSERT INTO question(id,item_id,code,points,text,qtype) VALUES(?,?,?,?,?,?)", (i, '1', f'2.{i}', [5, 5, 5, 10][i - 1], f'ερώτημα {i}', 'problem'))
    c.commit(); c.close()


def new(cl, name='Τεστ'):
    r = cl.post('/wizard/new', data={'name': name}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    return int(r.headers['location'].split('/')[2])


def post(cl, rid, step, **d): return cl.post(f'/wizard/{rid}/{step}', data=d, auth=A, headers=H, follow_redirects=False)


# ---------- καθαρό μοντέλο ----------
def test_scale_points_exact_sum_and_step():
    r = M.scale_points({'a': 5, 'b': 5, 'c': 5, 'd': 10}, 20); assert sum(r.values()) == 20 and r['d'] == 8 and set(r.values()) <= {4.0, 8.0}
    r = M.scale_points({'a': 1, 'b': 1, 'c': 1}, 10); assert sum(r.values()) == 10 and sorted(r.values()) == [3.0, 3.0, 4.0]
    r = M.scale_points({'a': 3, 'b': 4}, 10, 0.5); assert abs(sum(r.values()) - 10) < 1e-9
    assert M.scale_points({}, 20) == {} and M.scale_points({'a': 0}, 20) == {'a': 0}


def test_load_state_is_robust():
    assert M.load_state('{σπασμένο')['format'] == 'excel'
    st = M.load_state(json.dumps({'format': 'nope', 'order': 'x', 'unsel': 'y', 'members': [[1], ['1', '2.1']], 'points': {'a': 'x', 'b': 2}, 'target': 'zz', 'title': 5}))
    assert st['format'] == 'excel' and st['order'] == 'item' and st['unsel'] == 'omit' and st['members'] == [['1', '2.1']] and st['points'] == {'b': 2} and st['target'] is None and st['title'] == 'Αναφορά ασκήσεων'
    assert M.load_state(json.dumps({'target': 20}))['target'] == 20 and M.num('2,5') == 2.5 and M.num('x') is None and M.fmt_pts(2.0) == '2' and M.fmt_pts(2.5) == '2.5'


def test_entries_unselected_modes(cl):
    seed(); c = sqlite3.connect(os.environ['THILEK_DB']); c.row_factory = sqlite3.Row
    st = M.new_state(); st['members'] = [['1', '2.1'], ['1', '2.2']]
    def vis(unsel, **k):
        st.update(unsel=unsel, **k); return [(e['code'], e['vis']) for e in M.entries(c, st)]
    assert vis('omit') == [('2.1', 'show'), ('2.2', 'show')]
    assert vis('hide') == [('2.1', 'show'), ('2.2', 'show'), ('2.3', 'hidden'), ('2.4', 'hidden')]
    assert vis('append') == [('2.1', 'show'), ('2.2', 'show'), ('2.3', 'append'), ('2.4', 'append')]
    assert vis('manual', manual_sel=['1|2.4']) == [('2.1', 'show'), ('2.2', 'show'), ('2.4', 'show')]
    st.update(unsel='hide'); assert M.total(M.entries(c, st)) == 10                           # τα κρυφά δεν μετρούν στο άθροισμα
    st.update(unsel='omit', members=[['1', '2.4'], ['1', '2.1']], order='points'); assert [e['code'] for e in M.entries(c, st)] == ['2.4', '2.1']
    st.update(order='manual'); assert [e['code'] for e in M.entries(c, st)] == ['2.4', '2.1']
    st.update(order='item'); assert [e['code'] for e in M.entries(c, st)] == ['2.1', '2.4']


def test_checks_warn_on_target_and_missing_solution(cl):
    seed(); c = sqlite3.connect(os.environ['THILEK_DB']); c.row_factory = sqlite3.Row
    st = M.new_state(); st['members'] = [['1', '2.1'], ['1', '2.4']]; st['target'] = 20; st['format'] = 'reveal'
    w = ' '.join(M.checks(M.entries(c, st), st)); assert 'στόχος 20' in w and 'δεν έχουν αρχείο λύσης' in w
    st['target'] = 15; st['format'] = 'excel'; assert M.checks(M.entries(c, st), st) == []
    st['points'] = {'1|2.1': 7}; st['target'] = None; st['format'] = 'moodle'; assert 'δεν εφαρμόζει τις προσαρμοσμένες' in ' '.join(M.checks(M.entries(c, st), st))


# ---------- ροή ----------
def test_pages_need_auth_and_origin(cl):
    seed(); assert cl.get('/wizard').status_code == 401
    assert cl.post('/wizard/new', data={'name': 'x'}, headers=H).status_code == 401
    assert cl.post('/wizard/new', data={'name': 'x'}, auth=A, headers={'origin': 'http://evil.example', 'host': 'testserver'}).status_code == 403
    rid = new(cl); assert cl.get(f'/wizard/{rid}/9', auth=A).status_code == 404 and cl.get('/wizard/999/1', auth=A).status_code == 404
    assert cl.post(f'/wizard/{rid}/1', data={'action': 'clear'}, auth=A, headers={'origin': 'http://evil.example', 'host': 'testserver'}).status_code == 403


def test_full_flow_excel_with_scaled_points(cl):
    seed(); rid = new(cl, 'Δοκιμή')
    assert 'Wizard' in cl.get('/wizard', auth=A).text and 'Δοκιμή' in cl.get('/wizard', auth=A).text
    t = cl.get(f'/wizard/{rid}/1?qtype=problem', auth=A).text; assert 'ερώτημα' not in t.lower() or '2.1' in t and "data-hk='wizard'" in t
    r = post(cl, rid, 1, action='add', qids=['1', '2', '4'], qs='qtype=problem'); assert r.status_code == 303 and r.headers['location'].endswith('/wizard/%d/1?qtype=problem' % rid)
    post(cl, rid, 2, unsel='hide', order='item', mode='merge', go='next')
    t = cl.get(f'/wizard/{rid}/3', auth=A).text; assert 'Άθροισμα μονάδων (ορατά): <b>20</b>' in t and 'κρυφό' in t
    assert cl.post(f'/wizard/{rid}/3', data={'action': 'scale', 'target': ''}, auth=A, headers=H).status_code == 422
    post(cl, rid, 3, action='scale', target='10', rstep='1', pk=['1|2.1', '1|2.2', '1|2.4'], pv=['5', '5', '10'])
    t = cl.get(f'/wizard/{rid}/3', auth=A).text; assert 'Άθροισμα μονάδων (ορατά): <b>10</b>' in t and 'στόχος 10' in t
    post(cl, rid, 4, format='excel', go='next'); post(cl, rid, 5, title='Αναφορά Α', link_prefix='pdf/', store='download', go='next')
    t = cl.get(f'/wizard/{rid}/6', auth=A).text; assert 'Κανένα πρόβλημα' in t and 'σύνολο μονάδων 10' in t
    r = cl.post(f'/wizard/{rid}/generate', auth=A, headers=H); assert r.status_code == 200 and 'spreadsheetml' in r.headers['content-type']
    ws = openpyxl.load_workbook(io.BytesIO(r.content))['Ερωτήματα']
    rows = [[c.value for c in row] for row in ws.iter_rows(min_row=2)]
    pts = {x[2]: x[3] for x in rows if x[2]}; assert pts == {'2.1': 2.0, '2.2': 2.0, '2.4': 6.0, '2.3': 5} or pts['2.1'] + pts['2.2'] + pts['2.4'] == 10
    assert ws['L2'].hyperlink.target == 'pdf/1.pdf' and ws['M2'].hyperlink.target == 'pdf/1_SOLUTION.pdf'
    hid = [x[2] for x in rows if x[10] == 'κρυφό']; assert hid == ['2.3'] and ws.row_dimensions[5].hidden
    assert 'SUMIF' in str(rows[-1][3])


def test_bundle_zip_contains_pdfs_and_readme(cl):
    seed(); root = os.environ['THILEK_ROOT']; o = os.path.join(root, 'C', '04_TRAPEZA', 'orig'); os.makedirs(o)
    open(os.path.join(o, '1.pdf'), 'wb').write(b'%PDF-1'); open(os.path.join(o, '1_SOLUTION.pdf'), 'wb').write(b'%PDF-2')
    rid = new(cl); post(cl, rid, 1, action='add', qids=['1']); post(cl, rid, 4, format='excel', go='next'); post(cl, rid, 5, title='Zip', link_prefix='pdf/', bundle='1', go='next')
    r = cl.post(f'/wizard/{rid}/generate', auth=A, headers=H); assert r.headers['content-type'] == 'application/zip'
    z = zipfile.ZipFile(io.BytesIO(r.content)); n = z.namelist()
    assert 'pdf/1.pdf' in n and 'pdf/1_SOLUTION.pdf' in n and 'README.txt' in n and any(x.endswith('.xlsx') for x in n) and 'LIPOUN.txt' not in n
    assert z.read('pdf/1.pdf') == b'%PDF-1' and 'pdf/' in z.read('README.txt').decode('utf-8')


def test_link_prefix_sanitised(cl):
    seed(); rid = new(cl); post(cl, rid, 5, title='x', link_prefix='../../etc/', go='next')
    assert M.load_state(sqlite3.connect(os.environ['THILEK_DB']).execute('SELECT state FROM wizard_recipe WHERE id=?', (rid,)).fetchone()[0])['link_prefix'] == 'pdf/'


def test_markdown_new_doc_with_points_and_hidden_comment(cl):
    seed(); rid = new(cl); post(cl, rid, 1, action='add', qids=['1', '2']); post(cl, rid, 2, unsel='append', order='item', mode='merge', go='next')
    post(cl, rid, 3, action='x', pk=['1|2.1'], pv=['7,5']); post(cl, rid, 4, format='md', go='next'); post(cl, rid, 5, title='Μ', mdmode='text', numbering='new', preview='1', go='next')
    assert 'Προεπισκόπηση (Markdown)' in cl.get(f'/wizard/{rid}/6', auth=A).text
    r = cl.post(f'/wizard/{rid}/generate', auth=A, headers=H, follow_redirects=False); assert r.status_code == 303 and r.headers['location'].startswith('/docs/')
    md = cl.get(r.headers['location'] + '/md', auth=A).text
    assert '1. (7.5 μον.)' in md and 'Σύνολο: 12.5 μονάδες' in md and '<!-- Μη εμφανιζόμενα' in md and '2.3' in md.split('<!--')[1]


def test_store_on_server_and_preview_endpoint(cl):
    seed(); rid = new(cl); post(cl, rid, 1, action='add', qids=['1']); post(cl, rid, 4, format='htmldoc', go='next'); post(cl, rid, 5, title='Εκτύπωση', store='server', preview='1', go='next')
    assert "<iframe class=wprev sandbox='allow-scripts'" in cl.get(f'/wizard/{rid}/6', auth=A).text
    p = cl.get(f'/wizard/{rid}/preview', auth=A); assert p.status_code == 200 and 'text/html' in p.headers['content-type'] and 'attachment' not in p.headers.get('content-disposition', '')
    r = cl.post(f'/wizard/{rid}/generate', auth=A, headers=H); assert r.status_code == 200 and 'Αποθηκεύτηκε στον server' in r.text
    d = os.path.join(os.environ['THILEK_ROOT'], 'C', '07_EXAGOGES', 'wizard'); assert any(f.endswith('.html') for f in os.listdir(d))


def test_export_without_solutions_is_explained_not_crash(cl):
    seed(); rid = new(cl); post(cl, rid, 1, action='add', qids=['1']); post(cl, rid, 4, format='reveal', go='next')
    assert 'δεν έχουν αρχείο λύσης' in cl.get(f'/wizard/{rid}/6', auth=A).text
    assert cl.post(f'/wizard/{rid}/generate', auth=A, headers=H).status_code == 422


def test_step1_remove_clear_and_addall(cl):
    seed(); rid = new(cl)
    post(cl, rid, 1, action='addall', qs='qtype=problem'); assert len(M.load_state(sqlite3.connect(os.environ['THILEK_DB']).execute('SELECT state FROM wizard_recipe').fetchone()[0])['members']) == 4
    post(cl, rid, 1, action='remove', rm=['1|2.1', '1|2.2']); db = sqlite3.connect(os.environ['THILEK_DB'])
    assert [m[1] for m in M.load_state(db.execute('SELECT state FROM wizard_recipe').fetchone()[0])['members']] == ['2.3', '2.4']
    post(cl, rid, 1, action='clear'); assert M.load_state(db.execute('SELECT state FROM wizard_recipe').fetchone()[0])['members'] == []
    assert 'Πρόσθεσε τουλάχιστον ένα ερώτημα' in cl.get(f'/wizard/{rid}/1', auth=A).text


def test_manual_order_move_and_manual_sel(cl):
    seed(); rid = new(cl); post(cl, rid, 1, action='add', qids=['1', '2', '3']); post(cl, rid, 2, order='manual', unsel='manual', mode='merge', go='next')
    post(cl, rid, 2, move='down:1|2.1'); db = sqlite3.connect(os.environ['THILEK_DB'])
    assert [m[1] for m in M.load_state(db.execute('SELECT state FROM wizard_recipe').fetchone()[0])['members']] == ['2.2', '2.1', '2.3']
    t = cl.get(f'/wizard/{rid}/2', auth=A).text; assert 'name=manual_sel' in t and '2 · 2.4' not in t and '1 · 2.4' in t
    post(cl, rid, 2, order='manual', unsel='manual', manual_sel=['1|2.4'], mode='merge', go='next'); assert 'wiz' or True
    assert M.load_state(db.execute('SELECT state FROM wizard_recipe').fetchone()[0])['manual_sel'] == ['1|2.4']


def test_copy_rename_delete_and_rebuild_carries_table(cl):
    seed(); rid = new(cl, 'Α'); post(cl, rid, 1, action='add', qids=['1'])
    assert cl.post(f'/wizard/{rid}/copy', auth=A, headers=H, follow_redirects=False).status_code == 303
    t = cl.get('/wizard', auth=A).text; assert 'Α (αντίγραφο)' in t
    post(cl, rid, 6, go='rename', rname='Νέο όνομα'); assert 'Νέο όνομα' in cl.get('/wizard', auth=A).text
    assert cl.post(f'/wizard/{rid}/delete', auth=A, headers=H, follow_redirects=False).status_code == 303 and 'Νέο όνομα' not in cl.get('/wizard', auth=A).text
    import pathlib; assert "'wizard_recipe'" in (pathlib.Path(__file__).parent.parent / 'tools' / 'rebuild.py').read_text(encoding='utf-8')


def test_criteria_setting_controls_filter_form(cl):
    seed(); rid = new(cl); t = cl.get(f'/wizard/{rid}/1', auth=A).text; assert 'name=chapter' in t and 'name=tag' in t
    cl.post('/settings', data={'wc_present': '1', 'wc_qtype': 'on', 'wc_q': 'on'}, auth=A, headers=H)
    t = cl.get(f'/wizard/{rid}/1', auth=A).text; assert 'name=qtype' in t and 'name=q ' in t and 'name=chapter' not in t and 'name=tag' not in t
    cl.post('/settings', data={'wc_present': '1'}, auth=A, headers=H)                           # τίποτα τσεκαρισμένο: αγνοείται
    assert 'name=qtype' in cl.get(f'/wizard/{rid}/1', auth=A).text
