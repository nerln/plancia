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
