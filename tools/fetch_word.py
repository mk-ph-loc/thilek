#!/usr/bin/env python3
"""Κατεβάζει τα αρχεία Word (εκφώνηση και απάντηση) της Τράπεζας Θεμάτων ΙΕΠ, τα μετονομάζει και τα μετατρέπει σε .docx.

Τρέχει ΤΟΠΙΚΑ (Windows/Linux/Mac) και χρειάζεται μόνο Python 3.8+ (καμία εξωτερική βιβλιοθήκη).

Τι κάνει
  1. Διαβάζει τους συνδέσμους από το ευρετήριο  iep_index_219.xlsx  (στήλες «Εκφώνηση (Word)» και «Απάντηση (Word)»).
     Αν λείπει το xlsx, χρησιμοποιεί το manifest.csv και τη γνωστή μορφή συνδέσμου.
  2. Κατεβάζει κάθε αρχείο ευγενικά (παύση, επαναλήψεις) και αναγνωρίζει τη μορφή από το περιεχόμενο (όχι από την κατάληξη):
     .docx (νέο Word), .doc (παλιό Word), .rtf, ή λάθος (PDF/σελίδα σφάλματος).
  3. Αποθηκεύει δίπλα στα PDF με το ίδιο όνομα:   <ID>.docx   και   <ID>_SOLUTION.docx   (στον φάκελο orig/).
  4. Τα παλιά .doc μετατρέπονται σε .docx με LibreOffice (soffice) ή, αν δεν υπάρχει, με Microsoft Word.
     Το αρχικό .doc φυλάσσεται στο orig/word_original/.
  5. Γράφει αρχείο καταγραφής word_log.csv και δείχνει σύνοψη. Μπορεί να ξανατρέξει: όσα υπάρχουν ήδη προσπερνιούνται.

Χρήση
  python fetch_word.py  C:\\...\\B-ILEKTROTECHNIA\\04_TRAPEZA
  python fetch_word.py  <φάκελος>  --dry-run          (μόνο λίστα, χωρίς λήψη)
  python fetch_word.py  <φάκελος>  --limit 3           (δοκιμή με 3 θέματα)
  python fetch_word.py  <φάκελος>  --only statement    (μόνο εκφωνήσεις)   |  --only answer
  python fetch_word.py  <φάκελος>  --convert word      (αναγκαστικά με Microsoft Word)   |  soffice | none | auto
  python fetch_word.py  <φάκελος>  --force             (ξανακατέβασμα και αν υπάρχουν)
"""
import argparse, csv, datetime, hashlib, io, os, re, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request, zipfile
import xml.etree.ElementTree as ET

if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main', 'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
RNS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
URL_FMT = 'https://subjects.draw.iep.edu.gr/{id}-{ft}?unique_identifier={id}&file_type={ft}'
FT = {'statement': 0, 'answer': 4}                     # file_type: 0 = Word εκφώνησης, 4 = Word απάντησης
SUFFIX = {'statement': '', 'answer': '_SOLUTION'}
HEAD = {'statement': 'Εκφώνηση (Word)', 'answer': 'Απάντηση (Word)'}
UA = 'Mozilla/5.0 (compatible; thilek-fetch-word/1.0)'

# ---------- ευρετήριο ----------
def col_of(ref): return re.match(r'[A-Z]+', ref).group(0)

