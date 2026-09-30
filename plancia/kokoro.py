"""Kokoro, il motore neurale di Jarvis: un lavoratore tenuto caldo, e l'installazione.

Kokoro (82 milioni di parametri, `kokoro-onnx` su CPU) e' il primo motore neurale di
Jarvis. Su un Mac M4 sintetizza una frase in circa un quinto della sua durata e la prima
clausola in meno di un secondo, senza toccare la GPU. Plancia resta in libreria standard:
il modello gira in un PROCESSO A PARTE, `voce_kokoro.py`, lanciato con un Python esterno
che ha `kokoro_onnx` (quello del venv che crea `plancia voce installa`, o quello scelto con
`kokoro_python` in config.json).

Il lavoratore:

- parte su richiesta (quando Jarvis si prepara, o alla prima frase) e resta in memoria:
  pesa da 450 a 700 MB a riposo (misurato su un M4) e per un momento fino a circa 1 GB su
  una frase lunga, e questa macchina ne ha poca;
- si chiude da solo dopo cinque minuti senza richieste (`kokoro_inattivo_secondi`), alla
  chiusura del server, e quando Plancia muore (il suo stdin si chiude e lui esce);
- e' UNO solo: prima di lanciarne un altro si controlla che il vecchio sia finito;
- se muore, non si avvia o non risponde entro il tetto, chi lo chiamava riceve un errore
  con il motivo e ripiega sul motore dopo; per 30 secondi non lo si richiama, come per
  Pocket e Voicebox.

Configurazione (config.json), tutte facoltative:

    kokoro_python            il Python con kokoro_onnx (predefinito: <PLANCIA_HOME>/voce/venv)
    kokoro_modelli           la cartella con i due file del modello (<PLANCIA_HOME>/voce/modelli)
    voce_kokoro              {"it": "if_sara", "en": "af_heart", "es": "ef_dora"}: la voce per lingua
    velocita_kokoro          1.0: la velocita' se chi chiama non ne dice una
    kokoro_thread            4: i thread di onnxruntime
    kokoro_inattivo_secondi  300
    kokoro_attivo            false lo spegne senza disinstallarlo
"""

import atexit
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from . import config, piattaforma

VERSIONE = "0.5.0"
URL_MODELLI = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
#: I due file del modello con la dimensione esatta in byte: e' il controllo che un
#: download non e' rimasto a meta'.
MODELLI = {"kokoro-v1.0.onnx": 325532387, "voices-v1.0.bin": 28214398}

VOCI_PREDEFINITE = {"it": "if_sara", "en": "af_heart", "es": "ef_dora"}

INATTIVO = 300.0
#: Se il modello non e' pronto dopo tanto, il lavoratore e' piantato e si ferma.
CARICAMENTO_MASSIMO = 120.0
#: Dopo un guasto non si riprova per questi secondi (come `voice.RIPROVA_DOPO`).
RIPROVA_DOPO = 30.0
#: Silenzio aggiunto in fondo a un pezzo tagliato a una virgola, e a una frase intera.
#: Kokoro toglie il silenzio ai due capi di quello che sintetizza: senza, due file uno
#: dopo l'altro suonano attaccati (misurato su un M4 in un altro progetto: ~90 ms dove una
#: frase sola ha 190-320 ms).
PAUSA_CLAUSOLA = 0.18
PAUSA_FRASE = 0.20
THREAD = 4
SCRIPT = Path(__file__).resolve().with_name("voce_kokoro.py")

#: Per l'installazione: il venv si crea con un Python in questo intervallo (kokoro-onnx
#: 0.5.0 dichiara >=3.10,<3.14).
PYTHON_MIN = (3, 10)
PYTHON_MAX = (3, 14)


class ErroreKokoro(RuntimeError):
    """Base: Kokoro non ha prodotto la frase. Il messaggio dice perche', in italiano,
    ed e' quello che finisce nel piede del pannello."""


