"""Μικρός κωδικοποιητής QR (byte mode, διόρθωση σφαλμάτων M, εκδόσεις 1–10) → SVG. Χωρίς εξάρτηση."""
# (δεδομένα ανά μπλοκ, μπλοκ ομάδας 1, δεδομένα ομάδας 2, μπλοκ ομάδας 2, κωδικές λέξεις διόρθωσης ανά μπλοκ) για M
BLK = {1: (16, 1, 0, 0, 10), 2: (28, 1, 0, 0, 16), 3: (44, 1, 0, 0, 26), 4: (32, 2, 0, 0, 18), 5: (43, 2, 0, 0, 24), 6: (27, 4, 0, 0, 16), 7: (31, 4, 0, 0, 18),
       8: (38, 2, 39, 2, 22), 9: (36, 3, 37, 2, 22), 10: (43, 4, 44, 1, 26)}
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}
MAXLEN = 213
_EXP = [0] * 512; _LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x; _LOG[_x] = _i; _x <<= 1
    if _x & 256: _x ^= 0x11D
for _i in range(255, 512): _EXP[_i] = _EXP[_i - 255]


def _rs(data, n):
    gen = [1]
    for i in range(n):
        nx = [0] * (len(gen) + 1)
        for j, g in enumerate(gen):
            nx[j] ^= g
            if g: nx[j + 1] ^= _EXP[_LOG[g] + i]
        gen = nx
    res = [0] * n
    for b in data:
        f = b ^ res[0]; res = res[1:] + [0]
        if f:
            for j in range(n): res[j] ^= _EXP[_LOG[gen[j + 1]] + _LOG[f]]
    return res


def _cap(v): d1, n1, d2, n2, _ = BLK[v]; return d1 * n1 + d2 * n2


def _bits(data, v):
    cnt = 8 if v < 10 else 16; bs = '0100' + format(len(data), f'0{cnt}b') + ''.join(format(b, '08b') for b in data); total = _cap(v) * 8
    bs += '0' * min(4, total - len(bs)); bs += '0' * (-len(bs) % 8); out = [int(bs[i:i + 8], 2) for i in range(0, len(bs), 8)]; pad = (0xEC, 0x11); i = 0
    while len(out) < _cap(v): out.append(pad[i % 2]); i += 1
    return out


def _interleave(words, v):
    d1, n1, d2, n2, ec = BLK[v]; blocks = []; p = 0
    for size in [d1] * n1 + [d2] * n2: blocks.append(words[p:p + size]); p += size
    ecs = [_rs(b, ec) for b in blocks]; out = []
    for i in range(max(map(len, blocks))): out += [b[i] for b in blocks if i < len(b)]
    for i in range(ec): out += [e[i] for e in ecs]
    return out


def _bch(val, poly, nbits_poly, shift):
    v = val << shift
    while v.bit_length() >= nbits_poly: v ^= poly << (v.bit_length() - nbits_poly)
    return (val << shift) | v


