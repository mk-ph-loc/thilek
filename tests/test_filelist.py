"""0.28.0: αρχεία εξαγωγής στο βήμα 6 του wizard (λίστα, zip, merge PDF)."""
import io, os, sqlite3, zipfile
from pypdf import PdfReader, PdfWriter
from tests.test_docs import cl, A, H  # noqa: F401
from tests.test_wizard import seed, new, post


def pdf(n):
    w = PdfWriter()
    for _ in range(n): w.add_blank_page(200, 200)
    b = io.BytesIO(); w.write(b); return b.getvalue()


def setup(cl):
    seed(); root = os.environ['THILEK_ROOT']; o = os.path.join(root, 'C', '04_TRAPEZA', 'orig'); os.makedirs(o)
    open(os.path.join(o, '1.pdf'), 'wb').write(pdf(2)); open(os.path.join(o, '1_SOLUTION.pdf'), 'wb').write(pdf(3))
    open(os.path.join(o, '1.docx'), 'wb').write(b'PK-fake-docx')
    l = os.path.join(root, 'C', '05_LYSEIS'); os.makedirs(l); open(os.path.join(l, '1.2-1.md'), 'w', encoding='utf-8').write('# λύση\n')
    open(os.path.join(root, 'C', 'book.pdf'), 'wb').write(pdf(5))
    c = sqlite3.connect(os.environ['THILEK_DB'])
    c.execute("UPDATE book SET relpath='C/book.pdf', title_el='Βιβλίο Τεστ' WHERE id=1")
    c.execute("INSERT INTO qsolution(item_id,qcode,relpath) VALUES('1','2.1','C/05_LYSEIS/1.2-1.md')")
    c.execute("INSERT INTO wordsrc(item_id,kind,relpath,status) VALUES('1','statement','C/04_TRAPEZA/orig/1.docx','ok')")
    c.commit(); c.close()
    rid = new(cl); post(cl, rid, 1, action='add', qids=['1', '2']); post(cl, rid, 4, format='excel', go='next'); return rid


def keys(cl, rid):
    import re
    h = cl.get(f'/wizard/{rid}/6', auth=A).text
    return h, re.findall(r"name=f value='([^']+)'", h)


def test_step6_lists_files_with_links(cl):
    rid = setup(cl); h, ks = keys(cl, rid)
    assert 'Αρχεία που χρησιμοποιήθηκαν ή σχετίζονται' in h
    assert set(ks) == {'C/04_TRAPEZA/orig/1.pdf', 'C/04_TRAPEZA/orig/1_SOLUTION.pdf', 'C/04_TRAPEZA/orig/1.docx', 'C/05_LYSEIS/1.2-1.md', 'C/book.pdf'}
    assert '/fb/raw?p=C/04_TRAPEZA/orig/1.pdf&dl=1' in h and "/wizard/%d/files/zip" % rid in h and "/wizard/%d/files/merge" % rid in h
    assert "value='C/book.pdf'>" in h and "value='C/book.pdf' checked" not in h        # το βιβλίο δεν είναι προεπιλεγμένο
    assert "value='C/04_TRAPEZA/orig/1.pdf' checked" in h


def test_missing_file_shown_without_checkbox(cl):
    rid = setup(cl); os.remove(os.path.join(os.environ['THILEK_ROOT'], 'C', '04_TRAPEZA', 'orig', '1_SOLUTION.pdf'))
    h, ks = keys(cl, rid); assert 'C/04_TRAPEZA/orig/1_SOLUTION.pdf' not in ks and 'λείπει από τον server' in h and '1 λείπουν' in h