class KokoroNonDisponibile(ErroreKokoro):
    """Non installato, spento da config, o in pausa dopo un guasto."""


class KokoroNonRisponde(ErroreKokoro):
    """Il lavoratore c'era (o doveva partire) e non ha dato la frase."""


# --------------------------------------------------------------------------
# configurazione
# --------------------------------------------------------------------------

def _cfg() -> dict:
    return config.load_config()


def attivo() -> bool:
    return _cfg().get("kokoro_attivo", True) is not False


def cartella_voce() -> Path:
    return config.DATA_DIR / "voce"


def _python_del_venv(venv) -> Path:
    venv = Path(venv)
    return venv / "Scripts" / "python.exe" if os.name == "nt" else venv / "bin" / "python"


def python_esterno() -> bool:
    """Il Python di Kokoro lo ha scelto l'utente (`kokoro_python`): allora Plancia non
    ne crea uno."""
    return bool(_cfg().get("kokoro_python"))


def python_kokoro() -> Path:
    scelto = _cfg().get("kokoro_python")
    if scelto:
        return Path(str(scelto)).expanduser()
    return _python_del_venv(cartella_voce() / "venv")


def cartella_modelli() -> Path:
    scelta = _cfg().get("kokoro_modelli")
    if scelta:
        return Path(str(scelta)).expanduser()
    return cartella_voce() / "modelli"


def voci() -> dict:
    """La voce per lingua: quelle predefinite, con sopra `voce_kokoro` di config.json."""
    fuori = dict(VOCI_PREDEFINITE)
    scelte = _cfg().get("voce_kokoro")
    if isinstance(scelte, dict):
        for lingua, nome in scelte.items():
            if isinstance(lingua, str) and isinstance(nome, str) and nome.strip():
                fuori[lingua.lower()[:2]] = nome.strip()
    return fuori


def voce_per(lang) -> str:
    """Il nome della voce Kokoro per la lingua, o "" se per quella lingua non ce n'e'."""
    return voci().get((lang or "it").lower()[:2], "")


def velocita_normale(valore=None) -> float:
    """La velocita' da chiedere: quella di chi chiama, altrimenti `velocita_kokoro`,
    altrimenti 1.0. Fra 0.5 e 2.0 (i limiti di Kokoro), a passi di 0.05: cosi' i file in
    cache non si moltiplicano per un decimale in piu'."""
    if valore is None:
        valore = _cfg().get("velocita_kokoro", 1.0)
    try:
        v = float(valore)
    except (TypeError, ValueError):
        v = 1.0
    return round(min(2.0, max(0.5, v)) * 20) / 20


def _secondi(chiave, predefinito) -> float:
    try:
        return max(0.05, float(_cfg().get(chiave, predefinito)))
    except (TypeError, ValueError):
        return predefinito


def installazione():
    """(True, "") se ci sono il Python e i due file del modello; altrimenti
    (False, perche'). Solo controlli sul disco: non avvia niente."""
    py = python_kokoro()
    if not py.is_file():
        return False, ("manca il Python di Kokoro: `plancia voce installa` lo crea"
                       if not python_esterno()
                       else "kokoro_python non punta a un file: %s" % py)
    if not os.access(str(py), os.X_OK):
        return False, "il Python di Kokoro non e' eseguibile: %s" % py
    cartella = cartella_modelli()
    for nome in MODELLI:
        f = cartella / nome
        if not f.is_file() or f.stat().st_size == 0:
            return False, "manca il modello %s in %s: `plancia voce installa` lo scarica" % (nome, cartella)
    return True, ""


def disponibile(lang=None) -> bool:
    """Kokoro puo' parlare adesso: acceso, installato, con una voce per la lingua e non
    in pausa dopo un guasto. Solo lettura, non avvia il lavoratore."""
    if not attivo():
        return False
    if not installazione()[0]:
        return False
    if lang is not None and not voce_per(lang):
        return False
    return not _lavoratore.in_pausa()