MASKS = [lambda r, c: (r + c) % 2 == 0, lambda r, c: r % 2 == 0, lambda r, c: c % 3 == 0, lambda r, c: (r + c) % 3 == 0, lambda r, c: (r // 2 + c // 3) % 2 == 0,
         lambda r, c: (r * c) % 2 + (r * c) % 3 == 0, lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0, lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0]


def _matrix(codewords, v, mask):
    n = 17 + 4 * v; M = [[None] * n for _ in range(n)]
    def put(r, c, val):
        if 0 <= r < n and 0 <= c < n: M[r][c] = val
    for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
        for r in range(-1, 8):
            for c in range(-1, 8):
                inside = 0 <= r <= 6 and 0 <= c <= 6; put(r0 + r, c0 + c, inside and (r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4)))
    pos = ALIGN[v]
    for r in pos:
        for c in pos:
            if (r, c) in ((6, 6), (6, pos[-1]), (pos[-1], 6)) and len(pos) > 0 and (r, c) != (pos[-1], pos[-1]): continue
            for dr in range(-2, 3):
                for dc in range(-2, 3): M[r + dr][c + dc] = max(abs(dr), abs(dc)) != 1
    for i in range(8, n - 8): M[6][i] = M[i][6] = (i % 2 == 0)
    M[n - 8][8] = True
    res = set()                                                                 # δεσμευμένες θέσεις μορφής/έκδοσης
    for i in range(9): res.add((8, i)); res.add((i, 8))
    for i in range(8): res.add((8, n - 1 - i)); res.add((n - 1 - i, 8))
    if v >= 7:
        for i in range(6):
            for j in range(3): res.add((i, n - 11 + j)); res.add((n - 11 + j, i))
    bits = ''.join(format(w, '08b') for w in codewords); k = 0; up = True; c = n - 1
    while c > 0:
        if c == 6: c -= 1
        rng = range(n - 1, -1, -1) if up else range(n)
        for r in rng:
            for cc in (c, c - 1):
                if M[r][cc] is None and (r, cc) not in res:
                    bit = k < len(bits) and bits[k] == '1'; k += 1; M[r][cc] = bit != MASKS[mask](r, cc)
        up = not up; c -= 2
    fmt = _bch((0b00 << 3) | mask, 0b10100110111, 11, 10) ^ 0b101010000010010                  # M = 00
    fb = [(fmt >> i) & 1 == 1 for i in range(15)]
    for i in range(6): M[i][8] = fb[i]
    M[7][8] = fb[6]; M[8][8] = fb[7]; M[8][7] = fb[8]
    for i in range(9, 15): M[8][14 - i] = fb[i]
    for i in range(8): M[8][n - 1 - i] = fb[i]
    for i in range(8, 15): M[n - 15 + i][8] = fb[i]
    M[n - 8][8] = True
    if v >= 7:
        vi = _bch(v, 0b1111100100101, 13, 12)
        for i in range(18):
            b = (vi >> i) & 1 == 1; M[i // 3][n - 11 + i % 3] = b; M[n - 11 + i % 3][i // 3] = b
    return M


def _penalty(M):
    n = len(M); s = 0
    for g in (M, [list(x) for x in zip(*M)]):
        for row in g:
            run = 1
            for i in range(1, n):
                if row[i] == row[i - 1]: run += 1
                else:
                    if run >= 5: s += run - 2
                    run = 1
            if run >= 5: s += run - 2
            st = ''.join('1' if x else '0' for x in row)
            s += 40 * (st.count('10111010000') + st.count('00001011101'))
    for r in range(n - 1):
        for c in range(n - 1):
            if M[r][c] == M[r][c + 1] == M[r + 1][c] == M[r + 1][c + 1]: s += 3
    dark = sum(sum(1 for x in row if x) for row in M); s += 10 * (abs(dark * 100 // (n * n) - 50) // 5)
    return s


def encode(text):
    """Επιστρέφει πίνακα bool (True = σκούρο)· ValueError αν το κείμενο είναι πολύ μεγάλο."""
    data = text.encode('utf-8'); v = next((v for v in range(1, 11) if len(data) <= _cap(v) - (2 if v < 10 else 3)), None)
    if v is None: raise ValueError('Πολύ μεγάλο κείμενο για QR (έως ~210 byte).')
    cw = _interleave(_bits(data, v), v); best = None
    for m in range(8):
        M = _matrix(cw, v, m); p = _penalty(M)
        if best is None or p < best[0]: best = (p, M)
    return best[1]


def svg(text, scale=6, border=4, label=''):
    M = encode(text); n = len(M) + 2 * border; d = ''.join(f'M{c + border} {r + border}h1v1h-1z' for r, row in enumerate(M) for c, x in enumerate(row) if x)
    from html import escape
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {n} {n}' width='{n * scale}' height='{n * scale}' shape-rendering='crispEdges' role='img' aria-label='{escape(label or text, quote=True)}'>"
            f"<rect width='{n}' height='{n}' fill='#fff'/><path d='{d}' fill='#000'/></svg>")
