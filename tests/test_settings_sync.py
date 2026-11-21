"""0.20.0: ρυθμίσεις (tooltips, αρχική σελίδα, help mode, Drive), σελίδα /sync με mocked εντολές, πρότυπο λύσης."""
import sys, time
import pytest
from app import settings, syncui, qsol
from tests.test_docs import cl, A, H  # noqa: F401  (fixture και σταθερές του test_docs)


def post(cl, **d): return cl.post('/settings', data=d, auth=A, headers=H, follow_redirects=False)


def test_start_page_redirect_and_validation(cl):
    assert cl.get('/', auth=A, follow_redirects=False).headers['location'] == '/review'
    assert post(cl, start_page='/lyseis').status_code == 303
    assert cl.get('/', auth=A, follow_redirects=False).headers['location'] == '/lyseis'
    post(cl, start_page='https://evil.example/')                                   # άκυρη τιμή: αγνοείται
    assert settings.get('start_page') == '/lyseis'


def test_tips_per_kind_reach_html_attr(cl):
    assert "data-notips=''" in cl.get('/review', auth=A).text
    post(cl, tips_present='1', tip_btn='on', tip_hdr='on')                         # τα υπόλοιπα είδη αποεπιλέγονται
    t = cl.get('/review', auth=A).text
    off = t.split("data-notips='")[1].split("'")[0].split(',')
    assert 'btn' not in off and 'hdr' not in off and {'danger', 'sel', 'opt', 'list', 'txt', 'file', 'sum'} <= set(off)
    post(cl, tips_present='1', **{'tip_' + k: 'on' for k, _ in settings.TIP_KINDS})
    assert "data-notips=''" in cl.get('/review', auth=A).text
    assert 'name=tips_present' in cl.get('/settings', auth=A).text.replace('"', '')


def test_post_without_tips_marker_keeps_tips(cl):
    post(cl, tips_present='1')                                                     # όλα off
    post(cl, help_mode='open')                                                     # χωρίς tips_present: δεν πειράζει τα tips
    assert settings.get('tip_btn') == 'off' and settings.get('help_mode') == 'open'


def test_help_mode_attr_and_docs_js(cl):
    post(cl, help_mode='closed'); assert "data-helpmode='closed'" in cl.get('/review', auth=A).text
    post(cl, help_mode='bogus'); assert settings.get('help_mode') == 'closed'
    js = cl.get('/static/docs.js').text
    assert 'data-helpmode' in js and "mode === 'open'" in js
    assert 'data-notips' in cl.get('/static/ui.js').text and 'kindOf' in cl.get('/static/ui.js').text


def test_drive_url_and_remote_validation(cl):
    assert settings.DRIVE_URL in cl.get('/sync', auth=A).text and settings.DRIVE_URL in cl.get('/fb', auth=A).text
    post(cl, drive_url='https://drive.google.com/drive/folders/ABC123', rclone_remote='gdrive2:Φάκελος/TH')
    assert settings.get('drive_url').endswith('ABC123') and settings.get('rclone_remote') == 'gdrive2:Φάκελος/TH'
    post(cl, drive_url='javascript:alert(1)', rclone_remote='-x:y; rm -rf /"')     # άκυρα: αγνοούνται
    assert settings.get('drive_url').endswith('ABC123') and settings.get('rclone_remote') == 'gdrive2:Φάκελος/TH'


def test_sync_page_auth_and_menu(cl):
    assert cl.get('/sync').status_code == 401
    t = cl.get('/sync', auth=A).text
    assert "data-hk='sync'" in t and "href='/sync'" in t and all(f'value={k}' in t for k in syncui.ORDER)
    assert cl.get('/sync/status').status_code == 401


def test_build_cmd_whitelist_and_args(cl, monkeypatch):
    monkeypatch.setattr('shutil.which', lambda n: '/usr/bin/rclone')
    s = settings.get_all()
    assert syncui.build_cmd('sync', s)[:3] == ['/usr/bin/rclone', 'sync', 'gdrive:TH-ILEK'] and '--dry-run' not in syncui.build_cmd('sync', s)
    assert '--dry-run' in syncui.build_cmd('sync_dry', s) and '--dry-run' in syncui.build_cmd('copy_dry', s)
    assert 'sync' not in syncui.build_cmd('copy', s) and '07_EXAGOGES/**' in syncui.build_cmd('copy', s)
    assert syncui.build_cmd('rebuild', s)[1].endswith('rebuild.py')
    with pytest.raises(ValueError): syncui.build_cmd('bash -c id', s)
    monkeypatch.setattr('shutil.which', lambda n: None)
    with pytest.raises(ValueError): syncui.build_cmd('ls', s)


