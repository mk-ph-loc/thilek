"""0.39: προσωρινός φάκελος στα Εργαλεία αρχείων (upload, αντιγραφή θεμάτων, συγχώνευση με δικά μου αρχεία) και φίλτρο λίστας."""
import io, os, pathlib
from tests.test_qsol import env, A, H  # noqa: F401


def pdf_bytes(n=1):
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(n): w.add_blank_page(200, 200)
    b = io.BytesIO(); w.write(b); return b.getvalue()


def up(cl, files, **d):
    return cl.post('/fileops/stage/upload', data={'tab': 'merge', 'dir': '', **d}, files=[('files', f) for f in files], auth=A, headers=H, follow_redirects=False)


def test_upload_list_dedupe_and_rejects(env):
    cl, tmp = env; st = tmp / 'data' / '_PROSORINO'
    r = up(cl, [('00_exofyllo.pdf', pdf_bytes(1), 'application/pdf'), ('notes.txt', b'hello', 'text/plain')]); assert r.status_code == 303 and 'msg=' in r.headers['location']
    assert sorted(os.listdir(st)) == ['00_exofyllo.pdf', 'notes.txt']
    r = up(cl, [('00_exofyllo.pdf', pdf_bytes(2), 'application/pdf')]); assert (st / '00_exofyllo_2.pdf').exists()                    # δεν αντικαθίσταται
    r = up(cl, [('fake.pdf', b'not a pdf', 'application/pdf')]); assert r.status_code == 422 and not (st / 'fake.pdf').exists()
    r = up(cl, [('evil.html', b'<script>', 'text/html'), ('x.zip', b'PK', 'application/zip')]); assert r.status_code == 422
    r = up(cl, [('.hidden.pdf', pdf_bytes(), 'application/pdf'), ('../x.pdf', pdf_bytes(), 'application/pdf')]); assert not list(st.glob('.hidden*')) and not (tmp / 'data' / 'x.pdf').exists()
    assert cl.post('/fileops/stage/upload', data={'tab': 'merge'}, files=[('files', ('a.pdf', pdf_bytes(), 'application/pdf'))], auth=A).status_code == 403   # same_origin
    pg = cl.get('/fileops?tab=merge', auth=A).text; assert '_PROSORINO/00_exofyllo.pdf' in pg and 'foFilter' in pg and 'fileops.js' in pg and 'Άδειασμα προσωρινού' in pg
    pg = cl.get('/fileops?tab=split', auth=A).text; assert 'type=radio' in pg and 'foAuto' not in pg and '_PROSORINO/notes.txt' not in pg      # split: μόνο PDF, χωρίς αυτόματη επιλογή
    assert 'notes.txt' in cl.get('/fileops?tab=rename', auth=A).text


def test_merge_staged_with_topics_and_output_rules(env):
    cl, tmp = env; root = tmp / 'data'; up(cl, [('00_exofyllo.pdf', pdf_bytes(2), 'application/pdf')])
    out = root / 'C' / '04_TRAPEZA' / 'orig'; (out / 'a.pdf').write_bytes(pdf_bytes(3))
    r = cl.post('/fileops/stage/copy', data={'tab': 'merge', 'dir': 'C/04_TRAPEZA/orig', 'src': 'C/04_TRAPEZA/orig/a.pdf'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303 and (root / '_PROSORINO' / 'a.pdf').exists()
    assert (out / 'a.pdf').exists()                                                                                                             # το πρωτότυπο μένει
    assert cl.post('/fileops/stage/copy', data={'src': '_PROSORINO/a.pdf'}, auth=A, headers=H).status_code == 422
    base = {'tab': 'merge', 'dir': 'C/04_TRAPEZA/orig', 'outname': 'all.pdf', 'order': 'name'}
    # μόνο προσωρινά + κενός φάκελος εξόδου -> ζητά ρητό φάκελο εξόδου (δεν γράφει μέσα στον προσωρινό)
    r = cl.post('/fileops/preview', data={**base, 'src': ['_PROSORINO/00_exofyllo.pdf', '_PROSORINO/a.pdf']}, auth=A, headers=H); assert r.status_code == 422
    assert cl.post('/fileops/preview', data={**base, 'src': ['_PROSORINO/a.pdf'], 'outdir': '_PROSORINO/07_EXAGOGES'}, auth=A, headers=H).status_code == 422
    # φάκελος + προσωρινά: το μάθημα βγαίνει από το αρχείο του φακέλου
    sel = ['_PROSORINO/00_exofyllo.pdf', 'C/04_TRAPEZA/orig/a.pdf']
    pv = cl.post('/fileops/preview', data={**base, 'src': sel}, auth=A, headers=H); assert pv.status_code == 200 and 'C/07_EXAGOGES/files/all.pdf' in pv.text and '5 σελίδες' in pv.text
    assert cl.post('/fileops/apply', data={**base, 'src': sel}, auth=A, headers=H, follow_redirects=False).status_code == 303
    from pypdf import PdfReader; assert len(PdfReader(str(root / 'C' / '07_EXAGOGES' / 'files' / 'all.pdf')).pages) == 5
    assert cl.post('/fileops/apply', data={**base, 'src': sel, 'outdir': 'C/07_EXAGOGES/files'}, auth=A, headers=H).status_code in (409, 422)    # όχι αντικατάσταση
    assert 'fodirs' in cl.get('/fileops?tab=merge', auth=A).text and 'C/07_EXAGOGES/files' in cl.get('/fileops?tab=merge', auth=A).text


def test_rename_inplace_staged_delete_and_clear(env):
    cl, tmp = env; st = tmp / 'data' / '_PROSORINO'; up(cl, [('a.pdf', pdf_bytes(), 'application/pdf'), ('b.pdf', pdf_bytes(), 'application/pdf')])
    d = {'tab': 'rename', 'dir': '', 'mode': 'inplace', 'tpl': 'x_{name}', 'src': ['_PROSORINO/a.pdf', '_PROSORINO/b.pdf']}
    pv = cl.post('/fileops/preview', data=d, auth=A, headers=H); assert pv.status_code == 200 and 'x_a.pdf' in pv.text
    assert cl.post('/fileops/apply', data=d, auth=A, headers=H, follow_redirects=False).status_code == 303 and sorted(os.listdir(st)) == ['x_a.pdf', 'x_b.pdf']
    r = cl.post('/fileops/stage/delete', data={'tab': 'merge', 'src': ['_PROSORINO/x_a.pdf', 'C/04_TRAPEZA/orig/1.pdf']}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303 and os.listdir(st) == ['x_b.pdf']
    assert (tmp / 'data' / 'C' / '04_TRAPEZA' / 'orig' / '1.pdf').exists()                                                                      # διαγράφει μόνο προσωρινά
    assert cl.post('/fileops/stage/delete', data={'src': ['C/04_TRAPEZA/orig/1.pdf']}, auth=A, headers=H).status_code == 422
    assert cl.post('/fileops/stage/clear', data={'tab': 'merge'}, auth=A, headers=H, follow_redirects=False).status_code == 303 and os.listdir(st) == []


def test_filter_js_served_and_select_all_respects_hidden(env):
    cl, _ = env; js = cl.get('/static/fileops.js').text; assert 'foFilter' in js and 'normalize' in js and 'javascript:' not in js
    assert "l.hidden" in cl.get('/static/app.js').text and 'label[hidden]' in cl.get('/fileops?tab=merge', auth=A).text
