"""TH-ILEK: question bank API. Run: uvicorn app.main:app"""
import os, pathlib, sqlite3
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .main_auth import auth
from . import review, tools_merge, tools_html, exams, library, collections, quizzes, mddoc, search, qbrowse, pickq, manual, lyseis, filebrowser, uikit, settings, docsui, syncui, wizard, publish, iepcmp, courses, wordsrc, filelist, progress, fileops, deckui, siteui
from . import __version__, config, migrations

@asynccontextmanager
async def lifespan(app):
    """Εκκίνηση: αναβάθμιση σχήματος βάσης (migrations), χωρίς να εμποδίζει την εκκίνηση αν αποτύχει."""
    try:
        path = config.load()['db']
        if os.path.isfile(path): print('migrations:', migrations.migrate_path(path)); review._MIGRATED.add(path)
    except Exception as ex: print('migrations: αποτυχία', type(ex).__name__, ex)
    yield

app = FastAPI(title='TH-ILEK', version=__version__, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.mount('/static/vendor', StaticFiles(directory=str(pathlib.Path(__file__).parent / 'static' / 'vendor')), name='vendor')   # KaTeX/Reveal τοπικά (καμία CDN)
app.include_router(review.router)
app.include_router(tools_merge.router)
app.include_router(tools_html.router)
app.include_router(exams.router)
app.include_router(library.router)
app.include_router(collections.router)
app.include_router(quizzes.router)
app.include_router(mddoc.router)
app.include_router(search.router)
app.include_router(qbrowse.router)
app.include_router(pickq.router)
app.include_router(manual.router)
app.include_router(lyseis.router)
app.include_router(filebrowser.router)
app.include_router(uikit.router)
app.include_router(settings.router)
app.include_router(docsui.router)
app.include_router(syncui.router)
app.include_router(wizard.router)
app.include_router(publish.router)
app.include_router(iepcmp.router)
app.include_router(courses.router)
app.include_router(wordsrc.router)
app.include_router(filelist.router)
app.include_router(progress.router)
app.include_router(fileops.router)
app.include_router(deckui.router)
app.include_router(siteui.router)
app.add_middleware(docsui.PathMiddleware)
def cfg(): return config.load()

def q(sql, *a):
    c = sqlite3.connect(cfg()['db']); c.row_factory = sqlite3.Row
    try: return [dict(r) for r in c.execute(sql, a)]
    finally: c.close()

@app.get('/health')
def health(): return {'ok': True, 'version': __version__}

@app.get('/items', dependencies=[Depends(auth)])
def items(yli: str | None = None, position: int | None = None, course: str | None = None):
    w, a = [], []
    if yli: w.append('iep_yli LIKE ?'); a.append(yli + '%')
    if position: w.append('position=?'); a.append(position)
    if course: w.append('course_code=?'); a.append(course)
    return q('SELECT id,course_code,position,iep_yli,solution_status FROM item' + (' WHERE ' + ' AND '.join(w) if w else ''), *a)

@app.get('/questions', dependencies=[Depends(auth)])
def questions(qtype: str | None = None, has_image: int | None = None, yli: str | None = None, section: str | None = None, course: str | None = None, limit: int = 500):
    w, a = [], []
    if qtype: w.append('x.qtype=?'); a.append(qtype)
    if has_image is not None: w.append('x.has_image=?'); a.append(has_image)
    if yli: w.append('i.iep_yli LIKE ?'); a.append(yli + '%')
    if course: w.append('i.course_code=?'); a.append(course)
    if section: w.append("x.id IN (SELECT qs.question_id FROM question_section qs JOIN section s ON s.id=qs.section_id WHERE s.code LIKE ? AND qs.origin!='rejected')"); a.append(section + '%')
    return q('SELECT x.id,x.item_id,x.code,x.points,x.qtype,x.has_image,x.text FROM question x JOIN item i ON i.id=x.item_id' + (' WHERE ' + ' AND '.join(w) if w else '') + ' ORDER BY x.item_id,x.id LIMIT ?', *a, max(1, min(limit, 5000)))

@app.get('/items/{iid}', dependencies=[Depends(auth)])
def item(iid: str):
    r = q('SELECT * FROM item WHERE id=?', iid)
    if not r: raise HTTPException(404)
    qs = q('SELECT id,code,points,text,qtype,has_image FROM question WHERE item_id=?', iid)
    for x in qs:
        x['sections'] = q('SELECT s.code,s.title_el,s.page_from,s.page_to,qs.origin,qs.score FROM question_section qs JOIN section s ON s.id=qs.section_id WHERE qs.question_id=? AND qs.origin!=\'rejected\'', x['id'])
    return {**r[0], 'questions': qs}

@app.get('/pages/{n}', dependencies=[Depends(auth)])   # printed page of the book -> sections -> items
def page(n: int):
    secs = q('SELECT id,code,title_el,page_from,page_to FROM section WHERE page_from<=? AND (page_to IS NULL OR ?<=page_to) ORDER BY level DESC', n, n)
    ids = [s['id'] for s in secs]
    its = q('SELECT DISTINCT i.id,i.position,i.iep_yli FROM question_section qs JOIN question x ON x.id=qs.question_id JOIN item i ON i.id=x.item_id WHERE qs.origin!=\'rejected\' AND qs.section_id IN (%s)' % ','.join('?' * len(ids)), *ids) if ids else []
    return {'page': n, 'sections': secs, 'items': its}

@app.get('/files/{rel:path}', dependencies=[Depends(auth)])
def files(rel: str):
    root = os.path.realpath(cfg()['data_root'])
    p = os.path.realpath(os.path.join(root, rel))
    if not p.startswith(root + os.sep) or not os.path.isfile(p): raise HTTPException(404)
    return FileResponse(p)
