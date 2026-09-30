"""Il `claude` finto del pannello Jarvis: parla lo stesso stream-json del vero
(`--input-format stream-json --output-format stream-json --include-partial-messages`).

Non e' una prova (comincia con `_`, `tools/prova.py` non la scopre): la usano
`tools/prove/jarvis-sicuro.py` (dentro `_finti.crea_finto`) e `tools/prova-jarvis-mac.sh`
(dietro un piccolo script `claude` messo in testa al PATH del server di prova).

Cosa risponde, secondo la frase:
  "proponi: <json>"   una frase e poi la riga @@PROPOSTA <json>, cosi' com'e'
  "eco: <testo>"      risponde esattamente <testo> (per frasi che non sono gia' in cache)
  contiene "guasto"   tre frasi, la seconda con la parola "guasto" (il finto Pocket la rifiuta)
  contiene "lento"    scrive piano (un pezzo ogni quarto di secondo), per provare Esc
  altro               tre frasi corte

Scrive su $FINTO_LOG (se c'e') gli argomenti, il pid e ogni frase ricevuta. Non fa
altro: niente rete, niente disco oltre al registro.
"""
import json, os, sys, time

log = os.environ.get("FINTO_LOG")
def scrivi(riga):
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(riga + "\n")
def ev(o):
    sys.stdout.write(json.dumps(o, ensure_ascii=False) + "\n")
    sys.stdout.flush()

scrivi("ARGV " + json.dumps(sys.argv[1:], ensure_ascii=False))
scrivi("PID %d" % os.getpid())
for riga in sys.stdin:
    try:
        m = json.loads(riga)
        testo = m["message"]["content"][0]["text"]
    except Exception:
        continue
    scrivi("TURNO " + testo)
    if testo.startswith("proponi:"):
        risposta = "Ti propongo questo, guarda la scheda.\n@@PROPOSTA " + testo[len("proponi:"):].strip()
    elif testo.startswith("eco:"):
        risposta = testo[len("eco:"):].strip()
    elif "guasto" in testo:
        risposta = "Prima frase corta va bene. Questa e' la frase guasto apposta per la prova. Ultima frase qui."
    elif "lento" in testo:
        risposta = "Sto pensando con calma a questa cosa. Poi ti dico. Ancora un momento."
    else:
        risposta = "Hai tre task aperti. Il primo scade domani. Il resto puo' aspettare."
    ev({"type": "system", "subtype": "init"})
    for i in range(0, len(risposta), 5):
        ev({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0,
            "delta": {"type": "text_delta", "text": risposta[i:i + 5]}}})
        time.sleep(0.25 if "lento" in testo else 0.005)
    ev({"type": "assistant", "message": {"content": [{"type": "text", "text": risposta}]}})
    ev({"type": "result", "subtype": "success", "is_error": False, "result": risposta})
