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
