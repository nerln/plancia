"""Voce: sintesi, riproduzione e ascolto.

Due motori. Voicebox se il suo backend locale risponde, perché è la voce clonata
e regge bene le lingue. Altrimenti le voci di sistema, che non chiedono niente e
partono in un decimo di secondo: `say` su macOS, il sintetizzatore di Windows
(System.Speech, via PowerShell), `espeak-ng` o `espeak` su Linux. I comandi li
costruisce `piattaforma`. Dove non c'è niente di tutto questo la voce lo dice
(`NessunMotoreVoce`) e il resto continua: da CLI e da MCP (`parla`) il testo
arriva e la risposta dice che la voce manca; dalla dashboard (`api.py`, che
cattura `NessunMotoreVoce`) il riepilogo, "Chiedi" e Jarvis rispondono col testo,
con `voce: null` e una `nota_voce` (la dashboard non ha una voce sua nel browser,
riproduce il file che il server produce, e senza file salta solo l'ascolto).
"""

import hashlib
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import config, piattaforma
from .voce_testo import per_voce


class NessunMotoreVoce(RuntimeError):
    """Su questa macchina non c'è modo di sintetizzare o riprodurre la voce. Il
    messaggio dice cosa installare."""


class NessunaVoceNeurale(NessunMotoreVoce):
    """Il motore "neurale" (Pocket o Voicebox) non risponde. Non e' un errore
    grave: chi lo chiede (il pannello Jarvis dell'app Mac) ripiega da se' sulle
    voci avanzate di sistema e lo dice, invece di far parlare `say`."""


VOICEBOX = "http://127.0.0.1:17493"
# Pocket-TTS di Kyutai, se qualcuno lo tiene acceso. Misurato su questo Mac in
# italiano, con il modello gia' caricato: 111 ms al primo audio contro i 42
# secondi di Voicebox. Clona da un wav come l'altro, gira su due core e non
# tocca il percorso MLX che qui fa cadere il server.
POCKET = "http://127.0.0.1:8811"


def _url_voicebox() -> str:
    """L'indirizzo di Voicebox: quello di sempre, o `voicebox_url` in config.json (una
    porta diversa; le prove ci mettono un finto, cosi' non toccano mai quello vero)."""
    return str(config.load_config().get("voicebox_url") or VOICEBOX).rstrip("/")


def _url_pocket() -> str:
    """Come `_url_voicebox`, per Pocket (`pocket_url`)."""
    return str(config.load_config().get("pocket_url") or POCKET).rstrip("/")

AUDIO_DIR = config.DATA_DIR / "audio"

# Voci di sistema preferite per lingua, con il ripiego sulla prima che combacia.
PREFERITE = {
    "it": ["Alice", "Federica", "Luca"],
    "en": ["Samantha", "Alex", "Daniel", "Karen"],
    "es": ["Mónica", "Monica", "Jorge", "Paulina"],
    "fr": ["Thomas", "Amélie", "Amelie"],
    "de": ["Anna", "Markus", "Petra"],
    "pt": ["Luciana", "Joana", "Felipe"],
}

_voci = None


# --------------------------------------------------------------------------
# voci di sistema
# --------------------------------------------------------------------------

def voci_sistema() -> list:
    global _voci
    if _voci is None:
        _voci = []
        if not piattaforma.voce_sistema_presente():
            # fuori da macOS non c'e' `say -v ?`: si chiede al motore che c'e'
            # (System.Speech su Windows, espeak su Linux). Se non risponde
            # l'elenco resta vuoto e `stato()` dice perche'.
            try:
                argv = piattaforma.comando_elenco_voci()
                if argv:
                    res = piattaforma.esegui(argv, capture_output=True, text=True,
                                             timeout=20, stdin=subprocess.DEVNULL)
                    if res.returncode == 0:
                        _voci.extend(piattaforma.voci_da_elenco(res.stdout))
            except Exception:
                pass
            return _voci
        try:
            # le voci si elencano con `say -v ?`: c'è solo su macOS
            out = piattaforma.esegui(["say", "-v", "?"], capture_output=True, text=True,
                                     timeout=10).stdout
        except Exception:
            out = ""
        for line in out.splitlines():
            m = re.match(r"^(.+?)\s{2,}([a-z]{2}_[A-Z]{2,3})\s", line)
            if m:
                _voci.append((m.group(1).strip(), m.group(2)))
    return _voci


