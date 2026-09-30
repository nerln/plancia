"""Prove di Kokoro, la voce neurale di Jarvis (`plancia/kokoro.py`, `plancia/voce_kokoro.py`).

Tutte con un lavoratore FINTO (`_kokoro_finto.py`): un "Python" scritto dalla prova che
parla lo stesso protocollo del vero e scrive un WAV minimo. Niente modello, niente
onnxruntime, niente rete: `voce installa` gira con un pip e una rete finti e non scarica
mai niente. Pocket e Voicebox puntano a una porta chiusa (o al Pocket finto della prova).

Cosa si dimostra:

1. Avvio pigro: senza una richiesta non parte niente. Una frase (o `/api/jarvis/pronto`)
   lancia il lavoratore, e le frasi dopo lo riusano: un processo solo.
2. Chiusura: dopo `kokoro_inattivo_secondi` senza richieste, e alla chiusura del server; un
   lavoratore morto viene sostituito solo a vecchio finito (mai due insieme).
3. Ripiego: se muore, non si avvia, e' ancora a caricare o non risponde entro il tetto,
   la frase passa al motore dopo (Pocket, poi Voicebox) e la nota dice perche'.
4. Ordine: Kokoro, Pocket, Voicebox. Voce per lingua (`voce_kokoro`), velocita' rispettata,
   pausa in fondo ai pezzi, cache che non serve una voce vecchia.
5. Spezzatura: la prima frase esce in clausole, le altre intere.
6. `plancia voce prova` (senza suonare, senza avviare) e `plancia voce installa` (piano
   detto prima, conferma, dimensione esatta, niente file a meta').

`esegui(prova)` e' la firma che `tools/prova.py` scopre da sola. Su Windows si salta: i
lavoratori finti sono script POSIX.
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent.parent
QUI = Path(__file__).resolve().parent


def _carica(nome):
    if nome not in sys.modules:
        spec = importlib.util.spec_from_file_location(nome, QUI / (nome + ".py"))
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[nome] = modulo
        spec.loader.exec_module(modulo)
    return sys.modules[nome]


_finti = _carica("_finti")
_saltati = _carica("_saltati")
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))


def _porta_libera():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


def esegui(reale) -> None:
    prova = _saltati.Contatore(reale)
    if _saltati.WIN:
        _saltati.salta_il_resto("voce-kokoro", prova)
    else:
        _esegui(prova)
    _saltati.chiudi("voce-kokoro", prova, reale)


def _wrapper(ctl):
    """Il "Python" finto: chiama il lavoratore finto con il suo file di controllo."""
    return ("import sys\nsys.path.insert(0, %r)\nimport _kokoro_finto\n"
            "sys.exit(_kokoro_finto.main(sys.argv, %r))\n" % (str(QUI), str(ctl)))


def _vivo(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _attendi(condizione, secondi=6.0, passo=0.05):
    fine = time.monotonic() + secondi
    while time.monotonic() < fine:
        if condizione():
            return True
        time.sleep(passo)
    return bool(condizione())


class _Config:
    """Scrive chiavi in config.json e a fine prova rimette il file com'era."""

    def __init__(self, config):
        self.file = config.CONFIG_FILE
        self.prima = self.file.read_text("utf-8") if self.file.exists() else None

    def _leggi(self):
        try:
            return json.loads(self.prima) if self.prima else {}
        except ValueError:
            return {}

    def imposta(self, **chiavi):
        d = self._leggi()
        letto = json.loads(self.file.read_text("utf-8")) if self.file.exists() else d
        letto.update(chiavi)
        for k, v in list(letto.items()):
            if v is None:
                del letto[k]
        self.file.write_text(json.dumps(letto), "utf-8")

    def ripristina(self):
        if self.prima is None:
            with contextlib.suppress(OSError):
                self.file.unlink()
        else:
            self.file.write_text(self.prima, "utf-8")


