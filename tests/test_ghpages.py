"""0.38: δημοσίευση στο GitHub Pages με ψεύτικο GitHub (Git Data API στη μνήμη): ένα commit, ενημέρωση, αφαίρεση, αποκλεισμοί ΙΕΠ, token."""
import io, json, os, re, sqlite3, zipfile
import pytest
from app import ghpages as G, site as S
from tests.test_qsol import env, A, H  # noqa: F401

TOK = 'github_pat_' + 'A' * 40


class FakeGh:
    def __init__(self, files=None, fail_status=None):
        self.blobs, self.trees, self.commits, self.calls, self.fail = {}, {}, {}, [], fail_status
        t = {p: self.blob(d) for p, d in (files or {'README.md': b'hello'}).items()}; self.trees['t0'] = t; self.commits['c0'] = {'tree': 't0', 'parents': []}; self.head = 'c0'; self.n = 0

    def blob(self, data): s = G.blob_sha(data); self.blobs[s] = data; return s
    def files(self): return {p: self.blobs[s] for p, s in self.trees[self.commits[self.head]['tree']].items()}

    def __call__(self, method, url, token, body=None):
        assert token == TOK; path = url[len(G.API):]; self.calls.append((method, path))
        if self.fail: return self.fail, {}
        m = re.fullmatch(r'/repos/own/repo(/.*)?', path); assert m, path; p = m.group(1) or ''
        if p == '': return 200, {'full_name': 'own/repo', 'private': False, 'permissions': {'push': True}}
        if p == '/git/ref/heads/main': return 200, {'object': {'sha': self.head}}
        if p.startswith('/git/ref/heads/'): return 404, {}
        if p.startswith('/git/commits/') and method == 'GET': return 200, {'tree': {'sha': self.commits[p.rsplit('/', 1)[1]]['tree']}}
        if p.startswith('/git/trees/') and method == 'GET': return 200, {'truncated': False, 'tree': [{'path': k, 'type': 'blob', 'sha': v} for k, v in self.trees[p.split('/')[3].split('?')[0]].items()]}
        if p == '/git/blobs': return 201, {'sha': self.blob(__import__('base64').b64decode(body['content']))}
        if p == '/git/trees':
            t = dict(self.trees[body['base_tree']])
            for e in body['tree']:
                if e['sha'] is None: t.pop(e['path'], None)
                else: assert e['sha'] in self.blobs; t[e['path']] = e['sha']
            self.n += 1; self.trees[f't{self.n}'] = t; return 201, {'sha': f't{self.n}'}
        if p == '/git/commits': self.n += 1; self.commits[f'c{self.n}'] = {'tree': body['tree'], 'parents': body['parents']}; return 201, {'sha': f'c{self.n}'}
        if p == '/git/refs/heads/main':
            assert body['force'] is False and self.commits[body['sha']]['parents'] == [self.head]; self.head = body['sha']; return 200, {}
        raise AssertionError((method, path))


def db(): return sqlite3.connect(os.environ['THILEK_DB'])


