"""tiny-chess-01 engine: alpha-beta with quiescence, MVV-LVA order, PST eval.

Board: 0x88 bytearray, 1..6 white P N B R Q K, 7..12 black. 0 is empty.
The search is fixed by a node cap, never a clock, so a replay matches.
"""
import json
import os
import sys
import urllib.request as U

E = os.environ.get("MAKEFUN_ENV_URL") or sys.exit("MAKEFUN_ENV_URL is not set")

PV = (0, 100, 320, 330, 500, 900, 0)
MATE = 29000
CAP = 26000

# Piece-square tables, written a8..h1 (row 0 is rank 8) as the classics are.
PS = {
    1: (0, 0, 0, 0, 0, 0, 0, 0, 50, 50, 50, 50, 50, 50, 50, 50, 10, 10, 20, 30,
        30, 20, 10, 10, 5, 5, 10, 25, 25, 10, 5, 5, 0, 0, 0, 20, 20, 0, 0, 0, 5,
        -5, -10, 0, 0, -10, -5, 5, 5, 10, 10, -20, -20, 10, 10, 5, 0, 0, 0, 0, 0,
        0, 0, 0),
    2: (-50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 0, 0, 0, -20, -40,
        -30, 0, 10, 15, 15, 10, 0, -30, -30, 5, 15, 20, 20, 15, 5, -30, -30, 0,
        15, 20, 20, 15, 0, -30, -30, 5, 10, 15, 15, 10, 5, -30, -40, -20, 0, 5, 5,
        0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50),
    3: (-20, -10, -10, -10, -10, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10, -10,
        0, 5, 10, 10, 5, 0, -10, -10, 5, 5, 10, 10, 5, 5, -10, -10, 0, 10, 10, 10,
        10, 0, -10, -10, 10, 10, 10, 10, 10, 10, -10, -10, 5, 0, 0, 0, 0, 5, -10,
        -20, -10, -10, -10, -10, -10, -10, -20),
    4: (0, 0, 0, 0, 0, 0, 0, 0, 5, 10, 10, 10, 10, 10, 10, 5, -5, 0, 0, 0, 0, 0,
        0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0,
        0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, 0, 0, 0, 5, 5, 0, 0, 0),
    5: (-20, -10, -10, -5, -5, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10, -10,
        0, 5, 5, 5, 5, 0, -10, -5, 0, 5, 5, 5, 5, 0, -5, 0, 0, 5, 5, 5, 5, 0, -5,
        -10, 5, 5, 5, 5, 5, 0, -10, -10, 0, 5, 0, 0, 0, 0, -10, -20, -10, -10, -5,
        -5, -10, -10, -20),
    6: (-30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40,
        -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50,
        -40, -40, -30, -20, -30, -30, -40, -40, -30, -30, -20, -10, -20, -20, -20,
        -20, -20, -20, -10, 20, 20, 0, 0, 0, 0, 20, 20, 20, 30, 10, 0, 0, 10, 30,
        20),
}

N_OFF = (33, 31, 18, 14, -14, -18, -31, -33)
K_OFF = (1, -1, 16, -16, 15, 17, -15, -17)
B_OFF = (15, 17, -15, -17)
R_OFF = (1, -1, 16, -16)
SL = {3: B_OFF, 4: R_OFF, 5: K_OFF}

NODES = [0]


class Cut(Exception):
    pass


def post(path, body):
    q = U.Request(E + path, data=json.dumps(body).encode(),
                  headers={"content-type": "application/json"})
    with U.urlopen(q) as f:
        return json.load(f)


def sqi(name):
    return (int(name[1]) - 1) * 16 + "abcdefgh".index(name[0])


def uci(s):
    return "abcdefgh"[s & 7] + str((s >> 4) + 1)


def load(fen):
    """A FEN's placement as a 0x88 bytearray, with its side, ep and rights."""
    f = fen.split()
    b = bytearray(128)
    r, c = 7, 0
    for ch in f[0]:
        if ch == "/":
            r -= 1
            c = 0
        elif ch.isdigit():
            c += int(ch)
        else:
            b[r * 16 + c] = " PNBRQK".index(ch.upper()) + (8 if ch.islower() else 0)
            c += 1
    ep = sqi(f[3]) if len(f) > 3 and f[3] != "-" else -1
    cr = 0
    if len(f) > 2:
        for i, ch in enumerate("KQkq"):
            if ch in f[2]:
                cr |= 1 << i
    return b, f[1] == "w", ep, cr


