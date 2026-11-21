import pathlib, re, sqlite3, pytest
from fastapi.testclient import TestClient
from app import mdrich, helpdb, manual
SCHEMA = pathlib.Path(__file__).parent.parent / 'app' / 'schema.sql'
A = ('admin', 'pw'); H = {'origin': 'http://testserver', 'host': 'testserver'}

@pytest.fixture
def cl(tmp_path, monkeypatch):
    db = tmp_path / 't.db'; root = tmp_path / 'data'; (root / 'C').mkdir(parents=True)
    c = sqlite3.connect(db); c.executescript(SCHEMA.read_text(encoding='utf-8'))
    c.execute("INSERT INTO course VALUES('C','Test','B','TTDD')"); c.execute("INSERT INTO book(id,course_code,pdf_offset) VALUES(1,'C',1)")
    c.execute("INSERT INTO item(id,course_code,source,position,iep_yli,solution_status) VALUES('1','C','TTDD',2,'4.1 x','ok')")
    c.commit(); c.close()
    monkeypatch.setenv('THILEK_DB', str(db)); monkeypatch.setenv('THILEK_ROOT', str(root)); monkeypatch.setenv('THILEK_PASSWORD', 'pw'); monkeypatch.setenv('THILEK_CONFIG', str(tmp_path / 'none.yaml'))
    from app.main import app
    return TestClient(app)

# ---------- renderer ----------
def test_admonitions_static_and_collapsible():
    h, toc, _ = mdrich.render('!!! warning "Πρόσεξε"\n    Κείμενο **έντονο**\n\n??? tip "Κλειστό"\n    μέσα\n\n???+ note "Ανοιχτό"\n    μέσα\n')
    assert "<div class='adm adm-warning'>" in h and 'Πρόσεξε' in h and '<strong>έντονο</strong>' in h
    assert "<details class='adm adm-tip'><summary>" in h and "<details class='adm adm-note' open>" in h

def test_tabs_group_and_nesting():
    h, _, _ = mdrich.render('=== "Α"\n    πρώτο\n\n=== "Β"\n    !!! danger "Μέσα"\n        εμφωλευμένο\n\n::: group Πλαίσιο\nσώμα\n:::\n')
    assert h.count('<input type=radio') == 2 and 'checked' in h and '<label for=tg' in h and h.count("<div class=tp>") == 2
    assert 'adm-danger' in h and "<section class=grp><h4 class=grp-t>Πλαίσιο</h4>" in h

def test_checklist_and_badges():
    h, _, _ = mdrich.render('- [ ] ένα\n- [x] δύο\n\nΛέξη {{kw}} {{ok:οκ}} {{bad:όχι}} και `{{code}}`.\n', ck_prefix='t')
    assert h.count('data-ck=') == 2 and "data-ck='t-2' checked" in h and 'class="task"' in h
    assert "kw kw-key'>kw<" in h and "kw kw-ok'>οκ<" in h and '{{bad:όχι}}' in h and '<code>{{code}}</code>' in h

def test_syntax_inside_code_fence_is_not_parsed():
    h, _, _ = mdrich.render('```\n!!! note "x"\n=== "y"\n```mermaid\n```\n')
    assert 'class=\'adm' not in h and 'tabs2' not in h and 'figure' not in h

def test_toc_numbered_anchor_and_html_escaped():
    h, toc, _ = mdrich.render('## 4. Θέματα\n\nκείμενο <script>alert(1)</script>\n')
    assert toc[0][1] == '4. Θέματα' and "<a id='s4'></a>" in h and '<script>' not in h

def test_mermaid_modes(tmp_path, monkeypatch):
    src = 'flowchart LR\n  A --> B'
    _, _, env = mdrich.render(f'```mermaid\n{src}\n```', mermaid='local'); assert env['mermaid_local']
    monkeypatch.setattr(mdrich, 'DIAGRAMS', tmp_path)
    h, _, env = mdrich.render(f'```mermaid\n{src}\n```', mermaid='svg'); assert 'pre class=mermaid' in h and env['mermaid_local']       # λείπει το SVG: πέφτει σε τοπικό
    (tmp_path / f'{mdrich.diagram_hash(src)}.svg').write_text('<svg id="x"></svg>')
    h, _, env = mdrich.render(f'```mermaid\n{src}\n```', mermaid='svg'); assert '<svg id="x">' in h and not env.get('mermaid_local')

def test_every_manual_diagram_has_prerendered_svg():
    """Αν αλλάξει κείμενο διαγράμματος χωρίς `python tools/render_diagrams.py`, αποτυγχάνει εδώ."""
    for fn, *_ in manual.MANUALS.values():
        for s in mdrich.diagram_sources((manual.APP / fn).read_text(encoding='utf-8')):
            assert (mdrich.DIAGRAMS / f'{mdrich.diagram_hash(s)}.svg').is_file(), (fn, s[:40])

# ---------- εγχειρίδια ----------
def test_manual_pages_and_downloads(cl):
    for slug, (_, title, url, dl) in manual.MANUALS.items():
        r = cl.get(url, auth=A); assert r.status_code == 200 and title in r.text and 'class=tabs manbar' in r.text.replace('"', '')
        d = cl.get(url + '.md', auth=A); assert d.status_code == 200 and dl in d.headers['content-disposition']
    assert cl.get('/manual/nope', auth=A).status_code == 404 and cl.get('/manual/nope.md', auth=A).status_code == 404
    assert cl.get('/manual').status_code == 401

