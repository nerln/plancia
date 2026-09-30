"""Prove per LOTTO-L4-MEMORIA, lato back: plancia/esporta.py deve incorporare
web/moto.css come già fa con i font (un <style> in più, mai un <link>
esterno - vedi il docstring del modulo). Non incorpora il vortice in senso
utile (questa pagina non è web/index.html + web/app.js: è un
mini-visualizzatore scritto a mano, senza router, senza card con
data-chiave - vedi il commento su _moto_css() in plancia/esporta.py), ma le
regole ci devono essere comunque, per lo stesso motivo per cui i font sono
inline anche se l'utente magari non apre mai una card che li usa.

Funzione pubblica `esegui(prova)`, stessa forma di tools/prova.py:32 (vedi
tools/prove/README.md).
"""


def _prova_moto_incorporato(prova):
    from plancia import esporta

    percorso_moto = None
    try:
        from plancia import config
        percorso_moto = config.WEB_DIR / "moto.css"
        moto_vero = percorso_moto.read_text(encoding="utf-8")
    except FileNotFoundError:
        moto_vero = None

    prova("web/moto.css esiste (di proprietà di questo lotto, non di esporta.py)",
          moto_vero is not None, str(percorso_moto))
    if moto_vero is None:
        return

    dati = {"memorie": [], "progetti": [], "task": [], "quando": "ora"}
    pagina = esporta.costruisci(dati)

    # Non un frammento a caso: una regola vera di moto.css, non qualcosa che
    # potrebbe comparire per coincidenza in un'altra parte della pagina.
    prova("l'export incorpora le regole di moto.css (per intero, non solo un pezzo)",
          moto_vero.strip() in pagina, "")
    prova("l'export incorpora @keyframes entra-su (moto.css)",
          "@keyframes entra-su" in pagina, "")
    prova('nessun href="/moto.css" nell\'html esportato (mai un link esterno)',
          'href="/moto.css"' not in pagina and "href='/moto.css'" not in pagina, "")
    prova("nessun <link> esterno di nessun tipo nell'export (stesso criterio dei font)",
          "<link " not in pagina, "")


def esegui(prova) -> None:
    _prova_moto_incorporato(prova)


if __name__ == "__main__":
    import os
    import sys
    import tempfile
    from pathlib import Path

    RADICE = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(RADICE))

    CASA = Path(tempfile.mkdtemp(prefix="plancia-prova-esporta-moto-"))
    os.environ["PLANCIA_HOME"] = str(CASA)

    falliti = []
    passati = 0

    def prova(nome, condizione, dettaglio=""):
        global passati
        if condizione:
            passati += 1
            print(f"  ok   {nome}")
        else:
            falliti.append(nome)
            print(f"  NO   {nome} {dettaglio}")

    esegui(prova)
    print(f"\n{passati} passate, {len(falliti)} fallite")
    if falliti:
        for f in falliti:
            print(f"  - {f}")
        sys.exit(1)
