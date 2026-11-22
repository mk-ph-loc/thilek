"""Εκδόσεις Α/Β/Γ/Δ ενός διαγωνίσματος (ανακάτεμα με seed, χωρίς πίνακες) και πίνακας προδιαγραφών."""
import random, re
from html import escape as E

LETTERS = 'ΑΒΓΔΕΖΗΘ'; VERS = 'ΑΒΓΔ'; VLAT = {'A': 'Α', 'B': 'Β', 'C': 'Γ', 'D': 'Δ'}     # δέχεται και λατινικά A–D στη διεύθυνση


def clean_ver(v):
    v = VLAT.get((v or '').strip().upper(), (v or '').strip().upper())
    return v if v in VERS else ''


def clean_seed(s): return re.sub(r'[^0-9A-Za-zΑ-Ωα-ω_-]', '', (s or ''))[:20]


def variant(rows, eid, ver='', seed='', sg=False):
    """Επιστρέφει νέα λίστα γραμμών (dict) με grp/pos της έκδοσης και πεδίο `orig` (ετικέτα στην έκδοση Α, π.χ. 'Β2').
    Έκδοση Α (ή κενή) = η αρχική σειρά. Οι άλλες ανακατεύουν τα ερωτήματα μέσα σε κάθε Θέμα και, με sg, και τη σειρά των Θεμάτων.
    Ο ίδιος συνδυασμός (διαγώνισμα, έκδοση, seed) δίνει πάντα το ίδιο αποτέλεσμα· προσπαθεί να διαφέρει από την Α."""
    ver = clean_ver(ver) or 'Α'; seed = clean_seed(seed); rows = [dict(r) for r in rows]; groups = {}
    for r in rows: groups.setdefault(r['grp'], []).append(r)
    gs = sorted(groups)
    for g in gs:
        for k, r in enumerate(groups[g], 1): r['orig'] = f'{LETTERS[min(g, 8) - 1]}{k}'
    base = [(g, list(groups[g])) for g in gs]
    if ver == 'Α' or not rows: return _number(base, False)
    flat = lambda bs: [(r['item_id'], r['qcode']) for _, lst in bs for r in lst]; orig = flat(base); best = base
    for n in range(40):
        rng = random.Random(f'{eid}:{ver}:{seed}:{n}'); order = gs[:]
        if sg: rng.shuffle(order)
        bs = []
        for g in order:
            lst = list(groups[g]); rng.shuffle(lst); bs.append((g, lst))
        best = bs
        if flat(bs) != orig or len(orig) < 2: break
    return _number(best, sg)


def _number(bs, renum):
    out = []
    for i, (g, lst) in enumerate(bs, 1):
        ng = i if renum else g
        for k, r in enumerate(lst, 1): out.append(dict(r, grp=ng, pos=k))
    return out


def key_html(rows):
    """Αντιστοίχιση ετικετών της έκδοσης με την έκδοση Α (για τον καθηγητή)."""
    cells = ''.join(f"<tr><td>{LETTERS[min(r['grp'], 8) - 1]}{r['pos']}</td><td>{E(r['orig'])}</td><td>{E(r['item_id'])} ερ. {E(r['qcode'])}</td></tr>" for r in rows)
    return f"<table><tr><th>Σε αυτή την έκδοση</th><th>Στην έκδοση Α</th><th>Πηγή</th></tr>{cells}</table>"


def spec_data(rows, types):
    """{(ενότητα ΙΕΠ, τύπος): (πλήθος, μονάδες)} + ταξινομημένες ενότητες/τύποι που εμφανίζονται."""
    cells = {}; yl = set(); ts = set()
    for r in rows:
        y = (r['iep_yli'] or '').strip() or '—'; t = r['qtype'] or '—'; n, p = cells.get((y, t), (0, 0)); cells[(y, t)] = (n + 1, p + (r['points'] or 0)); yl.add(y); ts.add(t)
    return cells, sorted(yl, key=lambda s: [int(x) if x.isdigit() else x for x in re.findall(r'\d+|\D+', s)]), [t for t in list(types) + ['—'] if t in ts]


def spec_html(rows, types):
    if not rows: return '<p><i>Το διαγώνισμα είναι κενό.</i></p>'
    cells, yl, ts = spec_data(rows, types); tot = sum(p for _, p in cells.values()) or 0; lab = lambda t: types.get(t, 'Χωρίς τύπο')
    head = ''.join(f'<th>{E(lab(t))}</th>' for t in ts) + '<th>Σύνολο</th><th>%</th>'
    body = []
    for y in yl:
        n = p = 0; tds = []
        for t in ts:
            a, b = cells.get((y, t), (0, 0)); n += a; p += b; tds.append(f'<td>{a} ερ. · {b} μον.</td>' if a else '<td></td>')
        body.append(f"<tr><th>{E(y)}</th>{''.join(tds)}<td><b>{n} ερ. · {p} μον.</b></td><td>{round(100 * p / tot) if tot else 0}%</td></tr>")
    ft = []
    for t in ts:
        a = sum(cells.get((y, t), (0, 0))[0] for y in yl); b = sum(cells.get((y, t), (0, 0))[1] for y in yl); ft.append(f'<td><b>{a} ερ. · {b} μον.</b></td>')
    body.append(f"<tr><th>Σύνολο</th>{''.join(ft)}<td><b>{len(rows)} ερ. · {tot} μον.</b></td><td>100%</td></tr>")
    miss = sum(1 for r in rows if r['points'] is None)
    return (f"<table class=spec><tr><th>Ενότητα ΙΕΠ</th>{head}</tr>{''.join(body)}</table>"
            + (f"<p><small>{miss} ερώτημα/ερωτήματα χωρίς μονάδες δεν προσμετρούνται στις μονάδες.</small></p>" if miss else ''))
