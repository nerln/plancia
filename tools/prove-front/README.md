# Le prove del front di un lotto

Stessa convenzione di `tools/prove/README.md`, per le prove statiche sul
front (`tools/prova-front.py`): niente browser, si guarda il sorgente.

Un file qui dentro = un lotto, nome del file = nome del lotto. Espone
`def esegui(prova, radice):` (un argomento in più di `tools/prove/`:
`radice` è la cartella del repo, per leggere `web/app.js` o `web/index.html`
senza dover ricalcolare il percorso in ogni modulo).

`prova(nome, condizione, dettaglio="")` è la stessa firma di `tools/prova.py`:
`tools/prova-front.py` lo importa da solo, in ordine alfabetico, e chiama
`esegui(prova, RADICE)`.

Per lanciare solo il tuo modulo mentre lo scrivi:

```bash
python3 -c "
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('m', 'tools/prove-front/tuo-lotto.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.esegui(lambda nome, cond, dettaglio='': print(('ok  ' if cond else 'NO  '), nome, dettaglio),
         Path('.').resolve())
"
```

Non serve una `PLANCIA_HOME`: queste prove non toccano nessun archivio, vero
o finto, leggono solo i file del front.

Un file che comincia con `_` non viene scoperto.

## Le prove con Chrome

`memoria.py`, `appweb.py` e `web21.py` aprono la pagina per davvero: un server di prova con
l'archivio dimostrativo (`PLANCIA_HOME` in una cartella temporanea, `claude` e `codex` finti in
testa al `PATH`) e Chrome headless pilotato via CDP. Chrome parte con la casa vera dell'utente
letta dall'anagrafe (`_ambiente_chrome`), non da `$HOME`: sotto un `HOME` finto la sua rete non
risponde e ogni navigazione resta appesa. Senza Chrome le prove passano dicendo che non sono
state verificate, cosi' il numero resta lo stesso su ogni macchina.

`web21.py` e' il modulo della dashboard nella seconda passata di Plancia 2.0: font di sistema,
barra laterale senza logo, stato nel sottotitolo, Oggi a colonna, Task come tabella, grafo con
fisica (nodi che si trascinano, livelli, zoom), ricerca per ambiti, menu Impostazioni.
