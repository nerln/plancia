#!/usr/bin/env python3
"""Genera gli strati e il documento di Icon Composer dell'icona di Plancia.

L'icona e' un telegrafo d'ordini di macchina (ottone, vetro di strumento a settori,
leva con due impugnature) montato su tavole di legno di plancia con il calafataggio
nero tra l'una e l'altra. Gli strati sono PNG procedurali da 1024 px con alfa: si
rifanno da qui, non si ritoccano a mano.

    python3 mac/icona/genera_strati.py            riscrive mac/icona/Plancia.icon
    python3 mac/icona/genera_strati.py <cartella> lo scrive in un'altra cartella .icon

Serve Python 3 con numpy e Pillow (pip install numpy pillow). Il rumore e' a seme
fisso: rigenerando si ottengono gli stessi pixel.

Dopo aver cambiato qualcosa, si rifa' anche la PNG di ripiego (vedi ripiego.py):
il build la usa dove actool non compila il .icon.

Gli strati, dal basso: legno (opaco, in versione chiara e scura), ottone (la ghiera),
quadrante (il vetro dello strumento) e leva. Ottone, quadrante e leva chiedono il
vetro di sistema; il legno no. Il tema scuro usa due strati alternati con
hidden-specializations: image-name-specializations, in ictool, non viene letta.
"""
import json, math, os, shutil, sys
import numpy as np
from PIL import Image, ImageFilter

ICON = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "Plancia.icon")
OUT = os.path.join(ICON, "Assets")
shutil.rmtree(ICON, ignore_errors=True)
os.makedirs(OUT)
S = 2
W = 1024
N = W * S
CX = CY = W / 2
rng = np.random.default_rng(7)

# ---------- parametri di forma ----------
R_RING_OUT = 356.0
R_RING_IN = 282.0
R_FACE = 292.0
BAND_IN, BAND_OUT = 176.0, 278.0
LEVER_DEG = 55.0
K = 1.08   # scala globale del quadrante

def grid(n=N, s=S):
    a = (np.arange(n, dtype=np.float32) + 0.5) / s
    X, Y = np.meshgrid(a, a)
    return X, Y

X, Y = grid()
DX = (X - CX) / K
DY = (Y - CY) / K
R = np.sqrt(DX * DX + DY * DY)
# angolo in gradi, in senso orario dall'alto
TH = np.degrees(np.arctan2(DX, -DY))

def aa(edge_dist):
    """copertura da distanza con segno (positivo = dentro), in unita' 1024."""
    return np.clip(edge_dist * S + 0.5, 0.0, 1.0).astype(np.float32)

def down(arr):
    """media a blocchi S x S (arr: HxW o HxWxC)."""
    if arr.ndim == 2:
        return arr.reshape(W, S, W, S).mean(axis=(1, 3))
    return arr.reshape(W, S, W, S, arr.shape[2]).mean(axis=(1, 3))

def down_rgba(rgb, a):
    pm = rgb * a[..., None]
    pm = down(pm)
    aa_ = down(a)
    rgb_ = np.where(aa_[..., None] > 1e-4, pm / np.maximum(aa_[..., None], 1e-4), 0)
    return np.dstack([np.clip(rgb_, 0, 255), np.clip(aa_ * 255, 0, 255)]).astype(np.uint8)

def ramp(v, stops):
    """v in [0,1] -> colore con rampa a tappe [(pos,(r,g,b)),...]."""
    v = np.clip(v, 0, 1)
    pos = [p for p, _ in stops]
    out = np.zeros(v.shape + (3,), np.float32)
    for c in range(3):
        out[..., c] = np.interp(v, pos, [col[c] for _, col in stops])
    return out

BRASS = [(0.0, (40, 22, 6)), (0.22, (104, 62, 14)), (0.45, (182, 122, 34)),
         (0.7, (232, 178, 76)), (0.9, (255, 224, 140)), (1.0, (255, 248, 214))]

def smooth_noise(rows, cols, size=W):
    a = rng.random((rows, cols)).astype(np.float32)
    im = Image.fromarray((a * 255).astype(np.uint8)).resize((size, size), Image.BICUBIC)
    return np.asarray(im, np.float32) / 255.0

