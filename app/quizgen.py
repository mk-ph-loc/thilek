"""Μετατροπή ερωτημάτων ΙΕΠ σε στοιχεία quiz: Σωστό/Λάθος και πολλαπλής επιλογής με αυτόματη εύρεση σωστής απάντησης από το κείμενο της λύσης, αλλιώς ελεύθερη ερώτηση."""
import json, re

LET = ['α', 'β', 'γ', 'δ', 'ε', 'στ', 'ζ', 'η', 'θ']
MARK = re.compile(r'^[ \t]*(στ|α|β|γ|δ|ε|ζ|η|θ)[ \t]*[.)][ \t]+(?=\S)', re.M)
TAIL = re.compile(r'\(?\s*Μον(?:άδες|\.)\s*:?\s*\d+\s*\)?\s*$', re.I | re.S)
TF = re.compile(r'(?<![Α-Ωα-ωά-ώ])(στ|α|β|γ|δ|ε|ζ|η|θ)[ \t]*[–—−\-:.)=]+[ \t]*(Σωστ[όή]|Λάθος|Λανθασμένη|Σ|Λ)(?![Α-Ωα-ωά-ώ])')
MATH = re.compile('[\U0001D400-\U0001D7FF⃗→�]')       # μαθηματικοί χαρακτήρες Unicode / διανύσματα: συχνά χαλασμένοι στην εξαγωγή
CODE = re.compile(r'^\s*\d\.\d(?:\.\d+)?\.?\s*')

def clean(t):
    t = TAIL.sub('', (t or '').strip()); return ' '.join(t.split())

def split_parts(text):
    """[(γράμμα, κείμενο)] για διαδοχικά α. β. γ. …, και το εισαγωγικό κείμενο πριν το α."""
    seq, idx = [], 0
    for m in MARK.finditer(text or ''):
        if idx < len(LET) and m.group(1) == LET[idx]: seq.append(m); idx += 1
    if not seq: return (text or ''), []
    parts = [(m.group(1), (text[m.end(): seq[k + 1].start()] if k + 1 < len(seq) else text[m.end():])) for k, m in enumerate(seq)]
    return text[:seq[0].start()], parts

def tf_answers(sol):
    out = {}
    for m in TF.finditer(sol or ''):
        out.setdefault(m.group(1), 'Σωστό' if m.group(2).startswith('Σ') else 'Λάθος')
    return out

def mcq_answer(sol, n):
    body = CODE.sub('', sol or '', count=0)
    letters = {m.group(1) for m in re.finditer(r'(?<![Α-Ωα-ωά-ώ])(α|β|γ|δ|ε|στ|ζ)(?![Α-Ωα-ωά-ώ])', body) if m.group(1) in LET[:n]}
    return str(LET.index(next(iter(letters)))) if len(letters) == 1 else None

def flag(*texts): return 'review' if any(MATH.search(t or '') for t in texts) else 'ok'

def make_items(q):
    """q: dict με item_id, code, points, text, qtype, sol_text, has_geo. Επιστρέφει λίστα dict στοιχείων quiz."""
    base = {'src_item': q['item_id'], 'src_qcode': q['code']}; pts = float(q['points'] or 1); text = q['text'] or ''
    intro, parts = split_parts(text)
    if q['qtype'] == 'true_false' and len(parts) >= 2:
        ans = tf_answers(q.get('sol_text')); out = []
        for let, t in parts:
            st = clean(t); a = ans.get(let)
            out.append({**base, 'kind': 'tf', 'stem': st, 'options': '[]', 'answer': a or '', 'points': round(pts / len(parts), 2), 'src_part': let, 'use_image': 0,
                        'status': 'review' if (a is None or flag(st) == 'review') else 'ok'})
        return out
    if q['qtype'] == 'mcq' and 2 <= len(parts) <= 6:
        opts = [clean(t) for _, t in parts]; stem = clean(CODE.sub('', intro)); a = mcq_answer(q.get('sol_text'), len(opts))
        return [{**base, 'kind': 'mcq', 'stem': stem, 'options': json.dumps(opts, ensure_ascii=False), 'answer': a or '', 'points': pts, 'src_part': '', 'use_image': int(bool(q.get('has_geo')) and bool(q.get('has_image'))),
                 'status': 'review' if (a is None or flag(stem, *opts) == 'review') else 'ok'}]
    stem = clean(CODE.sub('', text)); ans = clean(CODE.sub('', q.get('sol_text') or ''))
    return [{**base, 'kind': 'free', 'stem': stem, 'options': '[]', 'answer': ans, 'points': pts, 'src_part': '', 'use_image': int(bool(q.get('has_geo'))),
             'status': 'review'}]      # οι ελεύθερες θέλουν πάντα έλεγχο (τύποι, σχήματα)
