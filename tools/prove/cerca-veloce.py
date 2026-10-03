"""Prove per MAC2-CERCA: la ricerca nei turni resta veloce su un archivio grande.

Sull'archivio vero di chi la usa `/api/search` impiegava da uno a trenta secondi per
parola (misurato il 29/09/2026: "plan" 6,9 s, "task aperti" oltre 30 s), mentre
sull'archivio dimostrativo, che ha una manciata di righe, 3-20 ms. La differenza e'
la scala, e con i compartimenti attivi contava il numero di sessioni: la giuntura
sulle viste temporanee (`sessions`, `projects` filtrate con `IN (SELECT ...)`) faceva
ripetere il controllo per ogni riga trovata, quindi righe x sessioni. Piu' a cache
fredda ogni riga trovata si leggeva dal disco per sapere di chi fosse.

Qui si costruisce un archivio abbastanza grande da far vedere il difetto (700 sessioni,
circa 31 mila turni scritti da `turni.indicizza` su transcript veri, in un
`PLANCIA_HOME` isolato in un sottoprocesso, mai `~/.plancia`), con un compartimento
`alfa` e il predefinito, e si controlla:

- il tempo: nessuna parola sopra il secondo, nemmeno quella che compare in ogni turno;
- la mappa da riga a file (`turni_mappa`) e' completa dopo l'indicizzazione e la ricerca
  la usa;
- i risultati: la strada veloce e quella lenta (la stessa ricerca in SQL) danno gli
  stessi turni nello stesso ordine e gli stessi gruppi, con e senza compartimenti;
- il filtro sta dentro la ricerca: una parola che compare in un turno solo di `alfa`, in
  mezzo a migliaia degli altri, si trova; non si trova dal predefinito;
- i conti dei gruppi tornano con un conteggio fatto a mano riga per riga;
- se la mappa non copre l'indice (una riga cancellata da fuori) la ricerca ripiega sulla
  strada lenta e da' lo stesso risultato, e la prossima indicizzazione rifa la mappa.

Su un commit senza `turni.mappa` (la base) le stesse misure girano lo stesso e il
controllo del tempo fallisce: e' la prova rossa.

Su Windows i compartimenti sono spenti (`piattaforma.compartimenti_supportati`): non
esistono ne' `alfa` ne' il predefinito, e `api._connessione_separata` torna una
connessione senza filtro. Quello che ha senso li' si fa lo stesso (la mappa, il tempo,
la strada veloce contro la lenta, i conti dei gruppi, il ripiego), solo senza
compartimenti; i tre controlli che parlano di compartimenti si segnano come passati con
"saltato: ..." scritto accanto, uno per uno, cosi' il conteggio delle prove e' lo stesso
su ogni sistema (il README ne dichiara uno solo).
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
PYTHON = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable

#: Il tetto per una parola su questo archivio. Il difetto costava da 4 a 12 secondi;
#: la strada nuova sta sotto i 200 ms su una macchina libera. Un secondo lascia
#: margine a una macchina sotto pressione senza far passare il difetto.
TETTO = 1.0

_SCRIPT = r'''
import json, os, sys, time, random, statistics
from pathlib import Path
sys.path.insert(0, os.environ["RADICE"])
from plancia import api, config, store, turni
from plancia import compartimenti_viste as viste

spec = json.loads(os.environ["SPEC"])
casa = Path(os.environ["PLANCIA_HOME"])
alfa_dir = Path(spec["alfa_dir"])
alfa_dir.mkdir(parents=True, exist_ok=True)
(casa / "config.json").write_text(json.dumps({
    "compartimenti": {"alfa": {"cartelle": [str(alfa_dir)]}, "predefinito": {}}}), "utf-8")

conn = store.connect(); store.init_db(conn)
rnd = random.Random(7)
vocab = ["parola%03d" % i for i in range(300)]
radice = config.CLAUDE_DIR / "projects"

progetti = []
for k in range(7):
    nome = "Progetto %d" % k
    pid = store.upsert_project(conn, "prj-%d" % k, nome, next_action="", auto=0,
                               last_activity="2026-09-20T09:00:00Z", summary=nome)
    if k == 0:
        store.link_project(conn, pid, "path", str(alfa_dir))
    progetti.append(pid)

n_riga = 0
righe_di = {}
for i in range(spec["sessioni"]):
    sid = "%08x-0000-4000-8000-000000000000" % (i + 1)
    e_alfa = i < spec["alfa"]
    k = 0 if e_alfa else 1 + (i % 6)
    cwd = str(alfa_dir) if e_alfa else str(casa / "altro" / str(k))
    cart = radice / ("-cartella-%d" % k)
    cart.mkdir(parents=True, exist_ok=True)
    file = cart / (sid + ".jsonl")
    with file.open("w", encoding="utf-8") as fh:
        for t in range(spec["turni"]):
            n_riga += 1
            parole = [rnd.choice(vocab) for _ in range(12)]
            if t % 3 == 0:
                parole.append("zenzero")
            if t % 5 == 0:
                parole.append("curcuma")
            if i == spec["alfa"] - 1 and t == 7:
                parole.append("unicorno")  # una volta sola, in un turno di alfa
            ts = "2026-09-20T%02d:%02d:%02dZ" % (n_riga // 3600 % 24, n_riga // 60 % 60, n_riga % 60)
            fh.write(json.dumps({
                "timestamp": ts,
                "message": {"role": "user" if t % 2 == 0 else "assistant",
                            "content": "riga %d " % n_riga + " ".join(parole)}}) + "\n")
    conn.execute(
        "INSERT INTO sessions(session_id, project_id, file, cwd, title, first_prompt, "
        "started_at, ended_at, n_user, n_assistant, n_tools, agent) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,'claude')",
        (sid, progetti[k], str(file), cwd, "sessione %d" % i, "primo", "2026-09-20T09:00:00Z",
         "2026-09-20T09:00:00Z", 3, 3, 1))
conn.commit()

t0 = time.time()
esito = turni.indicizza(conn, radice=radice)
tempo_indice = time.time() - t0
out = {"indicizzati": esito["turni"], "tempo_indice": tempo_indice}
mappa = getattr(turni, "mappa", None)
out["mappa_ok"] = bool(mappa and mappa(conn) is not None)
conn.close()

parole = ["zenzero", "curcuma", "zenzero curcuma", "parola001", "unicorno", "assente"]
out["misure"] = {}
# con i compartimenti spenti (Windows) "alfa" e il predefinito non esistono: la
# connessione tornerebbe senza filtro e le misure direbbero il falso
out["compartimenti"] = viste.attivo() is not None
scelte = ("alfa", "predefinito", None) if out["compartimenti"] else (None,)
for scelta in scelte:
    for q in parole:
        c, o = api._connessione_separata(scelta) if scelta else (store.connect(), None)
        t0 = time.time()
        if o is not None:
            a, g = viste.cerca_turni(c, o, q, 30)
        else:
            a, g = turni.cerca(c, q, 30), turni.raggruppa(c, q)
        dt = time.time() - t0
        rec = {"tempo": dt, "n": len(a), "gruppi": g,
               "turni": [(x["sessione"], x["riga"], x["progetto"]) for x in a]}
        if o is not None:
            rec["fuori"] = sum(1 for x in a if not o.sessione_ok(x["sessione"], x["percorso"]))
        if hasattr(turni, "_lento"):
            if o is not None:
                filtro = turni.Filtro(lambda s, p, o=o: o.sessione_ok(s, p or ""),
                                      o.ok["sessions"], o.ok["projects"])
            else:
                filtro = None
            dom = turni._domanda(q)
            la, lg = turni._lento(c, dom, 30, None, filtro, 8, True, True)
            rec["lento"] = {"turni": [(x["sessione"], x["riga"], x["progetto"]) for x in la],
                            "gruppi": lg}
        out["misure"]["%s|%s" % (scelta or "-", q)] = rec
        if o is not None:
            viste.chiudi(c, o)
        c.close()

# il conteggio fatto a mano, riga per riga, per le due parole piu' diffuse
c = store.connect()
sess_alfa = {r[0] for r in c.execute(
    "SELECT session_id FROM sessions WHERE cwd = ?", (str(alfa_dir),))}
mano = {}
for q in ("zenzero", "curcuma"):
    mano[q] = {"alfa": 0, "predefinito": 0}
    for sid, testo in c.execute("SELECT sessione, testo FROM turni_fts"):
        if q in testo.split():
            mano[q]["alfa" if sid in sess_alfa else "predefinito"] += 1
out["a_mano"] = mano

# una riga cancellata da fuori: la mappa non copre piu', la ricerca ripiega
if hasattr(turni, "mappa"):
    rid = c.execute("SELECT MIN(rowid) FROM turni_fts").fetchone()[0]
    c.execute("DELETE FROM turni_fts WHERE rowid = ?", (rid,))
    c.commit()
    out["mappa_dopo_cancella"] = turni.mappa(c) is not None
    c2, o2 = api._connessione_separata("predefinito")
    if o2 is not None:
        a, g = viste.cerca_turni(c2, o2, "zenzero", 30)
        filtro = turni.Filtro(lambda s, p: o2.sessione_ok(s, p or ""), o2.ok["sessions"], o2.ok["projects"])
    else:
        # senza compartimenti: la ricerca di sempre, senza filtro
        a, g = turni.cerca(c2, "zenzero", 30), turni.raggruppa(c2, "zenzero")
        filtro = None
    la, lg = turni._lento(c2, "zenzero", 30, None, filtro, 8, True, True)
    out["ripiego_uguale"] = ([(x["sessione"], x["riga"]) for x in a] ==
                             [(x["sessione"], x["riga"]) for x in la] and g == lg and len(a) > 0)
    c2.close()
    turni.indicizza(c, radice=radice)
    out["mappa_rifatta"] = turni.mappa(c) is not None
c.close()
print(json.dumps(out))
'''


def esegui(prova) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _finti

    with tempfile.TemporaryDirectory(prefix="plancia-cerca-") as tmp:
        base = Path(tmp)
        casa_finta, bin_finto = base / "home", base / "bin"
        casa_finta.mkdir()
        for nome in ("launchctl", "osascript", "schtasks", "systemctl", "crontab",
                     "claude", "codex"):
            _finti.crea_finto(bin_finto, nome, "import sys\nsys.exit(1)\n")
        env = dict(os.environ)
        _finti.casa_finta(env, casa_finta)
        env.update({
            "PATH": _finti.path_con(bin_finto),
            "PLANCIA_HOME": str(base / "dati"),
            "CLAUDE_CONFIG_DIR": str(base / "claude"),
            "CODEX_HOME": str(base / "codex"),
            "RADICE": str(RADICE),
            "SPEC": json.dumps({"alfa_dir": str(base / "alfa"), "sessioni": 700,
                                "alfa": 60, "turni": 45}),
        })
        _finti.variabili_di_sistema(env)
        (base / "dati").mkdir()
        r = subprocess.run([PYTHON, "-c", _SCRIPT], env=env, capture_output=True,
                           text=True, timeout=900)
        if r.returncode != 0:
            prova("ricerca veloce: l'archivio grande si costruisce", False,
                  (r.stderr or r.stdout)[-800:])
            return
        d = json.loads(r.stdout.strip().splitlines()[-1])

    m = d["misure"]
    # i compartimenti li ha chi li puo' avere: dal sistema vero, mai dal sottoprocesso
    # (se su macOS o Linux il sottoprocesso li dicesse spenti, le misure per alfa e per
    # il predefinito non esisterebbero e una prova vuota passerebbe lo stesso)
    senza_comp = os.name == "nt"
    scelte = ("-",) if senza_comp else ("alfa", "predefinito", "-")

    def solo_compartimenti(nome, condizione, dettaglio=""):
        """Un controllo che parla di compartimenti. Dove non ce ne sono (Windows) si segna
        passato con il perche' accanto, come tutti gli altri controlli che li' non si
        fanno: il conteggio resta quello degli altri sistemi. `condizione` e' una
        funzione, perche' su Windows le misure di `alfa` non esistono."""
        if senza_comp:
            prova(nome, True, "saltato: i compartimenti non esistono su Windows (sono spenti)")
        else:
            prova(nome, condizione(), dettaglio)

    prova("ricerca veloce: l'archivio di prova ha decine di migliaia di turni",
          d["indicizzati"] >= 30000, str(d["indicizzati"]))
    prova("ricerca veloce: dopo l'indicizzazione la mappa da riga a file copre tutto l'indice",
          d["mappa_ok"])

    lenti = {k: round(v["tempo"], 2) for k, v in m.items() if v["tempo"] > TETTO}
    prova("ricerca veloce: nessuna parola sopra %.0f s, con e senza compartimenti" % TETTO,
          not lenti, "troppo lente: %s" % lenti)
    prova("ricerca veloce: la parola in ogni turno trova la prima pagina piena",
          all(m["%s|zenzero" % s]["n"] == 30 for s in scelte))

    if "lento" in m["-|zenzero"]:
        diversi = [k for k, v in m.items()
                   if v["turni"] != v["lento"]["turni"] or v["gruppi"] != v["lento"]["gruppi"]]
        prova("ricerca veloce: la strada veloce e la lenta danno gli stessi turni, "
              "nello stesso ordine, e gli stessi gruppi (%d ricerche)" % len(m),
              not diversi, "diverse: %s" % diversi)
    else:
        prova("ricerca veloce: la strada lenta esiste per il confronto", False,
              "manca turni._lento")

    solo_compartimenti(
        "ricerca veloce: nessun turno di un altro compartimento nei risultati",
        lambda: d["compartimenti"] is True and all(v.get("fuori", 0) == 0 for v in m.values()),
        "compartimenti accesi nel sottoprocesso: %r" % d["compartimenti"])
    solo_compartimenti(
        "ricerca veloce: il turno unico di alfa in mezzo a migliaia si trova da alfa",
        lambda: (m["alfa|unicorno"]["n"] == 1 and m["alfa|unicorno"]["gruppi"]
                 and m["alfa|unicorno"]["gruppi"][0]["progetto"] == "Progetto 0"),
        str(m.get("alfa|unicorno")))
    solo_compartimenti(
        "ricerca veloce: e non si trova dal predefinito",
        lambda: (m["predefinito|unicorno"]["n"] == 0 and m["predefinito|unicorno"]["gruppi"] == []))
    prova("ricerca veloce: senza compartimenti lo trova",
          m["-|unicorno"]["n"] == 1)
    prova("ricerca veloce: una parola che non c'e' non trova niente e non fallisce",
          all(m["%s|assente" % s]["n"] == 0 for s in scelte))

    a_mano = d["a_mano"]
    for parola in ("zenzero", "curcuma"):
        tot = lambda scelta: sum(g["turni"] for g in m["%s|%s" % (scelta, parola)]["gruppi"])
        giusto = tot("-") == a_mano[parola]["alfa"] + a_mano[parola]["predefinito"]
        if not senza_comp:
            giusto = (giusto and tot("alfa") == a_mano[parola]["alfa"]
                      and tot("predefinito") == a_mano[parola]["predefinito"])
        prova("ricerca veloce: i gruppi di '%s' contano tutti i turni, non solo la pagina" % parola,
              giusto, "%s contro %s" % ({s: tot(s) for s in scelte}, a_mano[parola]))

    if "mappa_dopo_cancella" in d:
        prova("ricerca veloce: con una riga cancellata da fuori la mappa non copre piu'",
              d["mappa_dopo_cancella"] is False)
        prova("ricerca veloce: senza mappa la ricerca ripiega e da' lo stesso risultato "
              "della strada lenta", d["ripiego_uguale"])
        prova("ricerca veloce: la prossima indicizzazione rifa la mappa", d["mappa_rifatta"])
    else:
        prova("ricerca veloce: la mappa esiste (turni.mappa)", False, "manca turni.mappa")