def test_faq_has_questions_and_search(cl):
    t = cl.get('/manual/faq', auth=A).text
    assert t.count('data-faq=1') >= 15 and 'data-filter=' in t and 'Πού αποθηκεύεται ένα έγγραφο' in t

def test_db_manual_mentions_every_table(cl):
    t = (manual.APP / 'manual_db.md').read_text(encoding='utf-8')
    c = sqlite3.connect(':memory:'); c.executescript(SCHEMA.read_text(encoding='utf-8'))
    tabs = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not [x for x in tabs if f'`{x}`' not in t and f'**`{x}`**' not in t], 'πίνακας χωρίς περιγραφή στο manual_db.md'
    assert 'erDiagram' in t

def test_manual_sections_for_help_exist(cl):
    toc = mdrich.render((manual.APP / 'manual.md').read_text(encoding='utf-8'))[1]; nums = {t.split('.')[0] for _, t in toc}
    for k, h in helpdb.HELP.items():
        assert not h.get('sec') or h['sec'] in nums, (k, h['sec'])
        assert h['can'] and h['cannot'] and h['data'] and all(u.startswith('/') for u, _ in h['see']), k

# ---------- ρυθμίσεις ----------
def test_settings_roundtrip_and_validation(cl):
    t = cl.get('/settings', auth=A).text; assert 'name=diagram_mode value=svg checked' in t.replace('"', '') and 'localStorage' in t
    r = cl.post('/settings', data={'diagram_mode': 'local', 'help_default': 'closed', 'help_show': 'on'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    from app import settings; g = settings.get_all(); assert (g['diagram_mode'], g['help_default'], g['help_show']) == ('local', 'closed', 'on')
    cl.post('/settings', data={'diagram_mode': 'evil', 'help_default': 'open', 'help_show': 'x'}, auth=A, headers=H)
    g = settings.get_all(); assert (g['diagram_mode'], g['help_default'], g['help_show']) == ('local', 'open', 'on')      # άκυρες τιμές αγνοούνται

def test_settings_post_needs_same_origin_and_auth(cl):
    assert cl.post('/settings', data={'diagram_mode': 'local'}, auth=A, headers={'origin': 'http://evil.example', 'host': 'testserver'}).status_code == 403
    assert cl.post('/settings', data={'diagram_mode': 'local'}, headers=H).status_code == 401

def test_diagram_mode_switches_rendering(cl):
    t = cl.get('/manual/system', auth=A).text; assert '<svg' in t and 'pre class=mermaid' not in t and 'mermaid.min.js' not in t
    cl.post('/settings', data={'diagram_mode': 'local', 'help_default': 'open', 'help_show': 'on'}, auth=A, headers=H)
    t = cl.get('/manual/system', auth=A).text; assert 'pre class=mermaid' in t and "src='/static/vendor/mermaid/mermaid.min.js'" in t

def test_mermaid_and_docs_js_served_and_csp(cl):
    r = cl.get('/static/vendor/mermaid/mermaid.min.js'); assert r.status_code == 200 and len(r.content) > 1_000_000
    assert cl.get('/static/docs.js').status_code == 200
    r = cl.get('/manual/system', auth=A); assert "default-src 'self'" in r.headers['content-security-policy'] and '<script>' not in r.text      # κανένα inline JS

# ---------- help ανά σελίδα ----------
def test_help_on_pages_with_storage_info(cl):
    t = cl.get('/review', auth=A).text
    assert "<details class=help data-hk='review' data-def='open'>" in t and 'Πού αποθηκεύονται τα δεδομένα' in t and 'Τι ΔΕΝ μπορεί' in t and "/manual#s4" in t
    assert "data-hk='review_item'" in cl.get('/review/1', auth=A).text and "data-hk='fb'" in cl.get('/fb', auth=A).text and "data-hk='settings'" in cl.get('/settings', auth=A).text
    assert 'mdoc' in cl.get('/docs', auth=A).text

def test_help_settings_default_and_off(cl):
    cl.post('/settings', data={'diagram_mode': 'svg', 'help_default': 'closed', 'help_show': 'on'}, auth=A, headers=H)
    assert "data-def='closed'" in cl.get('/review', auth=A).text
    cl.post('/settings', data={'diagram_mode': 'svg', 'help_default': 'closed', 'help_show': 'off'}, auth=A, headers=H)
    assert 'class=help' not in cl.get('/review', auth=A).text

def test_help_key_routing():
    k = helpdb.key_for
    assert k('/review') == 'review' and k('/review/17698') == 'review_item' and k('/fb/trash') == 'trash' and k('/fb') == 'fb' and k('/docs/3') == 'doc' and k('/manual/faq') == 'manual'
    assert k('/health') is None and k('/files/x.pdf') is None

def test_no_help_on_json_routes_and_docs_js_wired(cl):
    assert 'help' not in cl.get('/health').text and '/static/docs.js' in cl.get('/review', auth=A).text