def codice_no(lang=None) -> str:
    """Il perche' Kokoro non parla adesso, in una parola per chi lo traduce (il pannello
    Mac): "spento", "non_installato", "senza_voce", "in_pausa", oppure "" se parla."""
    if not attivo():
        return "spento"
    if not installazione()[0]:
        return "non_installato"
    if lang is not None and not voce_per(lang):
        return "senza_voce"
    return "in_pausa" if _lavoratore.in_pausa() else ""


def perche_no(lang=None) -> str:
    """Una riga che spiega perche' Kokoro non parla adesso, o "" se parla."""
    if not attivo():
        return "Kokoro e' spento (kokoro_attivo: false)"
    ok, motivo = installazione()
    if not ok:
        return "Kokoro non e' installato: %s" % motivo
    if lang is not None and not voce_per(lang):
        return "Kokoro non ha una voce per la lingua %s (voce_kokoro)" % lang
    pausa = _lavoratore.perche_in_pausa()
    if pausa:
        return "Kokoro e' in pausa: %s" % pausa
    return ""


def impronta(lang, velocita=None) -> str:
    """Quello che cambia il suono di una frase con Kokoro (la voce e la velocita'), per
    la chiave della cache dei file audio. Vuoto se Kokoro non e' in gioco: le chiavi di
    chi non lo ha restano quelle di prima."""
    if not attivo() or not installazione()[0]:
        return ""
    voce = voce_per(lang)
    if not voce:
        return ""
    return "kokoro:%s:%.2f" % (voce, velocita_normale(velocita))


def pausa_dopo(testo) -> float:
    """Il silenzio da mettere in fondo a questo pezzo di testo."""
    fine = (testo or "").rstrip()[-1:]
    if fine in (",", ";", ":"):
        return PAUSA_CLAUSOLA
    if fine in (".", "!", "?", "…"):
        return PAUSA_FRASE
    return 0.0


# --------------------------------------------------------------------------
# il lavoratore
# --------------------------------------------------------------------------

class _Processo:
    """Un lavoratore lanciato: tutto quello che lo riguarda sta qui, cosi' le righe in
    ritardo di uno morto non toccano quello nuovo."""

    def __init__(self, p):
        self.p = p
        self.pronto = threading.Event()   # scatta anche se cade prima di essere pronto
        self.morto = threading.Event()
        self.info = {}
        self.perche = ""
        self.fallito = False              # ha detto "pronto: false"
        self.attese = {}                  # id -> [Event, risposta]
        self.chiuso_da_noi = False
        self.avviato = time.monotonic()


