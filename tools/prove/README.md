# Le prove di un lotto

Un file qui dentro = un lotto. Il nome del file è il nome del lotto
(`esempio-lotto.py`), così due lotti non litigano mai per lo stesso file.

Il file espone `def esegui(prova):`. `tools/prova.py` lo importa da solo, in
ordine alfabetico, e chiama `esegui(prova)`: non serve toccare `prova.py`.

Dentro `esegui`, chiama `prova(nome, condizione, dettaglio="")` per ogni
controllo: `nome` è quello che compare nell'elenco, `condizione` è vera o
falsa, `dettaglio` (facoltativo) si stampa solo se `condizione` è falsa.

Per lanciare solo il tuo modulo mentre lo scrivi:

```bash
python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('m', 'tools/prove/tuo-lotto.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.esegui(lambda nome, cond, dettaglio='': print(('ok  ' if cond else 'NO  '), nome, dettaglio))
"
```

Non serve aprire una `PLANCIA_HOME`: quando il tuo modulo gira, `tools/prova.py`
ha già fissato `PLANCIA_HOME` a un archivio finto temporaneo e importato
`plancia.config` (che legge quella variabile una volta sola, all'import).
Riassegnare `os.environ["PLANCIA_HOME"]` dentro il tuo modulo non cambia
niente per il processo in corso: usa semplicemente `store.connect()`, che
apre l'archivio già pronto. Se ti serve davvero un archivio pulito e isolato,
aprilo in un sottoprocesso (`subprocess.run(..., env={**os.environ, "PLANCIA_HOME": tempfile.mkdtemp()})`),
mai riassegnando `os.environ` nel processo di `prova.py`. In ogni caso: mai
`~/.plancia`, l'archivio vero dell'utente.

Un file che comincia con `_` non viene scoperto: usalo per una funzione
condivisa fra più moduli, non per una prova.

## Se la prova lancia un processo

Le prove girano anche su Windows (`windows-latest`). Tre cose cambiano li', e le
raccoglie `_finti.py` (accanto a questo file, non e' una prova):

- la casa di un processo e' `USERPROFILE`, non `HOME`: `_finti.casa_finta(env, casa)`
  le sposta tutte;
- uno script di `bin/` senza estensione non si esegue da solo (WinError 193): si
  lancia con `piattaforma.argv_script(script)`, che su macOS e Linux torna il solo
  script, com'e' sempre stato;
- un programma finto scritto come file con `#!/bin/sh` non parte: `_finti.crea_finto`
  lo scrive in Python, con lo shebang su macOS e Linux e con un `.cmd` su Windows.

Un controllo che su un sistema non si puo' fare (un `chmod 000` che su Windows non
rende illeggibile un file) passa con `dettaglio` che comincia per `saltato`, il perche'
scritto accanto: il numero dei controlli e' lo stesso ovunque, e il README ne
dichiara uno solo.