def read_index_xlsx(path):
    """[(id, {'statement': url|None, 'answer': url|None})] από το xlsx, με συνδέσμους από τα hyperlinks."""
    z = zipfile.ZipFile(path)
    names = z.namelist()
    shared = []
    if 'xl/sharedStrings.xml' in names:
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS):
            shared.append(''.join(t.text or '' for t in si.iter('{%s}t' % NS['m'])))
    # πρώτο φύλλο
    wb = ET.fromstring(z.read('xl/workbook.xml')); rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    rid = wb.find('m:sheets', NS)[0].get(RNS); target = next(r.get('Target') for r in rels if r.get('Id') == rid)
    sheet = 'xl/' + target.lstrip('/').replace('xl/', '', 1) if not target.startswith('/') else target.lstrip('/')
    sx = ET.fromstring(z.read(sheet)); rel_path = sheet.replace('worksheets/', 'worksheets/_rels/') + '.rels'
    links = {}
    if rel_path in names:
        rmap = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read(rel_path))}
        for h in sx.iter('{%s}hyperlink' % NS['m']):
            if h.get(RNS) in rmap: links[h.get('ref')] = rmap[h.get(RNS)]
    cells = {}
    for c in sx.iter('{%s}c' % NS['m']):
        v = c.find('m:v', NS)
        if v is None:
            t = c.find('m:is', NS); val = ''.join(x.text or '' for x in t.iter('{%s}t' % NS['m'])) if t is not None else None
        elif c.get('t') == 's': val = shared[int(v.text)]
        else: val = v.text
        cells[c.get('r')] = val
    hdr = None
    for ref, val in cells.items():
        if val and val.strip() == 'Κωδικός (#)': hdr = int(re.search(r'\d+', ref).group(0)); break
    if hdr is None: raise ValueError('Δεν βρέθηκε η επικεφαλίδα «Κωδικός (#)» στο xlsx.')
    cols = {}
    for ref, val in cells.items():
        if int(re.search(r'\d+', ref).group(0)) == hdr and val:
            for k, h in HEAD.items():
                if val.strip() == h: cols[k] = col_of(ref)
    idcol = next(col_of(r) for r, v in cells.items() if v and v.strip() == 'Κωδικός (#)' and int(re.search(r'\d+', r).group(0)) == hdr)
    out = []
    rows = sorted({int(re.search(r'\d+', r).group(0)) for r in cells} - set(range(0, hdr + 1)))
    for rn in rows:
        raw = cells.get(f'{idcol}{rn}')
        if raw is None or not str(raw).strip().replace('.0', '').isdigit(): continue
        i = str(int(float(raw)))
        out.append((i, {k: links.get(f'{cols[k]}{rn}') for k in cols}))
    return out

def read_index(folder):
    x = [f for f in os.listdir(folder) if f.lower().endswith('.xlsx') and 'index' in f.lower()]
    if x:
        try: return read_index_xlsx(os.path.join(folder, sorted(x)[0])), sorted(x)[0]
        except Exception as e: print('Προειδοποίηση: το xlsx δεν διαβάστηκε (%s). Δοκιμάζω το manifest.csv.' % e)
    m = os.path.join(folder, 'manifest.csv')
    if os.path.isfile(m):
        with open(m, encoding='utf-8-sig', newline='') as f: ids = [r['id'] for r in csv.DictReader(f) if r.get('id')]
        return [(i, {}) for i in ids], 'manifest.csv'
    raise SystemExit('Δεν βρέθηκε ούτε ευρετήριο .xlsx ούτε manifest.csv στον φάκελο: ' + folder)

# ---------- λήψη ----------
def sniff(b):
    if b[:4] == b'PK\x03\x04':
        try:
            n = zipfile.ZipFile(io.BytesIO(b)).namelist()
            return 'docx' if 'word/document.xml' in n else 'zip'
        except Exception: return 'bad'
    if b[:4] == b'\xd0\xcf\x11\xe0': return 'doc'
    if b[:5] == b'{\\rtf': return 'rtf'
    if b[:4] == b'%PDF': return 'pdf'
    head = b[:200].lstrip().lower()
    if head.startswith(b'<') or b'<html' in head: return 'html'
    return 'unknown'

def download(url, retries, delay, mirror=None):
    if mirror: url = re.sub(r'^https?://[^/]+', mirror.rstrip('/'), url)
    last = None
    for a in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=90) as r: return r.read(), None
        except urllib.error.HTTPError as e:
            last = f'HTTP {e.code}'
            if e.code in (400, 401, 403, 404, 410): break            # δεν αξίζει επανάληψη
        except Exception as e: last = f'{type(e).__name__}: {e}'
        time.sleep(delay * a * 2)
    return None, last

# ---------- μετατροπή .doc -> .docx ----------
def find_soffice():
    for n in ('soffice', 'libreoffice'):
        p = shutil.which(n)
        if p: return p
    for p in (r'C:\Program Files\LibreOffice\program\soffice.exe', r'C:\Program Files (x86)\LibreOffice\program\soffice.exe', '/Applications/LibreOffice.app/Contents/MacOS/soffice'):
        if os.path.isfile(p): return p
    return None