def test_zip_selected_structure(cl):
    rid = setup(cl); _, ks = keys(cl, rid)
    r = cl.post(f'/wizard/{rid}/files/zip', data={'f': ks}, auth=A, headers=H); assert r.status_code == 200 and r.headers['content-type'] == 'application/zip'
    z = zipfile.ZipFile(io.BytesIO(r.content)); n = z.namelist()
    assert {'pdf/1.pdf', 'pdf/1_SOLUTION.pdf', 'word/1.docx', 'lyseis/1.2-1.md', 'book/book.pdf', 'README.txt'} <= set(n)
    assert z.read('lyseis/1.2-1.md').decode('utf-8') == '# λύση\n'
    r = cl.post(f'/wizard/{rid}/files/zip', data={'f': ['C/04_TRAPEZA/orig/1.pdf']}, auth=A, headers=H); assert zipfile.ZipFile(io.BytesIO(r.content)).namelist().count('pdf/1.pdf') == 1 and len(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == 2


def test_merge_only_pdfs_in_list_order_with_bookmarks(cl):
    rid = setup(cl); _, ks = keys(cl, rid)
    r = cl.post(f'/wizard/{rid}/files/merge', data={'f': ks}, auth=A, headers=H); assert r.status_code == 200 and r.headers['content-type'] == 'application/pdf'
    rd = PdfReader(io.BytesIO(r.content)); assert len(rd.pages) == 2 + 3 + 5 and r.headers['x-pages'] == '10'
    assert [o.title for o in rd.outline] == ['Θέμα 1', 'Λύση ΙΕΠ 1', 'Βιβλίο Τεστ']


def test_rejects_foreign_paths_and_empty_selection(cl):
    rid = setup(cl)
    for f in (['../t.db'], ['C/../../etc/passwd'], ['/etc/passwd'], ['C/book.pdf/../../t.db']):
        r = cl.post(f'/wizard/{rid}/files/zip', data={'f': f}, auth=A, headers=H); assert r.status_code == 422
    assert cl.post(f'/wizard/{rid}/files/zip', data={}, auth=A, headers=H).status_code == 422
    assert cl.post(f'/wizard/{rid}/files/merge', data={'f': ['C/05_LYSEIS/1.2-1.md']}, auth=A, headers=H).status_code == 422     # δεν υπάρχει PDF
    assert cl.post(f'/wizard/{rid}/files/zip', data={'f': ['C/book.pdf']}).status_code in (401, 403)


def test_requires_same_origin_and_limits(cl, monkeypatch):
    rid = setup(cl); _, ks = keys(cl, rid)
    assert cl.post(f'/wizard/{rid}/files/zip', data={'f': ks}, auth=A, headers={'Origin': 'http://evil.example'}).status_code in (400, 403)
    from app import filelist
    monkeypatch.setattr(filelist, 'MAX_ZIP', 10); assert cl.post(f'/wizard/{rid}/files/zip', data={'f': ks}, auth=A, headers=H).status_code == 422
    monkeypatch.setattr(filelist, 'MAX_ZIP', 10 ** 9); monkeypatch.setattr(filelist, 'MAX_FILES', 2); assert cl.post(f'/wizard/{rid}/files/zip', data={'f': ks}, auth=A, headers=H).status_code == 422


def test_corrupt_pdf_gives_clear_error(cl):
    rid = setup(cl); open(os.path.join(os.environ['THILEK_ROOT'], 'C', '04_TRAPEZA', 'orig', '1.pdf'), 'wb').write(b'not a pdf')
    r = cl.post(f'/wizard/{rid}/files/merge', data={'f': ['C/04_TRAPEZA/orig/1.pdf']}, auth=A, headers=H); assert r.status_code == 422 and 'Θέμα 1' in r.text


def test_no_files_message(cl):
    seed(); rid = new(cl); post(cl, rid, 1, action='add', qids=['2']); post(cl, rid, 4, format='excel', go='next')
    c = sqlite3.connect(os.environ['THILEK_DB']); c.execute("UPDATE item SET statement_path=NULL, solution_path=NULL"); c.execute("UPDATE book SET relpath=NULL"); c.commit(); c.close()
    assert 'Δεν βρέθηκαν αρχεία' in cl.get(f'/wizard/{rid}/6', auth=A).text


def test_initial_selected_counter(cl):
    rid = setup(cl); h, ks = keys(cl, rid); assert '<span id=count>4</span>' in h      # 4 προεπιλεγμένα (χωρίς το βιβλίο)