class Lavoratore:
    def __init__(self):
        self._lucchetto = threading.RLock()   # avvio e chiusura: mai due insieme
        self._scrittura = threading.Lock()    # una riga alla volta sullo stdin
        self._corrente = None
        self._n = 0
        self._ultimo_uso = 0.0
        self._ultimo_no = None
        self._perche_no = ""
        self._strike = 0

    # ---- stato

    def _vivo(self) -> bool:
        pr = self._corrente
        return pr is not None and pr.p.poll() is None and not pr.morto.is_set()

    def in_pausa(self) -> bool:
        return (self._ultimo_no is not None
                and time.monotonic() - self._ultimo_no < _secondi("kokoro_riprova_secondi", RIPROVA_DOPO))

    def perche_in_pausa(self) -> str:
        return self._perche_no if self.in_pausa() else ""

    def dimentica_guasto(self) -> None:
        self._ultimo_no = None
        self._perche_no = ""
        self._strike = 0

    def stato(self) -> dict:
        pr = self._corrente
        vivo = self._vivo()
        return {"vivo": vivo, "pronto": bool(vivo and pr.pronto.is_set() and pr.info),
                "pid": pr.p.pid if vivo else None,
                "caricato_ms": (pr.info or {}).get("ms") if vivo else None,
                "picco_mb": (pr.info or {}).get("picco_mb") if vivo else None,
                "in_pausa": self.in_pausa(), "ultimo_guasto": self._perche_no}

    def _guasto(self, perche) -> None:
        self._ultimo_no = time.monotonic()
        self._perche_no = perche

    # ---- avvio

    def assicura(self) -> "_Processo":
        """Il lavoratore vivo, lanciandolo se non c'e'. Torna subito: non aspetta il
        modello."""
        with self._lucchetto:
            if self._vivo():
                self._ultimo_uso = time.monotonic()
                return self._corrente
            if not attivo():
                raise KokoroNonDisponibile(perche_no())
            ok, motivo = installazione()
            if not ok:
                raise KokoroNonDisponibile(motivo)
            if self.in_pausa():
                raise KokoroNonDisponibile("in pausa dopo un guasto: %s" % self._perche_no)
            return self._lancia()

    def _apri_log(self):
        try:
            cartella = cartella_voce()
            cartella.mkdir(parents=True, exist_ok=True)
            percorso = cartella / "kokoro.log"
            modo = "wb" if percorso.exists() and percorso.stat().st_size > 1_000_000 else "ab"
            return open(str(percorso), modo)
        except OSError:
            return None

    def _lancia(self) -> "_Processo":
        # mai due lavoratori insieme: se il vecchio e' ancora in piedi (caduto a meta') si ferma
        vecchio = self._corrente
        if vecchio is not None and vecchio.p.poll() is None:
            try:
                vecchio.p.kill()
                vecchio.p.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        argv = [str(python_kokoro()), str(SCRIPT), "--modelli", str(cartella_modelli()),
                "--thread", str(int(_secondi("kokoro_thread", THREAD)))]
        log = self._apri_log()
        try:
            p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=log if log is not None else subprocess.DEVNULL,
                                 text=True, bufsize=1, **piattaforma.opzioni_utf8(),
                                 **piattaforma.opzioni_figlio())
        except OSError as exc:
            self._guasto("non parte: %s" % exc)
            raise KokoroNonRisponde("il lavoratore non parte: %s" % exc)
        finally:
            if log is not None:
                log.close()
        pr = _Processo(p)
        self._corrente = pr
        self._ultimo_uso = time.monotonic()
        threading.Thread(target=self._leggi, args=(pr,), daemon=True).start()
        threading.Thread(target=self._guardia, args=(pr,), daemon=True).start()
        return pr

    def _leggi(self, pr) -> None:
        try:
            for riga in pr.p.stdout:
                try:
                    msg = json.loads(riga)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                if "pronto" in msg:
                    if msg.get("pronto"):
                        pr.info = msg
                    else:
                        pr.perche = "non si e' avviato: %s" % (msg.get("errore") or "senza dire perche'")
                        pr.fallito = True
                        self._guasto(pr.perche)
                    pr.pronto.set()
                    continue
                attesa = pr.attese.get(msg.get("id"))
                if attesa is not None:
                    attesa[1] = msg
                    attesa[0].set()
        except (OSError, ValueError):
            pass
        finally:
            self._finito(pr)

    def _finito(self, pr) -> None:
        """Il canale del lavoratore e' chiuso: se non l'abbiamo chiuso noi e' un guasto."""
        try:
            pr.p.wait(timeout=3)
        except Exception:  # noqa: BLE001
            pass
        if not pr.chiuso_da_noi and not pr.morto.is_set():
            codice = pr.p.poll()
            pr.perche = pr.perche or "e' terminato da solo (codice %s)" % codice
            self._guasto(pr.perche)
        pr.morto.set()
        pr.pronto.set()
        for attesa in list(pr.attese.values()):
            attesa[0].set()
        try:
            pr.p.stdin.close()
        except Exception:  # noqa: BLE001
            pass

    # ---- richieste

    def richiedi(self, corpo, attesa) -> dict:
        """Una frase al lavoratore. `attesa` e' il tetto in secondi, caricamento
        compreso. Solleva `ErroreKokoro` con il motivo."""
        fine = time.monotonic() + attesa
        pr = self.assicura()
        if not pr.pronto.wait(max(0.0, fine - time.monotonic())):
            # ancora a caricare: non e' un guasto, la frase ripiega e la prossima riprova
            raise KokoroNonRisponde("sta ancora caricando il modello")
        if pr.morto.is_set() or pr.fallito:
            raise KokoroNonRisponde("il lavoratore e' caduto: %s" % (pr.perche or "senza dire perche'"))
        with self._scrittura:
            self._n += 1
            ident = self._n
        slot = [threading.Event(), None]
        pr.attese[ident] = slot
        self._ultimo_uso = time.monotonic()
        try:
            with self._scrittura:
                pr.p.stdin.write(json.dumps(dict(corpo, id=ident)) + "\n")
                pr.p.stdin.flush()
        except (OSError, ValueError):
            pr.attese.pop(ident, None)
            self._uccidi(pr, pr.perche or "non accetta piu' richieste")
            raise KokoroNonRisponde("il lavoratore e' caduto: %s" % pr.perche)
        if not slot[0].wait(max(0.0, fine - time.monotonic())):
            pr.attese.pop(ident, None)
            self._strike += 1
            perche = "non ha risposto entro %g secondi" % attesa
            if self._strike >= 2:
                # due volte di fila senza una risposta in mezzo: e' piantato, se ne lancia
                # uno nuovo alla prossima occasione
                self._uccidi(pr, "non risponde (due richieste di fila senza risposta)")
            else:
                self._guasto(perche)
            raise KokoroNonRisponde(perche)
        pr.attese.pop(ident, None)
        self._ultimo_uso = time.monotonic()
        msg = slot[1]
        if msg is None:
            raise KokoroNonRisponde("il lavoratore e' caduto: %s" % (pr.perche or "senza dire perche'"))
        self._strike = 0
        if not msg.get("ok"):
            # una frase che non riesce non mette in pausa il motore: le altre possono andare
            raise KokoroNonRisponde("ha rifiutato la frase: %s" % (msg.get("errore") or "?"))
        return msg

    # ---- chiusura

    def _uccidi(self, pr, perche) -> None:
        with self._lucchetto:
            pr.perche = perche
            self._guasto(perche)
            self._strike = 0
            try:
                pr.p.kill()
            except OSError:
                pass
            try:
                pr.p.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
            if self._corrente is pr:
                self._corrente = None

    def _chiudi_pulito(self, pr) -> None:
        """Chiede al lavoratore di uscire; se non lo fa entro qualche secondo lo uccide.
        Da chiamare col lucchetto in mano: il prossimo si lancia solo a chiusura finita."""
        pr.chiuso_da_noi = True
        try:
            with self._scrittura:
                pr.p.stdin.write(json.dumps({"id": 0, "cmd": "esci"}) + "\n")
                pr.p.stdin.flush()
                pr.p.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            pr.p.wait(timeout=3)
        except Exception:  # noqa: BLE001
            try:
                pr.p.kill()
                pr.p.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        if self._corrente is pr:
            self._corrente = None

    def spegni(self) -> None:
        with self._lucchetto:
            pr = self._corrente
            if pr is not None:
                self._chiudi_pulito(pr)

    def _guardia(self, pr) -> None:
        """Chiude il lavoratore dopo `kokoro_inattivo_secondi` senza richieste, e lo
        ferma se non finisce di caricare."""
        while not pr.morto.is_set():
            inattivo = _secondi("kokoro_inattivo_secondi", INATTIVO)
            with self._lucchetto:
                if self._corrente is not pr:
                    return
                ora = time.monotonic()
                if not pr.pronto.is_set():
                    if ora - pr.avviato > _secondi("kokoro_caricamento_secondi", CARICAMENTO_MASSIMO):
                        self._uccidi(pr, "non ha finito di caricare il modello in tempo")
                        return
                    resto = 1.0
                elif pr.attese:
                    resto = 1.0
                else:
                    resto = inattivo - (ora - self._ultimo_uso)
                    if resto <= 0:
                        self._chiudi_pulito(pr)
                        return
            pr.morto.wait(min(max(resto, 0.05), 5.0))


