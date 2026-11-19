"""Georeferenced ground texture for the whole site from the road & pavement layout PDF (C-0100).
Classes: 0 paving (concrete), 1 grass, 2 existing asphalt road (solid grey), 3 new concrete road (yellow).
usage: python ground_texture.py <pdf> <affine.json> <out_dir>
"""
import sys, json, numpy as np, fitz
from PIL import Image, ImageFilter

pdf, aff, out = sys.argv[1], sys.argv[2], sys.argv[3]
X = np.array(json.load(open(aff)))                 # [ptx, pty, 1] @ X -> site metres
DPI = 200
pg = fitz.open(pdf)[0]
pix = pg.get_pixmap(dpi=DPI)                       # rotated page as displayed
src = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[..., :3].astype(np.int16)
print('pdf raster', src.shape)

# site window (metres) and output resolution
x0, x1, y0, y1 = -640.0, 320.0, -340.0, 390.0
RES = 0.25
W, H = int((x1 - x0) / RES), int((y1 - y0) / RES)
# inverse affine: site -> page pt -> pdf px
A = X[:2, :]; t = X[2, :]; Ainv = np.linalg.inv(A)
gx, gy = np.meshgrid(x0 + (np.arange(W) + .5) * RES, y1 - (np.arange(H) + .5) * RES)
site = np.stack([gx.ravel() - t[0], gy.ravel() - t[1]], 1)
pt = site @ Ainv
px = np.clip((pt[:, 0] * DPI / 72).round().astype(int), 0, pix.w - 1)
py = np.clip((pt[:, 1] * DPI / 72).round().astype(int), 0, pix.h - 1)
inpage = ((pt[:, 0] >= 0) & (pt[:, 0] < pg.rect.width) & (pt[:, 1] >= 0) & (pt[:, 1] < pg.rect.height)).reshape(H, W)
# classify on the FULL-RES pdf raster (thin grass tick marks vanish if sampled first), then sample
R, G, B = src[..., 0], src[..., 1], src[..., 2]
greyF = (abs(R - G) < 12) & (abs(G - B) < 12) & (R > 165) & (R < 222)
yellowF = (R > 210) & (G > 210) & (B < 170)
strokeF = ((R + G + B) < 700) & ~greyF & ~yellowF          # any linework / tick mark
def blurF(m, rad):
    im = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(rad))
    return np.asarray(im).astype(np.float32) / 255
m_per_px = 72 / DPI * abs(X[0, 0])                          # ~0.16 m per raster px
greyB = blurF(greyF, max(1, int(1.0 / m_per_px)))
yellB = blurF(yellowF, max(1, int(1.0 / m_per_px)))
strokeB = blurF(strokeF, int(2.5 / m_per_px))               # 5 m window
grey = greyB[py, px].reshape(H, W); yell = yellB[py, px].reshape(H, W); strk = strokeB[py, px].reshape(H, W)
cls = np.ones((H, W), np.uint8)                  # grass by default (dotted areas)
cls[strk < 0.0008] = 0                           # blank 5 m window -> paving
cls[grey > .55] = 2                              # asphalt
cls[yell > .5] = 3                               # new concrete road
cls[~inpage] = 1
# majority clean-up
cl = Image.fromarray(cls * 60).filter(ImageFilter.ModeFilter(9))
cls = (np.asarray(cl) // 60).astype(np.uint8)
np.save(out + '/ground_cls.npy', cls)
print('class shares %:', [round(float((cls == k).mean() * 100), 1) for k in range(4)])

# textured colour image
rng = np.random.default_rng(3)
n1 = rng.normal(0, 1, (H, W)).astype(np.float32)
n2 = np.asarray(Image.fromarray(((n1 * 30) + 128).clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))).astype(np.float32) - 128
pal = {0: (196, 192, 184), 1: (98, 132, 66), 2: (78, 80, 84), 3: (212, 208, 198)}
out_img = np.zeros((H, W, 3), np.float32)
for k, c in pal.items():
    m = cls == k
    out_img[m] = c
grain = n1 * 6 + n2 * 0.9
out_img += grain[..., None] * np.where(cls == 1, 1.6, 1.0)[..., None]
grass = cls == 1
out_img[grass, 1] += n2[grass] * 1.2                       # greener patches
# darker kerb edge between road and the rest
edge = np.asarray(Image.fromarray((cls == 2).astype(np.uint8) * 255).filter(ImageFilter.FIND_EDGES)) > 0
out_img[edge] = (150, 150, 146)
Image.fromarray(out_img.clip(0, 255).astype(np.uint8)).save(out + '/site_ground.jpg', quality=88)
Image.fromarray(out_img.clip(0, 255).astype(np.uint8)).resize((W // 4, H // 4)).save(out + '/site_ground_preview.jpg', quality=85)
json.dump({'x0': x0, 'x1': x1, 'y0': y0, 'y1': y1, 'res': RES, 'w': W, 'h': H}, open(out + '/site_ground.json', 'w'))
print('ground texture', W, 'x', H)
