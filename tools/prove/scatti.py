"""Prove di `tools/scatti.sh` e dell'archivio dimostrativo che fotografa (22-SERVER).

Gli screenshot dei README si rifanno con `tools/scatti.sh`. Erano rimasti a un layout
che non c'e' piu' (ritagli a offset misurati a mano su pagine piu' alte) e a una memoria
dimostrativa di cinque schede senza legami, che il grafo disegnava come cinque pallini.

Qui si prova, senza Chrome:

- ogni vista che lo script fotografa esiste nel web di oggi (`views.*` in web/app.js) e
  non c'e' piu' nessun ritaglio;
- i file che scrive sono quelli che i due README mostrano;
- `?memoria=grafo` esiste nel web (senza, lo scatto del grafo sarebbe l'elenco);
- `tools/scatti.sh --controlla` GIRA: avvia un server sull'archivio finto, in una casa e
  su una porta sue, e controlla che ogni vista abbia dati (la memoria: 60-90 schede,
  legami veri, orfane, i quattro tipi, ogni scheda con le sue coordinate);
- la memoria dimostrativa e' generica: nessun nome vero, nessun percorso della macchina.

`esegui(prova)` e' la firma che `tools/prova.py` scopre da sola.
"""

import getpass
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent


def _carica(nome):
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, Path(__file__).resolve().parent / (nome + ".py"))
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[nome] = modulo
        spec.loader.exec_module(modulo)
    return sys.modules[nome]


_finti = _carica("_finti")
_saltati = _carica("_saltati")


def _porta_libera():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


def esegui(reale) -> None:
    prova = _saltati.Contatore(reale)
    if _saltati.WIN:
        _saltati.salta_il_resto("scatti", prova)
    else:
        _esegui(prova)
    _saltati.chiudi("scatti", prova, reale)