def has_word():
    if os.name != 'nt' or not shutil.which('powershell'): return False
    r = subprocess.run(['powershell', '-NoProfile', '-Command', "if (Test-Path 'HKLM:\\SOFTWARE\\Classes\\Word.Application') { 'yes' }"], capture_output=True, text=True)
    return 'yes' in (r.stdout or '')

def convert_soffice(pairs, soffice):
    """pairs: [(src.doc, dst.docx)] — μία κλήση ανά παρτίδα."""
    ok = 0
    for i in range(0, len(pairs), 40):
        chunk = pairs[i:i + 40]
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as prof:
            cmd = [soffice, '--headless', '--norestore', '-env:UserInstallation=' + 'file:///' + prof.replace('\\', '/').lstrip('/'), '--convert-to', 'docx:MS Word 2007 XML', '--outdir', tmp] + [s for s, _ in chunk]
            subprocess.run(cmd, capture_output=True, timeout=600)
            for s, d in chunk:
                out = os.path.join(tmp, os.path.splitext(os.path.basename(s))[0] + '.docx')
                if os.path.isfile(out): shutil.move(out, d); ok += 1
    return ok

def convert_word(pairs):
    ps = ("$ErrorActionPreference='Stop'; $w=New-Object -ComObject Word.Application; $w.Visible=$false; $w.DisplayAlerts=0\n"
          "foreach($l in Get-Content -LiteralPath $args[0] -Encoding UTF8){ $p=$l -split '\\|'; if($p.Count -lt 2){continue}\n"
          " try{ $d=$w.Documents.Open($p[0],$false,$true); $d.SaveAs2($p[1],16); $d.Close($false) }catch{ Write-Host ('ERR '+$p[0]) } }\n$w.Quit()\n")
    with tempfile.TemporaryDirectory() as tmp:
        lst = os.path.join(tmp, 'list.txt'); scr = os.path.join(tmp, 'conv.ps1')
        with open(lst, 'w', encoding='utf-8-sig') as f: f.write('\n'.join(f'{s}|{d}' for s, d in pairs))
        with open(scr, 'w', encoding='utf-8-sig') as f: f.write(ps)
        subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', scr, lst], capture_output=True, timeout=3600)
    return sum(1 for _, d in pairs if os.path.isfile(d))

def valid_docx(p):
    try: return 'word/document.xml' in zipfile.ZipFile(p).namelist()
    except Exception: return False