_lavoratore = Lavoratore()
atexit.register(lambda: _lavoratore.spegni())


def spegni() -> None:
    """Chiude il lavoratore se c'e'. Alla chiusura del server e all'uscita del processo."""
    _lavoratore.spegni()


def scalda() -> bool:
    """Avvia il lavoratore senza aspettarlo (quando Jarvis si prepara). Vero se ci prova."""
    if not disponibile():
        return False

    def _avvia():
        try:
            _lavoratore.assicura()
        except ErroreKokoro:
            pass
    threading.Thread(target=_avvia, daemon=True).start()
    return True


def stato() -> dict:
    ok, motivo = installazione()
    return {"attivo": attivo(), "installato": ok, "motivo": motivo,
            "lavoratore": _lavoratore.stato()}


def sintetizza(testo, lang, out, velocita=None, attesa=9.0) -> dict:
    """La frase in un WAV (24 kHz mono). Torna `{"file", "voce", "ms", "durata", "hz"}`,
    o solleva `ErroreKokoro` con il motivo."""
    voce = voce_per(lang)
    if not voce:
        raise KokoroNonDisponibile("Kokoro non ha una voce per la lingua %s (voce_kokoro)" % lang)
    corpo = {"testo": testo, "voce": voce, "velocita": velocita_normale(velocita),
             "pausa": pausa_dopo(testo), "uscita": str(out)}
    msg = _lavoratore.richiedi(corpo, attesa)
    if not os.path.isfile(str(out)):
        raise KokoroNonRisponde("ha detto di aver scritto il file, ma non c'e'")
    return {"file": str(out), "voce": voce, "ms": msg.get("ms"), "durata": msg.get("durata"),
            "hz": msg.get("hz")}