# ---------- LEVA (geometria condivisa) ----------
th = math.radians(LEVER_DEG)
ddx, ddy = math.sin(th), -math.cos(th)         # direzione della leva (schermo)
ppx, ppy = -ddy, ddx                           # perpendicolare
U = DX * ddx + DY * ddy
V = DX * ppx + DY * ppy

LIGHT = np.array([-0.5, -0.62, 0.62], np.float32)
LIGHT /= np.linalg.norm(LIGHT)

def shade_brass(nu, nv, nz, gain=1.0, spec_k=38):
    Nx = nu * ddx + nv * ppx
    Ny = nu * ddy + nv * ppy
    Nz = nz
    ndl = np.clip(Nx * LIGHT[0] + Ny * LIGHT[1] + Nz * LIGHT[2], 0, 1)
    # riflesso speculare
    Rx = 2 * ndl * Nx - LIGHT[0]
    Ry = 2 * ndl * Ny - LIGHT[1]
    Rz = 2 * ndl * Nz - LIGHT[2]
    spec = np.clip(Rz, 0, 1) ** spec_k
    # riflesso d'ambiente (banda scura ai bordi, chiara verso il centro)
    env = 0.12 * np.cos(nv * 4.0 + 0.6)
    v = 0.16 + 0.60 * ndl + 0.50 * spec + env
    edge = np.clip(1.0 - np.sqrt(np.clip(Nx * 0 + nu * nu + nv * nv, 0, 1)), 0, 1)
    v *= 0.55 + 0.45 * np.clip(edge * 3.0, 0, 1)
    return np.clip(v * gain, 0, 1)

def ellipsoid(uc, a, b):
    nu = (U - uc) / a
    nv = V / b
    q = nu * nu + nv * nv
    inside = 1.0 - np.sqrt(np.clip(q, 0, 4))
    # distanza approssimata al bordo in unita' 1024
    dist = inside * min(a, b)
    alpha = aa(dist)
    nz = np.sqrt(np.clip(1 - q, 0.0, 1.0))
    return alpha, np.clip(nu, -1, 1), np.clip(nv, -1, 1), nz

def build_lever():
    """restituisce (rgb, alpha) a risoluzione supersample."""
    rgb = np.zeros((N, N, 3), np.float32)
    A = np.zeros((N, N), np.float32)

    def over(a, col):
        nonlocal rgb, A
        rgb = rgb * (1 - a[..., None]) + col * a[..., None]
        A = A + a * (1 - A)

    # asta: cilindro conico, da u=-200 a u=310
    hw = 30.0 - 6.0 * np.clip((U + 200) / 510, 0, 1)
    nv = np.clip(V / hw, -1, 1)
    nz = np.sqrt(np.clip(1 - nv * nv, 0, 1))
    a_bar = aa(hw - np.abs(V)) * aa(np.minimum(U + 200, 310 - U))
    over(a_bar, ramp(shade_brass(0 * nv, nv, nz), BRASS))

    # impugnatura anteriore (oliva torniata) e collari
    for (uc, a_, b_, gain) in [(352, 88, 60, 1.0), (262, 13, 42, 0.95), (-214, 58, 44, 0.95), (-152, 12, 36, 0.9)]:
        al, nu, nv2, nz2 = ellipsoid(uc, a_, b_)
        over(al, ramp(shade_brass(nu, nv2, nz2, gain), BRASS))
    return rgb, A

lev_rgb, lev_a = build_lever()

# ombra della leva (sullo strato sotto): spostata e sfocata
def lever_shadow(dx=14, dy=26, blur=15, strength=0.55):
    im = Image.fromarray((lev_a * 255).astype(np.uint8))
    im = im.transform(im.size, Image.AFFINE, (1, 0, -dx * S, 0, 1, -dy * S), resample=Image.BILINEAR)
    im = im.filter(ImageFilter.GaussianBlur(blur * S))
    return down(np.asarray(im, np.float32) / 255.0) * strength

SH = lever_shadow()

def apply_shadow(rgb_1024, mask):
    return rgb_1024 * (1 - SH[..., None] * mask[..., None])

