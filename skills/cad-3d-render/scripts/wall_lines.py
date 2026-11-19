"""Group wall lines from a dwg_extract.ps1 dump into wall faces, so wall positions,
thicknesses and gaps (open bays / openings) can be read off quickly.

usage: python wall_lines.py dump.txt [LAYER=A-WALL] [MINLEN=300]

Prints every vertical (x = const) and horizontal (y = const) line group with its spans.
Two faces 200-230 apart = one wall; a face that stops and restarts = an opening or open bay.
"""
import sys, collections

path = sys.argv[1]
layer = sys.argv[2] if len(sys.argv) > 2 else 'A-WALL'
minlen = float(sys.argv[3]) if len(sys.argv) > 3 else 300
V, H = collections.defaultdict(set), collections.defaultdict(set)
for line in open(path, encoding='utf-8-sig'):
    f = line.rstrip('\n').split('|')
    if f[0] != 'BL' or f[1] != layer:
        continue
    x1, y1, x2, y2 = map(lambda v: round(float(v)), f[2:6])
    if x1 == x2 and abs(y2 - y1) >= minlen:
        V[x1].add((min(y1, y2), max(y1, y2)))
    if y1 == y2 and abs(x2 - x1) >= minlen:
        H[y1].add((min(x1, x2), max(x1, x2)))
print('VERTICAL faces  x : spans in y')
for x in sorted(V):
    print(f'{x:>8} : {sorted(V[x])}')
print('\nHORIZONTAL faces  y : total length, spans in x')
for y in sorted(H):
    s = sorted(H[y]); print(f'{y:>8} : {sum(b - a for a, b in s):>7}  {s}')