# --------------------------------------------------------------------------
# installazione: `plancia voce installa`
# --------------------------------------------------------------------------

def _mb(byte) -> str:
    return "%d MB" % round(byte / 1_000_000)


def _versione_python(esegui, exe):
    """(maggiore, minore) del Python `exe`, o None se non risponde."""
    try:
        r = esegui([str(exe), "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
                   capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return None
        a, b = r.stdout.strip().split(".")[:2]
        return int(a), int(b)
    except Exception:  # noqa: BLE001
        return None


def cerca_python(esegui=subprocess.run, cerca=shutil.which):
    """Un Python fra 3.10 e 3.13 per creare il venv. (percorso, (maggiore, minore)) o
    (None, motivo)."""
    candidati = []
    for nome in ("python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"):
        trovato = cerca(nome)
        if trovato and trovato not in candidati:
            candidati.append(trovato)
    # i posti dove Homebrew mette Python: un'app avviata dal Finder non li ha nel PATH
    for cartella in ("/opt/homebrew/bin", "/usr/local/bin"):
        for minore in range(PYTHON_MAX[1] - 1, PYTHON_MIN[1] - 1, -1):
            percorso = "%s/python%d.%d" % (cartella, PYTHON_MIN[0], minore)
            if os.path.isfile(percorso) and percorso not in candidati:
                candidati.append(percorso)
    if sys.executable and sys.executable not in candidati:
        candidati.append(sys.executable)
    viste = []
    for exe in candidati:
        v = _versione_python(esegui, exe)
        if v is None:
            continue
        viste.append("%s %d.%d" % (exe, v[0], v[1]))
        if PYTHON_MIN <= v < PYTHON_MAX:
            return exe, v
    quale = ("; trovati: " + ", ".join(viste)) if viste else ""
    return None, ("serve un Python fra %d.%d e %d.%d per kokoro-onnx %s%s. Installane uno "
                  "(su macOS: `brew install python@3.12`) o indicalo con --python"
                  % (PYTHON_MIN + (PYTHON_MAX[0], PYTHON_MAX[1] - 1) + (VERSIONE, quale)))


def scarica(url, destinazione, atteso, apri=urllib.request.urlopen, scrivi=print) -> None:
    """Scarica `url` in `destinazione` e ci mette il nome vero solo se la dimensione e'
    ESATTAMENTE `atteso`. Altrimenti cancella il pezzo e solleva OSError."""
    destinazione = Path(destinazione)
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    parziale = destinazione.with_name(destinazione.name + ".part")
    letti = 0
    ultimo = -1
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "plancia"})
        with apri(req, timeout=60) as risposta, open(str(parziale), "wb") as f:
            while True:
                blocco = risposta.read(1 << 20)
                if not blocco:
                    break
                f.write(blocco)
                letti += len(blocco)
                decimo = int(letti * 10 / max(1, atteso))
                if decimo != ultimo:
                    ultimo = decimo
                    scrivi("  %s: %d%%" % (destinazione.name, min(100, decimo * 10)))
        if letti != atteso:
            raise OSError("%s: scaricati %d byte, ne servono %d" % (destinazione.name, letti, atteso))
        os.replace(str(parziale), str(destinazione))
    except BaseException:
        try:
            parziale.unlink()
        except OSError:
            pass
        raise


