"""0.30.0: bullets ένα-ένα (fragments), PowerPoint μέσω Pandoc, σελίδα βοήθειας Reveal."""
import io, re, shutil, zipfile
import pytest
from fastapi import HTTPException
from tests.test_qsol import env, A, H  # noqa: F401
from app import solexport as X

pandoc = pytest.mark.skipif(not shutil.which('pandoc'), reason='no pandoc')


def test_fragmentize_only_li():
    h = '<ul><li>a</li><li class="x">b</li><li data-k=1>c</li></ul><p>q</p><code>&lt;li&gt;</code>'
    o = X.fragmentize(h)
    assert len(re.findall(r'<li[^>]*fragment', o)) == 3 and '<li class=fragment>a</li>' in o
    assert '<li class=fragment data-k=1>' in o and "<p>q</p>" in o and '&lt;li&gt;' in o


def test_reveal_frag_option(env, monkeypatch):
    cl, tmp = env
    monkeypatch.setattr(X, 'render_md', lambda t, *a, **k: '<ul><li>α</li><li>β</li></ul>')
    n = lambda t: len(re.findall(r'<li[^>]*fragment', t))
    a = cl.post('/select/act', data={'act': 'reveal', 'qids': ['1']}, auth=A, headers=H).text
    b = cl.post('/select/act', data={'act': 'reveal', 'qids': ['1'], 'frag': '1'}, auth=A, headers=H).text
    assert '<li>α</li>' in a and n(a) == 0 and n(b) >= 2 and '<li>α</li>' not in b


def test_help_page_and_download(env):
    cl, tmp = env
    r = cl.get('/manual/reveal', auth=A); assert r.status_code == 200 and 'Βοήθεια Reveal.js' in r.text and 'Bullets ένα-ένα' in r.text.replace('«', '')
    d = cl.get('/manual/reveal.md', auth=A); assert 'thilek-reveal-help.md' in d.headers['content-disposition'] and '--' in d.text
    assert 'name=frag' in cl.get('/lyseis', auth=A).text and '/manual/reveal' in cl.get('/lyseis', auth=A).text


@pandoc
def test_pptx_export(env):
    cl, tmp = env
    r = cl.post('/select/act', data={'act': 'pptx', 'qids': ['1'], 'sol_title': 'Ohm'}, auth=A, headers=H)
    assert r.status_code == 200 and 'thilek-presentation.pptx' in r.headers['content-disposition']
    z = zipfile.ZipFile(io.BytesIO(r.content)); n = [x for x in z.namelist() if re.match(r'ppt/slides/slide\d+\.xml$', x)]
    assert len(n) >= 4 and b'a14:m' in b''.join(z.read(x) for x in n) or b'<m:oMath' in b''.join(z.read(x) for x in n)


def test_pptx_without_pandoc(env, monkeypatch):
    cl, tmp = env
    monkeypatch.setattr(X, 'pandoc_path', lambda: None)
    r = cl.post('/select/act', data={'act': 'pptx', 'qids': ['1']}, auth=A, headers=H)
    assert r.status_code == 422 and 'Pandoc' in r.text


def test_pptx_images_safe(tmp_path):
    (tmp_path / 'B' / 'images').mkdir(parents=True); (tmp_path / 'B' / 'images' / 'a.png').write_bytes(b'x')
    t = '![ok](images/a.png) ![svg](images/a.svg) ![up](../../etc/x.png) ![url](http://x/a.png)\n```\n![c](images/a.png)\n```'
    o = X._pptx_images(t, 'B', str(tmp_path))
    assert str(tmp_path / 'B' / 'images' / 'a.png') in o.split('```')[0] and o.count('![') == 1 + 1   # ok + μέσα στο fence
    assert '*[svg]*' in o and '*[up]*' in o and '*[url]*' in o
