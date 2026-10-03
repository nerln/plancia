"""Il processo Claude tenuto caldo: adesso e' quello in SOLA LETTURA di Jarvis.

Fino al 30/09/2026 qui viveva un secondo processo, con i tool di scrittura
`plancia_*` aperti ("se ti chiede di segnare o chiudere qualcosa, fallo: non serve
chiedere il permesso"), che rispondeva alla dashboard web, al terminale e agli
strumenti a voce. Era l'altra porta: una frase trascritta male poteva chiudere un
task o archiviare un progetto senza che nessuno avesse premuto niente. Non esiste
piu': c'e' un solo processo caldo per lingua, `jarvis.SessioneLettura`, con i tool
di scrittura negati per nome, e tutto quello che scrive passa da una proposta con
la sua scheda (vedi jarvis.py).

Resta questo modulo perche' c'e' chi chiede "il processo caldo" per nome
(`agente.scalda`, `agente.stato`, `agente.spegni`, `agente.chiedi`): sono le stesse
funzioni di prima, ma dietro c'e' il processo sicuro.
"""

from . import jarvis

#: Il processo caldo di una lingua: quello in sola lettura di Jarvis.
Agente = jarvis.SessioneLettura

#: Le istruzioni di sistema del processo caldo: quelle di Jarvis in sola lettura.
ISTRUZIONI = jarvis.ISTRUZIONI_SICURE

#: Gli unici tool che il processo caldo puo' usare: quelli di lettura.
TOOL = jarvis.TOOL_LETTURA


def per(lang: str) -> "jarvis.SessioneLettura":
    return jarvis.sessione_lettura(lang)


def chiedi(testo: str, lang: str, timeout=90) -> str:
    """La risposta del modello in sola lettura a una frase, senza la riga di
    proposta (se il modello ne ha scritta una). Stringa vuota se il modello non
    risponde. Non scrive e non avvia niente."""
    finale = ""
    turno = per(lang).turno(testo, timeout)
    try:
        for genere, valore in turno:
            if genere == "fine":
                finale = valore
            elif genere in ("errore", "interrotto"):
                return ""
    finally:
        turno.close()
    return jarvis.senza_proposta(finale)


def scalda(lang: str):
    jarvis.scalda(lang)


def stato() -> dict:
    import time
    with jarvis._sessioni_lucchetto:
        elenco = dict(jarvis._sessioni)
    return {lang: {"vivo": s._vivo(), "turni": s.turni,
                   "inattivo_da": round(time.time() - s.ultimo) if s.ultimo else None}
            for lang, s in elenco.items()}


def spegni():
    jarvis.spegni()
