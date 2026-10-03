"""La disposizione dei nodi della mappa della memoria: le coordinate, e basta.

Stdlib pura e nessun import di Plancia, di proposito: il server la lancia in un
processo a parte (`python -m plancia.disposizione`), e un processo che parte per
calcolare dei numeri non deve pagare l'import di mezza applicazione.

Il metodo e' sempre quello delle molle sugli archi e della repulsione fra i nodi
(Fruchterman e Reingold), ma la repulsione non si calcola piu' fra TUTTE le
coppie: quella vecchia costava il quadrato dei nodi (265 nodi un secondo di CPU
pulito, 1200 nodi venti volte tanto) e teneva il server in ostaggio. Adesso:

- la repulsione agisce solo entro un raggio (`RAGGIO_K` volte la distanza di
  riposo), con una griglia di celle di quel raggio: ogni nodo guarda le nove
  celle attorno a se', non gli altri mille. Il costo cresce come i nodi, non come
  il loro quadrato;
- a compensare cio' che il raggio non vede c'e' una gravita' leggera verso il
  centro, che tiene insieme i nodi senza legami e non li lascia scappare ai
  bordi del riquadro;
- le iterazioni sono limitate e calano con i nodi (oltre una certa taglia la
  forma grossa e' gia' data dalla partenza: una spirale che mette i piu'
  collegati al centro);
- si puo' partire dalle posizioni di una disposizione precedente: i nodi che
  c'erano restano dove stavano, quelli nuovi nascono accanto ai loro vicini, e
  bastano poche iterazioni per assestare. La mappa di domani assomiglia a quella
  di oggi invece di ridisporsi da capo a ogni scheda scritta.

- con i GRUPPI (`gruppi`: {nome: chiave}) la disposizione e' a isole. Prima si
  dispongono i gruppi come dischi (grandi quanto serve ai loro membri, distanziati,
  piu' vicini quelli che hanno piu' legami fra loro: i legami fra gruppi sono i
  ponti); poi i membri si mettono attorno al centro del loro gruppo (chi ha piu'
  legami piu' al centro) e si assestano con le molle: i legami dentro il gruppo
  tirano forte, quelli fra gruppi piano, e una cintura tiene ognuno nel suo disco.
  Il primo fotogramma e' gia' leggibile: i gruppi non si sovrappongono mai. Con i
  gruppi la disposizione parte sempre da zero (e' gia' strutturata, costa poche
  iterazioni), e se c'e' una `partenza` il risultato viene solo allineato ad essa
  (traslazione, rotazione e scala che avvicinano di piu' i nodi comuni): la mappa
  di domani non gira su se' stessa per una scheda in piu'.

Tutto e' deterministico: nessun caso, i numeri di partenza escono dal nome.
"""

import hashlib
import json
import math
import sys

# Distanza di riposo fra due nodi: 1/sqrt(n) nel quadrato unitario.
# La repulsione si sente entro RAGGIO_K distanze di riposo.
RAGGIO_K = 2.0
# Quanto pesa la gravita' verso il centro rispetto alla distanza di riposo.
GRAVITA = 0.35
# Iterazioni: tante quante ne bastano, non di piu'. Il prodotto giri*nodi resta
# nell'ordine di ~8e4, con un minimo perche' la forma si assesti sempre.
GIRI_MAX = 260
GIRI_MIN = 60
BUDGET = 80000
# Con una partenza che copre quasi tutti i nodi bastano meno giri e un passo piu' piccolo.
FRAZIONE_CALDA = 0.8
GIRI_CALDI = 40