def gen(b, w, ep, cr):
    """Pseudo-legal moves for side w as (from, to, promotion piece or 0)."""
    lo, hi = (1, 7) if w else (9, 15)
    out = []
    ad = out.append
    for s in range(128):
        if s & 0x88:
            continue
        p = b[s]
        if not p or p < lo or p >= hi:
            continue
        t = p if p < 8 else p - 8
        if t == 1:
            d = s + (16 if w else -16)
            if d & 0x88:
                continue
            if not b[d]:
                prom(ad, s, d, w)
                back = 1 if w else 6
                if (s >> 4) == back and not b[d + (16 if w else -16)]:
                    ad((s, d + (16 if w else -16), 0))
            for c in (d - 1, d + 1):
                if c & 0x88:
                    continue
                q = b[c]
                if q and (q < 8) != w:
                    prom(ad, s, c, w)
                elif c == ep:
                    ad((s, c, 0))
        else:
            if t == 2:
                for o in N_OFF:
                    d = s + o
                    if not d & 0x88:
                        q = b[d]
                        if not q or (q < 8) != w:
                            ad((s, d, 0))
            elif t == 6:
                for o in K_OFF:
                    d = s + o
                    if not d & 0x88:
                        q = b[d]
                        if not q or (q < 8) != w:
                            ad((s, d, 0))
                cast(b, w, cr, ad)
            else:
                for o in SL[t]:
                    d = s + o
                    while not d & 0x88:
                        q = b[d]
                        if q:
                            if (q < 8) != w:
                                ad((s, d, 0))
                            break
                        ad((s, d, 0))
                        d += o
    return out


def prom(ad, s, d, w):
    """A pawn move, expanded to the four promotions when it lands on the last."""
    if (d >> 4) == (7 if w else 0):
        for k in (5, 4, 3, 2):
            ad((s, d, k if w else k + 8))
    else:
        ad((s, d, 0))


def cast(b, w, cr, ad):
    """Add the castling moves the rights and the empty, safe squares allow."""
    r = 0 if w else 7
    k = 6 if w else 14
    base = r * 16
    if b[base + 4] != k:
        return
    if w:
        if cr & 1 and not b[base + 5] and not b[base + 6] and b[base + 7] == 4:
            if not atk(b, base + 4, 0) and not atk(b, base + 5, 0):
                ad((base + 4, base + 6, 0))
        if cr & 2 and not b[base + 3] and not b[base + 2] and not b[base + 1]:
            if b[base] == 4 and not atk(b, base + 4, 0) and not atk(b, base + 3, 0):
                ad((base + 4, base + 2, 0))
    else:
        if cr & 4 and not b[base + 5] and not b[base + 6] and b[base + 7] == 12:
            if not atk(b, base + 4, 1) and not atk(b, base + 5, 1):
                ad((base + 4, base + 6, 0))
        if cr & 8 and not b[base + 3] and not b[base + 2] and not b[base + 1]:
            if b[base] == 12 and not atk(b, base + 4, 1) and not atk(b, base + 3, 1):
                ad((base + 4, base + 2, 0))


def atk(b, sq, byw):
    """Does side byw attack sq? Nothing here is a legality test on its own."""
    lo, hi = (1, 7) if byw else (9, 15)
    for o in N_OFF:
        d = sq + o
        if not d & 0x88:
            p = b[d]
            if p and p < hi and p >= lo and (p if p < 8 else p - 8) == 2:
                return True
    for o in K_OFF:
        d = sq + o
        if not d & 0x88:
            p = b[d]
            if p and p < hi and p >= lo and (p if p < 8 else p - 8) == 6:
                return True
    off = (-15, -17) if byw else (15, 17)
    for o in off:
        d = sq + o
        if not d & 0x88:
            p = b[d]
            if p and p < hi and p >= lo and (p if p < 8 else p - 8) == 1:
                return True
    for o in K_OFF:
        d = sq + o
        diag = not (o == 1 or o == -1 or o == 16 or o == -16)
        while not d & 0x88:
            p = b[d]
            if p:
                if lo <= p < hi:
                    t = p if p < 8 else p - 8
                    if t == 5 or (t == 3 and diag) or (t == 4 and not diag):
                        return True
                break
            d += o
    return False


def do(n, m, w, ep, cr):
    """Play m on n in place: return the new en-passant square and rights."""
    f, t, pr = m
    p = n[f]
    n[f] = 0
    n[t] = pr if pr else p
    return finish(n, m, w, ep, cr, p, p if p < 8 else p - 8)


