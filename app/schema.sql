PRAGMA foreign_keys=ON;
CREATE TABLE course(code TEXT PRIMARY KEY, title_el TEXT NOT NULL, grade TEXT, exam_type TEXT);          -- TTDD | PAN
CREATE TABLE book(id INTEGER PRIMARY KEY, course_code TEXT REFERENCES course(code), title_el TEXT, relpath TEXT, pdf_offset INTEGER NOT NULL DEFAULT 1); -- printed = pdf - offset
CREATE TABLE section(id INTEGER PRIMARY KEY, book_id INTEGER REFERENCES book(id), code TEXT, level INTEGER, title_el TEXT, page_from INTEGER, page_to INTEGER, note TEXT, UNIQUE(book_id,code));
CREATE TABLE item(id TEXT PRIMARY KEY, course_code TEXT REFERENCES course(code), source TEXT NOT NULL,   -- TTDD|PAN|OWN|COLL
  position INTEGER, iep_date TEXT, iep_yli TEXT, iep_chapter TEXT, is_public INTEGER NOT NULL DEFAULT 1,
  statement_path TEXT, solution_path TEXT, solution_status TEXT, sha_statement TEXT, sha_solution TEXT);
CREATE TABLE question(id INTEGER PRIMARY KEY, item_id TEXT REFERENCES item(id), code TEXT, points INTEGER, text TEXT, kind TEXT,
  qtype TEXT, qtype_origin TEXT NOT NULL DEFAULT 'auto', has_image INTEGER NOT NULL DEFAULT 0, image_origin TEXT NOT NULL DEFAULT 'auto', -- qtype: mcq|true_false|matching|fill|problem|development
  geo TEXT, sol_geo TEXT, sol_text TEXT,   -- JSON {regions:[{p,x0,y0,x1,y1}],mask:[p,x0,y0,x1,y1]|null}, σε σημεία PDF
  UNIQUE(item_id,code));
CREATE TABLE question_section(question_id INTEGER REFERENCES question(id), section_id INTEGER REFERENCES section(id), origin TEXT NOT NULL, score REAL, -- iep|auto|manual|ai
  PRIMARY KEY(question_id,section_id));