def _esegui(prova) -> None:
    sh = (RADICE / "tools" / "scatti.sh").read_text("utf-8")
    sh_mac = (RADICE / "tools" / "scatti-mac.sh").read_text("utf-8")
    app = (RADICE / "web" / "app.js").read_text("utf-8")
    viste = set(re.findall(r"^views\.(\w+)\s*=", app, re.M))
    fotografate = re.findall(r"^scatta\s+'?([a-z]+)", sh, re.M)
    file_scritti = re.findall(r"^scatta\s+\S+\s+(\S+\.png)", sh, re.M)
    file_scritti_mac = re.findall(r"^metti\s+\S+\s+\S+\s+(\S+\.png)", sh_mac, re.M)

    prova("scatti: lo script fotografa le quattro viste del web (oggi, task, memoria col grafo, ricerca)",
          {"oggi", "lavagna", "memoria", "cerca"} <= set(fotografate), str(fotografate))
    prova("scatti: ogni vista fotografata esiste nel web di oggi (la ricerca e' un indirizzo)",
          all(v in viste or v == "cerca" for v in fotografate), str(sorted(set(fotografate) - viste)))
    prova("scatti: niente ritagli di una pagina piu' alta (crop, offset misurati a mano)",
          not re.search(r"sips\s+(-c|--cropOffset)|--cropToHeightWidth|cropOffset", sh))
    prova("scatti: ogni scatto e' controllato a 2400x1830",
          "2400x1830" in sh and "sips -g pixelWidth" in sh)
    prova("scatti: il grafo si fotografa con ?memoria=grafo, che il web capisce",
          "memoria=grafo" in sh and "get('memoria') === 'grafo'" in app)
    readme = (RADICE / "README.md").read_text("utf-8") + (RADICE / "README.it.md").read_text("utf-8")
    mostrati = set(re.findall(r"\(docs/([\w-]+\.png)\)", readme))
    prova("scatti: i file che i due README mostrano li scrivono tools/scatti.sh (web) e tools/scatti-mac.sh (app)",
          bool(mostrati) and mostrati <= set(file_scritti) | set(file_scritti_mac),
          str(sorted(mostrati - set(file_scritti) - set(file_scritti_mac))))
    prova("scatti: ogni immagine che scrivono gli script e' mostrata da entrambi i README (nessuna orfana in docs/)",
          set(file_scritti) | set(file_scritti_mac) <= mostrati
          and {f.name for f in (RADICE / "docs").glob("*.png")} == mostrati,
          str(sorted({f.name for f in (RADICE / "docs").glob("*.png")} ^ mostrati)))
    in_it = set(re.findall(r"\(docs/([\w-]+\.png)\)", (RADICE / "README.it.md").read_text("utf-8")))
    in_en = set(re.findall(r"\(docs/([\w-]+\.png)\)", (RADICE / "README.md").read_text("utf-8")))
    prova("scatti: i due README mostrano le stesse immagini", in_it == in_en, str(sorted(in_it ^ in_en)))
    prova("scatti: nessun PNG di docs/ pesa piu' di 1 MB",
          all(f.stat().st_size <= 1_000_000 for f in (RADICE / "docs").glob("*.png")),
          str([f.name for f in (RADICE / "docs").glob("*.png") if f.stat().st_size > 1_000_000]))
    prova("scatti: scatti-mac.sh non lancia l'app senza un ambiente suo (HOME, PLANCIA_HOME, CLAUDE_CONFIG_DIR, CODEX_HOME), "
          "si rifiuta della 7773 e dell'archivio vero",
          all(x in sh_mac for x in ('export PLANCIA_HOME=', 'export HOME=', 'export CLAUDE_CONFIG_DIR=',
                                    'export CODEX_HOME=', '"7773"', 'archivio vero', '--istantanee'))
          and sh_mac.index("export HOME=") < sh_mac.index('"$APP/Contents/MacOS/Plancia" --istantanee'))
    prova("scatti: scatti-mac.sh fissa lingua, stile e dimensione del testo sulla riga di comando",
          all(x in sh_mac for x in ("--lingua en", "--stile", "--testo 3")))
    prova("scatti: l'archivio finto si rifiuta di essere quello vero e non tocca ~/.plancia",
          "archivio vero" in sh and "7773" in sh and "plancia.db" in sh)

    # --- la memoria dimostrativa, letta dal sorgente
    spec = importlib.util.spec_from_file_location("demo_data_prova", RADICE / "tools" / "demo-data.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    memoria, legami = demo.MEMORIA, demo.LEGAMI_MEMORIA
    nomi = [m[0] for m in memoria]
    tipi = {m[1] for m in memoria}
    prova("demo: la memoria dimostrativa ha da 60 a 90 schede, nomi tutti diversi",
          60 <= len(memoria) <= 90 and len(set(nomi)) == len(nomi), str(len(memoria)))
    prova("demo: i quattro tipi di scheda ci sono tutti", tipi == {"user", "feedback", "project", "reference"}, str(tipi))
    archi = {tuple(sorted((a, b))) for a, vs in legami.items() for b in vs}
    prova("demo: i legami vanno fra schede che esistono, e sono piu' delle schede",
          all(a in nomi and b in nomi for a, b in archi) and len(archi) >= len(nomi), "%d legami" % len(archi))
    legate = {n for a, b in archi for n in (a, b)}
    orfane = [n for n in nomi if n not in legate]
    prova("demo: qualche scheda senza legami (gli orfani), non la meta'", 1 <= len(orfane) < len(nomi) // 3, str(orfane))
    corte = [m[0] for m in memoria if not m[5]]
    prova("demo: alcune schede restano corte (il grafo le mostra vuote), la maggior parte no",
          1 <= len(corte) < len(nomi) // 3, str(len(corte)))
    testo = json.dumps(memoria, ensure_ascii=False) + json.dumps(legami)
    prova("demo: nessun percorso della macchina ne' nome di persona nella memoria dimostrativa",
          not re.search(r"/Users/|/Volumes/|/home/|C:\\\\", testo, re.I)
          and not [w for w in (getpass.getuser(), Path.home().name) if len(w) > 2 and w.lower() in testo.lower()])
    prova("demo: nessun em dash, e le descrizioni sono in inglese",
          "\u2014" not in testo and not re.search(r"\b(il|della|che|con|gli|nel|sono|non)\b", " ".join(m[4] for m in memoria)))

    # --- lo script gira davvero (--controlla), in una casa e su una porta sue
    tmp = Path(tempfile.mkdtemp(prefix="plancia-prova-scatti-"))
    casa = tmp / "casa"
    casa.mkdir()
    env = dict(os.environ)
    _finti.casa_finta(env, casa)
    env["CLAUDE_CONFIG_DIR"] = str(casa / "claude")
    env["CODEX_HOME"] = str(casa / "codex")
    env["PLANCIA_DEMO_HOME"] = str(tmp / "demo")
    env["PLANCIA_DEMO_PORT"] = str(_porta_libera())
    env["PLANCIA_SCATTI_SITE"] = ""
    env["PLANCIA_SCATTI_OUT"] = str(tmp / "fuori")
    env["TMPDIR"] = str(tmp)
    env.pop("PLANCIA_HOME", None)
    r = subprocess.run(["bash", str(RADICE / "tools" / "scatti.sh"), "--controlla"], env=env, cwd=str(RADICE),
                       capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    uscita = r.stdout + r.stderr
    prova("scatti: `scatti.sh --controlla` gira e passa sull'archivio finto",
          r.returncode == 0 and "controllo passato" in uscita, uscita[-500:])
    m = re.search(r"memoria: (\d+) schede, (\d+) legami, (\d+) orfane, (\d+) tipi, (\d+) con posizione, "
                  r"(\d+) gruppi, (\d+) ponti, (\d+) titoli", uscita)
    prova("scatti: la memoria che il server serve ha schede, legami, orfane, tipi e coordinate",
          bool(m) and int(m.group(1)) == len(memoria) and int(m.group(4)) == 4
          and int(m.group(5)) == int(m.group(1)) and int(m.group(2)) >= int(m.group(1)), uscita[-400:])
    prova("scatti: ...in 6-12 gruppi leggibili, con dei ponti fra gruppi e un titolo per scheda",
          bool(m) and 6 <= int(m.group(6)) <= 12 and int(m.group(7)) >= 8 and int(m.group(8)) >= int(m.group(1)) - 2,
          uscita[-400:])
    # un archivio senza le viste da fotografare deve far FALLIRE il controllo
    env["PLANCIA_DEMO_HOME"] = str(tmp / "demo-vuoto")
    env["PLANCIA_DEMO_PORT"] = str(_porta_libera())
    vuoto = tmp / "demo-vuoto"
    vuoto.mkdir()
    (vuoto / "demo-data.py.saltato").write_text("x")
    r2 = subprocess.run(["bash", str(RADICE / "tools" / "scatti.sh"), "--controlla"], env=env, cwd=str(RADICE),
                        capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    prova("scatti: una cartella che non e' un archivio finto non viene cancellata",
          r2.returncode == 2 and (vuoto / "demo-data.py.saltato").exists(), (r2.stdout + r2.stderr)[-300:])
    prova("scatti: lo script non lascia server accesi",
          subprocess.run(["lsof", "-nP", "-iTCP:" + env["PLANCIA_DEMO_PORT"], "-sTCP:LISTEN"],
                         capture_output=True, text=True).stdout.strip() == "")


if __name__ == "__main__":
    _casa = tempfile.mkdtemp(prefix="plancia-prova-scatti-casa-")
    os.environ["PLANCIA_HOME"] = _casa
    sys.path.insert(0, str(RADICE))
    _falliti = []

    def _prova(nome, cond, dettaglio=""):
        print(("  ok   " if cond else "  NO   ") + nome + ("" if cond else "  " + str(dettaglio)))
        if not cond:
            _falliti.append(nome)

    esegui(_prova)
    print("\n%s" % ("FALLITE: %d" % len(_falliti) if _falliti else "tutte verdi"))
    sys.exit(1 if _falliti else 0)