def _modelli_mancanti(cartella, modelli):
    mancano = {}
    for nome, byte in modelli.items():
        f = Path(cartella) / nome
        if not (f.is_file() and f.stat().st_size == byte):
            mancano[nome] = byte
    return mancano


def _libero(percorso) -> int:
    """I byte liberi sul disco che ospitera' `percorso` (il primo antenato che esiste)."""
    p = Path(percorso)
    while not p.exists() and p.parent != p:
        p = p.parent
    return shutil.disk_usage(str(p)).free


def installa(si=False, python=None, modelli=None, esegui=subprocess.run,
             apri=urllib.request.urlopen, chiedi=input, scrivi=print,
             interattivo=None, cerca=shutil.which) -> int:
    """`plancia voce installa`: il venv con kokoro-onnx e i due file del modello.
    Dice prima cosa scarica e chiede conferma (salvo `si`). Torna il codice di uscita.

    Con `kokoro_python` in config.json il Python e' dell'utente: non se ne crea uno e non
    ci si installa niente, si scaricano solo i modelli che mancano."""
    modelli = dict(MODELLI if modelli is None else modelli)
    if interattivo is None:
        interattivo = sys.stdin is not None and sys.stdin.isatty()
    venv = cartella_voce() / "venv"
    py_kokoro = python_kokoro()
    cartella = cartella_modelli()
    esterno = python_esterno()
    if esterno and not py_kokoro.is_file():
        scrivi("kokoro_python non punta a un file (%s): correggilo o toglilo da config.json." % py_kokoro)
        return 1

    mancano = _modelli_mancanti(cartella, modelli)
    ha_kokoro = py_kokoro.is_file() and _ha_kokoro(esegui, py_kokoro)
    crea_venv = not esterno and not py_kokoro.is_file()
    pip_da_fare = not esterno and not ha_kokoro
    if not mancano and not pip_da_fare:
        scrivi("Kokoro e' gia' installato (modelli in %s)." % cartella)
        return 0

    creatore = None
    if crea_venv:
        if python:
            v = _versione_python(esegui, python)
            if v is None or not (PYTHON_MIN <= v < PYTHON_MAX):
                scrivi("Il Python indicato (%s) non va: serve fra %d.%d e %d.%d."
                       % (python, PYTHON_MIN[0], PYTHON_MIN[1], PYTHON_MAX[0], PYTHON_MAX[1] - 1))
                return 1
            creatore = python
        else:
            creatore, extra = cerca_python(esegui, cerca)
            if creatore is None:
                scrivi(extra)
                return 1

    totale = sum(mancano.values())
    scrivi("Kokoro e' la voce neurale di Jarvis e gira in locale. Ecco cosa faccio:")
    if crea_venv:
        scrivi("  - creo un ambiente Python in %s (con %s)" % (venv, creatore))
    if pip_da_fare:
        scrivi("  - installo kokoro-onnx==%s con pip (onnxruntime e altri pacchetti: alcune "
               "decine di MB dal sito dei pacchetti Python)" % VERSIONE)
    if mancano:
        scrivi("  - scarico %d file del modello, circa %s in tutto, da %s" %
               (len(mancano), _mb(totale), URL_MODELLI))
        for nome, byte in mancano.items():
            scrivi("      %s (%s)" % (nome, _mb(byte)))
        scrivi("    in %s" % cartella)
    else:
        scrivi("  - i file del modello ci sono gia' (%s)" % cartella)
    scrivi("Quando Jarvis parla, Kokoro occupa da 450 a 700 MB di memoria (fino a circa 1 GB "
           "per un momento su una frase lunga) e si chiude da solo dopo 5 minuti di silenzio.")

    servono = totale + (500_000_000 if pip_da_fare else 0) + 50_000_000
    try:
        libero = _libero(cartella if mancano else venv)
    except OSError:
        libero = None
    if libero is not None and libero < servono:
        scrivi("Spazio libero insufficiente: %s, ne servono almeno %s." % (_mb(libero), _mb(servono)))
        return 1

    if not si:
        if not interattivo:
            scrivi("Serve la tua conferma: rilancia con --si per procedere senza domande.")
            return 1
        risposta = chiedi("Procedo? [s/N] ").strip().lower()
        if risposta not in ("s", "si", "s\u00ec", "y", "yes"):
            scrivi("Non ho installato niente.")
            return 1

    if crea_venv:
        scrivi("Creo l'ambiente Python...")
        r = esegui([str(creatore), "-m", "venv", str(venv)])
        if r.returncode != 0:
            scrivi("La creazione dell'ambiente Python e' fallita (codice %s)." % r.returncode)
            shutil.rmtree(str(venv), ignore_errors=True)
            return 1
    if pip_da_fare:
        scrivi("Installo kokoro-onnx==%s..." % VERSIONE)
        r = esegui([str(py_kokoro), "-m", "pip", "install", "kokoro-onnx==%s" % VERSIONE])
        if r.returncode != 0:
            scrivi("pip non e' riuscito a installare kokoro-onnx (codice %s)." % r.returncode)
            if crea_venv:
                shutil.rmtree(str(venv), ignore_errors=True)
            return 1

    for nome, byte in mancano.items():
        scrivi("Scarico %s..." % nome)
        try:
            scarica("%s/%s" % (URL_MODELLI, nome), Path(cartella) / nome, byte, apri, scrivi)
        except (OSError, ValueError) as exc:
            scrivi("Download fallito: %s. Non tengo il file a meta': riprova." % exc)
            return 1

    try:
        r = esegui([str(py_kokoro), str(SCRIPT), "--controlla"], capture_output=True, text=True,
                   timeout=120)
        riga = [x for x in (r.stdout or "").splitlines() if x.strip().startswith("{")]
        esito = json.loads(riga[-1]) if riga else {"errore": (r.stderr or "nessuna risposta")[-200:]}
    except Exception as exc:  # noqa: BLE001
        esito = {"controllo": False, "errore": str(exc)}
    if not esito.get("controllo"):
        scrivi("L'installazione non supera il controllo: %s" % (esito.get("errore") or "?"))
        return 1
    scrivi("Fatto: kokoro-onnx %s, onnxruntime %s, Python %s." %
           (esito.get("kokoro_onnx"), esito.get("onnxruntime"), esito.get("python")))
    scrivi("Jarvis lo usera' dalla prossima frase. `plancia voce prova` dice quale motore sceglie.")
    return 0


def _ha_kokoro(esegui, python) -> bool:
    """Il Python `python` ha gia' kokoro_onnx?"""
    try:
        r = esegui([str(python), "-c", "import kokoro_onnx"], capture_output=True, timeout=60)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False