CREATE TABLE yli_year(book_id INTEGER REFERENCES book(id), school_year TEXT, covered_until_page INTEGER, note TEXT, PRIMARY KEY(book_id,school_year));
CREATE INDEX ix_item_course ON item(course_code); CREATE INDEX ix_sec_pages ON section(book_id,page_from,page_to);
CREATE TABLE exam(id INTEGER PRIMARY KEY, title TEXT NOT NULL, subtitle TEXT, school TEXT, class_name TEXT, exam_date TEXT, duration TEXT, notes TEXT, created TEXT);
CREATE TABLE exam_question(exam_id INTEGER NOT NULL, grp INTEGER NOT NULL DEFAULT 1, pos INTEGER NOT NULL, item_id TEXT NOT NULL, qcode TEXT NOT NULL, PRIMARY KEY(exam_id,item_id,qcode)); -- αναφορά με (item_id, qcode), επιβιώνει του rebuild
CREATE TABLE question_tag(item_id TEXT NOT NULL, qcode TEXT NOT NULL, tag TEXT NOT NULL, PRIMARY KEY(item_id,qcode,tag)); -- επιβιώνει του rebuild
CREATE INDEX ix_qtag ON question_tag(tag);
CREATE TABLE collection(id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'selection', note TEXT, criteria TEXT, options TEXT, created TEXT, saved_file TEXT); -- criteria/options: JSON
CREATE TABLE collection_member(collection_id INTEGER NOT NULL, pos INTEGER NOT NULL, item_id TEXT NOT NULL, qcode TEXT, PRIMARY KEY(collection_id,pos)); -- qcode NULL = ολόκληρο το θέμα
CREATE TABLE quiz(id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT, created TEXT);
CREATE TABLE quiz_item(id INTEGER PRIMARY KEY, quiz_id INTEGER NOT NULL, pos INTEGER NOT NULL, kind TEXT NOT NULL,   -- kind: tf|mcq|free
  stem TEXT, options TEXT, answer TEXT,   -- options: JSON λίστα· answer: tf 'Σωστό'/'Λάθος', mcq δείκτης επιλογής (0-based), free κείμενο
  points REAL NOT NULL DEFAULT 1, feedback TEXT, src_item TEXT, src_qcode TEXT, src_part TEXT, use_image INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ok'); -- status: ok|review
CREATE INDEX ix_qitem ON quiz_item(quiz_id,pos);
CREATE TABLE mdoc(id INTEGER PRIMARY KEY, name TEXT NOT NULL, markdown TEXT NOT NULL DEFAULT '', source TEXT, created TEXT, updated TEXT);
CREATE TABLE question_fav(item_id TEXT NOT NULL, qcode TEXT NOT NULL, added TEXT, PRIMARY KEY(item_id,qcode)); -- αγαπημένα· επιβιώνει του rebuild
CREATE TABLE qsolution(item_id TEXT NOT NULL, qcode TEXT NOT NULL, question_id INTEGER, iep_id TEXT, sub TEXT, relpath TEXT NOT NULL,   -- λύσεις εκπαιδευτικού από <ID>.<θέμα>-<υπ>.md
  fm TEXT, sections TEXT, quiz TEXT, status TEXT, warn TEXT, mtime REAL, sha TEXT, PRIMARY KEY(item_id,qcode)); -- JSON πεδία· ξαναχτίζεται από τα αρχεία (όχι δεδομένα χρήστη)
CREATE TABLE schema_version(version INTEGER NOT NULL); -- app/migrations.py: LATEST
INSERT INTO schema_version(version) VALUES(7);
-- 0.18.0: εργαλειοθήκες, κάδος αρχείων, ιστορικό ενεργειών αρχείων, ρυθμίσεις (δεδομένα χρήστη, διατηρούνται στο rebuild)
CREATE TABLE IF NOT EXISTS toolbox(slot INTEGER PRIMARY KEY CHECK(slot BETWEEN 1 AND 3), name TEXT NOT NULL, items TEXT NOT NULL DEFAULT '[]', enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS trash(id INTEGER PRIMARY KEY, orig_rel TEXT NOT NULL, trash_rel TEXT NOT NULL, kind TEXT, size INTEGER, deleted TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS fileops(id INTEGER PRIMARY KEY, ts TEXT, op TEXT, path TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS setting(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS wordsrc(item_id TEXT NOT NULL, kind TEXT NOT NULL, relpath TEXT, sha TEXT, mtime REAL, n_par INTEGER, n_eq INTEGER, n_img INTEGER, n_q INTEGER, pts INTEGER, status TEXT, warn TEXT, text TEXT, images TEXT, PRIMARY KEY(item_id,kind)); -- παράγωγος: ξαναχτίζεται από τα .docx (rebuild ή Σάρωση Word)
CREATE TABLE IF NOT EXISTS ownitem(item_id TEXT PRIMARY KEY, title TEXT, year TEXT, note TEXT); -- δικά μου/πανελλήνια θέματα (τα θέματα και ερωτήματά τους μεταφέρονται στο rebuild)
CREATE TABLE IF NOT EXISTS iepcmp(item_id TEXT NOT NULL, qcode TEXT NOT NULL, qn INTEGER NOT NULL, kind TEXT, mine TEXT, iep TEXT, auto TEXT, status TEXT, manual INTEGER NOT NULL DEFAULT 0, note TEXT, updated TEXT, PRIMARY KEY(item_id,qcode,qn)); -- επιβιώνει του rebuild
CREATE TABLE IF NOT EXISTS wizard_recipe(id INTEGER PRIMARY KEY, name TEXT NOT NULL, state TEXT NOT NULL DEFAULT '{}', created TEXT, updated TEXT); -- επιβιώνει του rebuild
CREATE TABLE deck(id INTEGER PRIMARY KEY, name TEXT NOT NULL, title TEXT, subtitle TEXT, recipe TEXT NOT NULL DEFAULT 'free', state TEXT NOT NULL DEFAULT '{}',
  style TEXT NOT NULL DEFAULT 'calm', opts TEXT NOT NULL DEFAULT '{}', kind INTEGER NOT NULL DEFAULT 0, course_code TEXT, note TEXT, created TEXT, updated TEXT);
CREATE TABLE deck_slide(id INTEGER PRIMARY KEY, deck_id INTEGER NOT NULL, pos INTEGER NOT NULL, layout TEXT NOT NULL DEFAULT 'content', title TEXT, body TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
  opts TEXT NOT NULL DEFAULT '{}', down INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0, src_item TEXT, src_qcode TEXT, src_unit TEXT, src_part INTEGER, src_sha TEXT, gen_sha TEXT, linked INTEGER NOT NULL DEFAULT 0, updated TEXT);
CREATE INDEX ix_dslide ON deck_slide(deck_id,pos); -- 0.32: παρουσιάσεις (δεδομένα χρήστη, επιβιώνουν του rebuild)