def _esegui(prova) -> None:
    from plancia import api, cli, config, jarvis, kokoro, voice

    T = Path(tempfile.mkdtemp(prefix="plancia-prova-kokoro-"))
    ctl = T / "finto.json"
    reg = T / "registro.log"
    voce_dir = config.DATA_DIR / "voce"
    cfg = _Config(config)
    pocket = None
    vere = {"riproduci": voice.riproduci, "scalda": jarvis.scalda, "say": voice.sintesi_say,
            "pocket_no": voice._pocket_no, "vb_no": voice._ultimo_no}

    def controllo(**chiavi):
        try:
            d = json.loads(ctl.read_text("utf-8"))
        except (OSError, ValueError):
            d = {}
        d.update(chiavi)
        d["registro"] = str(reg)
        ctl.write_text(json.dumps({k: v for k, v in d.items() if v is not None}), "utf-8")

    def righe():
        if not reg.exists():
            return []
        fuori = []
        for r in reg.read_text("utf-8").splitlines():
            p = r.split(" ", 3)
            if len(p) >= 3:
                fuori.append((float(p[0]), p[1], int(p[2]), p[3] if len(p) > 3 else ""))
        return fuori

    def eventi(nome):
        return [r for r in righe() if r[1] == nome]

    def richieste():
        """[(testo, voce, velocita, pausa)] nell'ordine in cui il finto le ha ricevute."""
        fuori = []
        for _, _, _, extra in eventi("RICH"):
            testo, voce, vel, pausa = [x.strip() for x in extra.rsplit(" | ", 3)]
            fuori.append((testo, voce, vel, pausa))
        return fuori

    def azzera(**chiavi):
        """Uno scenario nuovo: lavoratore chiuso, registro vuoto, guasti dimenticati."""
        kokoro.spegni()
        _attendi(lambda: not any(_vivo(r[2]) for r in eventi("AVVIO")), 6)
        with contextlib.suppress(OSError):
            reg.unlink()
        kokoro._lavoratore.dimentica_guasto()
        voice._pocket_no = 0.0
        voice._ultimo_no = 0.0
        controllo(**{k: None for k in ("carica_s", "guasto_avvio", "latenza_s",
                                       "muori_alla_richiesta", "tace_su", "rifiuta")})
        base = dict(kokoro_attivo=None, kokoro_python=None, kokoro_modelli=None,
                    voce_kokoro=None, velocita_kokoro=None, kokoro_inattivo_secondi=300,
                    kokoro_riprova_secondi=0.4, attesa_voce_neurale=5,
                    pocket_url="http://127.0.0.1:9", voicebox_url="http://127.0.0.1:9")
        base.update(chiavi)
        cfg.imposta(**base)

    def senza(f):
        """Chiama f e torna l'eccezione che solleva (o None)."""
        try:
            f()
        except Exception as exc:  # noqa: BLE001
            return exc
        return None

    def sintesi(testo="Ho aperto la vista dei task.", lang="it", motore="neurale", **kw):
        kw.setdefault("cache", False)
        return voice.sintesi(testo, lang, motore, **kw)

    def wav_ok(percorso):
        try:
            with wave.open(str(percorso), "rb") as w:
                return (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes())
        except (OSError, wave.Error, EOFError):
            return None

    try:
        # ------------------------------------------------------------ prima: senza Kokoro
        cfg.imposta(pocket_url="http://127.0.0.1:9", voicebox_url="http://127.0.0.1:9",
                    kokoro_riprova_secondi=0.4, attesa_voce_neurale=2)
        shutil.rmtree(voce_dir, ignore_errors=True)
        prova("senza il Python e i modelli Kokoro non e' installato e non parla",
              not kokoro.installazione()[0] and not kokoro.disponibile("it")
              and voice.voce_neurale("it") == "", str(kokoro.installazione()))
        info = jarvis.informazioni_voce("it")
        prova("...e il pannello ne riceve il perche' (non_installato) e nessun motore neurale",
              info.get("neurale") is None and info.get("kokoro") == "non_installato"
              and "voce installa" in info.get("nota", ""), str(info))
        errore = senza(lambda: sintesi())
        prova("la voce neurale senza nessun motore solleva NessunaVoceNeurale e dice di Kokoro",
              isinstance(errore, voice.NessunaVoceNeurale) and "Kokoro" in str(errore)
              and "voce installa" in str(errore), repr(errore))
        prova("stato(): Kokoro non installato e nessun lavoratore",
              voice.stato().get("kokoro") == {"installato": False, "vivo": False}, str(voice.stato().get("kokoro")))

        # ------------------------------------------------------------ il posto predefinito
        modelli = voce_dir / "modelli"
        modelli.mkdir(parents=True, exist_ok=True)
        for nome in kokoro.MODELLI:
            (modelli / nome).write_bytes(b"finto")
        _finti.crea_finto(voce_dir / "venv" / "bin", "python", _wrapper(ctl))
        controllo()
        azzera()
        prova("il posto predefinito e' <PLANCIA_HOME>/voce (venv e modelli)",
              kokoro.python_kokoro() == voce_dir / "venv" / "bin" / "python"
              and kokoro.cartella_modelli() == modelli, str((kokoro.python_kokoro(), kokoro.cartella_modelli())))
        prova("con i due file e il Python al loro posto Kokoro e' installato ed e' la voce neurale",
              kokoro.installazione()[0] and voice.voce_neurale("it") == "kokoro", str(kokoro.installazione()))
        prova("AVVIO PIGRO: sapere che c'e' non lancia niente",
              not righe() and not kokoro.stato()["lavoratore"]["vivo"], str(righe()))
        prova("una lingua senza voce (francese) non e' Kokoro", not kokoro.disponibile("fr"))

        # ------------------------------------------------------------ prima frase, riuso
        info = sintesi(velocita=1.15)
        w = wav_ok(info["file"])
        prova("la prima frase lancia il lavoratore e torna un WAV 24 kHz mono a 16 bit",
              info["motore"] == "kokoro" and w and w[:3] == (24000, 1, 2) and w[3] > 1000 and len(eventi("AVVIO")) == 1,
              str((info, w, righe())))
        prova("...con la voce italiana di serie e la velocita' chiesta (e il silenzio del punto)",
              richieste()[-1][1:] == ("if_sara", "1.15", "0.2"), str(richieste()))
        prova("...e senza `ripiego`: Kokoro ha risposto", "ripiego" not in info, str(info))
        pid = eventi("AVVIO")[0][2]
        sintesi("Un altro pezzo,")
        sintesi("E l'ultimo senza punto")
        prova("RIUSO: tre frasi, un solo lavoratore (un solo AVVIO, sempre lo stesso pid)",
              len(eventi("AVVIO")) == 1 and kokoro.stato()["lavoratore"]["pid"] == pid
              and len(eventi("RICH")) == 3, str(righe()))
        prova("il silenzio in fondo: 0,2 al punto, 0,18 alla virgola, niente senza punteggiatura",
              [r[3] for r in richieste()] == ["0.2", "0.18", "0.0"], str(richieste()))

        # ------------------------------------------------------------ voci e velocita'
        sintesi("Hello there.", "en")
        sintesi("Hola, mundo.", "es")
        prova("la voce per lingua: inglese af_heart, spagnolo ef_dora",
              [r[1] for r in richieste()[-2:]] == ["af_heart", "ef_dora"], str(richieste()[-2:]))
        cfg.imposta(voce_kokoro={"it": "im_nicola"})
        sintesi("Ciao.")
        sintesi("Hello again.", "en")
        prova("`voce_kokoro` cambia la voce di una lingua e lascia le altre alle predefinite",
              [r[1] for r in richieste()[-2:]] == ["im_nicola", "af_heart"], str(richieste()[-2:]))
        cfg.imposta(voce_kokoro=None, velocita_kokoro=0.9)
        sintesi("Piano.")
        sintesi("Molto veloce.", velocita=5)
        sintesi("Un filo piu' su.", velocita=1.13)
        prova("velocita': quella di config se chi chiama non ne dice una, tetto 2.0, passi di 0.05",
              [r[2] for r in richieste()[-3:]] == ["0.9", "2.0", "1.15"], str(richieste()[-3:]))
        cfg.imposta(velocita_kokoro=None)
        errore = senza(lambda: sintesi("Bonjour.", "fr"))
        prova("per una lingua senza voce la voce neurale non e' Kokoro e lo dice",
              isinstance(errore, voice.NessunaVoceNeurale) and "lingua fr" in str(errore), repr(errore))

        # ------------------------------------------------------------ cache
        cfg.imposta(voce_kokoro={"it": "if_sara"})
        prima = voice.sintesi("La stessa frase per la cache.", "it", "neurale", cache=True)
        cfg.imposta(voce_kokoro={"it": "im_nicola"})
        dopo = voice.sintesi("La stessa frase per la cache.", "it", "neurale", cache=True)
        ancora = voice.sintesi("La stessa frase per la cache.", "it", "neurale", cache=True)
        prova("cambiare voce non serve il file vecchio dalla cache; la stessa voce si', da cache",
              prima["file"] != dopo["file"] and dopo["motore"] == "kokoro" and ancora["motore"] == "cache"
              and ancora["file"] == dopo["file"], str((prima, dopo, ancora)))
        cfg.imposta(voce_kokoro=None)

        # ------------------------------------------------------------ mai due insieme
        azzera()
        controllo(carica_s=0.5)
        esiti = []

        def una():
            esiti.append(senza(lambda: sintesi("Frase in parallelo.")))
        fili = [threading.Thread(target=una) for _ in range(5)]
        [f.start() for f in fili]
        [f.join(20) for f in fili]
        prova("cinque richieste insieme a freddo: UN lavoratore solo, e tutte servite",
              len(eventi("AVVIO")) == 1 and len(eventi("RICH")) == 5 and esiti == [None] * 5,
              str((esiti, righe())))
        controllo(carica_s=0)

        # ------------------------------------------------------------ inattivita'
        azzera(kokoro_inattivo_secondi=1)
        sintesi()
        primo = eventi("AVVIO")[0][2]
        chiuso = _attendi(lambda: not _vivo(primo), 5)
        prova("INATTIVITA': dopo kokoro_inattivo_secondi senza richieste il lavoratore si chiude da solo",
              chiuso and not kokoro.stato()["lavoratore"]["vivo"] and len(eventi("USCITA")) == 1,
              str(righe()))
        sintesi()
        secondo = eventi("AVVIO")[-1][2]
        prova("...e alla frase dopo ne parte uno nuovo, solo a vecchio finito (mai due insieme)",
              secondo != primo and len(eventi("AVVIO")) == 2
              and eventi("USCITA")[0][0] <= eventi("AVVIO")[1][0], str(righe()))
        # una richiesta ogni mezzo secondo tiene il lavoratore in vita oltre l'inattivita'
        for _ in range(4):
            time.sleep(0.5)
            sintesi()
        prova("...ma finche' arrivano richieste resta vivo (l'inattivita' si conta dall'ultima)",
              _vivo(secondo) and len(eventi("AVVIO")) == 2, str(righe()))
        cfg.imposta(kokoro_inattivo_secondi=300)

        # ------------------------------------------------------------ chiusura del server
        azzera()
        sintesi()
        primo = eventi("AVVIO")[0][2]
        voice.spegni_neurale()
        prova("CHIUSURA DEL SERVER: spegni_neurale() chiude il lavoratore e lascia stdin chiuso",
              _attendi(lambda: not _vivo(primo), 5) and not kokoro.stato()["lavoratore"]["vivo"]
              and len(eventi("USCITA")) == 1, str(righe()))
        prova("...e api.serve() lo chiama alla fine", "voice.spegni_neurale()" in _sorgente(api.serve))

        # ------------------------------------------------------------ morte del lavoratore
        azzera()
        controllo(muori_alla_richiesta=1)
        sintesi()
        primo = eventi("AVVIO")[0][2]
        errore = senza(lambda: sintesi("Questa uccide il lavoratore."))
        prova("MORTE: se il lavoratore muore a meta' la frase ripiega (qui nessun altro motore) e dice perche'",
              isinstance(errore, voice.NessunaVoceNeurale) and "Kokoro" in str(errore)
              and ("terminato" in str(errore) or "caduto" in str(errore)), repr(errore))
        prova("...per un po' Kokoro e' in pausa e il pannello lo sa (in_pausa)",
              voice.voce_neurale("it") == "" and jarvis.informazioni_voce("it").get("kokoro") == "in_pausa",
              str(jarvis.informazioni_voce("it")))
        controllo(muori_alla_richiesta=None)
        _attendi(lambda: not kokoro._lavoratore.in_pausa(), 3)
        info = sintesi("Di nuovo.")
        secondo = eventi("AVVIO")[-1][2]
        prova("...passata la pausa ne parte uno nuovo (pid diverso, il vecchio e' morto) e funziona",
              info["motore"] == "kokoro" and secondo != primo and not _vivo(primo), str(righe()))
        vivi = 0
        massimo = 0
        for _, ev, _pid, _ in sorted(righe()):
            if ev == "AVVIO":
                vivi += 1
            elif ev in ("USCITA", "MORTE"):
                vivi -= 1
            massimo = max(massimo, vivi)
        prova("in nessun momento due lavoratori insieme (dal registro: avvii meno uscite)",
              massimo == 1, "%s %s" % (massimo, righe()))

        # ------------------------------------------------------------ ripiego su Pocket
        porta_pocket = _porta_libera()
        reg_pocket = T / "pocket.log"
        pocket = subprocess.Popen(
            [sys.executable, str(QUI / "_pocket_finto.py"), str(porta_pocket), str(reg_pocket)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _attendi(lambda: _risponde("http://127.0.0.1:%d/health" % porta_pocket), 6)
        azzera(pocket_url="http://127.0.0.1:%d" % porta_pocket, kokoro_riprova_secondi=5)
        info = sintesi("Frase con Kokoro e Pocket.")
        prova("ORDINE: con Kokoro e Pocket accesi parla Kokoro, e Pocket non riceve niente",
              info["motore"] == "kokoro" and not reg_pocket.exists(), str((info, reg_pocket.exists())))
        prova("...e voce_neurale() dice kokoro", voice.voce_neurale("it") == "kokoro")
        controllo(muori_alla_richiesta=1)  # gia' 1 richiesta fatta: la prossima uccide
        info = sintesi("Ora Kokoro cade.")
        prova("RIPIEGO: quando Kokoro cade la frase la fa Pocket, e `ripiego` dice perche'",
              info["motore"] == "pocket" and "Kokoro" in info.get("ripiego", "")
              and reg_pocket.exists() and "Kokoro cade" in reg_pocket.read_text("utf-8"), str(info))
        prova("...e per la pausa voce_neurale() dice pocket",
              voice.voce_neurale("it") == "pocket" and jarvis.informazioni_voce("it").get("neurale") == "pocket"
              and jarvis.informazioni_voce("it").get("kokoro") == "in_pausa", str(jarvis.informazioni_voce("it")))
        cfg.imposta(kokoro_attivo=False)
        info = sintesi("Kokoro spento da config.")
        prova("con `kokoro_attivo: false` Kokoro e' saltato senza disinstallarlo: parla Pocket",
              info["motore"] == "pocket" and jarvis.informazioni_voce("it").get("kokoro") == "spento",
              str((info, jarvis.informazioni_voce("it"))))
        info = voice.sintesi("Con l'auto.", "it", "auto", cache=False)
        prova("`auto` segue lo stesso ordine (qui, Kokoro spento: Pocket)", info["motore"] == "pocket", str(info))
        azzera(pocket_url="http://127.0.0.1:%d" % porta_pocket)
        info = voice.sintesi("Con l'auto e Kokoro.", "it", "auto", cache=False)
        prova("...e con Kokoro acceso `auto` sceglie Kokoro", info["motore"] == "kokoro", str(info))
        info = voice.sintesi("Solo Kokoro.", "it", "kokoro", cache=False)
        prova("`motore=kokoro` e' solo Kokoro", info["motore"] == "kokoro", str(info))
        pocket.terminate()
        pocket.wait(timeout=5)
        pocket = None

        # ------------------------------------------------------------ non si avvia
        azzera()
        controllo(guasto_avvio="modello danneggiato")
        errore = senza(lambda: sintesi())
        prova("NON SI AVVIA: il motivo del lavoratore arriva a chi chiedeva la frase",
              isinstance(errore, voice.NessunaVoceNeurale) and "modello danneggiato" in str(errore), repr(errore))
        prova("...e Kokoro va in pausa", kokoro._lavoratore.in_pausa() and voice.voce_neurale("it") == "")
        controllo(guasto_avvio=None)
        _attendi(lambda: not kokoro._lavoratore.in_pausa(), 3)
        prova("...poi, riparato, riparte", sintesi()["motore"] == "kokoro")

        # ------------------------------------------------------------ ancora a caricare
        azzera()
        controllo(carica_s=1.5)
        cfg.imposta(attesa_voce_neurale=0.4)
        errore = senza(lambda: sintesi())
        prova("ANCORA A CARICARE: la frase ripiega dicendolo, ma non e' un guasto (nessuna pausa)",
              isinstance(errore, voice.NessunaVoceNeurale) and "ancora caricando" in str(errore)
              and not kokoro._lavoratore.in_pausa(), repr(errore))
        cfg.imposta(attesa_voce_neurale=5)
        info = sintesi()
        prova("...e a modello pronto la frase dopo va, con lo stesso lavoratore (mai un secondo)",
              info["motore"] == "kokoro" and len(eventi("AVVIO")) == 1, str(righe()))

        # ------------------------------------------------------------ non risponde entro il tetto
        azzera()
        controllo(tace_su="silenzio")
        cfg.imposta(attesa_voce_neurale=0.8)
        sintesi("Una frase normale.")
        t0 = time.monotonic()
        errore = senza(lambda: sintesi("Questa cade nel silenzio."))
        durata = time.monotonic() - t0
        prova("TETTO: se il lavoratore non risponde entro attesa_voce_neurale la frase ripiega in tempo",
              isinstance(errore, voice.NessunaVoceNeurale) and "non ha risposto entro 0.8" in str(errore)
              and 0.7 <= durata < 3.0, "%r %.2f" % (errore, durata))
        pid = eventi("AVVIO")[0][2]
        prova("...una volta sola non lo uccide (potrebbe essere solo lento)", _vivo(pid))
        _attendi(lambda: not kokoro._lavoratore.in_pausa(), 3)
        errore = senza(lambda: sintesi("Di nuovo nel silenzio."))
        prova("...due volte di fila senza una risposta in mezzo: e' piantato, lo si ferma",
              _attendi(lambda: not _vivo(pid), 5), str(righe()))
        _attendi(lambda: not kokoro._lavoratore.in_pausa(), 3)
        controllo(tace_su=None)
        info = sintesi("Dopo il silenzio.")
        prova("...e la frase dopo ne lancia uno nuovo", info["motore"] == "kokoro"
              and eventi("AVVIO")[-1][2] != pid and len(eventi("AVVIO")) == 2, str(righe()))
        controllo(rifiuta="proibita")
        errore = senza(lambda: sintesi("Frase proibita."))
        prova("una frase rifiutata dal lavoratore ripiega ma non mette in pausa tutto Kokoro",
              isinstance(errore, voice.NessunaVoceNeurale) and "rifiutata" in str(errore)
              and not kokoro._lavoratore.in_pausa() and sintesi("Frase buona.")["motore"] == "kokoro", repr(errore))
        cfg.imposta(attesa_voce_neurale=5)

        # ------------------------------------------------------------ la pausa e il pannello
        azzera()
        info = jarvis.informazioni_voce("it")
        prova("Kokoro installato e sano: il pannello riceve neurale=kokoro e nessuna nota",
              info.get("neurale") == "kokoro" and "kokoro" not in info and "nota" not in info, str(info))

        # ------------------------------------------------------------ clausole
        c = voice.clausole
        pezzi = c("Oggi hai tre task aperti su Plancia, e il piu' urgente e' la nota di migrazione, "
                  "da chiudere entro venerdi'.")
        prova("clausole: taglia alle virgole con almeno 4 parole per pezzo",
              pezzi == ["Oggi hai tre task aperti su Plancia,", "e il piu' urgente e' la nota di migrazione,",
                        "da chiudere entro venerdi'."], str(pezzi))
        prova("clausole: 'Si', poi il resto' non fa un pezzo da una parola",
              c("Si, apro subito la vista dei task.") == ["Si, apro subito la vista dei task."],
              str(c("Si, apro subito la vista dei task.")))
        prova("clausole: 3,5 e 12:30 non si tagliano, e una frase senza pause resta intera",
              c("Sono le 12:30 e il valore e' 3,5 per cento.") == ["Sono le 12:30 e il valore e' 3,5 per cento."])
        prova("clausole: la coda troppo corta torna sul pezzo prima",
              c("Ho letto tutte le note della settimana, ok.") == ["Ho letto tutte le note della settimana, ok."])
        prova("clausole: un testo vuoto o di una parola non si rompe",
              c("") == [""] and c("Fatto") == ["Fatto"])

        # ------------------------------------------------------------ spezzatura nel flusso
        risposta = ("Oggi hai tre task aperti su Plancia, e il piu' urgente e' la nota di migrazione, "
                    "da chiudere entro venerdi'. Poi c'e' la revisione del testo, che puo' aspettare.")
        ev = list(jarvis._testo_intero(risposta, "it", [0]))
        frasi = [e["dire"] for e in ev if e["t"] == "frase"]
        prova("SPEZZATURA: con Kokoro la PRIMA frase esce in clausole e la seconda intera",
              len(frasi) == 4 and frasi[0].endswith("Plancia,") and frasi[2].endswith("venerdi'.")
              and frasi[3].startswith("Poi c'e' la revisione"), str(frasi))
        prova("...e il testo che scorre resta intero (le clausole sono solo per la voce)",
              [e["d"] for e in ev if e["t"] == "testo"] == [risposta])
        ev2 = list(jarvis._testo_intero(risposta, "it"))
        prova("senza il contatore delle uscite (chi non lo passa) niente si taglia: come prima",
              len([e for e in ev2 if e["t"] == "frase"]) == 2)
        cfg.imposta(kokoro_attivo=False)
        frasi = [e["dire"] for e in jarvis._testo_intero(risposta, "it", [0]) if e["t"] == "frase"]
        prova("senza Kokoro le frasi escono intere, come prima",
              len(frasi) == 2, str(frasi))
        cfg.imposta(kokoro_attivo=None)

        # ------------------------------------------------------------ pronto scalda il lavoratore
        azzera()
        jarvis.scalda = lambda lang: None
        finto_http = _Gestore()
        voice.riproduci = lambda *a, **k: (_ for _ in ()).throw(AssertionError("non si suona"))
        prima_voce = jarvis.rotta(finto_http, "POST", "/api/jarvis/voce", {"lang": "it"}, lambda: None)
        prova("/api/jarvis/voce dice che voce c'e' e non avvia il lavoratore",
              prima_voce and finto_http.dati.get("neurale") == "kokoro" and not righe(), str(finto_http.dati))
        jarvis.rotta(finto_http, "POST", "/api/jarvis/pronto", {"lang": "it"}, lambda: None)
        prova("/api/jarvis/pronto risponde subito con neurale=kokoro e avvia il lavoratore",
              finto_http.dati.get("neurale") == "kokoro" and finto_http.dati.get("scaldato") is True
              and _attendi(lambda: len(eventi("PRONTO")) == 1, 4), str((finto_http.dati, righe())))
        primo = eventi("AVVIO")[0][2]
        jarvis.rotta(finto_http, "POST", "/api/jarvis/pronto", {"lang": "it"}, lambda: None)
        time.sleep(0.3)
        prova("...un secondo `pronto` non ne avvia un altro", len(eventi("AVVIO")) == 1 and _vivo(primo))
        # ---------------------------------------------------------- voce prova
        azzera()
        suonato = []
        voice.riproduci = lambda *a, **k: suonato.append(a)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            codice = cli.main(["voce", "prova"])
        testo = out.getvalue()
        prova("`voce prova` dice che Jarvis parlerebbe con Kokoro e perche', e esce 0",
              codice == 0 and "Jarvis parlerebbe con: Kokoro" in testo and "if_sara" in testo
              and "pronto" in testo, testo)
        prova("...elenca gli altri motori nell'ordine, con il perche' (Pocket, Voicebox non rispondono)",
              testo.index("Kokoro") < testo.index("Pocket") < testo.index("Voicebox")
              and "non risponde" in testo, testo)
        time.sleep(0.6)   # un lavoratore avviato in un thread scrive nel registro dopo qualche decimo
        prova("...senza suonare e senza avviare il lavoratore", not suonato and not righe(), str((suonato, righe())))
        cfg.imposta(kokoro_python=str(T / "non-esiste"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            codice = cli.main(["voce", "prova"])
        prova("senza Kokoro (e senza altro) `voce prova` lo dice e esce 1",
              codice == 1 and "non ha una voce neurale" in out.getvalue() and "non installato" in out.getvalue(),
              out.getvalue())
        cfg.imposta(kokoro_python=None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            codice = cli.main(["voce", "prova", "--carica"])
        pid_c = eventi("AVVIO")[-1][2] if eventi("AVVIO") else 0
        prova("`voce prova --carica` avvia il lavoratore, sintetizza in un file senza suonarlo e lo richiude",
              codice == 0 and "Kokoro ha sintetizzato" in out.getvalue() and not suonato
              and _attendi(lambda: not _vivo(pid_c), 5) and (voice.AUDIO_DIR / "prova-kokoro.wav").exists(),
              out.getvalue() + str(righe()))
        with contextlib.suppress(OSError):
            (voice.AUDIO_DIR / "prova-kokoro.wav").unlink()
        voice.riproduci = vere["riproduci"]
        jarvis.scalda = vere["scalda"]

        # ------------------------------------------------------------ da HTTP, con un server vero
        _prova_http(prova, T, config)
        azzera()

        # ------------------------------------------------------------ voce installa
        _prova_installa(prova, T, kokoro, cli, config)

        # ------------------------------------------------------------ il lavoratore vero
        _prova_lavoratore(prova)

        # ------------------------------------------------------------ pulizia dei testi
        pubblici = ["plancia/kokoro.py", "plancia/voce_kokoro.py", "plancia/voice.py",
                    "tools/prove/voce-kokoro.py", "tools/prove/_kokoro_finto.py"]
        letti = {p: (RADICE / p).read_text("utf-8") for p in pubblici}
        vietati = ["/Us" + "ers/", "/Vol" + "umes/", "olive" + "ra", "euge" + "nio", "nere" + "lli"]
        prova("nel codice pubblico di Kokoro nessun percorso della macchina ne' nome vero",
              not [(p, v) for p, t in letti.items() for v in vietati if v in t.lower()], "")
        prova("...e nessun em dash", not [p for p, t in letti.items() if chr(0x2014) in t])
        import ast
        prova("il lavoratore e la libreria si leggono con la grammatica di Python 3.9",
              all(ast.parse(letti[p], feature_version=(3, 9)) for p in
                  ("plancia/kokoro.py", "plancia/voce_kokoro.py")))
        prova("il lavoratore non importa Plancia",
              "import plancia" not in letti["plancia/voce_kokoro.py"]
              and "from plancia" not in letti["plancia/voce_kokoro.py"]
              and "from ." not in letti["plancia/voce_kokoro.py"])
    finally:
        if pocket is not None:
            pocket.terminate()
        kokoro.spegni()
        voice.riproduci = vere["riproduci"]
        jarvis.scalda = vere["scalda"]
        voice._pocket_no, voice._ultimo_no = vere["pocket_no"], vere["vb_no"]
        kokoro._lavoratore.dimentica_guasto()
        cfg.ripristina()
        shutil.rmtree(voce_dir, ignore_errors=True)
        shutil.rmtree(T, ignore_errors=True)


def _sorgente(f):
    import inspect
    return inspect.getsource(f)


def _risponde(url):
    try:
        urllib.request.urlopen(url, timeout=0.5).read()
        return True
    except Exception:  # noqa: BLE001
        return False


class _Gestore:
    """Il gestore HTTP di api.py quanto basta a `jarvis.rotta`: raccoglie la risposta."""

    def __init__(self):
        self.dati = None

    def _json(self, dati, *a, **k):
        self.dati = dati


# --------------------------------------------------------------------------
# un server vero
# --------------------------------------------------------------------------

def _prova_http(prova, T, config):
    casa = T / "casa-http"
    ctl = T / "finto-http.json"
    reg = T / "registro-http.log"
    ctl.write_text(json.dumps({"registro": str(reg)}), "utf-8")
    (casa / "voce" / "modelli").mkdir(parents=True)
    for nome in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        (casa / "voce" / "modelli" / nome).write_bytes(b"finto")
    _finti.crea_finto(casa / "voce" / "venv" / "bin", "python", _wrapper(ctl))
    claude = _finti.crea_finto(T / "bin-http", "claude-inerte",
                               "import sys\nsys.stdin.read()\n")
    porta = _porta_libera()
    (casa / "config.json").write_text(json.dumps({
        "claude_bin": claude, "pocket_url": "http://127.0.0.1:9", "voicebox_url": "http://127.0.0.1:9",
        "gh_enabled": False}), "utf-8")
    env = dict(os.environ)
    env["PLANCIA_HOME"] = str(casa)
    _finti.casa_finta(env, casa)
    env["CLAUDE_CONFIG_DIR"] = str(casa / "claude-vuota")
    env["CODEX_HOME"] = str(casa / "codex-vuota")
    env["PATH"] = _finti.path_con(T / "bin-http")
    server = subprocess.Popen(
        [sys.executable, "-m", "plancia.cli", "serve", "--port", str(porta), "--no-sync"],
        cwd=str(RADICE), env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = "http://127.0.0.1:%d" % porta
    try:
        if not _attendi(lambda: _risponde(base + "/"), 20, 0.25):
            prova("il server di prova (HTTP) di Kokoro e' partito", False,
                  (server.stdout.read() if server.poll() is not None and server.stdout else "")[:500])
            return
        token = (casa / "token").read_text("utf-8").strip()

        def chiama(percorso, corpo):
            r = urllib.request.Request(
                base + percorso, data=json.dumps(corpo).encode("utf-8"), method="POST",
                headers={"Content-Type": "application/json", "X-Plancia-Token": token})
            return json.loads(urllib.request.urlopen(r, timeout=30).read().decode("utf-8"))

        def registro():
            return reg.read_text("utf-8").splitlines() if reg.exists() else []

        prova("[HTTP] a server appena acceso il lavoratore non c'e' (avvio pigro)", registro() == [])
        d = chiama("/api/jarvis/pronto", {"lang": "it"})
        prova("[HTTP] /api/jarvis/pronto: risponde neurale=kokoro e il lavoratore parte",
              d.get("neurale") == "kokoro" and _attendi(lambda: any(" PRONTO " in r for r in registro()), 8),
              str((d, registro())))
        pid = int([r for r in registro() if " AVVIO " in r][0].split()[2])
        d = chiama("/api/voice/speak", {"testo": "Una frase dal pannello.", "lang": "it",
                                        "motore": "neurale", "velocita": 1.2})
        rich = [r for r in registro() if " RICH " in r]
        prova("[HTTP] /api/voice/speak col motore neurale: motore kokoro, file WAV, velocita' arrivata al lavoratore",
              d.get("motore") == "kokoro" and Path(d.get("file", "")).is_file() and len(rich) == 1
              and rich[0].endswith("| if_sara | 1.2 | 0.2"), str((d, rich)))
        server.send_signal(signal.SIGTERM)
        with contextlib.suppress(Exception):
            server.wait(timeout=10)
        prova("[HTTP] quando il server muore il lavoratore muore con lui (nessun orfano da 700 MB)",
              _attendi(lambda: not _vivo(pid), 8), "pid %d ancora vivo" % pid)
    finally:
        if server.poll() is None:
            server.kill()
        with contextlib.suppress(Exception):
            server.wait(timeout=5)
        if server.stdout:
            server.stdout.close()


# --------------------------------------------------------------------------
# voce installa, con pip e rete finti
# --------------------------------------------------------------------------

class _Risposta:
    def __init__(self, dati):
        self._d = io.BytesIO(dati)

    def read(self, n=-1):
        return self._d.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _prova_installa(prova, T, kokoro, cli, config):
    cfg = _Config(config)
    casa = config.DATA_DIR / "voce"
    shutil.rmtree(casa, ignore_errors=True)
    piccoli = {"kokoro-v1.0.onnx": 3000, "voices-v1.0.bin": 1500}
    ctl = T / "finto-inst.json"
    ctl.write_text("{}", "utf-8")
    try:
        cfg.imposta(kokoro_python=None, kokoro_modelli=None)
        chiamate = []
        url_chiesti = []
        testo = []
        versione = {"v": "3.12"}
        pip_ok = {"v": True}
        venv_py = kokoro.python_kokoro()

        def esegui_finto(argv, **k):
            chiamate.append(list(argv))
            a = [str(x) for x in argv]
            res = lambda rc=0, out="", err="": type("R", (), {"returncode": rc, "stdout": out, "stderr": err})()  # noqa: E731
            if a[1:2] == ["-c"] and "sys.version_info" in a[2]:
                return res(0, versione["v"] + "\n")
            if a[1:2] == ["-c"] and "import kokoro_onnx" in a[2]:
                return res(0 if (venv_py.is_file() and getattr(esegui_finto, "pip_fatto", False)) else 1)
            if a[1:3] == ["-m", "venv"]:
                _finti.crea_finto(Path(a[3]) / "bin", "python", _wrapper(ctl))
                return res(0)
            if a[1:4] == ["-m", "pip", "install"]:
                esegui_finto.pip_fatto = pip_ok["v"]
                return res(0 if pip_ok["v"] else 1)
            if "--controlla" in a:
                return res(0, json.dumps({"controllo": True, "kokoro_onnx": "0.5.0",
                                          "onnxruntime": "1.x", "python": "3.12.0"}) + "\n")
            return res(1)

        def rete(dati_per_file):
            def apri(req, timeout=None):
                url_chiesti.append(req.full_url)
                nome = req.full_url.rsplit("/", 1)[-1]
                return _Risposta(dati_per_file[nome])
            return apri

        buoni = {n: b"x" * s for n, s in piccoli.items()}

        def lancia(**k):
            testo.clear()
            chiamate.clear()
            url_chiesti.clear()
            k.setdefault("esegui", esegui_finto)
            k.setdefault("apri", rete(buoni))
            k.setdefault("chiedi", lambda *_: (_ for _ in ()).throw(AssertionError("non si chiede")))
            k.setdefault("modelli", piccoli)
            k.setdefault("cerca", lambda nome: "/finto/" + nome if nome == "python3.12" else None)
            return kokoro.installa(scrivi=lambda *a: testo.append(" ".join(str(x) for x in a)), **k)

        # il piano si dice prima, con la dimensione vera, e senza conferma non si fa niente
        domande = []
        rc = lancia(modelli=None, chiedi=lambda q: domande.append(q) or "n", interattivo=True)
        piano = "\n".join(testo)
        prova("INSTALLA: prima di fare qualunque cosa dice quanto scarica (circa 354 MB) e chiede conferma",
              "circa 354 MB" in piano and "kokoro-onnx==0.5.0" in piano and len(domande) == 1
              and "github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0" in piano, piano)
        prova("...a 'no' non fa niente: nessun venv, nessun pip, nessuna rete, esce 1",
              rc == 1 and not url_chiesti and not any("venv" in " ".join(c) or "pip" in c for c in chiamate)
              and not casa.exists(), str((rc, chiamate, url_chiesti)))
        rc = lancia(interattivo=False)
        prova("...e senza terminale e senza --si chiede --si e non fa niente",
              rc == 1 and "--si" in "\n".join(testo) and not url_chiesti and not casa.exists(), "\n".join(testo))

        # Python troppo vecchio
        versione["v"] = "3.9"
        rc = lancia(si=True, cerca=lambda nome: "/finto/" + nome if nome == "python3" else None)
        prova("un Python sotto la 3.10 non va: lo dice e non crea niente",
              rc == 1 and "3.10" in "\n".join(testo) and not casa.exists(), "\n".join(testo))
        versione["v"] = "3.12"

        # una installazione riuscita
        rc = lancia(si=True)
        venv = casa / "venv"
        modelli = casa / "modelli"
        prova("con --si: crea il venv, ci installa kokoro-onnx==0.5.0 con pip, scarica i due modelli, controlla",
              rc == 0 and any(c[1:3] == ["-m", "venv"] and c[3] == str(venv) for c in chiamate)
              and any(c[1:4] == ["-m", "pip", "install"] and c[4] == "kokoro-onnx==0.5.0" for c in chiamate)
              and any("--controlla" in c for c in chiamate) and "Fatto" in "\n".join(testo), "\n".join(testo))
        prova("...i due file dal sito ufficiale, con la dimensione esatta, e niente pezzi a meta'",
              sorted(url_chiesti) == sorted(["https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
                                             "model-files-v1.0/" + n for n in piccoli])
              and all((modelli / n).stat().st_size == s for n, s in piccoli.items())
              and not list(modelli.glob("*.part")), str((url_chiesti, list(modelli.glob("*")))))
        prova("...e adesso Kokoro e' installato per Plancia (stesso posto predefinito)",
              kokoro.installazione()[0] is True, str(kokoro.installazione()))
        # ripetuta: e' gia' tutto
        rc = lancia(si=True)
        prova("ripetuta a cose fatte: dice che c'e' gia' e non scarica ne' installa niente",
              rc == 0 and "gia' installato" in "\n".join(testo) and not url_chiesti
              and not any(c[1:4] == ["-m", "pip", "install"] for c in chiamate), "\n".join(testo))

        # download a meta'
        shutil.rmtree(casa, ignore_errors=True)
        esegui_finto.pip_fatto = False
        tronchi = {n: b"x" * (s - 7) for n, s in piccoli.items()}
        rc = lancia(si=True, apri=rete(tronchi))
        prova("un download che non ha la dimensione esatta fallisce e non lascia ne' il file ne' il .part",
              rc == 1 and "scaricati" in "\n".join(testo)
              and not list((casa / "modelli").glob("*")), "\n".join(testo))
        # un modello sbagliato gia' presente viene sostituito solo da uno giusto
        shutil.rmtree(casa, ignore_errors=True)
        (casa / "modelli").mkdir(parents=True)
        (casa / "modelli" / "voices-v1.0.bin").write_bytes(b"y" * 10)
        (casa / "modelli" / "kokoro-v1.0.onnx").write_bytes(b"x" * piccoli["kokoro-v1.0.onnx"])
        esegui_finto.pip_fatto = True
        _finti.crea_finto(casa / "venv" / "bin", "python", _wrapper(ctl))
        rc = lancia(si=True)
        prova("un file presente ma della dimensione sbagliata si riscarica; quello giusto no",
              rc == 0 and (casa / "modelli" / "voices-v1.0.bin").stat().st_size == 1500
              and [u.rsplit("/", 1)[-1] for u in url_chiesti] == ["voices-v1.0.bin"], str(url_chiesti))
        # pip che fallisce
        shutil.rmtree(casa, ignore_errors=True)
        pip_ok["v"] = False
        esegui_finto.pip_fatto = False
        rc = lancia(si=True)
        prova("se pip fallisce esce 1, toglie il venv appena creato e non scarica i modelli",
              rc == 1 and not (casa / "venv").exists() and not url_chiesti, "\n".join(testo))
        pip_ok["v"] = True
        # un Python scelto dall'utente: niente venv ne' pip, solo i modelli
        shutil.rmtree(casa, ignore_errors=True)
        esterno = _finti.crea_finto(T / "python-utente", "python", _wrapper(ctl))
        cfg.imposta(kokoro_python=esterno, kokoro_modelli=str(T / "modelli-utente"))
        rc = lancia(si=True)
        prova("con kokoro_python e kokoro_modelli in config: nessun venv ne' pip, i modelli vanno dove dice lui",
              rc == 0 and not any(c[1:3] == ["-m", "venv"] for c in chiamate)
              and not any(c[1:4] == ["-m", "pip", "install"] for c in chiamate)
              and all((T / "modelli-utente" / n).stat().st_size == s for n, s in piccoli.items())
              and not casa.exists(), "\n".join(testo))
        cfg.imposta(kokoro_python=None, kokoro_modelli=None)

        # la riga di comando
        p = cli.build_parser().parse_args(["voce", "installa", "--si", "--python", "/x/python3.12"])
        q = cli.build_parser().parse_args(["voce", "prova", "--carica", "--lang", "en"])
        registro = []
        vero = kokoro.installa
        kokoro.installa = lambda **k: registro.append(k) or 0
        try:
            rc = cli.main(["voce", "installa", "--si"])
        finally:
            kokoro.installa = vero
        prova("la riga di comando: `plancia voce installa [--si] [--python P]` e `voce prova [--carica] [--lang]`",
              p.azione == "installa" and p.si and p.python == "/x/python3.12"
              and q.azione == "prova" and q.carica and q.lang == "en"
              and rc == 0 and registro == [{"si": True, "python": None}], str((p, q, registro)))
    finally:
        cfg.ripristina()
        shutil.rmtree(casa, ignore_errors=True)


# --------------------------------------------------------------------------
# il lavoratore vero, dove ci sono numpy (i suoi pezzi puri, senza il modello)
# --------------------------------------------------------------------------

def _prova_lavoratore(prova):
    spec = importlib.util.spec_from_file_location("voce_kokoro_prova", RADICE / "plancia" / "voce_kokoro.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    prova("il lavoratore sceglie i fonemi dalla prima lettera della voce (it, es, en-us, en-gb)",
          [w.fonemi_per(v) for v in ("if_sara", "im_nicola", "ef_dora", "af_heart", "bm_george")]
          == ["it", "it", "es", "en-us", "en-gb"])
    prova("...e `lingua` nella richiesta vince sulla voce", w.fonemi_per("if_sara", "en-us") == "en-us")
    try:
        import numpy as np
    except ImportError:
        np = None
    T = Path(tempfile.mkdtemp(prefix="plancia-prova-lavoratore-"))
    try:
        if np is None:
            prova("il WAV del lavoratore: 24 kHz mono, picchi tenuti sotto il fondo scala, silenzio in fondo",
                  True, "saltato: manca numpy in questo Python")
            prova("il lavoratore rifiuta una voce sconosciuta, un testo vuoto e un file di uscita mancante",
                  True, "saltato: manca numpy in questo Python")
            return
        audio = np.concatenate([np.full(2400, 1.01, dtype=np.float32), np.zeros(2400, dtype=np.float32)])
        durata = w.scrivi_wav(str(T / "a.wav"), audio, 24000, 0.5)
        with wave.open(str(T / "a.wav"), "rb") as f:
            campioni = np.frombuffer(f.readframes(f.getnframes()), dtype="<i2")
            hz, canali, larg, n = f.getframerate(), f.getnchannels(), f.getsampwidth(), f.getnframes()
        prova("il WAV del lavoratore: 24 kHz mono, picchi tenuti sotto il fondo scala, silenzio in fondo",
              (hz, canali, larg) == (24000, 1, 2) and n == 4800 + 12000 and abs(durata - 0.7) < 1e-6
              and int(np.max(np.abs(campioni))) <= int(0.981 * 32767) and not campioni[-12000:].any()
              and not (T / "a.wav.part").exists(), str((hz, canali, larg, n, durata)))

        class Stub:
            voices = {"if_sara": 0}

            def create(self, testo, voice, speed, lang):
                return np.zeros(0, dtype=np.float32), 24000

        errori = []
        for corpo in ({"testo": "Ciao.", "voce": "xx_nessuna", "uscita": str(T / "b.wav")},
                      {"testo": "   ", "uscita": str(T / "b.wav")},
                      {"testo": "Ciao.", "voce": "if_sara"},
                      {"testo": "Ciao.", "voce": "if_sara", "uscita": str(T / "b.wav")}):
            try:
                w.sintetizza(Stub(), corpo)
                errori.append(None)
            except ValueError as exc:
                errori.append(str(exc))
        prova("il lavoratore rifiuta una voce sconosciuta, un testo vuoto e un file di uscita mancante",
              "voce sconosciuta" in (errori[0] or "") and "vuoto" in (errori[1] or "")
              and "uscita" in (errori[2] or "") and "nessun audio" in (errori[3] or ""), str(errori))
    finally:
        shutil.rmtree(T, ignore_errors=True)