# ---------- LEGNO ----------
def build_wood(dark=False):
    x = (np.arange(W, dtype=np.float32) + 0.5)
    XX, YY = np.meshgrid(x, x)
    plank_h = 256
    idx = np.clip((YY // plank_h).astype(int), 0, 3)
    yl = YY - idx * plank_h
    # mogano verniciato, caldo e scuro; ogni tavola ha il suo tono
    tones = np.array([[122, 58, 30], [100, 46, 24], [130, 64, 33], [108, 51, 26]], np.float32)
    if dark:
        tones = tones * 0.60
    base = tones[idx]
    # venatura a tavola piana: archi larghi che deviano con un rumore lento,
    # piu' pori fini a trattini. Niente striature sottili da metallo spazzolato.
    arch = smooth_noise(5, 3)          # deviazione lenta (archi a "cattedrale")
    warp = smooth_noise(90, 4)         # ondulazione media, stirata in x
    fine = smooth_noise(420, 12)       # fibre
    pores = smooth_noise(1024, 90)     # trattini dei pori, corti
    seed_off = np.array([0.0, 41.0, 83.0, 127.0], np.float32)[idx]
    phase = (yl + seed_off) * 0.052 + 9.0 * arch + 2.6 * warp
    rings = 0.5 + 0.5 * np.sin(phase)
    rings = rings ** 2.2
    g = 1.0 + 0.30 * (rings - 0.5) + 0.10 * (fine - 0.5) + 0.10 * (pores - 0.5)
    slow = smooth_noise(4, 3)
    g *= 0.93 + 0.14 * slow
    # fibre nitide: linee sottili scure che seguono le tavole
    fibre = np.clip((smooth_noise(760, 9) - 0.60) * 5.0, 0, 1)
    g *= 1.0 - 0.13 * fibre
    col = base * g[..., None]

    # vernice: lucentezza diagonale in alto a sinistra, scurimento in basso a destra
    diag = (XX * 0.55 + YY * 0.83) / (W * 1.38)
    col *= (1.14 - 0.34 * diag)[..., None]
    band = np.exp(-(((XX + YY) - 640.0) / 210.0) ** 2)
    band2 = np.exp(-(((XX + YY) - 1380.0) / 90.0) ** 2)
    sheen = (0.10 * band + 0.05 * band2)
    if dark:
        sheen *= 0.6
    col = col + (255 - col) * sheen[..., None] * np.array([1.0, 0.92, 0.78])[None, None, :]

    # calafataggio: fuga di pece tra le tavole, di spessore che varia piano,
    # con il labbro chiaro della tavola sopra e l'ombra sotto (incavo vero)
    wob = (smooth_noise(2, 6)[0:1, :] - 0.5) * 2.4   # riga: varia lungo x
    seam = np.zeros((W, W), np.float32)
    lip = np.zeros((W, W), np.float32)
    shade = np.zeros((W, W), np.float32)
    for sy in (256, 512, 768):
        hw = 4.4 + wob
        d = YY - (sy + (wob * 0.6))
        ad = np.abs(d)
        seam = np.maximum(seam, np.clip((hw - ad) * 0.9 + 0.5, 0, 1))
        lip = np.maximum(lip, np.clip(1.0 - np.abs(d + hw + 2.2) / 2.2, 0, 1))
        shade = np.maximum(shade, np.clip(1.0 - np.maximum(d - hw, 0) / 9.0, 0, 1) * (d > 0))
    caulk = np.array([18, 11, 8], np.float32)
    col = col * (1 - shade[..., None] * 0.28)
    col = col + (255 - col) * (lip[..., None] * 0.13)
    col = col * (1 - seam[..., None]) + caulk * seam[..., None]

    # ombra del quadrante sul legno (incorporata)
    rr = np.sqrt((XX - CX) ** 2 + (YY - CY - 30) ** 2)
    m = np.clip((R_RING_OUT * K + 2 - rr) + 0.5, 0, 1)
    im = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(26))
    dsh = np.asarray(im, np.float32) / 255.0
    col = col * (1 - 0.72 * dsh[..., None])

    # vignetta leggera
    vr = np.sqrt((XX - CX) ** 2 + (YY - CY) ** 2) / (W * 0.72)
    col *= (1.0 - 0.16 * np.clip(vr, 0, 1) ** 2)[..., None]
    return np.clip(col, 0, 255)

# ---------- OTTONE (anello) ----------
def build_ring():
    t = np.clip((R - R_RING_IN) / (R_RING_OUT - R_RING_IN), 0, 1)
    # profilo torico della lunetta: normale radiale che gira lungo la sezione
    phi = (t - 0.5) * math.pi * 0.95            # da -85 a +85 gradi
    nr = np.sin(phi)                             # componente radiale
    nz = np.cos(phi)
    ux = DX / np.maximum(R, 1e-3)
    uy = DY / np.maximum(R, 1e-3)
    Nx, Ny = nr * ux, nr * uy
    ndl = np.clip(Nx * LIGHT[0] + Ny * LIGHT[1] + nz * LIGHT[2], 0, 1)
    Rz = 2 * ndl * nz - LIGHT[2]
    spec = np.clip(Rz, 0, 1) ** 26
    # riflesso d'ambiente tipo ottone lucido: due lobi angolari
    env = 0.5 + 0.5 * np.cos(np.radians(TH - 315) * 1.0)
    env2 = 0.5 + 0.5 * np.cos(np.radians(TH - 150) * 2.0)
    v = 0.10 + 0.55 * ndl + 0.45 * spec + 0.22 * env + 0.10 * env2
    v = np.clip(v, 0, 1)
    v = v * v * (3 - 2 * v) * 0.6 + v * 0.4
    # spazzolatura circolare
    br = smooth_noise(1024, 6, size=W)  # non si usa, ma consuma il seme: toglierla cambia il rumore dopo
    v = v * (1 + 0.03 * (np.repeat(np.repeat(rng.random((W, W)).astype(np.float32), S, 0), S, 1)[:N, :N] - 0.5))
    v *= 0.62 + 0.38 * np.clip(np.minimum(t, 1 - t) * 9.0, 0, 1)   # bordi netti scuri
    col = ramp(v, BRASS)
    # riflesso freddo del mare sul bordo esterno, in basso a destra
    fred = np.clip((t - 0.72) / 0.28, 0, 1) ** 1.5 * (0.5 + 0.5 * np.cos(np.radians(TH - 135)))
    col = col * (1 - 0.42 * fred[..., None]) + np.array([120, 172, 196], np.float32) * (0.42 * fred[..., None])
    outer = aa(R_RING_OUT - R)
    inner = aa(R - R_RING_IN)
    alpha = outer * inner
    # filetto scuro interno (dove la lunetta incontra il vetro)
    line = aa(1.8 - np.abs(R - (R_RING_IN + 3.0)))
    col = col * (1 - line[..., None] * 0.7) + np.array([22, 14, 6], np.float32) * line[..., None] * 0.7
    # filetto sottile inciso a meta' lunetta
    groove = aa(1.1 - np.abs(R - 336.0))
    col = col * (1 - groove[..., None] * 0.45)
    return col, alpha

# ---------- QUADRANTE ----------
SECTORS = [  # (th0, th1, colore): un solo gruppo forte, l'ambra, dove punta la leva
    (-24, 24, (192, 42, 36)),      # STOP
    (30, 80, (246, 178, 58)),      # avanti
    (86, 138, (226, 132, 44)),     # avanti tutta
    (-80, -30, (72, 112, 138)),    # indietro
    (-138, -86, (46, 76, 104)),    # indietro tutta
    (144, 216, (232, 226, 206)),   # fermo macchina
]

def build_face(dark=False):
    base_c = np.array([240, 230, 200], np.float32)
    edge_c = np.array([206, 190, 154], np.float32)
    if dark:
        base_c = np.array([196, 186, 160], np.float32)
        edge_c = np.array([150, 138, 110], np.float32)
    k = np.clip(R / R_FACE, 0, 1) ** 1.6
    col = base_c[None, None, :] * (1 - k[..., None]) + edge_c[None, None, :] * k[..., None]
    # ombra interna sotto la lunetta
    inner_sh = np.clip((R - (R_FACE - 42)) / 42, 0, 1) ** 1.5
    col *= (1 - 0.25 * inner_sh)[..., None]
    # settori colorati nella fascia
    band = aa(BAND_OUT - R) * aa(R - BAND_IN)
    for (a0, a1, c) in SECTORS:
        THs = np.where((a1 > 180) & (TH < 0), TH + 360, TH)
        m = aa(np.minimum(THs - a0, a1 - THs) * (math.pi / 180) * np.maximum(R, 1)) * band
        c = np.array(c, np.float32)
        if dark:
            c = c * 0.78
        # gradiente radiale leggero dentro il settore + smorzamento ai bordi
        rad = np.clip((R - BAND_IN) / (BAND_OUT - BAND_IN), 0, 1)
        cc = c[None, None, :] * (0.86 + 0.20 * rad[..., None])
        col = col * (1 - m[..., None]) + cc * m[..., None]
    rim = aa(R - BAND_OUT)
    col = col * (1 - rim[..., None]) + np.array([20, 16, 13], np.float32)[None, None, :] * rim[..., None]
    # disco interno scuro (vetro di strumento su fondo navy)
    inner = aa(BAND_IN - R)
    kk = np.clip(R / BAND_IN, 0, 1) ** 1.4
    c_in = np.array([40, 50, 70], np.float32)[None, None, :] * (1 - kk[..., None]) + np.array([16, 20, 30], np.float32)[None, None, :] * kk[..., None]
    if dark:
        c_in = c_in * 0.75
    col = col * (1 - inner[..., None]) + c_in * inner[..., None]
    # riflesso di vetro: fascia diagonale chiara in alto a sinistra, chiusa dal disco
    refl = np.exp(-(((DX * 0.7 + DY * 0.7) + 92.0) / 42.0) ** 2) * 0.10 + np.exp(-(((DX * 0.7 + DY * 0.7) + 40.0) / 16.0) ** 2) * 0.04
    col = col + (255 - col) * (refl * inner)[..., None]
    ink = np.array([28, 22, 18], np.float32)
    ivory = np.array([236, 224, 192], np.float32)

    def stroke(mask, s=1.0, c=None):
        nonlocal col
        c = ink if c is None else c
        col = col * (1 - mask[..., None] * s) + c * mask[..., None] * s

    # contorni fascia e separatori dei settori
    stroke(aa(3.2 - np.abs(R - BAND_IN)) * (1.0))
    stroke(aa(3.2 - np.abs(R - BAND_OUT)) * (1.0))
    stroke(aa(1.5 - np.abs(R - (BAND_IN - 5.0))) * 0.55, 1.0, ivory)
    for ang in (-144, -138, -86, -80, -30, -24, 24, 30, 80, 86, 138, 144):
        # linea radiale sottile ai bordi dei settori
        d = np.abs(TH - ang) * (math.pi / 180) * np.maximum(R, 1)
        m = aa(1.9 - d) * band
        stroke(m, 0.9)
    # tacche interne ogni 10 gradi (piu' lunghe ogni 30)
    for k_ in range(0, 360, 10):
        if 140 < k_ < 220:
            continue
        long_ = (k_ % 30 == 0)
        if not long_:
            continue
        r0, r1 = (156.0, 178.0) if long_ else (164.0, 178.0)
        d = np.abs(((TH - k_ + 180) % 360) - 180) * (math.pi / 180) * np.maximum(R, 1)
        m = aa((2.4 if long_ else 1.5) - d) * aa(np.minimum(R - r0, r1 - R))
        stroke(m, 0.9, ivory)
    stroke(aa(1.6 - np.abs(R - 146.0)) * 0.30, 1.0, ivory)
    alpha = aa(R_FACE - R)
    return col, alpha

def compose_lever_hub():
    # mozzo bombato al centro, sopra la leva
    rgb, A = lev_rgb.copy(), lev_a.copy()
    def over(a, col):
        nonlocal rgb, A
        rgb = rgb * (1 - a[..., None]) + col * a[..., None]
        A = A + a * (1 - A)
    ring_dark = aa(62.0 - R)
    over(ring_dark, np.array([24, 16, 8], np.float32)[None, None, :] * np.ones((N, N, 1), np.float32))
    r_h = 55.0
    nx = np.clip(DX / r_h, -1, 1)
    ny = np.clip(DY / r_h, -1, 1)
    q = nx * nx + ny * ny
    nz = np.sqrt(np.clip(1 - q, 0, 1))
    ndl = np.clip(nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2], 0, 1)
    spec = np.clip(2 * ndl * nz - LIGHT[2], 0, 1) ** 30
    v = 0.16 + 0.62 * ndl + 0.5 * spec
    v *= 0.65 + 0.35 * np.clip((1 - np.sqrt(q)) * 4, 0, 1)
    over(aa(r_h - R), ramp(v, BRASS))
    # perno centrale
    over(aa(12.0 - R), np.array([30, 20, 10], np.float32)[None, None, :] * np.ones((N, N, 1), np.float32))
    return rgb, A