def test_run_requires_origin_confirm_and_known_action(cl, monkeypatch):
    monkeypatch.setattr(syncui, 'build_cmd', lambda a, s=None: [sys.executable, '-c', 'print("ok")'])
    assert cl.post('/sync/run', data={'action': 'ls'}, auth=A, headers={'origin': 'http://evil.example', 'host': 'testserver'}).status_code == 403
    assert cl.post('/sync/run', data={'action': 'ls'}, headers=H).status_code == 401
    assert cl.post('/sync/run', data={'action': 'rm -rf /'}, auth=A, headers=H).status_code == 422
    assert cl.post('/sync/run', data={'action': 'sync'}, auth=A, headers=H).status_code == 422                 # χωρίς SYNC
    assert cl.post('/sync/run', data={'action': 'sync', 'confirm': 'yes'}, auth=A, headers=H).status_code == 422


def wait_done(t=10):
    for _ in range(int(t * 50)):
        if not syncui.STATE['running']: return
        time.sleep(.02)
    raise AssertionError('η εργασία δεν τελείωσε')


def test_job_runs_in_background_and_reports(cl, monkeypatch):
    monkeypatch.setattr(syncui, 'build_cmd', lambda a, s=None: [sys.executable, '-c', 'print("ΑΠΟΤΕΛΕΣΜΑ")'])
    r = cl.post('/sync/run', data={'action': 'sync', 'confirm': 'SYNC'}, auth=A, headers=H, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == '/sync'
    wait_done()
    j = cl.get('/sync/status', auth=A).json()
    assert j['rc'] == 0 and j['running'] is False and 'ΑΠΟΤΕΛΕΣΜΑ' in j['log'] and j['action'] == 'sync'
    assert 'ΑΠΟΤΕΛΕΣΜΑ' in cl.get('/sync', auth=A).text


def test_second_job_rejected_while_running(cl, monkeypatch):
    monkeypatch.setattr(syncui, 'build_cmd', lambda a, s=None: [sys.executable, '-c', 'import time; time.sleep(1.5)'])
    assert cl.post('/sync/run', data={'action': 'ls'}, auth=A, headers=H, follow_redirects=False).status_code == 303
    assert cl.post('/sync/run', data={'action': 'check'}, auth=A, headers=H).status_code == 409
    wait_done()


def test_failed_command_and_missing_binary(cl, monkeypatch):
    monkeypatch.setattr(syncui, 'build_cmd', lambda a, s=None: [sys.executable, '-c', 'import sys; sys.exit(3)'])
    cl.post('/sync/run', data={'action': 'ls'}, auth=A, headers=H); wait_done()
    assert cl.get('/sync/status', auth=A).json()['rc'] == 3
    monkeypatch.setattr(syncui, 'build_cmd', lambda a, s=None: ['/nonexistent/binary-xyz'])
    cl.post('/sync/run', data={'action': 'ls'}, auth=A, headers=H); wait_done()
    j = cl.get('/sync/status', auth=A).json(); assert j['rc'] == 127 and 'σφάλμα εκκίνησης' in j['log']


# ---------- πρότυπο λύσης ----------
def test_template_in_help_of_lyseis_and_lysi(cl):
    for path in ('/lyseis',):
        t = cl.get(path, auth=A).text
        assert 'Πρότυπο αρχείου λύσης' in t and 'book_solution_page' in t and 'Πιθανές επεκτάσεις' in t and 'Σημειώσεις και υποδείξεις' in t


def test_optional_front_matter_fields():
    assert qsol.opt_fields({}) == []
    assert qsol.opt_fields({'style': 'kids', 'book_first_page': 10, 'book_last_page': 12, 'book_solution_page': 11}) == []
    w = qsol.opt_fields({'style': 'neon', 'book_first_page': 'x', 'book_last_page': 5, 'book_solution_page': 0})
    assert any('style' in x for x in w) and any('book_first_page' in x for x in w) and any('≥ 1' in x for x in w)
    assert any('μεγαλύτερη' in x for x in qsol.opt_fields({'book_first_page': 9, 'book_last_page': 3}))
    assert any('εκτός' in x for x in qsol.opt_fields({'book_first_page': 3, 'book_last_page': 5, 'book_solution_page': 9}))


def test_book_line_and_style_default():
    from app import lyseis, library
    t = lyseis.book_line({'book_first_page': 10, 'book_last_page': 12, 'book_solution_page': 11, 'style': 'print'})
    assert '10–12' in t and 'σελίδα <b>11' in t and 'Εκτύπωση' in t and lyseis.book_line({}) == ''
    assert 'value=print selected' in library.sol_controls('print').replace('"', '') and 'value=kids selected' in library.sol_controls('zzz').replace('"', '')