def finish(n, m, w, ep, cr, p, t2):
    f, t, pr = m
    ne = -1
    if t2 == 1:
        if t != f and (t - f) % 16 and ep == t:
            n[t - 16 if w else t + 16] = 0
        if abs(t - f) == 32:
            ne = (f + t) // 2
    elif t2 == 6:
        if abs((t & 7) - (f & 7)) == 2:
            rk = (t & ~7) | (7 if t > f else 0)
            n[(t & ~7) | (5 if t > f else 3)] = n[rk]
            n[rk] = 0
        cr &= ~(3 if w else 12)
    if t == 0 or f == 0:
        cr &= ~1
    if t == 7 or f == 7:
        cr &= ~2
    if t == 112 or f == 112:
        cr &= ~4
    if t == 119 or f == 119:
        cr &= ~8
    return ne, cr


def ev(b):
    """Material and piece-square terms, from the side to move's view later."""
    s = 0
    for i in range(128):
        if i & 0x88:
            continue
        p = b[i]
        if not p:
            continue
        w = p < 8
        t = p if w else p - 8
        v = PV[t]
        idx = (7 - (i >> 4)) * 8 + (i & 7) if w else (i >> 4) * 8 + (i & 7)
        v += PS[t][idx]
        s += v if w else -v
    return s


def qs(b, w, ep, cr, a, be, d):
    NODES[0] += 1
    if NODES[0] > CAP:
        raise Cut
    chk = atk(b, b.index(6 if w else 14), not w)
    if not chk:
        st = ev(b) * (1 if w else -1)
        if st >= be:
            return be
        if st > a:
            a = st
        if d > 4:
            return a
    best = -32000
    mv = gen(b, w, ep, cr)
    mv.sort(key=lambda m: -ordr(b, m))
    for m in mv:
        if not chk and not b[m[1]] and not m[2] and m[1] != ep:
            continue
        n = b[:]
        ne, nc = do(n, m, w, ep, cr)
        if atk(n, n.index(6 if w else 14), not w):
            continue
        v = -qs(n, not w, ne, nc, -be, -a, d + 1)
        if v > best:
            best = v
        if best > a:
            a = best
        if a >= be:
            return be
    if chk and best == -32000:
        return -MATE
    return a if best == -32000 else best


def ordr(b, m):
    """MVV-LVA: the value of what a move takes, less a tenth of the taker's."""
    v = b[m[1]]
    s = PV[v if v < 8 else v - 8] * 10 if v else 0
    p = b[m[0]]
    return s - (PV[p if p < 8 else p - 8] // 10) + (m[2] and 900)


def ab(b, w, ep, cr, d, a, be):
    NODES[0] += 1
    if NODES[0] > CAP:
        raise Cut
    if d <= 0:
        return qs(b, w, ep, cr, a, be, 0)
    mv = gen(b, w, ep, cr)
    mv.sort(key=lambda m: -ordr(b, m))
    best = -32000
    n_legal = 0
    for m in mv:
        n = b[:]
        ne, nc = do(n, m, w, ep, cr)
        if atk(n, n.index(6 if w else 14), not w):
            continue
        n_legal += 1
        v = -ab(n, not w, ne, nc, d - 1, -be, -a)
        if v > best:
            best = v
        if best > a:
            a = best
        if a >= be:
            return a
    if not n_legal:
        return -MATE + (10 - d) if atk(b, b.index(6 if w else 14), not w) else 0
    return best


def pick(fen, legal, w):
    """The move to play: iterative deepening under the node cap."""
    b, _, ep, cr = load(fen)
    mv = []
    for m in legal:
        mv.append((sqi(m[:2]), sqi(m[2:4]),
                   (" PNBRQK".index(m[4].upper())) if len(m) == 5 else 0))
    best = mv[0]
    for d in range(1, 8):
        NODES[0] = 0
        bb, bv = None, -32000
        try:
            for m in mv:
                n = b[:]
                ne, nc = do(n, m, w, ep, cr)
                v = -ab(n, not w, ne, nc, d - 1, -30000, -bv)
                if bb is None or v > bv:
                    bv, bb = v, m
        except Cut:
            break
        if bb is not None:
            best = bb
            mv = [bb] + [m for m in mv if m != bb]
        if bv > MATE - 200 or NODES[0] > CAP:
            break
    return uci(best[0]) + uci(best[1]) + (chr(best[2] + 96) if best[2] else "")


while True:
    g = post("/game", {})
    if g["status"] == "done":
        break
    w = g["colour"] == "white"
    while g["status"] == "your_move":
        g = post("/move", {"game": g["game"], "move": pick(g["fen"], g["legal_moves"], w)})
    print("game %d: %s by %s" % (g["game"], g["outcome"], g["reason"]), file=sys.stderr)
print("done %sw %sd %sl" % (g.get("wins"), g.get("draws"), g.get("losses")), file=sys.stderr)