def voce_per(lang: str) -> str:
    scelta = config.load_config().get("voce_sistema", {})
    if isinstance(scelta, dict) and scelta.get(lang):
        return scelta[lang]
    if not piattaforma.voce_sistema_presente():
        # fuori da macOS non c'è un elenco di voci da cui scegliere: la voce è
        # quella predefinita del sistema (o quella scritta in voce_sistema)
        return ""
    nomi = {n for n, _ in voci_sistema()}
    for pref in PREFERITE.get(lang, []):
        if pref in nomi:
            return pref
    for nome, loc in voci_sistema():
        if loc.startswith(lang + "_") and "(" not in nome:
            return nome
    return "Alex"


def sintesi_say(testo: str, lang: str, out: Path) -> Path:
    voce = voce_per(lang)
    rate = str(config.load_config().get("velocita_voce", 185))
    argv = piattaforma.comando_sintesi(testo, lang, voce, rate, out)
    if argv is None:
        raise NessunMotoreVoce(piattaforma.motore_voce_assente())
    # stdin chiuso: PowerShell erediterebbe altrimenti il canale del server MCP
    piattaforma.esegui(argv, capture_output=True, timeout=180, check=True,
                       stdin=subprocess.DEVNULL)
    return out


# --------------------------------------------------------------------------
# Voicebox
# --------------------------------------------------------------------------

def _get(url, timeout=4):
    with urllib.request.urlopen(url, timeout=timeout) as res:
        return res.status, res.read()


def _post(url, payload, timeout=20):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8") or "{}")


# Quando Voicebox non risponde ci si ricorda per un po' che non risponde. Se e'
# spento la risposta e' immediata e non serve; se e' piantato, cioe' il processo
# c'e' ma non accetta, ogni frase pagherebbe l'attesa intera. E gli succede: il
# suo server e' morto due volte in un minuto dentro MLX.
_ultimo_no = 0.0
RIPROVA_DOPO = 30


def voicebox_vivo(timeout=1.5) -> bool:
    global _ultimo_no
    if time.time() - _ultimo_no < RIPROVA_DOPO:
        return False
    try:
        code, _ = _get(f"{_url_voicebox()}/profiles", timeout=timeout)
        if code == 200:
            _ultimo_no = 0.0
            return True
    except Exception:
        pass
    _ultimo_no = time.time()
    return False


_pocket_no = 0.0


def pocket_vivo(timeout=1.0) -> bool:
    """C'è un Pocket-TTS in ascolto? Stessa regola di Voicebox: se non risponde
    non glielo si richiede a ogni frase."""
    global _pocket_no
    if time.time() - _pocket_no < RIPROVA_DOPO:
        return False
    try:
        code, _ = _get(f"{_url_pocket()}/health", timeout=timeout)
        if code == 200:
            _pocket_no = 0.0
            return True
    except Exception:
        pass
    _pocket_no = time.time()
    return False