hub_rgb, hub_a = compose_lever_hub()

def save(name, arr):
    Image.fromarray(arr, "RGBA").save(os.path.join(OUT, name))
    print("scritto", name)

# maschere in 1024 per l'ombra
X1 = (np.arange(W, dtype=np.float32) + 0.5)
XX1, YY1 = np.meshgrid(X1, X1)
R1 = np.sqrt((XX1 - CX) ** 2 + (YY1 - CY) ** 2)

# legno
for dark in (False, True):
    w = build_wood(dark)
    w = w * (1 - SH[..., None] * 0.9 * np.clip((R1 - (R_RING_OUT * K - 4)) / 6, 0, 1)[..., None])
    a = np.full((W, W), 255, np.uint8)
    arr = np.dstack([np.clip(w, 0, 255).astype(np.uint8), a])
    save("legno_dark.png" if dark else "legno.png", arr)

# quadrante (vetro dello strumento)
for dark in (False, True):
    col, alpha = build_face(dark)
    arr = down_rgba(col, alpha)
    rgb = arr[..., :3].astype(np.float32)
    rgb = apply_shadow(rgb, np.ones((W, W), np.float32))
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    save("quadrante_dark.png" if dark else "quadrante.png", arr)

# anello
col, alpha = build_ring()
arr = down_rgba(col, alpha)
rgb = apply_shadow(arr[..., :3].astype(np.float32), np.ones((W, W), np.float32))
arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
save("ottone.png", arr)