def seme(nome: str) -> float:
    """Un numero fisso ricavato dal nome, fra 0 e 1."""
    h = hashlib.sha1(nome.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") / 0xFFFFFFFF


def giri_per(n: int, caldo: bool) -> int:
    if caldo:
        return GIRI_CALDI
    return max(GIRI_MIN, min(GIRI_MAX, BUDGET // max(n, 1)))


def _spirale(nomi: list, gradi: list) -> tuple:
    """Partenza su una spirale: i nodi non nascono mai sovrapposti, e chi ha piu'
    legami parte piu' al centro, dove poi resta."""
    n = len(nomi)
    ordine = sorted(range(n), key=lambda i: (-gradi[i], nomi[i]))
    px, py = [0.0] * n, [0.0] * n
    for posto, i in enumerate(ordine):
        ang = 2.399963 * posto + seme(nomi[i]) * 0.6
        raggio = 0.08 + 0.42 * math.sqrt((posto + 0.5) / n)
        px[i] = 0.5 + raggio * math.cos(ang)
        py[i] = 0.5 + raggio * math.sin(ang)
    return px, py


def _repulsione(px, py, fx, fy, raggio, kk):
    """La repulsione fra i nodi entro `raggio`, con una griglia di celle di quel
    lato: ogni nodo guarda le nove celle attorno a se'. Somma in fx, fy."""
    n = len(px)
    r2 = raggio * raggio
    celle = {}
    for i in range(n):
        chiave = (int(px[i] / raggio), int(py[i] / raggio))
        lista = celle.get(chiave)
        if lista is None:
            celle[chiave] = [i]
        else:
            lista.append(i)
    for (cx, cy), lista in celle.items():
        m = len(lista)
        # dentro la cella: ogni coppia una volta
        for a in range(m):
            i = lista[a]
            xi, yi = px[i], py[i]
            for b in range(a + 1, m):
                j = lista[b]
                dx, dy = xi - px[j], yi - py[j]
                d2 = dx * dx + dy * dy
                if d2 >= r2:
                    continue
                if d2 < 1e-9:
                    dx, dy, d2 = (i - j) * 1e-4, (j - i) * 1e-4, 2e-8
                forza = kk / d2
                fx[i] += dx * forza; fy[i] += dy * forza
                fx[j] -= dx * forza; fy[j] -= dy * forza
        # verso le quattro celle "in avanti": cosi' ogni coppia di celle vicine
        # si guarda una volta sola
        for ox, oy in ((1, 0), (1, 1), (0, 1), (-1, 1)):
            altra = celle.get((cx + ox, cy + oy))
            if not altra:
                continue
            for i in lista:
                xi, yi = px[i], py[i]
                for j in altra:
                    dx, dy = xi - px[j], yi - py[j]
                    d2 = dx * dx + dy * dy
                    if d2 >= r2:
                        continue
                    if d2 < 1e-9:
                        dx, dy, d2 = (i - j) * 1e-4, (j - i) * 1e-4, 2e-8
                    forza = kk / d2
                    fx[i] += dx * forza; fy[i] += dy * forza
                    fx[j] -= dx * forza; fy[j] -= dy * forza


def calcola(nomi: list, archi: list, partenza: dict = None, giri: int = None,
            gruppi: dict = None) -> dict:
    """Le coordinate {nome: [x, y]} in un riquadro da 0.03 a 0.97.

    `nomi` e' la lista dei nodi, `archi` una lista di coppie (a, b) di nomi,
    `partenza` un {nome: [x, y]} facoltativo con le posizioni di una disposizione
    precedente (coordinate 0..1), `gruppi` un {nome: chiave del gruppo} facoltativo:
    con almeno due gruppi diversi la disposizione e' a isole (vedi sopra)."""
    n = len(nomi)
    if n == 0:
        return {}
    if n == 1:
        return {nomi[0]: [0.5, 0.5]}
    if gruppi and len({gruppi.get(x, "") for x in nomi}) >= 2:
        return _calcola_gruppi(nomi, archi, partenza, giri, gruppi)
    indice = {nome: i for i, nome in enumerate(nomi)}
    legami = []
    visti = set()
    for a, b in archi:
        if a in indice and b in indice and a != b:
            i, j = indice[a], indice[b]
            coppia = (i, j) if i < j else (j, i)
            if coppia not in visti:
                visti.add(coppia)
                legami.append(coppia)
    gradi = [0] * n
    vicini = [[] for _ in range(n)]
    for i, j in legami:
        gradi[i] += 1
        gradi[j] += 1
        vicini[i].append(j)
        vicini[j].append(i)

    px, py = _spirale(nomi, gradi)
    noti = 0
    if partenza:
        posti = [False] * n
        for nome, xy in partenza.items():
            i = indice.get(nome)
            if i is None:
                continue
            try:
                x, y = float(xy[0]), float(xy[1])
            except (TypeError, ValueError, IndexError, KeyError):
                continue
            if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                px[i], py[i] = x, y
                posti[i] = True
                noti += 1
        # I nuovi nascono accanto ai vicini gia' piazzati (un poco discosti, dal
        # nome, per non sovrapporsi); quelli senza vicini piazzati restano dov'erano
        # sulla spirale.
        for i in range(n):
            if posti[i]:
                continue
            amici = [v for v in vicini[i] if posti[v]]
            if amici:
                cx = sum(px[v] for v in amici) / len(amici)
                cy = sum(py[v] for v in amici) / len(amici)
                ang = seme(nomi[i]) * 6.283185
                px[i] = min(0.98, max(0.02, cx + 0.03 * math.cos(ang)))
                py[i] = min(0.98, max(0.02, cy + 0.03 * math.sin(ang)))
    caldo = bool(partenza) and noti >= FRAZIONE_CALDA * n
    if giri is None:
        giri = giri_per(n, caldo)

    k = math.sqrt(1.0 / n)
    raggio = RAGGIO_K * k
    kk = k * k
    gravita = GRAVITA * k
    passo = 0.02 if caldo else 0.1

    for giro in range(giri):
        fx = [0.0] * n
        fy = [0.0] * n
        _repulsione(px, py, fx, fy, raggio, kk)
        for a, b in legami:
            dx, dy = px[a] - px[b], py[a] - py[b]
            d = math.hypot(dx, dy) or 1e-6
            forza = d / k
            fx[a] -= dx * forza; fy[a] -= dy * forza
            fx[b] += dx * forza; fy[b] += dy * forza
        # Il passo si raffredda: prima si sistema la forma grossa, poi si limano
        # le sovrapposizioni senza piu' stravolgere niente.
        limite = passo * (1.0 - giro / giri) + 0.002
        for i in range(n):
            gx = fx[i] + (0.5 - px[i]) * gravita
            gy = fy[i] + (0.5 - py[i]) * gravita
            d = math.hypot(gx, gy) or 1e-9
            s = min(d, limite) / d
            x = px[i] + gx * s
            y = py[i] + gy * s
            px[i] = 0.99 if x > 0.99 else (0.01 if x < 0.01 else x)
            py[i] = 0.99 if y > 0.99 else (0.01 if y < 0.01 else y)

    minx, maxx = min(px), max(px)
    miny, maxy = min(py), max(py)
    larghezza = (maxx - minx) or 1.0
    altezza = (maxy - miny) or 1.0
    return {nome: [round(0.03 + 0.94 * (px[i] - minx) / larghezza, 4),
                   round(0.03 + 0.94 * (py[i] - miny) / altezza, 4)]
            for i, nome in enumerate(nomi)}


# ---------------------------------------------------------------------------
# la disposizione a isole
# ---------------------------------------------------------------------------
#
# Si lavora in un piano astratto dove due nodi vicini stanno a distanza ~1; solo
# alla fine si scala nel riquadro 0..1. Un gruppo di s nodi e' un disco di raggio
# `_raggio_gruppo(s)`: i membri si dispongono a girasole (angolo aureo), che riempie
# un disco con distanza quasi uguale fra tutti.

_PASSO_GIRASOLE = 0.7
_VUOTO_FRA_GRUPPI = 4.0
GIRI_ISOLE = 44                      # iterazioni dei membri, con un tetto sul prodotto
BUDGET_ISOLE = 30000


def _raggio_gruppo(taglia: int) -> float:
    return _PASSO_GIRASOLE * math.sqrt(taglia) + 0.7


def _centri_gruppi(chiavi: list, taglie: dict, ponti: dict, prec: list = None) -> dict:
    """{chiave: (x, y)}: i gruppi come dischi che non si toccano, piu' vicini
    quanto piu' ponti hanno fra loro. Pochi corpi (decine): il quadrato costa niente.

    `prec` (facoltativo): per ogni gruppo il centro che aveva nella disposizione
    precedente, in coordinate 0..1, o None se non c'era. Se i gruppi che c'erano
    sono la maggior parte si parte da li' (e si assesta con poche iterazioni dolci):
    i gruppi non si scambiano di posto perche' in uno e' arrivata una scheda."""
    g = len(chiavi)
    raggi = [_raggio_gruppo(taglie[c]) for c in chiavi]
    vuoto = max(_VUOTO_FRA_GRUPPI, 0.45 * sum(raggi) / g)
    legati = {}
    for (a, b), n in ponti.items():
        legati[(a, b) if a < b else (b, a)] = n
    px, py = [0.0] * g, [0.0] * g
    giri = max(60, min(260, 160000 // (g * g)))
    tetto0 = 0.6
    noti = [i for i in range(g) if prec and prec[i] is not None]
    if prec and len(noti) >= max(2, (g + 1) // 2):
        # la scala: le distanze che i dischi vogliono, su quelle che avevano
        voluto = [raggi[i] + raggi[j] + vuoto for i in noti for j in noti if i < j]
        avute = [math.hypot(prec[i][0] - prec[j][0], prec[i][1] - prec[j][1])
                 for i in noti for j in noti if i < j]
        scala = (sum(voluto) / len(voluto)) / (sum(avute) / len(avute)) if sum(avute) > 1e-9 else 1.0
        for i in noti:
            px[i], py[i] = (prec[i][0] - 0.5) * scala, (prec[i][1] - 0.5) * scala
        fuori = max([math.hypot(px[i], py[i]) + raggi[i] for i in noti] or [0.0])
        for i in range(g):
            if i in noti:
                continue
            # un gruppo nuovo nasce accanto al gruppo noto con cui ha piu' ponti,
            # altrimenti fuori da tutti, da un lato scelto dal nome
            amici = sorted(((legati.get((min(i, j), max(i, j)), 0), j) for j in noti), reverse=True)
            ang = seme(chiavi[i]) * 6.283185
            if amici and amici[0][0] > 0:
                j = amici[0][1]
                dist = raggi[i] + raggi[j] + vuoto
                px[i], py[i] = px[j] + dist * math.cos(ang), py[j] + dist * math.sin(ang)
            else:
                dist = fuori + raggi[i] + vuoto
                px[i], py[i] = dist * math.cos(ang), dist * math.sin(ang)
        giri = max(30, giri // 4)
        tetto0 = 0.12
    else:
        # partenza: i piu' grandi al centro su una spirale, ognuno fuori da chi c'e' gia'
        area = 0.0
        for i in range(g):
            ang = 2.399963 * i + seme(chiavi[i]) * 0.5
            dist = 0.0 if i == 0 else 1.25 * math.sqrt(area / math.pi) + raggi[i]
            px[i], py[i] = dist * math.cos(ang), dist * math.sin(ang)
            area += math.pi * (raggi[i] + vuoto * 0.5) ** 2
    for giro in range(giri):
        tetto = tetto0 * (1.0 - giro / giri) + 0.03
        mx, my = [0.0] * g, [0.0] * g
        for i in range(g):
            for j in range(i + 1, g):
                dx, dy = px[i] - px[j], py[i] - py[j]
                d = math.hypot(dx, dy)
                if d < 1e-6:
                    dx, dy, d = (i - j) * 1e-3, (j - i) * 1e-3, 1e-3 * abs(i - j) * 1.414
                ux, uy = dx / d, dy / d
                voglio = raggi[i] + raggi[j] + vuoto
                n = legati.get((i, j), 0)
                if d < voglio:
                    spinta = (voglio - d) * 0.5
                elif n:
                    spinta = -(d - voglio) * 0.25 * min(3.0, math.log2(1 + n))
                else:
                    spinta = max(0.0, (3.0 * voglio - d)) * 0.03
                mx[i] += ux * spinta; my[i] += uy * spinta
                mx[j] -= ux * spinta; my[j] -= uy * spinta
        for i in range(g):
            mx[i] -= px[i] * 0.012
            my[i] -= py[i] * 0.012
            d = math.hypot(mx[i], my[i]) or 1e-9
            f = min(d, tetto) / d
            px[i] += mx[i] * f
            py[i] += my[i] * f
    _libera_dischi(px, py, [r + vuoto * 0.5 for r in raggi], 80)
    return {chiavi[i]: (px[i], py[i]) for i in range(g)}


def _libera_dischi(px: list, py: list, raggi: list, passate: int) -> bool:
    """Allontana i dischi che si toccano (spostamento rigido, meta' a testa).
    Torna True se alla fine nessuno si tocca."""
    g = len(px)
    for _ in range(passate):
        toccati = False
        for i in range(g):
            for j in range(i + 1, g):
                dx, dy = px[i] - px[j], py[i] - py[j]
                d = math.hypot(dx, dy)
                voglio = raggi[i] + raggi[j]
                if d >= voglio:
                    continue
                toccati = True
                if d < 1e-6:
                    dx, dy, d = 1.0, 0.0, 1.0
                m = (voglio - d) * 0.5 + 1e-3
                px[i] += dx / d * m; py[i] += dy / d * m
                px[j] -= dx / d * m; py[j] -= dy / d * m
        if not toccati:
            return True
    return False


def _allinea(pos: dict, partenza: dict) -> dict:
    """Ruota, trasla e scala `pos` (coordinate 0..1) perche' i nodi in comune con
    `partenza` finiscano il piu' vicino possibile a dove stavano (Procrustes sulla
    similarita', in forma chiusa coi numeri complessi, rifatto sui soli nodi che si
    sono mossi meno: pochi nodi che hanno cambiato posto non devono trascinare via
    tutti gli altri). Serve a una cosa: la mappa di domani non deve girare su se'
    stessa perche' c'e' una scheda in piu'. Se non migliora la mediana
    dello spostamento, o i nodi in comune sono meno di tre, non si muove niente."""
    comuni = []
    for nome, xy in pos.items():
        vecchio = partenza.get(nome)
        try:
            vx, vy = float(vecchio[0]), float(vecchio[1])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if 0.0 <= vx <= 1.0 and 0.0 <= vy <= 1.0:
            comuni.append((complex(xy[0], xy[1]), complex(vx, vy)))
    if len(comuni) < 3:
        return pos
    mediana = lambda l: sorted(l)[len(l) // 2]  # noqa: E731
    base = mediana([abs(a - b) for a, b in comuni])
    usati = comuni
    migliore = None
    for _ in range(4):
        ca = sum(a for a, _ in usati) / len(usati)
        cb = sum(b for _, b in usati) / len(usati)
        num = sum((b - cb) * (a - ca).conjugate() for a, b in usati)
        den = sum(abs(a - ca) ** 2 for a, _ in usati)
        if den < 1e-12 or abs(num) < 1e-12:
            break
        m = num / den                       # rotazione e scala insieme
        res = sorted(((abs(cb + m * (a - ca) - b), (a, b)) for a, b in comuni), key=lambda t: t[0])
        punteggio = mediana([r for r, _ in res])
        if migliore is None or punteggio < migliore[0]:
            migliore = (punteggio, ca, cb, m)
        usati = [c for _, c in res[:max(3, int(len(res) * 0.6))]]
    if migliore is None or migliore[0] >= base:
        return pos
    _, ca, cb, m = migliore
    return {nome: _complex_a_coppia(cb + m * (complex(xy[0], xy[1]) - ca))
            for nome, xy in pos.items()}


def _complex_a_coppia(z):
    return [z.real, z.imag]


def _nel_riquadro(px: list, py: list) -> tuple:
    """Scala uniforme (le isole restano tonde) e centra nel riquadro 0.03..0.97."""
    minx, maxx = min(px), max(px)
    miny, maxy = min(py), max(py)
    lato = max(maxx - minx, maxy - miny) or 1.0
    f = 0.94 / lato
    ox = 0.5 - (minx + maxx) / 2 * f
    oy = 0.5 - (miny + maxy) / 2 * f
    return ([round(x * f + ox, 4) for x in px], [round(y * f + oy, 4) for y in py])


def _centri_precedenti(elenco, chiave_di, nomi, partenza):
    per = [([], []) for _ in elenco]
    posto = {c: i for i, c in enumerate(elenco)}
    for i, nome in enumerate(nomi):
        xy = partenza.get(nome)
        try:
            x, y = float(xy[0]), float(xy[1])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
            per[posto[chiave_di[i]]][0].append(x)
            per[posto[chiave_di[i]]][1].append(y)
    mediana = lambda l: sorted(l)[len(l) // 2]  # noqa: E731
    return [(mediana(xs), mediana(ys)) if xs else None for xs, ys in per]


def _calcola_gruppi(nomi: list, archi: list, partenza: dict, giri: int, gruppi: dict) -> dict:
    n = len(nomi)
    indice = {nome: i for i, nome in enumerate(nomi)}
    chiave_di = [str(gruppi.get(nome, "")) for nome in nomi]
    elenco = sorted(set(chiave_di))
    taglie = {c: 0 for c in elenco}
    for c in chiave_di:
        taglie[c] += 1
    # i gruppi grandi per primi: stesso ordine a ogni calcolo
    elenco.sort(key=lambda c: (-taglie[c], c))
    pos_g = {c: i for i, c in enumerate(elenco)}
    gi = [pos_g[c] for c in chiave_di]

    legami, visti = [], set()
    for a, b in archi:
        if a in indice and b in indice and a != b:
            i, j = indice[a], indice[b]
            coppia = (i, j) if i < j else (j, i)
            if coppia not in visti:
                visti.add(coppia)
                legami.append(coppia)
    gradi = [0] * n
    dentro = [0] * n
    ponti = {}
    for i, j in legami:
        gradi[i] += 1
        gradi[j] += 1
        if gi[i] == gi[j]:
            dentro[i] += 1
            dentro[j] += 1
        else:
            chiave = (gi[i], gi[j]) if gi[i] < gi[j] else (gi[j], gi[i])
            ponti[chiave] = ponti.get(chiave, 0) + 1

    # Il centro che ogni gruppo aveva prima (la mediana dei suoi membri gia' noti):
    # `ponti` e' indicizzato per posizione nell'elenco dei gruppi, come `_centri_gruppi`
    # si aspetta.
    prec = _centri_precedenti(elenco, chiave_di, nomi, partenza) if partenza else None
    centri = _centri_gruppi(elenco, taglie, ponti, prec)
    cx_g = [centri[c][0] for c in elenco]
    cy_g = [centri[c][1] for c in elenco]
    raggi = [_raggio_gruppo(taglie[c]) for c in elenco]

    # i membri a girasole attorno al centro, chi ha piu' legami dentro piu' al centro
    px, py = [0.0] * n, [0.0] * n
    membri = [[] for _ in elenco]
    for i in range(n):
        membri[gi[i]].append(i)
    for g, lista in enumerate(membri):
        lista.sort(key=lambda i: (-dentro[i], -gradi[i], nomi[i]))
        for posto, i in enumerate(lista):
            ang = 2.399963 * posto + seme(nomi[i]) * 0.3
            r = _PASSO_GIRASOLE * math.sqrt(posto + 0.5)
            px[i] = cx_g[g] + r * math.cos(ang)
            py[i] = cy_g[g] + r * math.sin(ang)

    if giri is None:
        giri = max(12, min(GIRI_ISOLE, BUDGET_ISOLE // n))
    raggio_rep = 2.0
    for giro in range(giri):
        fx = [0.0] * n
        fy = [0.0] * n
        _repulsione(px, py, fx, fy, raggio_rep, 1.0)
        for a, b in legami:
            dx, dy = px[a] - px[b], py[a] - py[b]
            d = math.hypot(dx, dy) or 1e-6
            peso = 1.0 if gi[a] == gi[b] else 0.05
            forza = d * peso
            fx[a] -= dx * forza; fy[a] -= dy * forza
            fx[b] += dx * forza; fy[b] += dy * forza
        # la cintura: ognuno resta dentro il disco del suo gruppo
        mx = [0.0] * len(elenco)
        my = [0.0] * len(elenco)
        for i in range(n):
            mx[gi[i]] += px[i]
            my[gi[i]] += py[i]
        for g in range(len(elenco)):
            mx[g] /= taglie[elenco[g]]
            my[g] /= taglie[elenco[g]]
        limite = 0.3 * (1.0 - giro / giri) + 0.02
        for i in range(n):
            g = gi[i]
            dx, dy = px[i] - mx[g], py[i] - my[g]
            d = math.hypot(dx, dy)
            fuori = d - 0.62 * raggi[g]
            if fuori > 0 and d > 1e-9:
                fx[i] -= dx / d * fuori * 2.0
                fy[i] -= dy / d * fuori * 2.0
            gx, gy = fx[i], fy[i]
            m = math.hypot(gx, gy) or 1e-9
            f = min(m, limite) / m
            px[i] += gx * f
            py[i] += gy * f
        # le isole non si toccano mai: se i membri hanno spinto, si riallargano
        # i dischi (spostamento rigido dei membri)
        if giro % 4 == 3 or giro == giri - 1:
            _separa_isole(px, py, gi, membri, raggi)
    _separa_isole(px, py, gi, membri, raggi, passate=40)

    px, py = _nel_riquadro(px, py)
    risultato = {nome: [px[i], py[i]] for i, nome in enumerate(nomi)}
    if partenza:
        risultato = _allinea(risultato, partenza)
        xs = [v[0] for v in risultato.values()]
        ys = [v[1] for v in risultato.values()]
        if min(xs) < 0.0 or max(xs) > 1.0 or min(ys) < 0.0 or max(ys) > 1.0:
            qx, qy = _nel_riquadro(xs, ys)
            risultato = {nome: [qx[i], qy[i]] for i, nome in enumerate(nomi)}
        else:
            risultato = {nome: [round(v[0], 4), round(v[1], 4)] for nome, v in risultato.items()}
    return risultato


def _separa_isole(px, py, gi, membri, raggi, passate=6):
    """Dischi di raggio effettivo (il piu' grande fra il nominale*0.85 e la distanza
    del membro piu' lontano dal centro) che non si toccano: spostamento rigido."""
    g = len(membri)
    cx = [0.0] * g
    cy = [0.0] * g
    for gr, lista in enumerate(membri):
        if lista:
            cx[gr] = sum(px[i] for i in lista) / len(lista)
            cy[gr] = sum(py[i] for i in lista) / len(lista)
    eff = []
    for gr, lista in enumerate(membri):
        lontano = max((math.hypot(px[i] - cx[gr], py[i] - cy[gr]) for i in lista), default=0.0)
        eff.append(max(0.85 * raggi[gr], lontano) + 0.9)
    ox = list(cx)
    oy = list(cy)
    _libera_dischi(cx, cy, eff, passate)
    for gr, lista in enumerate(membri):
        dx, dy = cx[gr] - ox[gr], cy[gr] - oy[gr]
        if dx or dy:
            for i in lista:
                px[i] += dx
                py[i] += dy


def principale() -> int:
    """Legge {"nomi", "archi", "partenza", "gruppi"} dallo stdin, scrive {nome: [x, y]} sullo stdout."""
    try:
        import os
        if hasattr(os, "nice"):
            os.nice(10)      # cede il passo a chi serve le richieste
    except OSError:
        pass
    dati = json.load(sys.stdin)
    risultato = calcola(dati["nomi"], [tuple(a) for a in dati["archi"]], dati.get("partenza"),
                        gruppi=dati.get("gruppi"))
    sys.stdout.write(json.dumps(risultato))
    return 0


if __name__ == "__main__":
    sys.exit(principale())