def sintesi_pocket(testo: str, out: Path, voce_wav: str = None, timeout=60) -> Path:
    """Una POST multipart, perché è quello che accetta: text, e voice_wav per la
    voce clonata."""
    import uuid
    conf = "----" + uuid.uuid4().hex
    pezzi = [f"--{conf}\r\nContent-Disposition: form-data; name=\"text\"\r\n\r\n{testo}\r\n"]
    corpo = "".join(pezzi).encode("utf-8")
    if voce_wav and Path(voce_wav).exists():
        dati = Path(voce_wav).read_bytes()
        corpo += (f"--{conf}\r\nContent-Disposition: form-data; name=\"voice_wav\"; "
                  f"filename=\"voce.wav\"\r\nContent-Type: audio/wav\r\n\r\n").encode() \
            + dati + b"\r\n"
    corpo += f"--{conf}--\r\n".encode()
    req = urllib.request.Request(f"{_url_pocket()}/tts", data=corpo, method="POST",
                                 headers={"Content-Type":
                                          f"multipart/form-data; boundary={conf}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out.write_bytes(r.read())
    return out


def voicebox_profili() -> list:
    try:
        _, body = _get(f"{_url_voicebox()}/profiles")
        data = json.loads(body.decode("utf-8"))
        return data if isinstance(data, list) else data.get("profiles", [])
    except Exception:
        return []


def voicebox_avvia(attesa=25) -> bool:
    """Apre l'app e aspetta che il backend risponda. Serve solo se richiesto."""
    if voicebox_vivo():
        return True
    try:
        subprocess.run(["open", "-a", "Voicebox"], capture_output=True, timeout=15,
                       **piattaforma.opzioni_figlio())
    except Exception:
        return False
    scaduto = time.time() + attesa
    while time.time() < scaduto:
        if voicebox_vivo():
            return True
        time.sleep(1.2)
    return False


def sintesi_voicebox(testo: str, lang: str, out: Path, timeout=180) -> Path:
    cfg = config.load_config()
    profilo = cfg.get("voicebox_profilo")
    if not profilo:
        profili = voicebox_profili()
        if not profili:
            raise RuntimeError("Voicebox non ha profili vocali")
        profilo = profili[0].get("id") or profili[0].get("profile_id")
    res = _post(f"{_url_voicebox()}/generate", {
        "profile_id": profilo, "text": testo, "language": lang,
        "engine": cfg.get("voicebox_engine", "qwen"),
    })
    gid = res.get("id") or res.get("generation_id") or res.get("job_id")
    if not gid:
        raise RuntimeError(f"Voicebox non ha restituito un id: {res}")
    # Lo stato arriva come event-stream. Invece di interpretarlo, si aspetta che
    # l'audio esista: è lo stesso segnale e non dipende dal formato degli eventi.
    scaduto = time.time() + timeout
    while time.time() < scaduto:
        try:
            code, body = _get(f"{_url_voicebox()}/audio/{gid}", timeout=10)
            if code == 200 and len(body) > 2048:
                out.write_bytes(body)
                return out
        except urllib.error.HTTPError:
            pass
        except Exception:
            pass
        time.sleep(0.8)
    raise TimeoutError("Voicebox non ha prodotto l'audio in tempo")


# --------------------------------------------------------------------------
# interfaccia unica
# --------------------------------------------------------------------------

def motore_scelto() -> str:
    return config.load_config().get("motore_voce", "auto")


# Oltre questo, aspettare non ha senso: si passa alla voce di sistema.
# Misurato sul suo Mac: Voicebox mette 42 secondi anche per una frase corta,
# che vanno bene per il riepilogo della mattina, dove nessuno sta aspettando,
# e non vanno bene per niente in una conversazione.
ATTESA_VOICEBOX = 5


# Attesa massima per una frase con il motore "neurale", quando qualcuno sta
# ascoltando una risposta che arriva a pezzi. Piu' lunga di ATTESA_VOICEBOX
# perche' qui il ripiego non e' `say`, che e' robotico e Jarvis non lo usa mai:
# e' la voce avanzata di sistema, e la sceglie l'app quando l'attesa e' finita.
# `attesa_voce_neurale` in config.json la cambia.
ATTESA_NEURALE = 9


def voce_neurale() -> str:
    """Quale voce neurale locale risponde adesso: "pocket", "voicebox" o "".
    Sola lettura: due GET su 127.0.0.1, con il ricordo dell'ultimo no."""
    if pocket_vivo():
        return "pocket"
    if voicebox_vivo():
        return "voicebox"
    return ""


def sintesi(testo: str, lang: str = "it", motore: str = None, cache=True,
            subito=False) -> dict:
    """Il file audio, generato solo se non c'è già.

    `subito` è per quando qualcuno sta aspettando di sentire: si prova la voce
    clonata per pochi secondi e poi si passa a quella di sistema, invece di
    lasciare la persona davanti al silenzio.

    `motore="neurale"` e' per Jarvis: Pocket, poi Voicebox, e MAI la voce di
    `say`. Se nessuna delle due risponde solleva `NessunaVoceNeurale` e il
    chiamante ripiega sulle voci avanzate di sistema. Aspetta al massimo
    `ATTESA_NEURALE` secondi per frase.
    """
    # Ultimo punto prima dell'audio: qui il testo diventa una cosa da dire.
    testo = per_voce(testo, lang)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    motore = motore or motore_scelto()
    chiave = hashlib.sha1(f"{motore}|{lang}|{testo}".encode("utf-8")).hexdigest()[:16]
    out = AUDIO_DIR / f"{chiave}.wav"
    if cache and out.exists() and out.stat().st_size > 2048:
        return {"file": str(out), "motore": "cache", "lingua": lang}

    usato = None
    # Prima si prova quello veloce, se c'è. Non è configurato da nessuna parte:
    # o risponde, o non esiste, e in un decimo di secondo si sa quale delle due.
    if motore in ("auto", "pocket", "neurale"):
        try:
            if pocket_vivo():
                sintesi_pocket(testo, out, config.load_config().get("voce_campione"))
                usato = "pocket"
        except Exception:
            usato = None
    if usato is None and motore in ("auto", "voicebox", "neurale"):
        try:
            if motore == "voicebox" and config.load_config().get("voicebox_avvio_automatico"):
                voicebox_avvia()
            if voicebox_vivo():
                if motore == "neurale":
                    attesa = float(config.load_config().get("attesa_voce_neurale",
                                                            ATTESA_NEURALE))
                else:
                    attesa = ATTESA_VOICEBOX if subito else 180
                sintesi_voicebox(testo, lang, out, timeout=attesa)
                usato = "voicebox"
        except Exception:
            usato = None
    if usato is None:
        if motore == "neurale":
            raise NessunaVoceNeurale(
                "nessuna voce neurale locale risponde (Pocket su 127.0.0.1:8811, "
                "Voicebox su 127.0.0.1:17493)")
        if motore == "voicebox":
            raise RuntimeError("Voicebox non risponde su 127.0.0.1:17493")
        sintesi_say(testo, lang, out)
        # il nome vero del motore: `say` su macOS, System.Speech o espeak fuori
        usato = piattaforma.motore_sistema() or "say"
    return {"file": str(out), "motore": usato, "lingua": lang}


_riproduzione = None


def riproduci(path, attendi=False):
    global _riproduzione
    ferma()
    argv = piattaforma.comando_riproduzione(path)
    if argv is None:
        raise NessunMotoreVoce(piattaforma.motore_voce_assente())
    # senza stdin ne' console: vedi `piattaforma.opzioni_processo`
    _riproduzione = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     **piattaforma.opzioni_processo())
    if attendi:
        _riproduzione.wait()
    return _riproduzione.pid


def ferma():
    global _riproduzione
    if _riproduzione and _riproduzione.poll() is None:
        _riproduzione.terminate()
    _riproduzione = None


def parla(testo: str, lang: str = "it", motore: str = None, attendi=True) -> dict:
    """Dice `testo` ad alta voce. Fuori da macOS non solleva mai per colpa della
    voce: se non c'è un motore, o se c'è ma fallisce o non risponde, torna
    `{"motore": "nessuno", "file": None, "errore": <cosa è andato storto>}`, così
    il resto (il testo del riepilogo, l'esito di un comando) arriva lo stesso. Su
    macOS un `say` che fallisce solleva ancora, come prima.

    Vale per chi chiama `parla` (la CLI e il server MCP). Chi chiama `sintesi`
    direttamente, come il server web (`api.py`), riceve `NessunMotoreVoce` e lo
    cattura da sé."""
    try:
        info = sintesi(testo, lang, motore)
        riproduci(info["file"], attendi=attendi)
        return info
    except NessunMotoreVoce as exc:
        # Solo Linux: `spd-say` sa dire una frase ma non scriverla in un file.
        argv = piattaforma.comando_dire(per_voce(testo, lang), lang, attendi)
        if argv:
            try:
                if attendi:
                    piattaforma.esegui(argv, capture_output=True, timeout=180,
                                       stdin=subprocess.DEVNULL)
                else:
                    piattaforma.avvia_distaccato(argv)
                return {"file": None, "motore": "spd-say", "lingua": lang}
            except Exception:
                pass
        return {"file": None, "motore": "nessuno", "lingua": lang, "errore": str(exc)}
    except (subprocess.SubprocessError, OSError) as exc:
        # il motore c'e' ma non va (PowerShell che esce con un errore o si pianta,
        # un lettore audio che manca davvero): fuori da macOS la voce non ferma il resto
        if piattaforma.nome() == piattaforma.MAC:
            raise
        return {"file": None, "motore": "nessuno", "lingua": lang,
                "errore": "la voce non ha funzionato: %s" % (exc,)}


# --------------------------------------------------------------------------
# testo che arriva a pezzi, voce che parte prima della fine
# --------------------------------------------------------------------------

class Frasi:
    """Spezza un testo che arriva a pezzi in frasi da dire una alla volta.

    E' quello che permette alla voce di partire mentre il modello sta ancora
    scrivendo: appena una frase e' finita esce da `nutri`, e chi ascolta puo'
    sintetizzarla mentre la successiva arriva. Il taglio e' su . ! ? … seguiti da
    uno spazio (cosi' "3.5" e "github.com" non si spezzano) e sugli a capo.

    Le frasi troppo corte si tengono insieme alla successiva ("Ok. Fatto." e' una
    frase sola per la voce: due sintesi da una parola l'una suonano a scatti),
    tranne la prima: quella parte appena c'e', perche' e' lei che decide quanto
    aspetta chi ascolta. Una frase che non finisce mai si taglia comunque a
    `massimo` caratteri, su una virgola o su uno spazio.
    """

    FINALI = ".!?…"

    def __init__(self, minimo: int = 24, massimo: int = 200, minimo_prima: int = 8):
        self.minimo = minimo
        self.massimo = massimo
        self.minimo_prima = minimo_prima
        self._buf = ""
        self._uscite = 0

    def _soglia(self) -> int:
        return self.minimo_prima if self._uscite == 0 else self.minimo

    def _confine(self):
        """Indice (esclusivo) della fine della prossima frase completa, o None."""
        b = self._buf
        soglia = self._soglia()
        i = 0
        while i < len(b):
            c = b[i]
            fine = False
            if c == "\n":
                fine = True
            elif c in self.FINALI:
                # aspetta di vedere cosa segue: uno spazio o un a capo chiude la frase
                j = i + 1
                while j < len(b) and b[j] in self.FINALI + "\"')»":
                    j += 1
                if j < len(b) and b[j].isspace():
                    i = j
                    fine = True
                elif j >= len(b):
                    return None
                else:
                    i = j - 1
            if fine and len(b[:i + 1].strip()) >= soglia:
                return i + 1
            i += 1
        if len(b) > self.massimo:
            taglio = max(b.rfind(", ", 0, self.massimo), b.rfind("; ", 0, self.massimo))
            if taglio < self.massimo // 2:
                taglio = b.rfind(" ", 0, self.massimo)
            return (taglio + 1) if taglio > 0 else self.massimo
        return None

    def nutri(self, pezzo: str) -> list:
        """Aggiunge un pezzo e torna le frasi complete che ora ci sono."""
        self._buf += pezzo or ""
        fuori = []
        while True:
            fine = self._confine()
            if fine is None:
                break
            frase = self._buf[:fine].strip()
            self._buf = self._buf[fine:]
            if frase:
                fuori.append(frase)
                self._uscite += 1
        return fuori

    def chiudi(self) -> list:
        """Il testo e' finito: quello che resta e' l'ultima frase."""
        resto = self._buf.strip()
        self._buf = ""
        if resto:
            self._uscite += 1
            return [resto]
        return []


def frasi_da_dire(testo: str, lang: str = "it") -> list:
    """Il testo intero spezzato in frasi, ognuna ripulita per la voce. Le frasi
    che dopo la pulizia restano vuote (un percorso da solo) spariscono."""
    f = Frasi()
    grezze = f.nutri(testo) + f.chiudi()
    return [d for d in (per_voce(x, lang) for x in grezze) if d and d.strip(" .,;:")]


# --------------------------------------------------------------------------
# ascolto
# --------------------------------------------------------------------------

def trascrivi(path, lang: str = "it") -> str:
    """Voicebox se c'è, altrimenti il whisper locale, altrimenti niente."""
    path = str(path)
    if voicebox_vivo():
        try:
            return _multipart_transcribe(path)
        except Exception:
            pass
    for exe in ("whisper-cli", "whisper"):
        try:
            res = subprocess.run([exe, path, "--language", lang, "--output_format", "txt",
                                  "--output_dir", str(AUDIO_DIR)],
                                 capture_output=True, text=True, timeout=300,
                                 **piattaforma.opzioni_figlio(), **piattaforma.opzioni_utf8())
            if res.returncode == 0:
                txt = AUDIO_DIR / (Path(path).stem + ".txt")
                if txt.exists():
                    return txt.read_text("utf-8").strip()
        except FileNotFoundError:
            continue
        except Exception:
            break
    return ""


def _multipart_transcribe(path: str) -> str:
    confine = "----plancia" + hashlib.sha1(path.encode()).hexdigest()[:12]
    dati = Path(path).read_bytes()
    corpo = (
        f"--{confine}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{Path(path).name}\"\r\nContent-Type: audio/wav\r\n\r\n"
    ).encode() + dati + (
        f"\r\n--{confine}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nturbo"
        f"\r\n--{confine}--\r\n"
    ).encode()
    req = urllib.request.Request(
        f"{_url_voicebox()}/transcribe", data=corpo,
        headers={"Content-Type": f"multipart/form-data; boundary={confine}"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as res:
        data = json.loads(res.read().decode("utf-8"))
    return (data.get("text") or data.get("transcript") or "").strip()


def stato() -> dict:
    cfg = config.load_config()
    fuori = {
        "motore": motore_scelto(),
        "lingua": cfg.get("lingua", "it"),
        "voce_attuale": voce_per(cfg.get("lingua", "it")),
        "voicebox_vivo": voicebox_vivo(),
        "voicebox_installato": Path("/Applications/Voicebox.app").exists(),
        "voci_sistema": len(voci_sistema()),
        "lingue_disponibili": sorted({loc[:2] for _, loc in voci_sistema()}),
    }
    if piattaforma.nome() != piattaforma.MAC:
        # Windows e Linux: il motore col suo nome vero, e se l'elenco delle voci
        # e' vuoto il perche' (senza, il pannello delle voci sembra rotto)
        fuori["motore_sistema"] = piattaforma.motore_sistema()
        if fuori["voci_sistema"]:
            fuori["nota_voci"] = None
        elif fuori["motore_sistema"] is None:
            fuori["nota_voci"] = piattaforma.motore_voce_assente()
        else:
            fuori["nota_voci"] = ("il motore %s non ha dato un elenco di voci: si usa "
                                  "la voce predefinita del sistema"
                                  % fuori["motore_sistema"])
    return fuori
