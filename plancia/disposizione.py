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


def calcola(nomi: list, archi: list, partenza: dict = None, giri: int = None) -> dict:
    """Le coordinate {nome: [x, y]} in un riquadro da 0.03 a 0.97.

    `nomi` e' la lista dei nodi, `archi` una lista di coppie (a, b) di nomi,
    `partenza` un {nome: [x, y]} facoltativo con le posizioni di una disposizione
    precedente (coordinate 0..1)."""
    n = len(nomi)
    if n == 0:
        return {}
    if n == 1:
        return {nomi[0]: [0.5, 0.5]}
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
    r2 = raggio * raggio
    kk = k * k
    gravita = GRAVITA * k
    passo = 0.02 if caldo else 0.1

    for giro in range(giri):
        fx = [0.0] * n
        fy = [0.0] * n
        # La griglia: una cella per quadratino di lato `raggio`.
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


def principale() -> int:
    """Legge {"nomi", "archi", "partenza"} dallo stdin, scrive {nome: [x, y]} sullo stdout."""
    try:
        import os
        if hasattr(os, "nice"):
            os.nice(10)      # cede il passo a chi serve le richieste
    except OSError:
        pass
    dati = json.load(sys.stdin)
    risultato = calcola(dati["nomi"], [tuple(a) for a in dati["archi"]], dati.get("partenza"))
    sys.stdout.write(json.dumps(risultato))
    return 0


if __name__ == "__main__":
    sys.exit(principale())