# leva + mozzo
save("leva.png", down_rgba(hub_rgb, hub_a))


# ---------- documento di Icon Composer ----------
pos = {"scale": 1.0, "translation-in-points": [0, 0]}
def layer(nm, img, glass=False, dark_img=None):
    def one(name, image, hidden):
        l = {"image-name": image + ".png", "name": name, "position": pos}
        if glass: l["glass"] = True
        l["hidden-specializations"] = hidden
        return l
    if not dark_img:
        l = {"image-name": img + ".png", "name": nm, "position": pos}
        if glass: l["glass"] = True
        return [l]
    return [one(nm + "_scuro", dark_img, [{"value": True}, {"appearance": "dark", "value": False}]),
            one(nm, img, [{"appearance": "dark", "value": True}])]
def gruppo(layers, ombra, op):
    return {"layers": layers, "lighting": "individual",
            "shadow": {"kind": ombra, "opacity": op},
            "translucency": {"enabled": False, "value": 0.0}}
icon = {
 "fill": {"solid": "srgb:0.20000,0.10000,0.05000,1.00000"},
 "groups": [
  gruppo(layer("leva", "leva", glass=True), "neutral", 0.6),
  gruppo(layer("quadrante", "quadrante", glass=True, dark_img="quadrante_dark"), "none", 0.0),
  gruppo(layer("ottone", "ottone", glass=True), "neutral", 0.5),
  gruppo(layer("legno", "legno", dark_img="legno_dark"), "none", 0.0),
 ],
 "supported-platforms": {"squares": "shared"}
}
with open(os.path.join(ICON, "icon.json"), "w") as f:
    json.dump(icon, f, indent=2)
print("scritto icon.json")
