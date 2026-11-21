#!/usr/bin/env python3
"""Rebuild the SQLite DB from files. Manual/AI links (question_section.origin != 'iep') are carried over.
Λύσεις εκπαιδευτικού (<ID>.<θέμα>-<υπ>.md στο orig/) ξαναδιαβάζονται από τα αρχεία (qsol.scan)· προειδοποιήσεις στο 04_TRAPEZA/solution_warnings.txt.
usage: rebuild.py <data_root> <db>"""
import sys, re, json, csv, sqlite3, pathlib, tempfile, shutil, os
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import ingest, suggest_links, openpyxl
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app import qsol
SCHEMA = pathlib.Path(__file__).parent.parent / 'app' / 'schema.sql'
COURSES = [{'code': 'B-ILEKTROTECHNIA', 'title': 'Ηλεκτροτεχνία', 'grade': 'Β΄ ΕΠΑΛ', 'exam': 'TTDD',
            'xlsx': '04_TRAPEZA/iep_index_219.xlsx', 'book': '02_VIVLIA/24-0332-02-V3_Ilektrotechnia_B-G-EPAL_Vivlio-Mathiti.pdf',
            'book_title': 'Ηλεκτροτεχνία Β΄ & Γ΄ ΕΠΑ.Λ.', 'pdf_offset': 1}]