# ---------- κύριο ----------
def main():
    ap = argparse.ArgumentParser(description='Λήψη, μετονομασία και μετατροπή των Word της Τράπεζας Θεμάτων ΙΕΠ.')
    ap.add_argument('folder', help='ο φάκελος 04_TRAPEZA του μαθήματος (με το iep_index_*.xlsx και τον υποφάκελο orig)')
    ap.add_argument('--only', choices=['statement', 'answer', 'both'], default='both')
    ap.add_argument('--convert', choices=['auto', 'soffice', 'word', 'none'], default='auto')
    ap.add_argument('--delay', type=float, default=0.8, help='παύση μεταξύ λήψεων σε δευτερόλεπτα (προεπιλογή 0.8)')
    ap.add_argument('--retries', type=int, default=3)
    ap.add_argument('--limit', type=int, default=0, help='μόνο τα πρώτα Ν θέματα (δοκιμή)')
    ap.add_argument('--force', action='store_true'); ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--mirror', help=argparse.SUPPRESS)      # μόνο για δοκιμές
    a = ap.parse_args()
    folder = os.path.abspath(a.folder)
    if not os.path.isdir(folder): raise SystemExit('Δεν υπάρχει ο φάκελος: ' + folder)
    orig = os.path.join(folder, 'orig'); old = os.path.join(orig, 'word_original')
    index, src = read_index(folder)
    kinds = ['statement', 'answer'] if a.only == 'both' else [a.only]
    if a.limit: index = index[:a.limit]
    print(f'Ευρετήριο: {src} — {len(index)} θέματα · φάκελος προορισμού: {orig}')
    todo = []
    for i, links in index:
        for k in kinds:
            dst = os.path.join(orig, f'{i}{SUFFIX[k]}.docx')
            if os.path.isfile(dst) and not a.force and valid_docx(dst): continue
            todo.append((i, k, links.get(k) or URL_FMT.format(id=i, ft=FT[k]), dst))
    print(f'Προς λήψη: {len(todo)} αρχεία (τα υπόλοιπα υπάρχουν ήδη).')
    if a.dry_run:
        for i, k, u, d in todo[:20]: print('  ', i, k, u)
        if len(todo) > 20: print('   …')
        return 0
    os.makedirs(orig, exist_ok=True); os.makedirs(old, exist_ok=True)
    log_path = os.path.join(folder, 'word_log.csv'); newlog = not os.path.isfile(log_path)
    log = open(log_path, 'a', encoding='utf-8-sig', newline=''); lw = csv.writer(log)
    if newlog: lw.writerow(['χρόνος', 'id', 'είδος', 'κατάσταση', 'μορφή', 'bytes', 'sha256', 'σημείωση'])
    need_convert = []; stats = {}; fails_in_row = 0
    def rec(i, k, status, fmt='', n=0, sha='', note=''):
        stats[status] = stats.get(status, 0) + 1
        lw.writerow([datetime.datetime.now().isoformat(timespec='seconds'), i, k, status, fmt, n, sha, note]); log.flush()
    for n, (i, k, url, dst) in enumerate(todo, 1):
        data, err = download(url, a.retries, a.delay, a.mirror)
        tag = f'[{n}/{len(todo)}] {i} {k}'
        if data is None:
            print(tag, '— αποτυχία:', err); rec(i, k, 'σφάλμα', note=err); fails_in_row += 1
            if fails_in_row >= 8: print('Πολλές διαδοχικές αποτυχίες: διακοπή (πιθανός περιορισμός από τον server ή πρόβλημα δικτύου). Ξανατρέξε αργότερα.'); break
            time.sleep(a.delay); continue
        fails_in_row = 0; fmt = sniff(data); sha = hashlib.sha256(data).hexdigest(); stem = f'{i}{SUFFIX[k]}'
        if fmt == 'docx':
            with open(dst, 'wb') as f: f.write(data)
            print(tag, '— docx'); rec(i, k, 'ok', 'docx', len(data), sha)
        elif fmt in ('doc', 'rtf'):
            sp = os.path.join(old, f'{stem}.{fmt}')
            with open(sp, 'wb') as f: f.write(data)
            need_convert.append((sp, dst, i, k, fmt, len(data), sha)); print(tag, f'— {fmt} (θα μετατραπεί)')
        else:
            print(tag, f'— μη αποδεκτή μορφή ({fmt})'); rec(i, k, 'λάθος μορφή', fmt, len(data), sha, 'ο server δεν έδωσε Word (πιθανώς δεν υπάρχει για αυτό το θέμα)')
        time.sleep(a.delay)
    if need_convert:
        mode = a.convert; soffice = find_soffice() if mode in ('auto', 'soffice') else None
        word = (mode in ('auto', 'word')) and has_word() if mode != 'soffice' else False
        pairs = [(s, d) for s, d, *_ in need_convert]
        if mode == 'none': print(f'Μετατροπή απενεργοποιημένη: {len(pairs)} αρχεία .doc παραμένουν στο {old}')
        else:
            print(f'Μετατροπή {len(pairs)} αρχείων .doc → .docx …')
            if soffice: print('  με LibreOffice:', soffice); convert_soffice(pairs, soffice)
            missing = [(s, d) for s, d in pairs if not (os.path.isfile(d) and valid_docx(d))]
            if missing and word: print('  με Microsoft Word …'); convert_word(missing)
            if not soffice and not word: print('  ΔΕΝ βρέθηκε ούτε LibreOffice ούτε Microsoft Word. Εγκατάστησε LibreOffice (winget install TheDocumentFoundation.LibreOffice) και ξανατρέξε.')
        for s, d, i, k, fmt, nb, sha in need_convert:
            if os.path.isfile(d) and valid_docx(d): rec(i, k, 'ok', f'{fmt}→docx', nb, sha)
            else: rec(i, k, 'αποτυχία μετατροπής', fmt, nb, sha, 'το αρχικό είναι στο word_original')
    log.close()
    print('\nΣύνοψη:', ', '.join(f'{k}: {v}' for k, v in sorted(stats.items())) or 'τίποτα νέο')
    print('Καταγραφή:', log_path)
    return 1 if any(k != 'ok' for k in stats) else 0

if __name__ == '__main__':
    sys.exit(main())
