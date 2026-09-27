"""Prove per i primi due residui dei tester dell'ondata 2 (16/09/2026), i due
punti per cui il lotto ammette anche `plancia/turni.py` fra i file di
proprietà (oltre a questo modulo, nuovo):

1. `plancia serve --no-sync` avviava comunque il ticker che chiama
   `start_sync` ogni due minuti (`plancia/api.py:serve`), e tre tester
   indipendenti hanno visto i db di prova riempirsi di progetti veri della
   macchina.
2. `plancia/turni.py` ignorava `CLAUDE_CONFIG_DIR` e leggeva sempre
   `~/.claude/projects` reale: misurato sulla macchina di prova, l'indice
   trovava 5168 file e 48062 turni VERI anche con `CLAUDE_CONFIG_DIR` puntato
   a una cartella vuota, perché la vecchia `RADICE` era una costante di
   modulo calcolata una volta da `Path.home()`, non da `config.CLAUDE_DIR`.

LOTTO-L3-RITOCCO punto 9, su questo file: la prima versione di `_prova_no_sync`
lanciava `plancia.api.serve` in un thread DENTRO il processo di
`tools/prova.py`, e a fine attesa leggeva `plancia.api.SYNC_STATE` (un dict a
livello di modulo) per dire "non è partito niente". Due difetti, non uno:

- `SYNC_STATE` è condiviso da OGNI prova che nello stesso processo importa
  `plancia.api` (e ce ne sono altre, in `tools/prove/`): un'altra prova che
  prima di questa avesse davvero avviato un sync sullo stesso processo (o
  che lo avviasse dopo, in un thread ancora vivo mentre questa legge)
  lascerebbe `SYNC_STATE["result"]` non-None o `["running"]` vero per un
  motivo che non ha niente a che fare con `--no-sync`, e la prova
  fallirebbe (o peggio: passerebbe per il motivo sbagliato) a seconda
  dell'ordine di scoperta di `tools/prova.py`.
- Un secondo `serve()` nello stesso processo, sulla stessa porta, non
  chiuderebbe mai il primo httpd (nessun `shutdown()` da nessuna parte):
  lanciarla due volte di fila avrebbe semplicemente fallito il bind della
  porta la seconda volta.

Ora il server gira in un sottoprocesso vero (`python3 -m plancia.cli serve
--no-sync`, come fa `tools/prova-video.sh`): PLANCIA_HOME e
PLANCIA_TICKER_SECONDI passano nell'ambiente DI QUEL processo, che non
importa mai `plancia.api` nel processo di `tools/prova.py` e quindi non
condivide `SYNC_STATE` con nessun'altra prova. La misura resta quella che il
lotto suggerisce como "meglio": `meta.last_sync_end` (scritta da
`ingest.sync` solo a sync completato, mai spostata da sola) letta con una
connessione sqlite fresca, prima di avviare il sottoprocesso e dopo l'attesa.
`esegui()`, in fondo, chiama `_prova_no_sync` DUE volte di fila (porte e
PLANCIA_HOME diverse, stesso processo Python di `tools/prova.py`): la seconda
chiamata non deve trovare in giro niente lasciato dalla prima, ed è
esattamente la dimostrazione che il lotto chiede.

Isolamento (punto 2): `config.CLAUDE_DIR` riassegnato a una cartella vuota
(letto a ogni chiamata da `turni.indicizza`, mai congelato in una chiusura:
riassegnare l'attributo del modulo basta, stesso schema di
`tools/prove/sessione.py`), poi ripristinato.

`esegui(prova)` è la firma che `tools/prova.py` scopre da sola (vedi
`tools/prove/README.md`).
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))


def _porta_libera(preferita) -> int:
    porta = preferita
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if s.connect_ex(("127.0.0.1", porta)) != 0:
                return porta
        finally:
            s.close()
        porta += 1


def _aspetta_server(porta, tentativi=60) -> bool:
    for _ in range(tentativi):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=0.5)
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.25)
    return False


def _prova_no_sync(prova, porta_preferita) -> None:
    from plancia import config, store

    casa = Path(tempfile.mkdtemp(prefix="plancia-prova-serve-no-sync-"))
    vecchio_data_dir, vecchio_db_path = config.DATA_DIR, config.DB_PATH
    # Stessa tecnica delle altre prove (es. tools/prove/sessione.py):
    # DATA_DIR/DB_PATH sono calcolati una volta da PLANCIA_HOME all'importazione
    # del modulo in QUESTO processo (quello di tools/prova.py), quindi si
    # riassegnano gli attributi per la lettura di `meta`, invece di sperare che
    # un PLANCIA_HOME cambiato a runtime venga riletto da solo (non succede).
    # Il sottoprocesso che lancia il server vero, sotto, non ha questo
    # problema: parte da zero e legge PLANCIA_HOME dal suo ambiente.
    config.DATA_DIR = casa
    config.DB_PATH = casa / "plancia.db"
    porta = _porta_libera(porta_preferita)
    server = None
    try:
        conn = store.connect()
        store.init_db(conn)
        prima = store.get_meta(conn, "last_sync_end")
        conn.close()

        env = dict(os.environ)
        env["PLANCIA_HOME"] = str(casa)
        # Consigliata del critico (L3-RIPRENDI-UI-4): il sottoprocesso non
        # deve ereditare HOME/CLAUDE_CONFIG_DIR veri. Se il difetto originale
        # tornasse (il ticker che parte comunque), un turni.indicizza() sulla
        # ~/.claude vera del banco di prova finirebbe nel db temporaneo: qui
        # non c'è modo di distinguerlo da un sync innocuo. Puntando anche
        # HOME/CLAUDE_CONFIG_DIR a cartelle vuote, un sync che partisse per
        # errore non troverebbe niente da indicizzare comunque, ma soprattutto
        # non tocca mai i dati veri di chi lancia la prova.
        env["HOME"] = str(casa)
        env["CLAUDE_CONFIG_DIR"] = str(casa / "claude-vuota")
        (casa / "claude-vuota").mkdir(parents=True, exist_ok=True)
        # Forza il periodo del ticker a un secondo invece dei minuti veri
        # (plancia/api.py:serve, `PLANCIA_TICKER_SECONDI`, solo per le prove):
        # senza, il ticker (period `caldo * 60` = 120s di default) non
        # avrebbe fatto in tempo a scattare nemmeno nei tre secondi d'attesa
        # sotto, e la prova sarebbe stata verde anche col difetto - non per
        # il fix, ma perché non aveva aspettato abbastanza.
        env["PLANCIA_TICKER_SECONDI"] = "1"
        server = subprocess.Popen(
            [sys.executable, "-m", "plancia.cli", "serve", "--port", str(porta), "--no-sync"],
            cwd=str(RADICE), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        attivo = _aspetta_server(porta)
        if not attivo or server.poll() is not None:
            uscita = server.stdout.read() if server.stdout else ""
            prova(f"il server di prova (porta {porta}) è partito",
                  False, f"uscita: {uscita[:800]}")
            return

        # Tre secondi, come chiede il lotto: con PLANCIA_TICKER_SECONDI=1 il
        # ticker (se partisse, cioè col difetto) avrebbe già scattato due o
        # tre volte in questa finestra.
        time.sleep(3)

        conn2 = store.connect()
        dopo = store.get_meta(conn2, "last_sync_end")
        conn2.close()
        prova(f"'plancia serve --no-sync' (sottoprocesso, porta {porta}) non fa "
              "partire nessun sync in 3 secondi, anche con un ticker forzato a 1 secondo",
              dopo == prima, f"last_sync_end: {prima!r} -> {dopo!r}")
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        config.DATA_DIR, config.DB_PATH = vecchio_data_dir, vecchio_db_path
        shutil.rmtree(str(casa), ignore_errors=True)


def _prova_contratto_http_no_sync(prova, porta_preferita) -> None:
    # L3-RIPRENDI-UI-4 (obbligatoria del critico): il lotto chiede alla
    # lettera "POST /api/sync con il server partito --no-sync risponde
    # {"avviato": false, "motivo": "--no-sync"}" - nessuna prova esistente lo
    # verificava via HTTP (solo Jarvis, forzando `api._NO_SYNC_ATTIVO` a
    # mano, e una sottostringa del front). Se domani qualcuno togliesse le
    # due righe di `plancia/api.py` che scrivono `motivo` nel corpo, questa
    # suite restava verde: qui il contratto si prova per davvero, con un
    # server vero in un sottoprocesso e una richiesta HTTP vera.
    from plancia import config, store

    casa = Path(tempfile.mkdtemp(prefix="plancia-prova-serve-no-sync-http-"))
    vecchio_data_dir, vecchio_db_path = config.DATA_DIR, config.DB_PATH
    config.DATA_DIR = casa
    config.DB_PATH = casa / "plancia.db"
    porta = _porta_libera(porta_preferita)
    server = None
    try:
        conn = store.connect()
        store.init_db(conn)
        prima = store.get_meta(conn, "last_sync_end")
        conn.close()

        env = dict(os.environ)
        env["PLANCIA_HOME"] = str(casa)
        env["HOME"] = str(casa)
        env["CLAUDE_CONFIG_DIR"] = str(casa / "claude-vuota")
        (casa / "claude-vuota").mkdir(parents=True, exist_ok=True)
        env["PLANCIA_TICKER_SECONDI"] = "1"
        server = subprocess.Popen(
            [sys.executable, "-m", "plancia.cli", "serve", "--port", str(porta), "--no-sync"],
            cwd=str(RADICE), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        attivo = _aspetta_server(porta)
        if not attivo or server.poll() is not None:
            uscita = server.stdout.read() if server.stdout else ""
            prova(f"il server di prova (porta {porta}, contratto HTTP) è partito",
                  False, f"uscita: {uscita[:800]}")
            return

        # Il token vive nel sottoprocesso (PLANCIA_HOME=casa lì dentro): si
        # legge dalla pagina index, che lo incorpora in un <meta> (stessa
        # cosa che fa web/app.js all'avvio), invece di toccare
        # config.TOKEN_FILE in QUESTO processo (che punta ancora a `casa`
        # solo per DATA_DIR/DB_PATH, non per TOKEN_FILE: sono attributi
        # separati, calcolati una volta all'importazione del modulo).
        pagina = urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=2).read().decode("utf-8")
        m = re.search(r'name="plancia-token"\s+content="([^"]+)"', pagina)
        if not m:
            prova("la pagina index del server di prova porta il token",
                  False, pagina[:400])
            return
        token = m.group(1)

        richiesta = urllib.request.Request(
            f"http://127.0.0.1:{porta}/api/sync", data=b"{}", method="POST",
            headers={"X-Plancia-Token": token, "Content-Type": "application/json"})
        with urllib.request.urlopen(richiesta, timeout=2) as risposta:
            corpo_raw = risposta.read().decode("utf-8")
        corpo = json.loads(corpo_raw)
        prova('POST /api/sync con --no-sync risponde esattamente '
              '{"avviato": false, "motivo": "--no-sync"}',
              corpo == {"avviato": False, "motivo": "--no-sync"}, corpo_raw)

        # Nessun sync deve essere partito: né subito (via /api/status), né
        # dopo un'attesa (via last_sync_end, come nell'altra prova).
        stato_raw = urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/status", timeout=2).read()
        stato = json.loads(stato_raw.decode("utf-8"))
        prova("subito dopo il POST, /api/status non mostra nessun sync in corso",
              stato.get("sync", {}).get("running") is False, stato_raw.decode("utf-8"))

        time.sleep(2.5)
        conn2 = store.connect()
        dopo = store.get_meta(conn2, "last_sync_end")
        conn2.close()
        prova("dopo il POST /api/sync con --no-sync, last_sync_end resta invariato",
              dopo == prima, f"last_sync_end: {prima!r} -> {dopo!r}")
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        config.DATA_DIR, config.DB_PATH = vecchio_data_dir, vecchio_db_path
        shutil.rmtree(str(casa), ignore_errors=True)


def _prova_turni_claude_config_dir(prova) -> None:
    from plancia import config, store, turni

    cartella = Path(tempfile.mkdtemp(prefix="plancia-prova-turni-config-dir-"))
    vecchio = config.CLAUDE_DIR
    config.CLAUDE_DIR = cartella  # vuota apposta: nessun 'projects/' dentro
    try:
        conn = store.connect()
        store.init_db(conn)
        esito = turni.indicizza(conn, completo=True)
        conn.close()
        prova("con CLAUDE_CONFIG_DIR su una cartella vuota, turni non trova niente "
              "(non legge più sempre ~/.claude/projects reale)",
              esito["file_nuovi"] == 0 and esito["turni"] == 0, str(esito))
    finally:
        config.CLAUDE_DIR = vecchio
        shutil.rmtree(str(cartella), ignore_errors=True)


def esegui(prova) -> None:
    # Due volte di fila, PLANCIA_HOME e porta diverse ma stesso processo
    # Python (quello che sta eseguendo `prova`): la dimostrazione che il
    # lotto chiede per il punto 9, che una prova precedente sullo stesso
    # processo non lascia niente da cui la prossima debba proteggersi -
    # qui non c'è niente da proteggere, perché il server vero gira altrove.
    _prova_no_sync(prova, 7794)
    _prova_no_sync(prova, 7795)
    _prova_contratto_http_no_sync(prova, 7796)
    _prova_turni_claude_config_dir(prova)


if __name__ == "__main__":
    # `_prova_no_sync` si isola da sola (rialloca PLANCIA_HOME/config.DATA_DIR
    # per la sua durata e li rimette com'erano), ma senza una PLANCIA_HOME
    # fissata PRIMA di ogni importazione `_prova_turni_claude_config_dir`
    # aprirebbe `store.connect()` sulla '~/.plancia' vera di chi lancia la
    # prova (config.DB_PATH è calcolato una volta sola, al primo import di
    # plancia.config, da PLANCIA_HOME così com'è in quel momento): misurato,
    # "database is locked" perché quel database vero era già aperto altrove.
    _CASA_MAIN = tempfile.mkdtemp(prefix="plancia-prova-serve-no-sync-main-")
    os.environ["PLANCIA_HOME"] = _CASA_MAIN

    falliti = []
    passati = 0

    def _prova(nome, condizione, dettaglio=""):
        global passati
        if condizione:
            passati += 1
            print(f"  ok   {nome}")
        else:
            falliti.append(nome)
            print(f"  NO   {nome} {dettaglio}")

    try:
        esegui(_prova)
    finally:
        shutil.rmtree(_CASA_MAIN, ignore_errors=True)
    print(f"\n{passati} passate, {len(falliti)} fallite")
    if falliti:
        for f in falliti:
            print(f"  - {f}")
        sys.exit(1)