def main(root, db):
    root = pathlib.Path(root); old = []; books = []; old_q = []; done = []
    if os.path.exists(db):
        o = sqlite3.connect(db)
        old = o.execute("SELECT x.item_id,x.code,s.code,qs.origin FROM question_section qs JOIN question x ON x.id=qs.question_id JOIN section s ON s.id=qs.section_id WHERE qs.origin IN ('manual','ai','rejected')").fetchall(); old_q = o.execute("SELECT item_id,code,qtype,qtype_origin,has_image,image_origin FROM question WHERE qtype_origin='manual' OR image_origin='manual'").fetchall() if 'qtype_origin' in [r[1] for r in o.execute('PRAGMA table_info(question)')] else []; o.close()
    tmp = db + '.new'; pathlib.Path(tmp).unlink(missing_ok=True)
    c = sqlite3.connect(tmp); c.executescript(SCHEMA.read_text(encoding='utf-8'))
    for co in COURSES:
        cdir = root / co['code']
        if not (cdir / '04_TRAPEZA' / 'orig').is_dir(): print('παράλειψη', co['code']); continue
        xlsx = cdir / co['xlsx']; ingest.run(cdir, xlsx)
        c.execute('INSERT INTO course VALUES(?,?,?,?)', (co['code'], co['title'], co['grade'], co['exam']))
        bid = c.execute('INSERT INTO book(course_code,title_el,relpath,pdf_offset) VALUES(?,?,?,?)', (co['code'], co['book_title'], f"{co['code']}/{co['book']}", co['pdf_offset'])).lastrowid
        books.append((bid, cdir / co['book'], co['pdf_offset'])); done.append((co['code'], cdir))
        rows = list(csv.DictReader(open(cdir / '03_YLI' / 'book_sections.csv', encoding='utf-8'))); units = {}
        for r in rows:
            a = int(r['page_from']); b = int(r['page_to_next_start'] or a)
            c.execute('INSERT INTO section(book_id,code,level,title_el,page_from,page_to,note) VALUES(?,?,?,?,?,?,?)', (bid, r['code'], int(r['level']), r['title'], a, b if r['page_to_next_start'] else None, r['note']))
            u = '.'.join(r['code'].split('.')[:2]); lo, hi = units.get(u, (a, b)); units[u] = (min(lo, a), max(hi, b))
        for u, (a, b) in units.items():
            c.execute("INSERT OR IGNORE INTO section(book_id,code,level,title_el,page_from,page_to,note) VALUES(?,?,2,?,?,?,'ενότητα (υπολογίστηκε)')", (bid, u, 'Ενότητα ' + u, a, b))
        for r in openpyxl.load_workbook(xlsx)['Θέματα'].iter_rows(min_row=5, values_only=True):
            if not r[0]: continue
            i = str(r[0]); tt = cdir / '04_TRAPEZA'; j = tt / 'derived' / i / 'item.json'
            info = json.loads(j.read_text(encoding='utf-8')) if j.exists() else {}
            m = re.match(r'(\d+\.\d+)', r[8] or '')
            c.execute('INSERT INTO item(id,course_code,source,position,iep_date,iep_yli,iep_chapter,statement_path,solution_path,solution_status) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (i, co['code'], 'TTDD', int(r[2].split()[-1]) if r[2] else None, r[1].date().isoformat() if r[1] else None, r[8], r[9],
                 f"{co['code']}/04_TRAPEZA/orig/{i}.pdf" if (tt / 'orig' / f'{i}.pdf').exists() else None,
                 f"{co['code']}/04_TRAPEZA/orig/{i}_SOLUTION.pdf" if (tt / 'orig' / f'{i}_SOLUTION.pdf').exists() else None, info.get('solution_status', 'not_ingested')))
            for qd in info.get('questions', []):
                qid = c.execute('INSERT INTO question(item_id,code,points,text,qtype,has_image,geo,sol_geo,sol_text) VALUES(?,?,?,?,?,?,?,?,?)', (i, qd['code'], qd['points'], qd['text'], qd.get('qtype'), qd.get('has_image', 0), json.dumps(qd['geo']) if qd.get('geo') else None, json.dumps(qd['sol_geo']) if qd.get('sol_geo') else None, qd.get('sol_text'))).lastrowid
                if m:
                    s = c.execute('SELECT id FROM section WHERE book_id=? AND code=?', (bid, m.group(1))).fetchone()
                    if s: c.execute("INSERT INTO question_section(question_id,section_id,origin) VALUES(?,?,'iep')", (qid, s[0]))
    kept = 0
    for item_id, qcode, scode, origin in old:
        r = c.execute('SELECT x.id,(SELECT id FROM section WHERE code=? LIMIT 1) FROM question x WHERE x.item_id=? AND x.code=?', (scode, item_id, qcode)).fetchone()
        if r and r[1]: c.execute('INSERT OR REPLACE INTO question_section(question_id,section_id,origin) VALUES(?,?,?)', (r[0], r[1], origin)); kept += 1
    for item_id, code, qt, qo, hi, io in old_q:        # χειροκίνητες διορθώσεις τύπου/εικόνας
        if qo == 'manual': c.execute("UPDATE question SET qtype=?,qtype_origin='manual' WHERE item_id=? AND code=?", (qt, item_id, code))
        if io == 'manual': c.execute("UPDATE question SET has_image=?,image_origin='manual' WHERE item_id=? AND code=?", (hi, item_id, code))
    if os.path.exists(db):                                  # διαγωνίσματα: αντιγραφή όπως είναι
        c.commit(); c.execute('ATTACH DATABASE ? AS old', (db,))
        have = {r[0] for r in c.execute("SELECT name FROM old.sqlite_master WHERE type='table'")}
        for t in ('exam', 'exam_question', 'question_tag', 'collection', 'collection_member', 'quiz', 'quiz_item', 'mdoc', 'question_fav', 'toolbox', 'trash', 'fileops', 'setting', 'wizard_recipe', 'iepcmp'):      # δεδομένα χρήστη: αντιγραφή (κοινές στήλες)
            if t in have:
                new = [r[1] for r in c.execute(f'PRAGMA main.table_info({t})')]; oldc = {r[1] for r in c.execute(f'PRAGMA old.table_info({t})')}
                cols = ','.join(x for x in new if x in oldc); c.execute(f'INSERT INTO main.{t}({cols}) SELECT {cols} FROM old.{t}')
        c.commit(); c.execute('DETACH DATABASE old')
    for code, cdir in done:                                 # λύσεις εκπαιδευτικού: από τα αρχεία .md (πηγή αλήθειας), μετά τα ερωτήματα
        res = qsol.scan(c, root, code); print(code + ':', qsol.summary(res))
        try: (cdir / '04_TRAPEZA' / 'solution_warnings.txt').write_text('\n'.join(res['warnings']), encoding='utf-8')
        except OSError as ex: print('δεν γράφτηκε το solution_warnings.txt:', ex)
        for w in res['warnings'][:20]: print('  ', w)
    c.commit()
    auto = 0
    for bid, pdf, off in books:
        if pdf.exists(): auto += suggest_links.suggest(c, bid, pdf, off)
        else: print('δεν βρέθηκε το βιβλίο:', pdf)
    c.commit()
    from app import searchindex
    pg, nq = searchindex.reindex(c, root); print(f'ευρετήριο αναζήτησης: {pg} σελίδες βιβλίου, {nq} ερωτήματα')
    n = [c.execute(f'select count(*) from {t}').fetchone()[0] for t in ('item', 'question', 'question_section')]; c.close()
    os.replace(tmp, db); print(f'items={n[0]} questions={n[1]} links={n[2]} auto_links={auto} carried_over={kept}/{len(old)}')
    if kept != len(old): print('ΠΡΟΣΟΧΗ: χάθηκαν', len(old) - kept, 'χειροκίνητες συνδέσεις (άλλαξε θέμα/ερώτημα/ενότητα)')
if __name__ == '__main__': main(*sys.argv[1:3])