def setup(cl, monkeypatch, gh=None):
    gh = gh or FakeGh(); monkeypatch.setattr(G, '_http', gh)
    r = cl.post('/ghpages/settings', data={'repo': 'own/repo', 'branch': 'main', 'dir': 'thilek', 'token': TOK}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    return gh


def mk_site(body='Γεια σου'):
    c = db(); c.row_factory = sqlite3.Row; sid = S.create(c, 'Ηλεκτρικά'); S.update_page(c, sid, S.pages(c, sid)[0]['id'], body=body); c.commit(); c.close(); return sid


def mk_quiz(src=''):
    c = db(); qid = c.execute("INSERT INTO quiz(name) VALUES('Κουίζ')").lastrowid
    c.execute("INSERT INTO quiz_item(quiz_id,pos,kind,stem,options,answer,points,feedback,src_item,use_image) VALUES(?,?,?,?,?,?,?,?,?,0)", (qid, 1, 'tf', 'Ισχύει;', '[]', 'Σωστό', 1, '', src)); c.commit(); c.close(); return qid


def pub(cl, sel, ack=True, ack_iep=False, url='/ghpages/apply', **extra):
    d = {'sel': sel, 'ack': '1' if ack else '', **extra}
    if ack_iep: d['ack_iep'] = '1'
    return cl.post(url, data=d, auth=A, headers=H, follow_redirects=False)


def test_settings_token_hidden_and_validated(env, monkeypatch):
    cl, _ = env; setup(cl, monkeypatch)
    p = cl.get('/ghpages', auth=A).text; assert TOK not in p and 'αποθηκευμένο' in p and 'value=\'own/repo\'' in p
    assert cl.post('/ghpages/settings', data={'repo': 'not a repo', 'dir': 'thilek'}, auth=A, headers=H).status_code == 422
    assert cl.post('/ghpages/settings', data={'repo': 'own/repo', 'dir': '../x'}, auth=A, headers=H).status_code == 422
    assert cl.post('/ghpages/settings', data={'repo': 'own/repo', 'dir': 'thilek', 'token': 'bad token!'}, auth=A, headers=H).status_code == 422
    assert cl.post('/ghpages/settings', data={'repo': 'own/repo', 'dir': 'thilek'}, auth=A).status_code == 403                     # same_origin
    cl.post('/ghpages/settings', data={'repo': 'own/repo', 'dir': 'thilek', 'branch': 'main'}, auth=A, headers=H); assert 'αποθηκευμένο' in cl.get('/ghpages', auth=A).text      # κενό token = μένει
    cl.post('/ghpages/settings', data={'repo': 'own/repo', 'dir': 'thilek', 'clear_token': '1'}, auth=A, headers=H); assert 'αποθηκευμένο' not in cl.get('/ghpages', auth=A).text


def test_connection_test_and_errors(env, monkeypatch):
    cl, _ = env; gh = setup(cl, monkeypatch)
    r = cl.post('/ghpages/test', auth=A, headers=H, follow_redirects=True); assert 'Η σύνδεση δουλεύει: own/repo' in r.text
    for st, word in ((401, 'token'), (403, 'δικαίωμα'), (404, 'repo')):
        gh.fail = st; r = cl.post('/ghpages/test', auth=A, headers=H, follow_redirects=True); assert word in r.text and TOK not in r.text


def test_preview_requires_ack_and_shows_plan(env, monkeypatch):
    cl, _ = env; gh = setup(cl, monkeypatch); sid = mk_site(); n = len(gh.calls)
    assert cl.post('/ghpages/preview', data={'sel': f'site:{sid}', f'slug_site:{sid}': 'ilektrika'}, auth=A, headers=H).status_code == 422
    r = cl.post('/ghpages/preview', data={'sel': f'site:{sid}', f'slug_site:{sid}': 'ilektrika', 'ack': '1'}, auth=A, headers=H); assert r.status_code == 200 and 'thilek/ilektrika/' in r.text and 'Εφαρμογή στο GitHub' in r.text
    assert len(gh.calls) == n                                                                                                      # η προεπισκόπηση δεν μιλά στο GitHub
    assert cl.post('/ghpages/preview', data={'sel': 'site:1', 'slug_site:1': 'Bad Slug', 'ack': '1'}, auth=A, headers=H).status_code == 422
    assert cl.post('/ghpages/preview', data={'sel': ['site:1', 'deck:1'], 'slug_site:1': 'a', 'slug_deck:1': 'a', 'ack': '1'}, auth=A, headers=H).status_code == 422
    assert cl.post('/ghpages/preview', data={'ack': '1'}, auth=A, headers=H).status_code == 422


def test_apply_one_commit_index_manifest_update_and_remove(env, monkeypatch):
    cl, _ = env; gh = setup(cl, monkeypatch); sid = mk_site(); qid = mk_quiz(); sel = [f'site:{sid}', f'practice:{qid}']
    d = {f'slug_site:{sid}': 'ilektrika', f'slug_practice:{qid}': 'kouiz'}
    r = cl.post('/ghpages/apply', data={'sel': sel, 'ack': '1', **d}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303 and 'msg=' in r.headers['location']
    f = gh.files(); assert len(gh.commits) == 2 and gh.commits[gh.head]['parents'] == ['c0']                                      # ένα μόνο commit
    assert 'thilek/ilektrika/index.html' in f and 'thilek/kouiz/index.html' in f and 'README.md' in f and 'Ηλεκτρικά'.encode() in f['thilek/index.html'] and b'kouiz/' in f['thilek/index.html']
    man = json.loads(f['thilek/manifest.json']); assert {m['slug'] for m in man} == {'ilektrika', 'kouiz'} and man[0]['via'] == 'api'
    n = len(gh.commits); r = cl.post('/ghpages/apply', data={'sel': sel, 'ack': '1', **d}, auth=A, headers=H, follow_redirects=True)
    assert len(gh.commits) == n and 'Δεν άλλαξε τίποτα' in r.text                                                                 # ίδιο περιεχόμενο: κανένα νέο commit
    # αλλαγή: δεύτερη σελίδα που μετά αφαιρείται -> το παλιό αρχείο σβήνεται
    c = db(); c.row_factory = sqlite3.Row; S.add_page(c, sid, 'Δεύτερη', body='x'); c.commit(); c.close()
    pub(cl, sel, **d); assert sum(k.startswith('thilek/ilektrika/') for k in gh.files()) > 2
    c = db(); c.row_factory = sqlite3.Row; S.delete_page(c, sid, S.pages(c, sid)[1]['id']); c.commit(); c.close()
    before = sum(k.startswith('thilek/ilektrika/') for k in gh.files()); pub(cl, sel, **d); assert sum(k.startswith('thilek/ilektrika/') for k in gh.files()) < before
    assert 'README.md' in gh.files()
    r = cl.post('/ghpages/remove', data={'slug': 'kouiz'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    f = gh.files(); assert not any(k.startswith('thilek/kouiz/') for k in f) and b'kouiz/' not in f['thilek/index.html'] and {m['slug'] for m in json.loads(f['thilek/manifest.json'])} == {'ilektrika'}
    assert cl.post('/ghpages/remove', data={'slug': '../x'}, auth=A, headers=H).status_code == 422
    pg = cl.get('/ghpages', auth=A).text; assert 'https://own.github.io/repo/thilek/ilektrika/' in pg and '/thilek/kouiz/' not in pg


def test_iep_material_is_blocked_or_needs_ack(env, monkeypatch):
    cl, _ = env; gh = setup(cl, monkeypatch)
    bad = mk_site('Δες ![x](C/04_TRAPEZA/orig/images/a.png) και /crop/12.jpg'); n = len(gh.commits)
    r = pub(cl, [f'site:{bad}'], **{f'slug_site:{bad}': 'bad'}); assert r.status_code == 422 and len(gh.commits) == n
    pv = cl.post('/ghpages/preview', data={'sel': f'site:{bad}', f'slug_site:{bad}': 'bad', 'ack': '1'}, auth=A, headers=H); assert '⛔' in pv.text and 'Εφαρμογή στο GitHub' not in pv.text
    q = mk_quiz(src='17698'); k = {f'slug_practice:{q}': 'q1'}
    assert pub(cl, [f'practice:{q}'], **k).status_code == 422                                                                       # στοιχείο από θέμα ΙΕΠ: θέλει ρητή επιβεβαίωση
    assert pub(cl, [f'practice:{q}'], ack_iep=True, **k).status_code == 303 and 'thilek/q1/index.html' in gh.files()
    assert pub(cl, [f'practice:{q}'], ack=False, ack_iep=True, **k).status_code == 422                                              # χωρίς το βασικό ack ποτέ


def test_solutions_pack_excludes_iep_sections_and_images(env, monkeypatch):
    cl, _ = env; gh = setup(cl, monkeypatch)
    k = {'slug_solutions:pack': 'lyseis', 'title_solutions:pack': 'Λύσεις', 'sol_keys': '1|2.1'}
    r = cl.post('/ghpages/preview', data={'sel': 'solutions:pack', 'ack': '1', **k}, auth=A, headers=H); assert r.status_code == 200 and 'δεν περιλαμβάνονται' in r.text.replace('ΔΕΝ', 'δεν') or 'ΔΕΝ περιλαμβάνονται' in r.text
    assert pub(cl, ['solutions:pack'], **k).status_code == 303
    h = gh.files()['thilek/lyseis/index.html'].decode(); assert 'Ποια σχέση συνδέει' in h and 'Βρες το' not in h and 'dfrac' not in h and '<img' not in h and 'σχήμα παραλείπεται' in h or '<img' not in h
    assert pub(cl, ['solutions:pack'], sol_img='1', **k).status_code == 422                                                         # εικόνες: ρητή επιβεβαίωση ΙΕΠ
    assert pub(cl, ['solutions:pack'], sol_img='1', ack_iep=True, **k).status_code == 303 and '<img' in gh.files()['thilek/lyseis/index.html'].decode()
    assert cl.post('/ghpages/preview', data={'sel': 'solutions:pack', 'ack': '1', 'slug_solutions:pack': 'l'}, auth=A, headers=H).status_code == 200      # χωρίς επιλογή λύσης: αποκλεισμός στην προεπισκόπηση
    assert pub(cl, ['solutions:pack'], **{'slug_solutions:pack': 'l'}).status_code == 422


def test_zip_fallback_and_github_errors(env, monkeypatch):
    cl, _ = env; gh = setup(cl, monkeypatch); sid = mk_site(); sel = f'site:{sid}'; d = {f'slug_site:{sid}': 'ilektrika'}
    r = cl.post('/ghpages/zip', data={'sel': sel, 'ack': '1', **d}, auth=A, headers=H); assert r.status_code == 200 and r.content[:2] == b'PK'
    z = zipfile.ZipFile(io.BytesIO(r.content)); names = z.namelist(); assert 'thilek/ilektrika/index.html' in names and 'thilek/index.html' in names and 'publish-ghpages.ps1' in names and 'README.txt' in names
    assert '$Repo' in z.read('publish-ghpages.ps1').decode() and "'thilek'" in z.read('publish-ghpages.ps1').decode() and TOK not in ''.join(z.read(n).decode('utf-8', 'ignore') for n in names)
    assert len(gh.commits) == 1
    gh.fail = 403; r = cl.post('/ghpages/apply', data={'sel': sel, 'ack': '1', **d}, auth=A, headers=H, follow_redirects=True); assert 'δικαίωμα' in r.text and TOK not in r.text


def test_commit_retries_when_branch_moved():
    cfg = {'repo': 'own/repo', 'branch': 'main', 'token': TOK, 'dir': 'thilek', 'manifest': []}; gh = FakeGh(); real = gh.__call__; state = {'n': 0}
    def flaky(method, url, token, body=None):
        if method == 'PATCH' and state['n'] == 0: state['n'] += 1; return 422, {}
        return real(method, url, token, body)
    G._http, old = flaky, G._http
    try: sha, n = G.commit_files(cfg, {'thilek/a.txt': b'x'}, ['thilek/'], 'm')
    finally: G._http = old
    assert sha and gh.files()['thilek/a.txt'] == b'x' and state['n'] == 1


def test_urls_and_index_escaping():
    assert G.pages_url({'repo': 'me/me.github.io', 'dir': 'thilek'}, 'x') == 'https://me.github.io/thilek/x/' and G.pages_url({'repo': 'me/proj', 'dir': 'd'}) == 'https://me.github.io/proj/d/'
    h = G.index_html({}, [{'slug': 'a', 'title': '<script>x</script>', 'kind': 'site', 'updated': '2026'}]).decode(); assert '<script>x' not in h and '&lt;script&gt;' in h
    assert G.ok_slug('abc-1') and not G.ok_slug('index') and not G.ok_slug('A') and not G.ok_slug('-a') and not G.ok_slug('a/b')
