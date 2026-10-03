"""Compartimenti: due (o piu') gruppi di lavoro sulla stessa macchina che non
si vedono. Qui sta la logica pura, senza effetti collaterali oltre al registro
e alla copia dell'ultima config valida; la usa `bin/plancia-guardiano` (l'hook
PreToolUse) e la userà il resto di Plancia quando filtrerà per compartimento.

Il modello, in breve:

- Un compartimento NOMINATO e' un elenco di PERMESSI: la sessione che gli
  appartiene vede solo le sue `cartelle` piu' un elenco neutro di binari e
  ambienti (`NEUTRI_FISSI`, `NEUTRI_HOME`), la propria cartella di lavoro
  temporaneo e la propria cartella in `~/.claude/projects`. Tutto il resto e'
  vietato.
- Il `predefinito` e' un elenco di DIVIETI: le cartelle di tutti i
  compartimenti nominati, piu' `divieti`, piu' ogni riga del file
  `manifesto_divieti` (uno per riga, `#` commenti, glob ammessi). Il manifesto
  e' la fonte unica dei percorsi del lavoro comune che sta ancora nell'albero
  del predefinito: non si riscrive a mano due volte.

Limiti da dire chiari (non sono difetti da correggere qui):

- E' un guardiano di INCIDENTI, non un confine di sicurezza. Ferma il
  comportamento ordinario di un agente, non uno che vuole aggirarlo: un
  percorso costruito a pezzi dentro uno script, un symlink creato apposta e poi
  letto da dentro un programma, un percorso scritto in un file e letto da un
  altro comando. Dentro lo stesso utente del sistema operativo non c'e' modo di
  farlo diventare un confine vero: quello serve un utente separato.
- L'estrazione dei percorsi da un comando Bash e' euristica (vedi
  `_candidati_an`): token e sottostringhe che sembrano percorsi. Un argomento e' un
  percorso candidato solo nella posizione di un FILE: non il modello di `grep`/`rg`,
  non lo script di `sed`/`awk`, non il filtro di `jq`, non il codice di `python -c`
  o `perl -e`, non un endpoint (`gh api /repos/x`), non un url, non il valore di
  `find -name`, di `git log --grep` o di `git commit -m` (`_classi_token`). E un
  `/...` dato a un comando che non opera su file (`_FILE_CMD`) o trovato dentro un
  codice e' un percorso solo se esiste, o se sta sotto una cartella che esiste
  diversa dalla radice (`_plausibile`): `</article>`, `/script`, `/api/users`, una
  regex che comincia con `/`, non lo sono. Una `/` da sola vale solo come radice di
  una ricerca del suo stesso comando (`find / -name x`), non perche' sta nella stessa
  pipe (`find . | awk -F/ ...`). Lo stesso comando nominato dentro `-v a:/b` vale
  come due percorsi.
- Una ricerca RICORSIVA lanciata da Bash (`grep -r`, `rg`, `find`, `ls -R`,
  `tree`, `tar`, `zip`, `cp -r`, `rsync`, `git grep`) si riconosce dal nome del
  comando e vale come Grep: le cartelle nominate nel comando e la cwd sono
  trattate come radici di una ricerca, e una ricerca che include un percorso
  vietato e' negata. Il riconoscimento e' sul testo del comando: un programma
  che cammina l'albero per conto suo (uno script, `make`) non si vede. Grep e
  Glob si vedono sempre (partono da un `path` esplicito o dalla cwd).
- Un divieto scritto come modello di nome senza barre (`*.segreto`,
  `NOTA-X.md`) vale per un percorso solo quando il nome compare in quel
  percorso: la regola "la ricerca include un percorso vietato" non scatta mai
  per lui, perche' non ha una cartella da cui una ricerca possa partire.
- I token di shell con un glob (`cat cartella/*`) si espandono sul disco
  (fino a 200 voci per token) prima del confronto. L'espansione e' propria
  (`_glob_disco`), non `glob.glob`: la traduzione in regex di `fnmatch` fa un
  `re.error` di un token come `t[i-200:i+200]` (lo slicing di uno script Python
  nel comando) o `a[[-1]`, e sarebbe un errore interno. Un intervallo invertito o
  una `[` senza `]` sono caratteri letterali, come in bash. Lo stesso vale per i
  divieti con un glob (`_glob_combacia`): il testo di un comando o di un manifesto
  non puo' costruire una regex non valida. Nemmeno una lenta: un modello con molte
  stelle uguali (`*a*a*a*a*a*a*a*b`) su un nome lungo non va in backtracking
  catastrofico (ogni `*` seguito da un pezzo fisso e' atomico, come in
  `fnmatch.translate` di Python 3.9), e un modello di piu' di 512 caratteri o di
  piu' di 24 stelle vale come testo (`_rx_glob`, `_MAX_GLOB`, `_MAX_STELLE`).
- Il confronto dei percorsi e' senza distinzione di maiuscole (APFS non le
  distingue): su un volume che le distingue puo' negare di piu', mai di meno.
- Gli strumenti che elencano o cercano senza un bersaglio esplicito
  (`search_files`, `list_sessions`, `ListAgents`, ...) non si possono valutare
  per il predefinito: passano, anche in `bloccante`. Per un nominato sono
  negati. Per `list_sessions` e `ListAgents`, quando esistono nominati, in
  `solo-registro` resta una riga `avrebbe-negato` (vedi `_misura`), per sapere
  quanto si usano: sono elenchi (titoli, cartelle di lavoro), non contenuti, ma
  chi accende E1 deve saperlo, perche' e' un canale aperto. Fa eccezione
  `search_session_transcripts`, che cerca nel CONTENUTO delle trascrizioni di
  tutte le sessioni: negato ai nominati sempre e al predefinito quando esistono
  nominati (`SESSIONI_RICERCA`).
- Gli strumenti di sessione ricevono l'id dell'app (`local_<uuid>`) o un nome
  (il titolo), non il `session_id` dell'hook: si risolvono leggendo il registro
  dell'app (`_voci_app`). Un id o un titolo che il registro e la tabella di
  Plancia non conoscono e' "sconosciuto" (negato a un nominato).
- Un `Artifact` con `files` come mappa e `root` si controlla sui valori
  (i sorgenti locali) e su `root`; un altro strumento MCP che legge un file
  con un nome di parametro nuovo no, finche' il nome non e' in `CHIAVI_PERCORSO`.
- I file del guardiano (config, copia, registro, manifesto, hook, questo
  modulo, `plancia/__init__.py`, `plancia/config.py`, il loro codice compilato in
  `plancia/__pycache__`, e ogni `.py` in `bin/` e nella
  radice del checkout da cui gira l'hook) non si modificano da nessuna sessione,
  e nemmeno le sue chiavi di config (`guardiano`, `compartimenti`,
  `strumenti_drive`) con la CLI di Plancia (`plancia config guardiano ...`,
  `python3 -m plancia.cli config ...`, `$(which plancia) config ...`,
  `config.save_config` o `main([...])` da un interprete): `_valuta_protetti`. Da
  Bash e' euristico (redirezioni, `tee`, `sed -i`, `cp`/`mv`/`install`/`rsync`
  verso il file, `rm`/`mv` del file o della cartella che lo contiene,
  `find -delete`/`-exec rm`, `chmod -R`, `curl -o`, `wget -O`, `tar x -C`,
  `unzip -d`, `git checkout` nella cartella dei dati, `chmod`/`chown` senza -R sulla
  cartella dei dati e su quelle del codice, `ln -sfn` sulla cartella, `>&` e `<>`,
  `patch`, `gzip`, `sort -o`, le stesse operazioni con graffe, glob, variabili, cicli
  `for`, sostituzioni `$(...)`, `xargs` e `while read`, codice di un interprete che
  nomina il file o `.plancia`+`config.json` e scrive, o che lancia una shell
  (`os.system('rm x')`, `subprocess.run(['rm', 'x'])`, `execSync`, `system(...)`,
  `do shell script`: le stringhe del codice si leggono come comandi, e le stringhe
  attaccate con `+` si uniscono): un percorso costruito a pezzi con l'ambiente o
  con un glob dentro uno script non si vede, ne' un `git checkout` nel checkout
  stesso, ne' una copia in massa nella radice del checkout, ne' `kill` del processo. Vale solo in
  `bloccante`, come ogni diniego: chi vuole cambiare la config con l'aiuto di
  una sessione deve prima passare a `solo-registro`. Anche `plancia config <chiave>`
  rifiuta di riscrivere un config.json che non si legge (uscita 2).
- I file `settings.json` e `settings.local.json` di Claude Code (di `~`, di
  `CLAUDE_CONFIG_DIR` e dei progetti, cioe' sotto una cartella `.claude`) sono
  protetti in modo MIRATO: Write/Edit/MultiEdit passano solo se il contenuto
  risultante non ha `disableAllHooks` a vero, non mette in `env` una variabile che
  fa partire l'hook altrove o senza le sue librerie (`PLANCIA_HOME`, `HOME`,
  `CLAUDE_CONFIG_DIR`, `PYTHONPATH`, `PYTHONHOME`, `PATH`, `LD_PRELOAD`, `DYLD_*`:
  per TUTTI i settings, se nuova o cambiata) e, quando il file ha oggi la voce
  PreToolUse di `plancia-guardiano`, la ha ancora, col comando uguale e efficace:
  sotto PreToolUse, senza un `matcher` che la restringe, senza `if`, non `async`,
  con un `timeout` di almeno un secondo. Bash che li scrive e' negato con l'invito a
  usare Edit. Dedotto, non visto: l'effetto di `disableAllHooks` e di `env` letti da
  Claude Code. Non coperti: `managed settings`, l'app (`mcp__ccd_settings__*`), un
  secondo hook che approva (dedotto: un `deny` prevale), un `settings.json` cambiato
  prima che il guardiano fosse acceso.
- Il guardiano che non parte (il pacchetto non si importa, l'hook solleva, un
  `sys.exit` o un `KeyboardInterrupt` nel modulo, oltre due secondi di calcolo) resta
  fail-open ma lascia una riga `guardiano-non-parte` nel registro e un
  `systemMessage` per l'utente (`bin/plancia-guardiano`); il pacchetto si carica
  senza mettere `bin/`, la radice ne' `PYTHONPATH` sul `sys.path`. Non si prende
  `os._exit`, ne' un ciclo in codice C che non guarda i segnali. Una config che non si
  legge per PERMESSI (la cartella dei dati con `chmod 000`) non e' un fail-open muto:
  l'hook lo dice con un `systemMessage` (al massimo ogni dieci minuti; a ogni chiamata
  se la marca non si puo' scrivere) e, se la copia dell'ultima config si legge, continua
  a negare.
- Trascrizioni e memoria di un compartimento nominato stanno sotto
  `<CLAUDE_CONFIG_DIR o ~/.claude>/projects/<cartella codificata>`: sono suo
  lavoro come le sue cartelle (`Ambito.proprietario_specchio`; E1 usa la stessa
  regola). Il predefinito non le legge, ne' cerca da `projects` o da un antenato
  (Grep, Glob, Bash ricorsivo). Il confine e' il trattino della codifica
  (`<enc>` e `<enc>-...`, non `<enc>altro`), ma la codifica perde la differenza
  fra `/` e `-`: una cartella sorella `alfa-2` di `alfa` risulta di alfa, e si
  nega per prudenza. Un `ls ~/.claude/projects` (non ricorsivo) mostra i nomi
  codificati delle cartelle, e un `ls` della cartella padre di un percorso
  vietato mostra i nomi dei suoi file: i contenuti no.
- Un percorso in `/tmp`, `/private/tmp`, `/var/folders` e simili non e' di
  nessun compartimento, ma un nominato non lo usa (e' un posto dove passarsi
  file: vedi il commento di `NEUTRI_FISSI`), e il motivo del diniego lo dice.
  `mktemp -d` da solo passa (nessun percorso nel testo) e cio' che si scrive
  li' non si vede: la separazione di `/tmp` e' di facciata contro un agente che
  la cerca. Un comando come `tar czf /tmp/x.tgz src` da un nominato e' negato per
  scelta: se si vuole ammettere `/tmp`, e' una riga in `NEUTRI_FISSI`.
- Cartelle di codice CONDIVISE (`condivise` di config, default nessuna): tutti i
  compartimenti le leggono e ci eseguono (i checkout degli strumenti pubblici che
  una sessione di un nominato lancia: Plancia, boa), nessun nominato ci scrive fuori
  dai propri permessi (`_valuta_condivise` per Bash, `_percorso_nominato` per gli
  strumenti di scrittura). Vince sempre il piu' specifico: la cartella di un
  nominato dentro una condivisa e' sua, e una ricerca che parte dalla condivisa e
  include la cartella di un altro nominato e' negata. Mai condivisa: la cartella dei
  dati di Plancia, `<claude>/projects`, `<claude>`, la home e i loro antenati: una voce
  che e' una di queste, ne contiene una o sta dentro i dati o projects e' IGNORATA con
  una nota nel registro (`voce_condivisa_vietata`; `plancia config condivise` la
  rifiuta), e una ricerca ricorsiva che parte da una condivisa non entra mai nei dati ne'
  in projects (`Ambito.riservata_inclusa`, seconda difesa). La scrittura da Bash e'
  quella che `_bersagli_scrittura` riconosce: redirezioni, `tee`, `cp`, `rm`, `touch`,
  `sed -i`, `sed w`, `awk print >`, le scritture di git (`commit`, `add`, `fetch`,
  `pull`, `branch`, `tag`, `config`, `gc`, `clone` dentro, `checkout`, `reset`,
  `stash`; NON le letture: `log`, `show`, `diff`, `status`, `blame`, `rev-parse`, `branch`
  senza operandi o con `--contains`/`--list`, `tag -l MODELLO`, `config --get`, `reflog`,
  `notes list`/`show`, `fetch --dry-run`, `stash list`, `worktree list`, `submodule
  status`: `_git_e_lettura`), `-t DIR` e `--target-directory`, `-o`/`--output` (per `-o` i comandi che
  lo intendono cosi': `gcc`, `pandoc`...), `zip`, `split`, `mktemp -p`, `mkfifo`,
  `xattr -w`, `ffmpeg`, un collegamento simbolico creato nello stesso comando (`ln -s X
  l && touch l/f`), codice di un interprete: un programma che scrive per conto suo
  (un'installazione di pacchetti, una compilazione) non si vede.
- Un codice dato a un interprete (`python3 -c`, un heredoc, `node -e`) si legge cosi':
  i percorsi assoluti che nomina; le stringhe che sono il nome di un file del guardiano
  (`open('settings.json', 'w')`, `Path('config.json')`), risolte sulla cartella da cui
  parte il segmento quando SI SA (`cd X && ...`, la cartella della sessione; con un `cd -`
  non si sa e non si guarda); i comandi di shell dentro le sue stringhe (`os.system`,
  `subprocess`). Una cartella di PRIMO livello nominata nel testo (`'/home/'` in una regex)
  conta solo se e' un OPERANDO di una chiamata che scrive o cancella (`shutil.rmtree('/x')`,
  `os.chmod`, `Path('/x').rename(...)`, `fs.rmSync`), anche legata a una variabile (`p =
  '/x'; shutil.rmtree(p)`, `for d in ['/x']: ...`): `_operando_di_scrittura`, euristico, un
  tratto corto di testo attorno a ogni comparsa. La cartella dei dati di Plancia costruita
  da `PLANCIA_HOME` (o da `HOME` con `.plancia`, o `CLAUDE_CONFIG_DIR` con `settings.json`)
  punta dove il COMANDO assegna la variabile (`PLANCIA_HOME=/x python3 ...`, `export`,
  `env`, `PLANCIA_HOME=$(mktemp -d)`), quindi una cartella di prova non e' quella vera; se
  la variabile non e' assegnata dal comando, o lo e' a un valore che non si sa (una
  sostituzione, un `source` o un `eval` prima), il bersaglio e' ignoto e si nega.
- Le variabili di un comando (`cat $DIR/x`) si espandono con quelle assegnate
  nello stesso comando (`VAR=x; cat $VAR/f`, `export VAR=x`), poi con
  l'ambiente del payload, se ce n'e' uno (nessun hook di Claude Code lo manda,
  per quanto si e' visto), poi con quello dell'hook; una variabile non definita
  si ignora (un percorso che non si sa ricostruire non si risolve sulla cwd).
  Una `/` da sola non e' un percorso.
- La cartella si SIMULA lungo il comando: `cd X && cat f`, `cd X; cat f`,
  `pushd`, `popd`, una subshell fra parentesi (`(cd X; cat f)` non sposta niente
  dopo), e i percorsi relativi dei segmenti successivi si risolvono li'. Un `cd`
  relativo verso una cartella che non c'e' fallisce e non sposta (`cd comune;
  grep -r x .` cerca dove era); una destinazione che e' una sostituzione di comando
  che si sa valutare senza lanciarla si risolve (`cd $(pwd)`, `cd $(dirname X)`,
  `cd $(git rev-parse --show-toplevel)`, `cd $(realpath X)`, `cd "$(cd X && pwd)"`:
  `_valuta_sost`); un `cd -`, un `cd` con una variabile non definita, con `$0`, con
  graffe che portano a piu' cartelle, con una sostituzione che non si sa valutare, o
  dopo un `||` lasciano la cartella SCONOSCIUTA: un percorso relativo CON una barra
  dopo si nega per prudenza, un nome semplice (`ls`, `git status`, `cat nota.txt`)
  no, per nessuno: non si puo' dire dove porta, e negarlo sarebbe il falso positivo di
  ogni script. Una SCRITTURA con un nome semplice (`git init`, `git commit`, `git add .`,
  `touch f`, `echo x > f`, `mkdir x`, `cp a b`) non nega per il PREDEFINITO; per un
  nominato nega ancora ("scrivi percorsi assoluti"). Per il predefinito restano negati un
  percorso con una barra o `..` (`touch sub/f`), una ricerca o una copia ricorsiva (`grep -r
  x .`, `cp -r . x`) e il nome di un file del guardiano (`rm config.json`). Dedotto, non
  provato su una shell vera: un `cd` che fallisce in un `&&`.
- `echo` e `printf` stampano i loro argomenti e non toccano percorsi, MA solo se
  il testo non arriva a un comando che lo usa: fuori da una pipe, fuori da una
  sostituzione (`$(...)`, apici inversi: `f=$(echo x); cat $f`), e se scritto in
  un file non e' poi dato a un esecutore nello stesso comando (`echo 'cat x' >
  run.sh && bash run.sh`, `echo x > lista; xargs cat < lista`). Il corpo di un
  heredoc e' testo solo se lo riceve un comando che non esegue (`cat` verso un
  file o `git commit -F -`, anche dentro `git commit -m "$(cat <<EOF ...)"`); se
  lo riceve una shell, un interprete, `eval`, `source`, `xargs`, `ssh`, o se il
  comando che lo riceve manda l'output a una pipe verso un esecutore o a una
  sostituzione (`eval "$(cat <<EOF ...)"`), il suo contenuto si controlla come
  comando. Lo stesso vale per una here-string (anche con le virgolette: `sh <<<
  'cat x'`), per una sostituzione di processo o di comando data a un esecutore
  (`bash <(echo 'cat x')`, `eval "$(echo 'cat x')"`), per un testo scritto in un file
  (redirezione, `tee`, anche da una pipe) e poi eseguito per percorso (`./run.sh`,
  `$f` con `f=$(mktemp)`), letto dentro una sostituzione (`sh -c "$(<s.sh)"`, `cat
  $(cat lista)`, `for f in $(cat lista)`) o mandato a un esecutore lungo la pipe
  (`cat lista | xargs cat`). Due comandi dati in due chiamate separate (uno scrive lo
  script, l'altro lo esegue) non si vedono. Restano fuori, dichiarati: il testo di
  comando dentro gli argomenti di un altro comando (`awk 'BEGIN{system("cat x")}'`,
  `find -exec sh -c 'cat x'`, `git -c core.pager='cat x'`, `env -S 'cat x'`), e le
  variabili costruite con `printf -v` o `IFS=: read`.
- Le virgolette ANSI-C (`$'...'`, con `\x2f` e simili) e `$"..."` si leggono come
  virgolette normali. Un ciclo `for VAR in PAROLE; do ...; done` con parole note (anche
  glob e graffe) si svolge: il segmento che usa `$VAR` si controlla per ogni valore;
  con parole non note (`while read f`, `for f in $(cmd)`) il comando che scrive con `$f`
  si controlla con tutti i percorsi nominati nel resto del comando. Le graffe di
  shell (`rm dati/{config,x}.json`) si espandono. Un `cd` verso una destinazione con
  le graffe o con una sostituzione di comando (`cd alfa-{uno,due}`, `cd "$(cmd)"`) lascia
  la cartella SCONOSCIUTA; `$(pwd)` e `$PWD` sono la cartella simulata.
- I tetti dell'analisi non sono silenziosi: oltre 300 nomi semplici, 1000 voci
  espanse da glob, 5000 percorsi in un comando, il resto non si guarda e un nominato e'
  negato ("troppi percorsi"), il predefinito lascia una riga `nota` nel registro. Un
  percorso vero (`/...`) non e' mai fermato dal tetto dei nomi.
- La cwd di un nominato aperto fuori dalle sue cartelle (per id) vale per ogni
  comando Bash (vedi `valuta`); al contrario una sessione del predefinito che
  entra per errore in una cartella di un nominato (`cd` persistente) diventa
  quel nominato e perde il proprio lavoro: e' la scelta dichiarata in
  `chiamante` (la cwd puo' solo aggiungere un'appartenenza).
- Cartelle ANNIDATE fra compartimenti (alfa in `/w/alfa`, beta in `/w/alfa/beta`):
  un percorso, una cwd, una cartella di apertura sono del nominato piu'
  SPECIFICO (per componenti, indipendentemente dall'ordine della config; la
  stessa regola di boa). Due nominati sulla STESSA cartella sono incerti: la
  sessione li' ha i permessi di entrambi (nessuno) e il percorso e' negato a
  tutti, con il motivo "assegnata a piu' di un compartimento". L'id della
  madre di un subagente, ricavato dal percorso del suo transcript, conta solo
  se quel file esiste davvero sotto `<claude>/projects` e la madre ha il suo
  transcript (dedotto: che a ogni chiamata di un subagente il file esista
  gia').
- Una ricerca ricorsiva con limite di profondita' (`find -maxdepth N`, `tree -L N`,
  `rg --max-depth N`, `fd -d N`) include una cartella vietata solo se ci arriva:
  `find . -maxdepth 1` non e' una ricerca illimitata. `du` (senza `-a`) non conta
  i nomi che un glob espande. Un url `file:` (WebFetch, i browser, `curl`) e' un
  percorso. Glob con un modello assoluto e senza `path` non usa la cwd.
- Gli strumenti di sessione senza id (`set_session_title`, `clear_session`, ...)
  restano negati a un nominato: lo schema non dice che senza id agiscano su di
  lei (solo `get_usage` lo dice); il motivo suggerisce `session_id: "self"`.
- L'appartenenza dell'id Drive e' per id esatto, senza risalire agli antenati
  (la verifica degli antenati non e' affidabile da qui).

LIMITI DICHIARATI (sesto giro: la corsa ai buchi finisce qui)

Questo modulo e' un ANALIZZATORE EURISTICO del testo di un comando: un guardiano di
INCIDENTI, non un confine di sicurezza. Ferma quello che un agente fa senza pensarci
(un `cat` di un file dell'altro compartimento, un `rm` della config, una ricerca che
attraversa una cartella vietata). Non ferma chi lo aggira apposta, e non lo pretende.
Un confine vero e' un utente del sistema operativo separato, o un contenitore. Cio' che
il guardiano NON vede, elenco onesto:

- percorsi costruiti a runtime dentro programmi e script gia' esistenti: uno script
  `.sh` o `.py` scritto in una chiamata e lanciato in un'altra, una compilazione, un
  test che apre file, un programma che cammina l'albero per conto suo, uno script che
  compone il percorso con l'ambiente, un glob o un `os.path.join`;
- codice scaricato o generato e poi eseguito (`curl x | sh` si vede come testo, non il
  suo contenuto; un pacchetto installato, un binario scaricato, un plugin);
- processi figli che si lanciano da soli e vivono oltre il comando (un demone, un
  `launchd`, un `cron`, un `at`, un watcher, un server di sviluppo che poi scrive);
- gli strumenti MCP di terzi con un parametro che non sta in `CHIAVI_PERCORSO` o in
  `strumenti_drive`, e qualunque strumento che apre un file per un argomento di nome
  nuovo; le app native (Finder, un editor) pilotate con computer-use;
- percorsi che passano per un altro canale del sistema: gli appunti, la rete locale
  (`localhost`), un database, un `git remote` che punta a una cartella;
- un comando scritto in due chiamate (uno scrive lo script, l'altro lo esegue), una
  variabile costruita con `printf -v` o `IFS=: read`, `eval` di una variabile fra
  virgolette, un percorso relativo dentro il codice di un interprete (tranne il nome di
  un file del guardiano dopo un `cd` che si sa dove porta) o dopo un `cd` che non si sa;
- i `managed settings`, l'app (`mcp__ccd_settings__*`), un secondo hook che approva, un
  `disableAllHooks` scritto prima che il guardiano fosse acceso, `kill` del processo;
- un comando che l'analisi non finisce di guardare in due secondi: per un nominato (o un
  incerto) GIA' STABILITO e' negato ("comando troppo complesso da controllare in tempo:
  spezzalo"), per il predefinito, e per un chiamante non ancora stabilito (l'allarme
  scatta prima di sapere a che compartimento appartiene la sessione), e' ammesso con un
  avviso ogni volta (`uscita_tempo_scaduto`); il tetto dei percorsi (5000) lascia solo una
  nota per il predefinito;
- Windows (manca SIGALRM: niente allarme), un volume che distingue le maiuscole, un Python
  diverso dal 3.9 di sistema per l'hook: non provati.

Il guardiano si accende in `solo-registro`, si legge il registro (`plancia guardiano
--registro`) e si decide dopo: `bloccante` e' una scelta, non il default.

Leggero apposta: gira su OGNI strumento di OGNI sessione. Solo `json`, `os`,
`re` e `time` all'avvio; `shlex`, `glob`, `sqlite3` solo quando servono.
Non importa `plancia.config`: quel modulo, all'import, costruisce decine di
oggetti `pathlib` e importa `secrets` (che tira dentro `hmac` e `hashlib`), un
costo che un hook globale non deve pagare a ogni strumento. La posizione della
cartella dati e' la stessa regola, ripetuta in `percorso_dati()`, e una prova
le confronta.
"""

import json
import os
import re
import time

PREDEFINITO = "predefinito"
MODI = ("spento", "solo-registro", "bloccante")
MODO_DEFAULT = "spento"

REGISTRO_MAX_BYTE = 5 * 1024 * 1024
# Una riga "config illeggibile" al massimo ogni tanto: senza questo limite
# ogni strumento di ogni sessione ne scriverebbe una, e il registro (che deve
# restare leggibile) sarebbe tutto li'.
NOTA_CONFIG_OGNI_SECONDI = 600

# --------------------------------------------------------------------------
# l'elenco neutro di un compartimento nominato
# --------------------------------------------------------------------------

# Binari e ambienti che ogni sessione deve poter leggere per lavorare, e che
# non portano lavoro di nessuno. Costante e commentata apposta: e' il punto in
# cui si decide cosa e' "di tutti".
#
# /tmp NON c'e' per i nominati: una cartella temporanea condivisa e' un posto
# dove un compartimento lascia un file e l'altro lo trova. Ogni nominato ha
# solo la propria cartella di sessione sotto `/private/tmp/claude-<uid>/`
# (vedi `_scratch_ok`). Anche `/var/folders` (la TMPDIR per utente di macOS)
# resta fuori, per lo stesso motivo.
NEUTRI_FISSI = (
    "/usr",                       # binari e librerie di sistema
    "/bin", "/sbin",
    "/etc",                       # configurazione di sistema, in sola lettura
    "/System",
    "/opt/homebrew",              # Homebrew su Apple Silicon
    "/Library/Developer",         # Command Line Tools
    "/Library/Frameworks",        # Python.framework e simili
    "/Applications/Xcode.app",
    # Dispositivi che i comandi nominano di continuo ("2>/dev/null"): non
    # portano contenuto di nessuno.
    "/dev/null", "/dev/zero", "/dev/random", "/dev/urandom",
    "/dev/stdin", "/dev/stdout", "/dev/stderr", "/dev/tty", "/dev/fd",
)
# Sotto la home di chi lancia l'hook.
NEUTRI_HOME = (
    ".local/bin",                 # comandi installati per l'utente
    ".pyenv",                     # ambienti Python
    "Library/Python",             # site-packages e binari utente di Python
)

# Strumenti MCP del Drive che un nominato puo' usare solo su id ammessi. Un
# altro nome si aggiunge con la chiave di config `strumenti_drive`.
STRUMENTI_DRIVE = (
    "read_file_content", "download_file_content", "search_files",
    "list_recent_files", "get_file_metadata", "get_file_permissions",
    "copy_file", "create_file", "update_file", "share_file", "trash_file",
)
# Quelli che elencano tutto il Drive: per un nominato non c'e' id che tenga.
STRUMENTI_DRIVE_ELENCO = ("search_files", "list_recent_files")
CHIAVI_ID_DRIVE = ("fileId", "file_id", "id", "parentId", "parent_id",
                   "folderId", "folder_id")

PREFISSO_SESSIONI = "mcp__ccd_session_mgmt__"
CHIAVI_ID_SESSIONE = ("session_id", "sessionId", "id", "target_session_id")
CHIAVI_LISTA_SESSIONI = ("session_ids", "sessionIds")
# Strumenti di sessione senza bersaglio che non guardano altre sessioni.
SESSIONI_SENZA_BERSAGLIO_OK = ("get_usage",)

# Chiavi di tool_input che portano un percorso (o una lista di percorsi).
CHIAVI_PERCORSO = ("file_path", "path", "notebook_path", "directory", "cwd",
                   "dir", "root")
CHIAVI_LISTA_PERCORSI = ("files", "paths", "file_paths")
# Chiavi che portano un url: un `file:` e' un percorso (WebFetch, i browser).
CHIAVI_URL = ("url", "uri")

# I tetti dell'analisi di un comando. Nomi semplici (`cd cartella`): 300 per
# comando; voci espanse dai glob: 1000 per comando (200 per token, sotto);
# percorsi in tutto: 5000. Oltre il tetto il resto NON si guarda, e non e' mai
# silenzioso: un nominato e' negato, il predefinito lascia una nota nel registro
# (`valuta`). Un percorso vero (`/...`) non e' mai fermato dal tetto dei nomi.
MAX_PERCORSI_COMANDO = 300
MAX_ESPANSIONE_TOTALE = 1000
MAX_PERCORSI_DURO = 5000
MAX_ESPANSIONE_GLOB = 200

# Le sessioni "misurate": strumenti dell'app che cercano o elencano fra TUTTE
# le sessioni, senza un bersaglio. Per il predefinito non si possono negare
# (limite dichiarato), ma in `solo-registro` se ne scrive una riga, per sapere
# quanto si usano prima di decidere cosa farne.
SESSIONI_DA_MISURARE = ("list_sessions",)
# Strumenti che cercano nel CONTENUTO delle trascrizioni di tutte le sessioni:
# negati ai nominati sempre e al predefinito quando esistono nominati (non c'e'
# un id che li renda ammissibili: cercano dappertutto).
SESSIONI_RICERCA = ("search_session_transcripts",)

# Strumenti che scrivono un file con `file_path`/`notebook_path`.
STRUMENTI_SCRITTURA = ("Write", "Edit", "MultiEdit", "NotebookEdit")

# Il registro dell'app: `<home>/Library/Application Support/Claude/
# claude-code-sessions/*/*/local_<uuid>.json`, con `sessionId` (l'id `local_`
# che gli strumenti di sessione ricevono), `cliSessionId` (il `session_id`
# dell'hook: e' il nome del .jsonl), `cwd`, `originCwd` e `title`.
_RX_LOCAL = re.compile(r"^local_[0-9A-Za-z-]{1,80}$")
MAX_FILE_REGISTRO_APP = 5000

_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


# --------------------------------------------------------------------------
# percorsi
# --------------------------------------------------------------------------

def percorso_dati(env=None) -> str:
    """La cartella dati di Plancia: la stessa regola di `config.DATA_DIR`
    (PLANCIA_HOME, altrimenti ~/.plancia), senza importare `config`."""
    env = os.environ if env is None else env
    return env.get("PLANCIA_HOME") or os.path.join(os.path.expanduser("~"), ".plancia")


def _norm(p, base=None) -> str:
    """Percorso assoluto, con i symlink risolti fino in fondo. Funziona anche
    su un percorso che non esiste (risolve i pezzi iniziali che esistono).
    Stringa vuota se non e' un percorso usabile."""
    if not isinstance(p, str) or not p or "\x00" in p:
        return ""
    try:
        p = os.path.expanduser(p)
        if not os.path.isabs(p):
            p = os.path.join(base or os.getcwd(), p)
        r = os.path.realpath(p)
    except (OSError, ValueError):
        return ""
    return r.rstrip("/") or "/"


def _codifica(p: str) -> str:
    """Come Claude Code trasforma una cartella nel nome che le da' sotto
    `~/.claude/projects`: ogni carattere non `[A-Za-z0-9]` diventa un trattino,
    uno per uno (stessa regola di `plancia/esclusi.py:_codifica`, ripetuta:
    quella sta in un modulo che importa il database)."""
    return re.sub(r"[^A-Za-z0-9]", "-", p)


def _dentro(p: str, radice: str) -> bool:
    """`p` e' `radice` o sta sotto. Senza distinzione di maiuscole (vedi i
    limiti nel docstring del modulo)."""
    if not p or not radice:
        return False
    a, b = p.lower(), radice.lower().rstrip("/")
    if b == "":
        return True
    return a == b or a.startswith(b + "/")


def _ha_glob(s: str) -> bool:
    return any(c in s for c in "*?[")


_CACHE_RX_GLOB = {}


def _classe_glob(m: str, i: int, barre: bool):
    """La classe fra parentesi quadre che comincia in `m[i]` (subito dopo la `[`),
    come `(espressione_regolare, indice_dopo_la_])`, o `(None, i)` se NON e' una classe
    e la `[` va presa come un carattere qualsiasi: nessuna `]` che la chiude
    (`file[1`), o un intervallo invertito (`[i-2]`, `[z-a]`, `[[-1]`), come fa il glob di
    bash con quello che non capisce. Ogni carattere finisce nella regex con
    `re.escape`: il testo del comando non puo' costruire una regex non valida."""
    n = len(m)
    j = i
    nega = j < n and m[j] in "!^"
    if nega:
        j += 1
    inizio = j
    if j < n and m[j] == "]":       # una `]` subito dopo la `[` (o la `[!`) e' un carattere
        j += 1
    while j < n and m[j] != "]":
        j += 1
    if j >= n:
        return None, i
    corpo = m[inizio:j]
    pezzi = []
    k = 0
    while k < len(corpo):
        lo = corpo[k]
        if k + 2 < len(corpo) and corpo[k + 1] == "-":
            hi = corpo[k + 2]
            if lo > hi:
                return None, i
            pezzi.append(re.escape(lo) + "-" + re.escape(hi))
            k += 3
        else:
            pezzi.append(re.escape(lo))
            k += 1
    return "[" + ("^" if nega else "") + ("" if barre else "/" if nega else "") \
        + "".join(pezzi) + "]", j + 1


# Tetti del glob: un modello piu' lungo o con piu' stelle di cosi' non e' un glob di
# nessuno (un file, un divieto di un manifesto), e vale come testo letterale.
_MAX_GLOB = 512
_MAX_STELLE = 24


def _rx_glob(modello: str, barre: bool):
    """La regex compilata (da usare con `fullmatch`) di un modello glob. Con `barre` il `*`
    e il `?` attraversano le barre (come `fnmatch`, per i divieti con un percorso); senza,
    valgono dentro un solo componente (come il glob di shell). Costruita a mano, non con
    `fnmatch.translate` (e `glob.glob`, che ci passa): la sua traduzione di `[i-2]` o di
    `[[-1]` e' una regex non valida (`re.error: bad character range`), e il testo di un
    comando (`t[i-2:i+2]` dentro uno script, `arr[[-1]`) non deve poter rompere il guardiano.
    Un modello che non si traduce non torna mai un errore: vale come testo letterale.

    Il tempo e' polinomiale, mai esponenziale (al piu' la lunghezza del nome per la lunghezza
    del pezzo, per ogni stella): il guardiano gira prima di OGNI strumento, e con la
    traduzione ingenua (ogni `*` diventa `[^/]*`) un modello come `*a*a*a*a*a*a*b` su un nome
    di sessanta `a` impiega secondi, poi minuti (backtracking catastrofico). Qui, come fa
    `fnmatch.translate` da Python 3.9, un `*` seguito da un pezzo
    fisso si scrive `(?=(?P<gN>.*?fisso))(?P=gN)`: la ricerca del pezzo sta in un'asserzione
    che, una volta riuscita, non si rimette in discussione, e la regex non prova le altre
    posizioni. L'ultimo `*` del modello resta un `*` normale. Il tempo non dipende dalla
    versione di Python, perche' la traduzione e' questa e non quella della libreria.
    Un modello di piu' di `_MAX_GLOB` caratteri o di piu' di `_MAX_STELLE` stelle vale come
    testo letterale."""
    chiave = (modello, barre)
    rx = _CACHE_RX_GLOB.get(chiave)
    if rx is not None:
        return rx
    _STELLA = None
    pezzi = []
    if len(modello) <= _MAX_GLOB:
        i, n = 0, len(modello)
        while i < n:
            c = modello[i]
            i += 1
            if c == "*":
                while i < n and modello[i] == "*":
                    i += 1
                pezzi.append(_STELLA)
            elif c == "?":
                pezzi.append("." if barre else "[^/]")
            elif c == "[":
                classe, dopo = _classe_glob(modello, i, barre)
                if classe is None:
                    pezzi.append(re.escape("["))
                else:
                    pezzi.append(classe)
                    i = dopo
            else:
                pezzi.append(re.escape(c))
    try:
        if len(modello) > _MAX_GLOB or pezzi.count(_STELLA) > _MAX_STELLE:
            raise OverflowError("modello troppo grande")
        stella = ".*" if barre else "[^/]*"
        out, i, n, gruppi = [], 0, len(pezzi), 0
        while i < n and pezzi[i] is not _STELLA:            # i pezzi fissi all'inizio
            out.append(pezzi[i])
            i += 1
        while i < n:                                        # STELLA fisso STELLA fisso ...
            i += 1
            if i == n:
                out.append(stella)
                break
            fisso = []
            while i < n and pezzi[i] is not _STELLA:
                fisso.append(pezzi[i])
                i += 1
            fisso = "".join(fisso)
            if i == n:
                out.append(stella + fisso)
            else:
                nome = "g%d" % gruppi
                gruppi += 1
                out.append("(?=(?P<%s>%s?%s))(?P=%s)" % (nome, stella, fisso, nome))
        rx = re.compile("".join(out), re.S)
    except (re.error, RecursionError, OverflowError):
        rx = re.compile(re.escape(modello), re.S)
    if len(_CACHE_RX_GLOB) > 512:
        _CACHE_RX_GLOB.clear()
    _CACHE_RX_GLOB[chiave] = rx
    return rx


def _glob_combacia(nome: str, modello: str, barre: bool = True) -> bool:
    """`nome` combacia con il modello glob (intero, come `fnmatch.fnmatchcase`)."""
    return _rx_glob(modello, barre).fullmatch(nome) is not None


# --------------------------------------------------------------------------
# il registro dell'app: da un id `local_...` (o da un titolo) alla sessione
# --------------------------------------------------------------------------

def _leggi_voce_app(percorso: str):
    try:
        if os.path.getsize(percorso) > 4 * 1024 * 1024:
            return None
        with open(percorso, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not isinstance(d, dict):
        return None

    def testo(k):
        v = d.get(k)
        return v if isinstance(v, str) else ""
    return {"local": testo("sessionId"), "cli": testo("cliSessionId"),
            "cwd": testo("cwd"), "origine": testo("originCwd"),
            "titolo": testo("title")}


def _voci_app(home: str, chiave=None, titolo=None, cli=None) -> list:
    """Le sessioni del registro dell'app che corrispondono a un id `local_`
    (`chiave`) o a un titolo (senza distinzione di maiuscole). Il titolo
    costringe a leggere tutti i file del registro (poche centinaia): si fa
    solo per gli strumenti di sessione che ricevono un nome. Un id `local_`
    e' un solo file. Con `cli` (un `session_id` crudo, un uuid: il nome del
    `.jsonl`) si cerca il `cliSessionId`, e anche questo legge tutto il registro."""
    import glob
    base = os.path.join(glob.escape(home), "Library", "Application Support",
                        "Claude", "claude-code-sessions", "*", "*")
    if chiave is not None:
        if not _RX_LOCAL.match(chiave):
            return []
        pattern = os.path.join(base, chiave + ".json")
    else:
        pattern = os.path.join(base, "local_*.json")
    voci = []
    try:
        trovati = sorted(glob.glob(pattern))
    except OSError:
        return []
    for percorso in trovati[:MAX_FILE_REGISTRO_APP]:
        v = _leggi_voce_app(percorso)
        if not v:
            continue
        if titolo is not None and v["titolo"].lower() != titolo.lower():
            continue
        if cli is not None and v["cli"] != cli:
            continue
        if not v["local"] and chiave:
            v["local"] = chiave
        voci.append(v)
    return voci


# --------------------------------------------------------------------------
# config: lettura, validazione, copia dell'ultima valida
# --------------------------------------------------------------------------

def _lista_str(v, nome):
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ValueError(f"{nome} non e' una lista di stringhe")
    return list(v)


def valida_compartimenti(raw):
    """`compartimenti` di config.json, controllato. Torna la stessa struttura
    con le liste sempre presenti, o solleva ValueError con il motivo. Un
    tipo sbagliato in qualunque punto rende TUTTA la sezione inaffidabile
    (fail-closed: vedi `carica()`)."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("compartimenti non e' un oggetto")
    out = {}
    for nome, c in raw.items():
        if not isinstance(nome, str) or not nome:
            raise ValueError("nome di compartimento non valido")
        if not isinstance(c, dict):
            raise ValueError(f"compartimento {nome!r} non e' un oggetto")
        if nome == PREDEFINITO:
            man = c.get("manifesto_divieti")
            if man is not None and not isinstance(man, str):
                raise ValueError("manifesto_divieti non e' una stringa")
            out[nome] = {
                "manifesto_divieti": man or "",
                "divieti": _lista_str(c.get("divieti"), "divieti"),
                "comandi_vietati": _lista_str(c.get("comandi_vietati"),
                                              "comandi_vietati"),
            }
        else:
            out[nome] = {
                "cartelle": _lista_str(c.get("cartelle"), "cartelle"),
                "sessioni": _lista_str(c.get("sessioni"), "sessioni"),
                "drive_ids": _lista_str(c.get("drive_ids"), "drive_ids"),
            }
    return out


def _da_json(letta, solo_modo=False):
    """(modo, compartimenti, strumenti_drive, condivise) da un oggetto gia' letto, o
    ValueError. Con `solo_modo` e modo `spento` non si guarda altro: uno spento con
    un resto scritto male e' comunque spento (l'hook spento non legge niente oltre
    il modo)."""
    if not isinstance(letta, dict):
        raise ValueError("config.json non e' un oggetto")
    modo = letta.get("guardiano", MODO_DEFAULT)
    if not isinstance(modo, str) or modo.strip().lower() not in MODI:
        raise ValueError("guardiano: modo sconosciuto")
    modo = modo.strip().lower()
    if solo_modo and modo == "spento":
        return modo, {}, [], []
    comp = valida_compartimenti(letta.get("compartimenti"))
    drive = _lista_str(letta.get("strumenti_drive"), "strumenti_drive")
    condivise = _lista_str(letta.get("condivise"), "condivise")
    return modo, comp, drive, condivise


def leggi_config(data_dir: str, rapida: bool = False) -> dict:
    """Legge `config.json` SENZA scriverlo e senza creare cartelle. Con
    `rapida` (l'hook) un `guardiano: "spento"` non valida il resto.

    Torna `{"stato": "assente"|"ok"|"rotta", "modo", "compartimenti",
    "strumenti_drive", "errore"}`. `assente`: il file non c'e' (guardiano
    spento, come da default)."""
    r = {"stato": "ok", "modo": MODO_DEFAULT, "compartimenti": {},
         "strumenti_drive": [], "condivise": [], "errore": None}
    percorso = os.path.join(data_dir, "config.json")
    try:
        with open(percorso, "r", encoding="utf-8") as f:
            testo = f.read()
    except FileNotFoundError:
        r["stato"] = "assente"
        return r
    except (OSError, UnicodeDecodeError) as exc:
        r["stato"], r["errore"] = "rotta", f"config.json non leggibile: {exc}"
        r["permessi"] = isinstance(exc, PermissionError)
        return r
    try:
        (r["modo"], r["compartimenti"], r["strumenti_drive"],
         r["condivise"]) = _da_json(json.loads(testo), rapida)
    except (ValueError, RecursionError) as exc:
        r["stato"], r["errore"] = "rotta", f"config.json non valido: {exc}"
    return r


def _percorso_copia(data_dir: str) -> str:
    return os.path.join(data_dir, "compartimenti.ultima-valida.json")


def _leggi_copia(data_dir: str):
    """L'ultima config valida salvata, o None (assente, illeggibile, non piu'
    valida)."""
    try:
        with open(_percorso_copia(data_dir), "r", encoding="utf-8") as f:
            modo, comp, drive, condivise = _da_json(json.load(f))
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    return {"modo": modo, "compartimenti": comp, "strumenti_drive": drive,
            "condivise": condivise}


def _salva_copia_se_diversa(data_dir: str, cfg: dict) -> None:
    """Scrive la copia solo se cambia: una scrittura a ogni strumento sarebbe
    rumore e usura. Scrittura atomica (file temporaneo + rename): un hook
    interrotto a meta' non deve lasciare una copia tagliata."""
    nuovo = json.dumps({"guardiano": cfg["modo"],
                        "compartimenti": cfg["compartimenti"],
                        "strumenti_drive": cfg["strumenti_drive"],
                        "condivise": cfg.get("condivise", [])},
                       indent=2, sort_keys=True, ensure_ascii=False)
    dest = _percorso_copia(data_dir)
    try:
        with open(dest, "r", encoding="utf-8") as f:
            if f.read() == nuovo:
                return
    except OSError:
        pass
    try:
        os.makedirs(data_dir, exist_ok=True)
        tmp = f"{dest}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(nuovo)
        os.replace(tmp, dest)
    except OSError:
        pass


def carica(data_dir: str) -> dict:
    """La configurazione EFFETTIVA del guardiano, con le regole di guasto.

    - config assente o `guardiano: "spento"`: spento, non si legge altro
      (se esiste la copia dell'ultima valida la si riscrive come spento).
    - config valida: si usa, e (se non spento) se ne tiene la copia.
    - config rotta CON copia valida: si usa la copia, modo compreso: un
      nominato resta confinato (fail-closed per i nominati).
    - config rotta SENZA copia: `solo-registro` per tutti, con una riga
      "config illeggibile" (limitata nel tempo). Il predefinito non viene mai
      bloccato per un errore di config.

    Torna `{"modo", "compartimenti", "strumenti_drive", "stato", "nota"}`.
    `nota` e' il testo della riga di registro da scrivere, o None."""
    c = leggi_config(data_dir, rapida=True)
    if c["stato"] == "ok" and c["modo"] == "spento":
        # `spento` e' una config valida come le altre: se c'e' una copia
        # dell'ultima valida la si aggiorna, altrimenti una virgola in piu' in
        # config.json (a mano, il file e' condiviso con il resto di Plancia)
        # rimetterebbe in piedi il vecchio `bloccante` che l'utente aveva
        # spento. Senza copia non se ne crea una: spento non scrive niente.
        if os.path.exists(_percorso_copia(data_dir)):
            _salva_copia_se_diversa(data_dir, {
                "modo": "spento", "compartimenti": {}, "strumenti_drive": [],
                "condivise": []})
        return {"modo": "spento", "compartimenti": {}, "strumenti_drive": [],
                "condivise": [], "stato": "ok", "nota": None, "avviso": None}
    if c["stato"] == "assente":
        return {"modo": "spento", "compartimenti": {}, "strumenti_drive": [],
                "condivise": [], "stato": c["stato"], "nota": None, "avviso": None}
    if c["stato"] == "ok":
        _salva_copia_se_diversa(data_dir, c)
        return {"modo": c["modo"], "compartimenti": c["compartimenti"],
                "strumenti_drive": c["strumenti_drive"],
                "condivise": c["condivise"], "stato": "ok", "nota": None,
                "avviso": None}
    # un config.json che esiste e non si legge per permessi (una cartella dei dati
    # con `chmod 000`) spegne il guardiano senza rumore: l'avviso lo dice
    avviso = None
    if c.get("permessi"):
        avviso = ("plancia-guardiano non legge la sua config (%s): senza, i "
                  "compartimenti non sono protetti finche' non si ripristinano i "
                  "permessi." % (c["errore"],))
    copia = _leggi_copia(data_dir)
    if copia is not None:
        return {"modo": copia["modo"], "compartimenti": copia["compartimenti"],
                "strumenti_drive": copia["strumenti_drive"],
                "condivise": copia["condivise"], "stato": "copia",
                "nota": "config illeggibile (%s): uso l'ultima valida"
                        % (c["errore"],), "avviso": avviso}
    return {"modo": "solo-registro", "compartimenti": {}, "strumenti_drive": [],
            "condivise": [], "stato": "rotta",
            "nota": "config illeggibile (%s): nessuna copia valida, "
                    "solo-registro per tutti" % (c["errore"],), "avviso": avviso}


# --------------------------------------------------------------------------
# registro
# --------------------------------------------------------------------------

def _percorso_registro(data_dir: str) -> str:
    return os.path.join(data_dir, "guardiano.log")


def scrivi_registro(data_dir: str, riga: dict) -> None:
    """Una riga JSON in `guardiano.log`. Rotazione semplice: oltre 5 MB il
    file diventa `.1` (sostituendo l'eventuale `.1` precedente). Non solleva
    mai: un registro che non si scrive non deve fermare un hook."""
    try:
        os.makedirs(data_dir, exist_ok=True)
        p = _percorso_registro(data_dir)
        try:
            if os.path.getsize(p) > REGISTRO_MAX_BYTE:
                os.replace(p, p + ".1")
        except OSError:
            pass
        riga = dict(riga)
        riga.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        dati = (json.dumps(riga, ensure_ascii=False) + "\n").encode("utf-8")
        fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, dati)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        pass


def _nota_config_dovuta(data_dir: str, nome_marca: str = "guardiano.config-illeggibile") -> bool:
    """Vero se e' ora di scrivere di nuovo la riga "config illeggibile" (o un'altra
    nota, con la sua marca). Se la marca non si puo' scrivere (la cartella dei dati
    senza permessi) e' sempre ora."""
    marca = os.path.join(data_dir, nome_marca)
    try:
        if time.time() - os.path.getmtime(marca) < NOTA_CONFIG_OGNI_SECONDI:
            return False
    except OSError:
        pass
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(marca, "w") as f:
            f.write("")
    except OSError:
        pass
    return True


def leggi_registro(data_dir: str, n: int = 20) -> list:
    """Le ultime `n` righe del registro, come dizionari (le righe rotte si
    saltano)."""
    try:
        with open(_percorso_registro(data_dir), "rb") as f:
            f.seek(0, os.SEEK_END)
            dim = f.tell()
            f.seek(max(0, dim - 2 * 1024 * 1024))
            testo = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    righe = []
    for linea in testo.splitlines():
        try:
            d = json.loads(linea)
        except ValueError:
            continue
        if isinstance(d, dict):
            righe.append(d)
    return righe[-n:] if n > 0 else []


def _epoch(ts) -> float:
    import calendar
    return calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))


def stato(data_dir: str) -> dict:
    """Modo, compartimenti (nomi e numero di cartelle, MAI i percorsi) e
    righe di registro nelle ultime 24 ore. Sola lettura."""
    c = leggi_config(data_dir)
    copia = _leggi_copia(data_dir) if c["stato"] == "rotta" else None
    if c["stato"] == "ok":
        comp, modo = c["compartimenti"], c["modo"]
    elif copia:
        comp, modo = copia["compartimenti"], copia["modo"]
    else:
        comp = {}
        modo = MODO_DEFAULT if c["stato"] == "assente" else "solo-registro"
    elenco = []
    for nome, v in sorted(comp.items()):
        if nome == PREDEFINITO:
            elenco.append({"nome": nome, "divieti": len(v["divieti"]),
                           "comandi_vietati": len(v["comandi_vietati"]),
                           "manifesto": bool(v["manifesto_divieti"])})
        else:
            elenco.append({"nome": nome, "cartelle": len(v["cartelle"]),
                           "sessioni": len(v["sessioni"]),
                           "drive_ids": len(v["drive_ids"])})
    soglia = time.time() - 24 * 3600
    recenti = {"negato": 0, "avrebbe-negato": 0, "altro": 0}
    non_parte = {"righe": 0, "ultima": None}
    for d in leggi_registro(data_dir, 100000):
        try:
            t = _epoch(d.get("ts"))
        except (ValueError, TypeError):
            continue
        if t < soglia:
            continue
        e = d.get("esito")
        if e == "guardiano-non-parte":
            # scritta da `bin/plancia-guardiano` quando il pacchetto non si
            # importa o l'hook solleva: il guardiano e' spento per tutti
            non_parte["righe"] += 1
            non_parte["ultima"] = {"ts": d.get("ts"), "motivo": d.get("motivo")}
            continue
        recenti[e if e in recenti else "altro"] += 1
    if c["stato"] == "ok":
        condivise = len(c["condivise"])
    else:
        condivise = len(copia["condivise"]) if copia else 0
    return {"modo": modo, "config": c["stato"], "errore": c["errore"],
            "usa_copia": bool(copia), "compartimenti": elenco,
            "condivise": condivise,
            "registro_24h": recenti, "non_parte": non_parte}


# --------------------------------------------------------------------------
# l'insieme dei compartimenti, pronto per decidere
# --------------------------------------------------------------------------

def voce_condivisa_vietata(raw, data_dir, claude_dir=None, home=None):
    """Il motivo per cui una voce di `condivise` non puo' essere condivisa, o None. Non
    si condividono mai: la cartella dei dati di Plancia (ne' una che la contiene o sta
    dentro), `<claude>/projects` (trascrizioni e memoria: ne' una che la contiene o sta
    dentro), la cartella di configurazione di Claude (`<claude>` o un antenato), la
    home e i suoi antenati, la radice del disco. Una voce che contenga una di queste
    aprirebbe a ogni ricerca ricorsiva il lavoro degli altri compartimenti. Una
    cartella DENTRO `<claude>` che non e' `projects` (per esempio le skill) va bene.
    Lo usano `Ambito` (ignora la voce con una nota) e `plancia config condivise`
    (la rifiuta)."""
    e = os.path.expanduser(raw) if isinstance(raw, str) else ""
    n = _norm(e) if os.path.isabs(e) else ""
    if not n:
        return "non e' una cartella assoluta"
    if n == "/":
        return "e' la radice del disco"
    home_n = _norm(home or os.path.expanduser("~"))
    claude_n = _norm(claude_dir or cartella_claude(home=home))
    progetti = _norm(os.path.join(claude_n, "projects")) if claude_n else ""
    dati = _norm(data_dir) if data_dir else ""
    if dati and (_dentro(n, dati) or _dentro(dati, n)):
        return ("e' la cartella dei dati di Plancia, sta dentro o la contiene (i dati non "
                "sono mai condivisi)")
    if progetti and (_dentro(n, progetti) or _dentro(progetti, n)):
        return ("e' `<claude>/projects`, sta dentro o la contiene (trascrizioni e memoria "
                "non sono mai condivise)")
    if claude_n and _dentro(claude_n, n):
        return "e' la cartella di configurazione di Claude o un suo antenato"
    if home_n and _dentro(home_n, n):
        return "e' la home o un suo antenato"
    return None


class Ambito:
    """I compartimenti di una config, con i percorsi gia' risolti."""

    def __init__(self, comp: dict, strumenti_drive=None, home=None, uid=None,
                 data_dir=None, claude_dir=None, condivise=None):
        self.home = home or os.path.expanduser("~")
        # Su Windows `os.getuid` non esiste: l'uid serve solo a riconoscere la
        # cartella temporanea di Claude Code sul Mac (/private/tmp/claude-<uid>).
        if uid is None and hasattr(os, "getuid"):
            uid = os.getuid()
        self.uid = uid
        self.data_dir = data_dir or ""
        # `<CLAUDE_CONFIG_DIR o ~/.claude>/projects`: dove Claude Code tiene
        # trascrizioni e memoria di ogni cartella (vedi `proprietario_specchio`).
        self.claude_dir = claude_dir or cartella_claude(home=self.home)
        self.progetti = _norm(os.path.join(self.claude_dir, "projects"))
        self.strumenti_drive = set(STRUMENTI_DRIVE) | set(strumenti_drive or [])
        self.nominati = {}
        for nome, c in comp.items():
            if nome == PREDEFINITO:
                continue
            cartelle, codifiche = [], set()
            for raw in c["cartelle"]:
                n = _norm(raw)
                if not n:
                    continue
                cartelle.append(n)
                # La codifica si prova sia sulla grafia scritta sia su quella
                # risolta: Claude Code codifica la cwd com'e' stata aperta.
                codifiche.add(_codifica(os.path.expanduser(raw)).lower())
                codifiche.add(_codifica(n).lower())
            # `sessioni` accetta il `session_id` dell'hook (il nome del .jsonl)
            # e l'id `local_<uuid>` dell'app: questo si traduce nel
            # `cliSessionId` leggendo il registro dell'app, cosi' chi chiama
            # (che ha solo il session_id) si riconosce in tutti e due i modi.
            sessioni = set(c["sessioni"])
            for s in c["sessioni"]:
                if s.startswith("local_"):
                    for v in _voci_app(self.home, chiave=s):
                        if v["cli"]:
                            sessioni.add(v["cli"])
            self.nominati[nome] = {
                "cartelle": cartelle, "codifiche": codifiche,
                "sessioni": sessioni,
                "drive_ids": set(c["drive_ids"]),
            }
        pred = comp.get(PREDEFINITO) or {}
        self.divieti_raw = list(pred.get("divieti") or [])
        self.manifesto = pred.get("manifesto_divieti") or ""
        self.comandi_vietati = [s for s in (pred.get("comandi_vietati") or []) if s]
        self._divieti = None
        self._neutri = None
        # Cartelle di CODICE CONDIVISE (`condivise` di config): tutti i
        # compartimenti le LEGGONO e ci ESEGUONO, nessuno ci SCRIVE fuori dai propri
        # permessi. Servono i checkout degli strumenti che una sessione di un
        # nominato lancia (Plancia stessa, boa). Mai condivisa: la cartella dei dati
        # di Plancia (PLANCIA_HOME), anche se sta dentro una cartella condivisa; una
        # voce che e' quella cartella o sta dentro si ignora, con una nota.
        self.dati_norm = _norm(self.data_dir) if self.data_dir else ""
        self.condivise, self.note = [], []
        for raw in condivise or []:
            e = os.path.expanduser(raw)
            n = _norm(e) if os.path.isabs(e) else ""
            perche = voce_condivisa_vietata(raw, self.data_dir, self.claude_dir, self.home)
            if perche:
                # ignorata con una nota (senza il percorso: il registro non lo
                # ripete): una voce che contiene i dati o le trascrizioni aprirebbe a
                # ogni ricerca ricorsiva il lavoro degli altri
                self.note.append("condivise: una voce %s: ignorata" % perche)
            elif n not in self.condivise:
                self.condivise.append(n)

    def riservata_inclusa(self, p: str, ric=True):
        """`p` (dentro una cartella condivisa) e' una ricerca che entra nella cartella dei
        dati di Plancia o in `<claude>/projects`? Il nome della cartella, o None. Una
        voce di `condivise` non le contiene mai (`voce_condivisa_vietata`): questa e'
        la seconda difesa, se una voce ci arrivasse lo stesso."""
        for r in (self.dati_norm, self.progetti):
            if r and _dentro(r, p) and _ric(ric, _prof(r, p)):
                return r
        return None

    def in_condivisa(self, p: str) -> bool:
        """`p` sta in una cartella di codice condivisa. Non la cartella dei dati di
        Plancia ne' `<claude>/projects` (trascrizioni e memoria), anche se una voce
        di `condivise` le contiene."""
        if not self.condivise or not p:
            return False
        if self.dati_norm and _dentro(p, self.dati_norm):
            return False
        if self.progetti and _dentro(p, self.progetti):
            return False
        return any(_dentro(p, c) for c in self.condivise)

    def neutri(self):
        """L'elenco neutro, risolto una volta per chiamata."""
        if self._neutri is None:
            elenco = [_norm(p) for p in NEUTRI_FISSI]
            elenco += [_norm(os.path.join(self.home, p)) for p in NEUTRI_HOME]
            self._neutri = [p for p in elenco if p]
        return self._neutri

    def divieti(self):
        """Lista di `(letterale, glob)`: `glob` e' None per un percorso
        letterale (gia' risolto), altrimenti il modello. Si costruisce una
        volta per chiamata e solo se serve (il manifesto e' un file da
        leggere)."""
        if self._divieti is not None:
            return self._divieti
        # Ogni riga con la cartella rispetto a cui si risolve se e' relativa
        # con una barra: quella dei dati per `divieti`, quella del manifesto per
        # le sue righe. Mai la cwd dell'hook: cambia da una sessione all'altra e
        # un divieto relativo colpirebbe posti diversi a seconda di dove si e'.
        righe = [(r, self.data_dir) for r in self.divieti_raw]
        if self.manifesto:
            man = os.path.expanduser(self.manifesto)
            try:
                with open(man, "r", encoding="utf-8") as f:
                    for linea in f.read().splitlines():
                        linea = linea.strip()
                        if linea and not linea.startswith("#"):
                            righe.append((linea, os.path.dirname(
                                os.path.abspath(man))))
            except (OSError, UnicodeDecodeError):
                # Un manifesto illeggibile non blocca il predefinito (vedi
                # `carica`): perde solo quelle righe, e la prova del
                # manifesto e' li' apposta per accorgersene.
                pass
        out = []
        for riga, base in righe:
            riga = os.path.expanduser(riga)
            if base and "/" in riga and not os.path.isabs(riga):
                riga = os.path.join(base, riga)
            if _ha_glob(riga):
                out.append((_prefisso_letterale(riga), _norm_glob(riga)))
            else:
                n = _norm(riga) if "/" in riga else riga
                if n:
                    out.append((n, None))
        self._divieti = out
        return out

    def proprietari_percorso(self, p: str) -> list:
        """I nomi dei nominati che possiedono `p`, col criterio del PIU'
        SPECIFICO: se le cartelle sono annidate (alfa in `/w/alfa`, beta in
        `/w/alfa/beta`) un percorso e' del nominato la cui cartella lo contiene
        con piu' componenti (per componenti, non per prefisso di stringa),
        qualunque sia l'ordine della config. Due nominati sulla STESSA cartella
        (config sbagliata) sono due nomi: chi decide tratta il percorso come
        incerto. Lista vuota se non e' di nessuno."""
        migliore, nomi = -1, []
        for nome, c in self.nominati.items():
            for f in c["cartelle"]:
                if _dentro(p, f):
                    d = _n_componenti(f)
                    if d > migliore:
                        migliore, nomi = d, [nome]
                    elif d == migliore and nome not in nomi:
                        nomi.append(nome)
        return nomi

    def proprietario_percorso(self, p: str):
        """Il nome del nominato che possiede `p` (il piu' specifico), o None. Con
        un percorso ambiguo (due nominati sulla stessa cartella) il primo:
        serve a dare un nome al diniego, non a decidere."""
        nomi = self.proprietari_percorso(p)
        return nomi[0] if nomi else None

    def proprietari_codifica(self, cod: str) -> list:
        """I nominati a cui appartiene una cartella di apertura CODIFICATA sotto
        `<claude>/projects` (`<enc>` o `<enc>-...`), col criterio del piu'
        specifico: vince la codifica piu' lunga. La codifica perde la differenza
        fra `/` e `-`, quindi `alfa-2` (sorella di `alfa`) risulta di alfa, e
        `alfa-beta` di un nominato che ha `alfa/beta`: in dubbio si confina. Due
        nominati con la stessa codifica sono due nomi."""
        cod = (cod or "").lower()
        migliore, nomi = -1, []
        if not cod:
            return nomi
        for nome, c in self.nominati.items():
            for e in c["codifiche"]:
                if cod == e or cod.startswith(e + "-"):
                    if len(e) > migliore:
                        migliore, nomi = len(e), [nome]
                    elif len(e) == migliore and nome not in nomi:
                        nomi.append(nome)
        return nomi

    def proprietario_specchio(self, p: str):
        """Il nome del nominato a cui appartiene `p` come SPECCHIO di una sua
        cartella sotto `<claude>/projects`: le trascrizioni, la memoria, le
        cartelle di sessione e dei subagenti di una cartella di X e delle sue
        discendenti sono lavoro di X. None se `p` non e' li' sotto o non e' di
        nessun nominato. Il confine e' il trattino: `<enc>` e `<enc>-...`
        (una discendente), non `<enc>altro` (una sorella con lo stesso inizio).
        Ma la codifica perde la differenza fra `/` e `-`, quindi una sorella
        `alfa-2` di `alfa` risulta di alfa: in dubbio si nega (vedi
        `proprietari_codifica`)."""
        if not p or not self.progetti or not _dentro(p, self.progetti):
            return None
        resto = p[len(self.progetti):].strip("/")
        if not resto:
            return None
        nomi = self.proprietari_codifica(resto.split("/")[0])
        return nomi[0] if nomi else None

    def specchio_incluso(self, p: str, ric=True):
        """Il nome di un nominato (con almeno una cartella) il cui specchio in
        `<claude>/projects` sta dentro `p` o e' `p` stessa: una ricerca ricorsiva
        che parte da `p` (`projects`, `~/.claude`, `~`) lo leggerebbe. `ric` e'
        il limite di profondita' della ricerca (True: nessuno). None se non ce
        n'e'."""
        if not p or not self.progetti or not _dentro(self.progetti, p):
            return None
        # la cartella di un nominato sta un livello sotto `projects`
        if not _ric(ric, _prof(self.progetti, p) + 1):
            return None
        for nome, c in self.nominati.items():
            if c["codifiche"]:
                return nome
        return None


def _n_componenti(p: str) -> int:
    return len([x for x in p.split("/") if x])


def _prof(f: str, p: str) -> int:
    """Quanti livelli sotto `p` sta `f` (0 se e' `p`); `f` deve stare dentro `p`."""
    return _n_componenti(f) - _n_componenti(p)


def cartella_claude(env=None, home=None) -> str:
    """La cartella di configurazione di Claude Code: `CLAUDE_CONFIG_DIR`, se
    c'e', altrimenti `~/.claude`."""
    env = os.environ if env is None else env
    return env.get("CLAUDE_CONFIG_DIR") or os.path.join(
        home or os.path.expanduser("~"), ".claude")


def proprietario_specchio(p: str, ambito: "Ambito"):
    """Il nominato a cui appartiene `p` come trascrizione, memoria o cartella
    di sessione sotto `<claude>/projects` (o None). `p` deve essere gia'
    risolto con `_norm`. E' la regola che il richiamo di Plancia (E1) usa per
    non leggere il lavoro di un compartimento nominato nelle trascrizioni."""
    return ambito.proprietario_specchio(p)


def _prefisso_letterale(pattern: str) -> str:
    """La parte di `pattern` prima del primo componente con un glob, risolta.
    `/a/b/*.txt` -> `/a/b`. Senza barre (un modello di nome): stringa vuota."""
    if "/" not in pattern or not os.path.isabs(pattern):
        return ""
    fisso = []
    for z in pattern.split("/"):
        if _ha_glob(z):
            break
        fisso.append(z)
    return _norm("/".join(fisso) or "/")


def _norm_glob(pattern: str) -> str:
    """Il modello con il prefisso letterale risolto (`/tmp` e' un symlink a
    `/private/tmp`: un modello scritto con l'uno deve valere per l'altro)."""
    if "/" not in pattern or not os.path.isabs(pattern):
        return pattern
    pezzi = pattern.split("/")
    fisso = []
    for z in pezzi:
        if _ha_glob(z):
            break
        fisso.append(z)
    coda = pezzi[len(fisso):]
    base = _norm("/".join(fisso) or "/")
    return (base.rstrip("/") + "/" + "/".join(coda)) if coda else base


def _combacia_glob(modello: str, p: str) -> bool:
    """Un divieto con glob contro un percorso.

    Con una barra e' un modello di percorso: vale per `p` e per ogni suo
    antenato (negare una cartella nega tutto quello che sta sotto). Il `*`
    attraversa le barre (come `fnmatch`): piu' largo, quindi piu' prudente. Senza
    barra e' un modello di NOME: vale se combacia un componente qualsiasi."""
    m, q = modello.lower(), p.lower()
    if "/" in m:
        parti = q.split("/")
        for i in range(2, len(parti) + 1):
            if _glob_combacia("/".join(parti[:i]) or "/", m):
                return True
        return False
    return any(_glob_combacia(c, m) for c in q.split("/") if c)


# --------------------------------------------------------------------------
# chi chiama
# --------------------------------------------------------------------------

def _da_trascrizione(tp, claude_dir=None):
    """`(id_madre, cartella_codificata, cartella_progetto)` da un
    `transcript_path`.

    Una sessione: `<progetti>/<codificata>/<id>.jsonl`. Un subagente:
    `<progetti>/<codificata>/<id madre>/subagents/[workflows/<x>/]agent-...
    .jsonl`: l'id della madre e' il componente che precede `subagents`. Un id
    ricavato da un percorso e' una AFFERMAZIONE di chi lo scrive, non un fatto:
    per un subagente conta solo se il file esiste davvero (realpath) dentro
    `<claude>/projects`, nella forma `<codificata>/<madre>/subagents/...`, e
    se esiste anche la trascrizione della madre (`<codificata>/<madre>.jsonl`)
    (`_madre_verificata`, stessa regola di boa). Senza `claude_dir` non si
    verifica (le funzioni che leggono una riga della tabella di Plancia)."""
    if not isinstance(tp, str) or not tp:
        return "", "", ""
    parti = tp.replace("\\", "/").split("/")
    if "subagents" in parti:
        i = parti.index("subagents")
        madre = parti[i - 1] if i >= 1 else ""
        codificata = parti[i - 2] if i >= 2 else ""
        progetto = "/".join(parti[:i - 1]) if i >= 2 else ""
        if claude_dir is not None and not _madre_verificata(tp, claude_dir):
            madre = ""
        return madre, codificata, progetto
    nome = parti[-1]
    madre = nome[:-6] if nome.endswith(".jsonl") else nome
    codificata = parti[-2] if len(parti) >= 2 else ""
    return madre, codificata, "/".join(parti[:-1])


def _madre_verificata(tp: str, claude_dir: str) -> bool:
    """Il transcript di un subagente esiste davvero sotto `<claude>/projects`
    e la madre ha il suo transcript."""
    try:
        reale = os.path.realpath(tp)
        if not os.path.isfile(reale):
            return False
        base = os.path.realpath(os.path.join(claude_dir, "projects"))
        if not reale.startswith(base + os.sep):
            return False
        rel = reale[len(base) + 1:].split(os.sep)
        if len(rel) < 4 or not rel[0] or not rel[1] or rel[2] != "subagents":
            return False
        return os.path.isfile(os.path.join(base, rel[0], rel[1] + ".jsonl"))
    except (OSError, ValueError):
        return False


def _nomi_da_segnali(ambito: Ambito, ids=(), cwds=(), codifiche=()) -> list:
    """I nomi dei compartimenti nominati a cui puntano i segnali: un id in
    `sessioni`, una cwd dentro le cartelle, una cartella di apertura
    codificata. Ne basta uno per compartimento (prudenza). Fra le cartelle
    annidate un segnale di cartella (cwd o codifica) vale per il nominato piu'
    specifico, non per quelli che la contengono soltanto: una sessione in
    `/w/alfa/beta/x` e' di beta, una in `/w/alfa/y` e' di alfa. Due nominati che
    elencano la stessa cartella sono tutti e due: la sessione e' incerta e ha i
    permessi di entrambi, cioe' quasi nessuno."""
    ids = {x for x in ids if x}
    nomi = set()
    for nome, c in ambito.nominati.items():
        if ids & c["sessioni"]:
            nomi.add(nome)
    for cw in cwds:
        if cw:
            nomi.update(ambito.proprietari_percorso(cw))
    for cod in codifiche:
        if cod:
            nomi.update(ambito.proprietari_codifica(cod))
    return sorted(nomi)


def chiamante(payload: dict, ambito: Ambito) -> dict:
    """A quali compartimenti appartiene la sessione che chiama.

    Tre segnali, e ne basta UNO (prudenza: una sessione che sembra di due
    compartimenti deve rispettare i permessi di entrambi):

    1. l'id di sessione, o l'id della sessione MADRE se chi chiama e' un
       subagente (ricavato dal `transcript_path`), e' in `X.sessioni`;
    2. la cartella in cui la sessione e' stata APERTA, ricavata dal
       `transcript_path` (la cartella codificata sotto `~/.claude/projects`),
       e' una cartella di X o una sua discendente;
    3. il `cwd` del payload sta dentro una cartella di X.

    Con cartelle ANNIDATE fra compartimenti (alfa in `/w/alfa`, beta in
    `/w/alfa/beta`) i segnali 2 e 3 valgono per il nominato piu' SPECIFICO, per
    componenti di percorso e indipendentemente dall'ordine della config (la
    stessa regola di boa); due nominati sulla stessa cartella valgono tutti e
    due (la sessione e' incerta: ha i permessi di entrambi, cioe' quasi
    nessuno). L'id della madre ricavato dal percorso di un subagente conta solo
    se il suo transcript esiste davvero sotto `projects` e la madre ha il suo
    (`_madre_verificata`): un percorso inventato non e' un id.

    Il `cwd` da solo NON basta come segnale di appartenenza: un `cd` (e ogni
    strumento che cambia directory) lo sposta, quindi un nominato che esce
    dalla sua cartella con un `cd` sembrerebbe di colpo predefinito e
    uscirebbe dal confinamento. Per questo gli altri due segnali (id e
    cartella di apertura) non si muovono mai. Il `cwd` puo' solo AGGIUNGERE
    un'appartenenza, mai toglierla.

    Torna `{"nomi": [...], "sessione", "madre", "codificata",
    "cartella_progetto", "cwd", "subagente"}`. `nomi` vuoto = predefinito."""
    sid = payload.get("session_id")
    sid = sid if isinstance(sid, str) else ""
    madre, codificata, progetto = _da_trascrizione(payload.get("transcript_path"),
                                                   ambito.claude_dir)
    cwd_raw = payload.get("cwd")
    cwd = _norm(cwd_raw) if isinstance(cwd_raw, str) and cwd_raw else ""
    nomi = _nomi_da_segnali(ambito, (sid, madre), (cwd,), (codificata,))
    tp = payload.get("transcript_path")
    subagente = bool(payload.get("agent_id")) or (
        isinstance(tp, str) and "/subagents/" in tp.replace("\\", "/"))
    return {"nomi": nomi, "sessione": sid or madre, "madre": madre,
            "codificata": codificata, "cartella_progetto": progetto,
            "da_codifica": ambito.proprietari_codifica(codificata),
            "cwd": cwd, "subagente": subagente}


def _scratch_ok(p: str, chi: dict, ambito: Ambito) -> bool:
    """La cartella di lavoro temporaneo di QUESTA sessione:
    `/private/tmp/claude-<uid>/<qualcosa>/<id di sessione>/...`. Senza uid
    (Windows) quella cartella non esiste: nessuna scratch da riconoscere."""
    if ambito.uid is None:
        return False
    base = _norm("/private/tmp/claude-%s" % ambito.uid)
    if not _dentro(p, base):
        return False
    resto = p[len(base):].strip("/").split("/")
    ids = {x for x in (chi["sessione"], chi["madre"]) if x}
    return len(resto) >= 2 and resto[1] in ids


def _progetto_ok(p: str, chi: dict, dalla_cartella: bool) -> bool:
    """La propria cartella sotto `~/.claude/projects`. Se la sessione e' li'
    perche' la sua cartella di apertura e' di X, e' tutta sua. Se invece e'
    di X solo per id (aperta in una cartella normale che condivide con altre
    sessioni), solo la propria trascrizione e la propria cartella di
    sessione: le trascrizioni degli altri non sono sue, e neanche `memory`.
    `memory` e' la memoria di TUTTE le sessioni del predefinito aperte in quella
    cartella: leggerla mostrerebbe i loro ricordi al nominato, e scriverci
    metterebbe i suoi in un `MEMORY.md` che Claude Code carica da solo in ogni
    sessione del predefinito (il canale 7 della specifica, nei due sensi)."""
    prog = _norm(chi["cartella_progetto"]) if chi["cartella_progetto"] else ""
    if not prog:
        return False
    if dalla_cartella:
        return _dentro(p, prog)
    for x in (chi["sessione"], chi["madre"]):
        if x and (_dentro(p, os.path.join(prog, x))
                  or p.lower() == os.path.join(prog, x + ".jsonl").lower()):
            return True
    return False


# --------------------------------------------------------------------------
# percorsi dagli strumenti e dai comandi Bash
# --------------------------------------------------------------------------

_RX_URL = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://\S+")
# Un percorso assoluto dentro un testo qualsiasi (codice passato a un
# interprete): preceduto da inizio riga, spazio, virgolette, `=`, `(`, `,`, ...
# ma non da una lettera, un punto, `$`, `}`, `:` o `/` (cosi' `s/a/b/` di sed e
# `https://x/y` non si scambiano per percorsi). Almeno un carattere dopo la
# barra: una `/` da sola (`os.listdir('/')`, una divisione) non e' un percorso.
_RX_ASSOLUTO = re.compile(r"""(?<![\w.$}:/])((?:~|)/[^\s'"`;|&<>()\\]+)""")
_RX_VAR = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))")

# Comandi che eseguono CODICE dato come testo (`python3 -c "..."`, un heredoc
# passato a `python3 -`): dentro le stringhe ci sono percorsi che il comando
# aprira' davvero, quindi si cercano con l'espressione regolare. Gli altri
# comandi non interpretano i loro argomenti come codice.
_RX_INTERPRETE = re.compile(
    r"^(?:python[\d.]*|node|nodejs|deno|bun|ruby|perl|php|osascript|lua|rscript"
    r"|swift)$", re.I)
# Le shell: il testo di `sh -c '...'` e il corpo di un heredoc dato a `bash` SONO
# comandi, e si analizzano come tali.
_SHELL = ("sh", "bash", "zsh", "dash", "ksh", "fish")
# Comandi che stampano i loro argomenti: `echo $HOME` non tocca nessun percorso.
# Restano le redirezioni (`echo x > file` scrive un file) e le sostituzioni di
# comando dentro gli argomenti (`echo $(cat file)`, che si analizzano a parte).
# ATTENZIONE: l'eccezione vale SOLO se il loro testo non arriva a un altro
# comando (una pipe, una sostituzione, un file che poi si esegue): vedi
# `_analizza`.
_MUTI = ("echo", "printf")
_PUNTEGGIATURA = frozenset("();<>|&")
# Chi riceve un testo (un heredoc, una pipe) e lo USA: una shell, un
# interprete, un comando che ne legge i percorsi (`xargs`, `read`), una parola
# chiave di ciclo. Il testo che arriva a uno di questi si controlla come comando.
_ESECUTORI = frozenset(_SHELL + (
    "eval", "source", ".", "ssh", "parallel", "while", "for", "until", "do",
    "done", "then", "else", "elif", "if", "read", "mapfile", "readarray", "exec",
    "watch", "script", "{", "case", "select", "coproc"))
# Interpreti di codice che si danno ANCHE come heredoc (`awk -f - <<EOF`,
# `sqlite3 <<EOF`): non si cercano nei loro argomenti (`awk '/x/'` non ha
# percorsi), ma il corpo di un heredoc si.
_RX_CODICE_HD = re.compile(r"^(?:awk|gawk|mawk|nawk|sqlite3?|psql|expect|tclsh)$", re.I)
# La cartella di un segmento quando non si sa (un `cd -`, una destinazione con
# una variabile non definita): un percorso relativo li' non si sa dove porta.
_IGNOTA = "\x00cwd-ignota"


def _e_interprete(nome: str) -> bool:
    return bool(_RX_INTERPRETE.match(nome or ""))


def _e_codice(nome: str) -> bool:
    return _e_interprete(nome) or bool(_RX_CODICE_HD.match(nome or ""))


def _punt(t: str) -> bool:
    """Un token di punteggiatura della shell (`>`, `>>`, `<<`, `2>&1` a pezzi)."""
    return bool(t) and all(c in _PUNTEGGIATURA for c in t)


def _prefisso_glob_dir(pattern: str) -> str:
    """La cartella letterale in cui cade un modello di Glob."""
    tagliato = re.split(r"[*?\[{]", pattern, 1)[0]
    if tagliato == pattern:
        return pattern
    return tagliato.rsplit("/", 1)[0] if "/" in tagliato else ""


# --- il comando Bash, a pezzi ----------------------------------------------
#
# EURISTICO, dichiarato: ferma gli incidenti, non chi vuole aggirarlo. Il
# comando si scompone cosi': (1) i corpi degli heredoc si tolgono dal testo e si
# tengono a parte, legati al comando che li riceve (un segnaposto `<<\x01N\x01`
# al posto del delimitatore); (2) segmenti separati da `;`, `&&`, `||`, `|`, a
# capo, parentesi (con le virgolette rispettate), ognuno con il separatore che
# lo segue; (3) ogni segmento in token con `shlex`; (4) lungo i segmenti si
# SIMULANO la cartella (`cd`, `pushd`, `popd`, subshell fra parentesi) e le
# variabili (`VAR=x`, `export VAR=x`), cosi' un percorso relativo si risolve
# dove il comando lo leggerebbe davvero; (5) le sostituzioni `$(...)` e `` `...` ``,
# il testo di `sh -c` e di `eval`, e i testi che arrivano a un esecutore (un
# heredoc dato a una shell, un `echo ... | sh`) si analizzano di nuovo, a parte.
# Se le virgolette non tornano si ripiega su uno split per spazi.
#
# Il testo di `echo`/`printf` e il corpo di un heredoc sono INERTI (non si
# guardano) solo se non arrivano a un comando che li usa: `echo $HOME`,
# `cat <<EOF > file`, `git commit -m "$(cat <<EOF ...)"`. Se escono in una pipe,
# o in una sostituzione, o li riceve una shell o un interprete, si controllano
# come comandi. Un testo scritto in un file (`echo ... > f`) e poi dato a un
# esecutore nello stesso comando (`bash f`, `xargs cat < f`, `. f`) si controlla.

_RX_HEREDOC = re.compile(
    r"<<(-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([A-Za-z_][A-Za-z_0-9.-]*))")
_RX_MARCA_HD = re.compile(r"^\x01(\d+)\x01$")
_RX_WHICH = re.compile(
    r"\$\(\s*(?:which|command\s+-v|type\s+-p|whence)\s+([A-Za-z0-9_./-]+)\s*\)"
    r"|`\s*(?:which|command\s+-v)\s+([A-Za-z0-9_./-]+)\s*`")
_CACHE_ANALISI = {}
_CONTATORE = [0]


_RX_ANSI_C = re.compile(r"\$'((?:[^'\\]|\\.)*)'")
_RX_ANSI_L = re.compile(r'\$"((?:[^"\\]|\\.)*)"')


def _decodifica_ansi_c(corpo: str) -> str:
    """Il contenuto di `$'...'` con le sue sequenze di escape (`\\n`, `\\x2f`,
    `\\057`, `\\'`): quello che la shell passa al comando."""
    try:
        return corpo.encode("latin-1", "backslashreplace").decode("unicode_escape")
    except (UnicodeError, ValueError):
        return corpo


def _senza_ansi_c(seg: str) -> str:
    """`$'...'` e `$"..."` (le virgolette ANSI-C e di traduzione di bash) diventano
    virgolette normali: `shlex` li leggerebbe come un `$` seguito da un testo
    fra apici, e `cat $'/percorso'` non nominerebbe piu' il percorso."""
    if "$'" not in seg and '$"' not in seg:
        return seg
    seg = _RX_ANSI_C.sub(
        lambda m: "'" + _decodifica_ansi_c(m.group(1)).replace("'", "'\\''") + "'", seg)
    return _RX_ANSI_L.sub(lambda m: '"' + m.group(1) + '"', seg)


def _token(seg: str) -> list:
    import shlex
    seg = _senza_ansi_c(seg)
    try:
        lex = shlex.shlex(seg, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        return list(lex)
    except ValueError:
        return [t.strip("'\"") for t in seg.split()]


# I prefissi di comando: il comando vero e' quello che segue. Per ognuno, le opzioni
# che prendono un valore nel token dopo (`nice -n 5`, `sudo -u root`, `timeout -s
# KILL`, `xargs -I {}`) e quanti argomenti posizionali hanno dopo le opzioni
# (`timeout 5 cmd`: la durata). Le opzioni senza valore (`-i`, `-arm64`, `-o0`) si
# saltano una a una.
_PREFISSI_SPEC = {
    "sudo": (frozenset(("-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-T", "-U",
                        "-R", "--user", "--group", "--chdir", "--host", "--prompt",
                        "--role", "--type")), 0),
    "doas": (frozenset(("-u", "-C")), 0),
    "time": (frozenset(), 0),
    "command": (frozenset(), 0),
    "builtin": (frozenset(), 0),
    "exec": (frozenset(("-a",)), 0),
    "nohup": (frozenset(), 0),
    "nice": (frozenset(("-n", "--adjustment")), 0),
    "ionice": (frozenset(("-c", "-n", "-p", "-P", "-u", "--class", "--classdata")), 0),
    "timeout": (frozenset(("-s", "-k", "--signal", "--kill-after")), 1),
    "gtimeout": (frozenset(("-s", "-k", "--signal", "--kill-after")), 1),
    "caffeinate": (frozenset(("-t", "-w")), 0),
    "stdbuf": (frozenset(("-i", "-o", "-e")), 0),
    "arch": (frozenset(("-e", "-d")), 0),
    "env": (frozenset(("-u", "-C", "-S", "-P", "--unset", "--chdir",
                       "--split-string")), 0),
    "xargs": (frozenset(("-I", "-n", "-P", "-L", "-s", "-d", "-E", "-a", "-J",
                         "--max-args", "--max-procs", "--delimiter", "--arg-file",
                         "--max-lines", "--max-chars", "--eof")), 0),
    "setsid": (frozenset(), 0),
    "flock": (frozenset(("-w", "-E", "--timeout", "--conflict-exit-code")), 1),
    "busybox": (frozenset(), 0),
}
_PREFISSI_COMANDO = tuple(_PREFISSI_SPEC)
_CTRL = frozenset(("do", "then", "else", "elif", "if", "while", "until", "!", "{"))
_RX_ASSEGNA = re.compile(r"^[A-Za-z_]\w*=")


def _espandi_graffe(t: str, tetto: int = 64) -> list:
    """Le espansioni con le graffe di shell di un token: `a{b,c}d` -> `abd`, `acd`
    (anche annidate). Le `${...}` non sono graffe, un `{}` senza virgole nemmeno
    (`find -exec x {} \\;`). Al massimo `tetto` voci."""
    i, n = 0, len(t)
    while i < n:
        if t[i] == "{" and (i == 0 or t[i - 1] != "$"):
            prof, virg, j = 0, [], i
            while j < n:
                if t[j] == "{":
                    prof += 1
                elif t[j] == "}":
                    prof -= 1
                    if prof == 0:
                        break
                elif t[j] == "," and prof == 1:
                    virg.append(j)
                j += 1
            if j < n and virg:
                pre, post = t[:i], t[j + 1:]
                parti, ini = [], i + 1
                for v in virg:
                    parti.append(t[ini:v])
                    ini = v + 1
                parti.append(t[ini:j])
                out = []
                for p in parti:
                    for e in _espandi_graffe(pre + p + post, tetto):
                        out.append(e)
                        if len(out) >= tetto:
                            return out
                return out
        i += 1
    return [t]


def _scandisci_prefissi(t) -> tuple:
    """`(indice, prefissi, assegnazioni)` di un segmento in token: l'indice del token
    che e' il comando vero, dopo i prefissi (`sudo -u root`, `timeout 5`, `nice -n 5`,
    `env -i A=1`, `xargs -I {}`, anche con il percorso: `/usr/bin/env`), le
    assegnazioni (`VAR=x`), le parole di controllo (`do`, `then`, ...) e la
    punteggiatura."""
    i, n = 0, len(t)
    pre, ass = [], []
    while i < n:
        x = t[i]
        base = os.path.basename(x)
        if base in _PREFISSI_SPEC:
            pre.append(base)
            opz, posizionali = _PREFISSI_SPEC[base]
            i += 1
            while i < n and t[i].startswith("-") and t[i] != "-":
                if t[i] == "--":
                    i += 1
                    break
                i += 2 if t[i] in opz else 1
            while posizionali and i < n and not _punt(t[i]):
                i += 1
                posizionali -= 1
            continue
        if x in _CTRL or _punt(x):
            i += 1
        elif re.match(r"^\w+=", x):
            if _RX_ASSEGNA.match(x):
                ass.append(x)
            i += 1
        elif x.startswith("-") and n - i > 1:
            i += 1
        else:
            break
    return min(i, n), pre, ass


def _spezza(tok):
    """`(prefissi, assegnazioni, primo_token, nome, argomenti)` di un segmento,
    dopo i prefissi (`sudo -u root`, `timeout 5`, `nice -n 5`, `env`, `xargs`,
    `VAR=x`, con il percorso: `/usr/bin/env`) e le parole di controllo (`do`,
    `then`, ...). `nome` e' senza cartella; vuoto se il segmento e' solo
    assegnazioni."""
    t = list(tok)
    i, pre, ass = _scandisci_prefissi(t)
    t = t[i:]
    if not t:
        return pre, ass, "", "", []
    return pre, ass, t[0], os.path.basename(t[0]), t[1:]


def _nome_e_args(tok) -> tuple:
    """Il nome del comando (senza cartella) e i suoi argomenti."""
    _, _, _, nome, args = _spezza(tok)
    return nome, args


def _togli_heredoc(cmd: str, hd=None):
    """`(testo, heredoc)`. Il corpo di ogni heredoc si toglie dal testo e si
    tiene in `heredoc[N]` (`{"corpo", "quotato"}`); il delimitatore diventa il
    segnaposto `\\x01N\\x01`, cosi' `_analizza` lo lega al segmento che lo
    riceve. Non si decide qui se e' testo o comandi: dipende da chi lo riceve."""
    hd = [] if hd is None else hd
    if "<<" not in cmd and "#" not in cmd:
        return cmd, hd
    out, attesa = [], []
    q, i, n, esc_fine = None, 0, len(cmd), -1
    while i < n:
        c = cmd[i]
        if q:
            out.append(c)
            if q == '"' and c == "\\" and i + 1 < n:
                out.append(cmd[i + 1])
                i += 2
                continue
            if c == q:
                q = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(c + cmd[i + 1])
            i += 2
            esc_fine = i
            continue
        if c in "'\"":
            q = c
            out.append(c)
            i += 1
            continue
        if c == "#" and i != esc_fine and (i == 0 or cmd[i - 1] in " \t\n;&|("):
            # un commento (`#` all'inizio di una parola, fuori dalle virgolette): fino
            # a fine riga non e' codice. Si toglie PRIMA di cercare gli heredoc: un
            # `# usa <<EOF` non apre niente, e i suoi apici non aprono virgolette.
            j = cmd.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "$" and cmd.startswith(("${", "$(("), i):
            # `${x:-<<EOF}`, `${#x}` e `$(( 1 << b ))`: dentro non c'e' un heredoc
            # ne' un commento
            chiudi = "}" if cmd[i + 1] == "{" else "))"
            j = cmd.find(chiudi, i + 2)
            if j != -1:
                out.append(cmd[i:j + len(chiudi)])
                i = j + len(chiudi)
                continue
        if c == "\n" and attesa:
            out.append("\n")
            i += 1
            for idx, delim in attesa:
                righe = []
                while i < n:
                    j = cmd.find("\n", i)
                    j = n if j == -1 else j
                    riga = cmd[i:j]
                    i = j + 1
                    if riga.strip() == delim:
                        break
                    righe.append(riga)
                hd[idx]["corpo"] = "\n".join(righe)
            attesa = []
            continue
        if c == "<" and cmd.startswith("<<<", i):
            # una here-string: tutte e tre le `<` insieme, altrimenti la seconda
            # coppia `<<` sembrerebbe un heredoc (`sh <<< 'cat x'`)
            out.append("<<<")
            i += 3
            continue
        if c == "<" and cmd.startswith("<<", i):
            m = _RX_HEREDOC.match(cmd, i)
            if m:
                delim = next((g for g in m.group(2, 3, 4) if g is not None), "")
                quotato = m.group(2) is not None or m.group(3) is not None or (
                    "\\" in m.group(0))
                hd.append({"corpo": "", "quotato": quotato})
                attesa.append((len(hd) - 1, delim))
                out.append("<<\x01%d\x01" % (len(hd) - 1))
                i = m.end()
                continue
        out.append(c)
        i += 1
    return "".join(out), hd


def _dividi_segmenti(t: str) -> list:
    """Il testo diviso ai `;`, `&&`, `||`, `|`, `|&`, `&`, a capo e alle
    parentesi che non sono dentro virgolette, `$(...)` o apici inversi. `>&`,
    `&>` e `>|` non dividono. Torna `("seg", testo, separatore_dopo)` (il
    separatore e' "" alla fine) e `("(",)` / `(")",)` per le parentesi."""
    out, cur = [], []
    q, sub, bt, i, n = None, 0, False, 0, len(t)

    def chiudi(dopo):
        s = "".join(cur).strip()
        del cur[:]
        if s:
            out.append(("seg", s, dopo))
        elif dopo and out and out[-1][0] == "seg" and out[-1][2] in ("", "\n", ";"):
            # un separatore piu' forte dopo uno debole (`a\n| b`): vale il forte
            out[-1] = ("seg", out[-1][1], dopo)

    while i < n:
        c = t[i]
        if q:
            cur.append(c)
            if q == '"' and c == "\\" and i + 1 < n:
                cur.append(t[i + 1])
                i += 2
                continue
            if c == q:
                q = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            cur.append(c + t[i + 1])
            i += 2
            continue
        if c in "'\"":
            q = c
            cur.append(c)
            i += 1
            continue
        if c == "`":
            bt = not bt
            cur.append(c)
            i += 1
            continue
        if bt:
            cur.append(c)
            i += 1
            continue
        if c in "$<>" and t[i + 1:i + 2] == "(" and not (
                c != "$" and t[i - 1:i] == c):
            # `$(...)`, e la sostituzione di processo `<(...)` / `>(...)`: un
            # comando dentro, non una subshell del comando stesso
            sub += 1
            cur.append(c + "(")
            i += 2
            continue
        if sub:
            sub += 1 if c == "(" else -1 if c == ")" else 0
            cur.append(c)
            i += 1
            continue
        prec = t[i - 1] if i else ""
        succ = t[i + 1] if i + 1 < n else ""
        if c == "(":
            chiudi("")
            out.append(("(",))
        elif c == ")":
            chiudi("")
            out.append((")",))
        elif c in ";\n":
            chiudi(c)
        elif c == "|" and prec != ">":
            if succ == "|":
                chiudi("||")
                i += 1
            elif succ == "&":
                chiudi("|&")
                i += 1
            else:
                chiudi("|")
        elif c == "&" and prec not in "<>" and succ != ">":
            if succ == "&":
                chiudi("&&")
                i += 1
            else:
                chiudi("&")
        else:
            cur.append(c)
        i += 1
    chiudi("")
    return out


def _scansiona_sost(t: str) -> list:
    """Le sostituzioni di comando di un testo come `(inizio, fine, interno)`:
    `$(...)`, `` `...` `` e `<(...)` (non quelle fra apici singoli). Anche quelle
    annidate."""
    out, sq, dq, i, n = [], False, False, 0, len(t)
    while i < n:
        c = t[i]
        if c == "\\":
            i += 2
            continue
        if c == '"' and not sq:
            dq = not dq
        elif c == "'" and not dq:
            sq = not sq
        elif not sq:
            if c in "$<>" and t[i + 1:i + 2] == "(" and (c == "$" or not dq):
                j, prof = i + 2, 1
                while j < n and prof:
                    prof += 1 if t[j] == "(" else -1 if t[j] == ")" else 0
                    j += 1
                out.append((i, j, t[i + 2:j - 1 if prof == 0 else j]))
                i += 2
                continue
            if c == "`":
                k = t.find("`", i + 1)
                if k != -1:
                    out.append((i, k + 1, t[i + 1:k]))
                    i = k + 1
                    continue
        i += 1
    return out


def _sostituzioni(t: str) -> list:
    """I testi dentro `$(...)`, `` `...` `` e `<(...)`: sono comandi da
    analizzare a parte."""
    return [x[2] for x in _scansiona_sost(t)]


def _maschera(t: str) -> str:
    """`t` con ogni sostituzione (le piu' esterne) sostituita da un solo
    carattere `\\x02`: cosi' `shlex` non spezza un `$(cat x)` ai suoi spazi e un
    `VAR=$(...)` resta un'assegnazione sola."""
    res, pos = [], 0
    for a, b, _ in sorted(_scansiona_sost(t)):
        if a < pos:
            continue
        res.append(t[pos:a])
        res.append("\x02")
        pos = b
    res.append(t[pos:])
    return "".join(res)


def _espandi_var(c: str, env=None, locali=None):
    """`c` con le variabili `$VAR` e `${VAR}` espanse: prima le variabili
    assegnate nello stesso comando (`locali`), poi l'ambiente del payload (se
    c'e'), poi quello dell'hook. `None` se ne resta una non definita (o un `$`
    di altro genere: `$1`, `$?`): un percorso che non si sa ricostruire si
    ignora, invece di risolverlo sulla cwd come se `$X` fosse un nome di
    cartella."""
    if "$" not in c:
        return c
    mancante = []

    def sost(m):
        nome = m.group(1) or m.group(2)
        if locali is not None and nome in locali:
            v = locali[nome]
        else:
            v = (env or {}).get(nome)
            if not isinstance(v, str):
                v = os.environ.get(nome)
        if not isinstance(v, str):
            mancante.append(nome)
            return ""
        return v
    r = _RX_VAR.sub(sost, c)
    return None if mancante or "$" in r else r


def _valore_var(v: str, env, locali, nome=None, grezzo=None):
    """Il valore che una assegnazione `VAR=v` da' alla variabile, o None se
    non si sa (una sostituzione di comando, una variabile non definita). Fa eccezione
    `PLANCIA_HOME=$(mktemp -d)` (e `HOME`, `CLAUDE_CONFIG_DIR`), se si passano il `nome` della
    variabile e il testo `grezzo` del segmento: la cartella e' nuova, e nessun file protetto
    puo' stare in una cartella che non esisteva (vedi `_DIR_FRESCA`)."""
    if "$(" in v or "`" in v or "\x02" in v:
        if (nome in _VAR_SPIATE and grezzo and v == "\x02"
                and re.search(r"(?<![\w])%s=[\"']?(?:\$\(|`)\s*(?:command\s+)?g?mktemp\b"
                              % re.escape(nome), grezzo)):
            return _DIR_FRESCA
        return None
    e = _espandi_var(v, env, locali)
    if e is None:
        return None
    return os.path.expanduser(e) if e.startswith("~") else e


def _operandi_cd(args):
    out, prec, fine = [], "", False
    for a in args:
        if _punt(a):
            prec = a
            continue
        if prec:
            prec = ""
            continue
        if not fine and a == "--":
            fine = True
            continue
        if not fine and a.startswith("-") and a != "-":
            continue
        out.append(a)
    return out


def _sost_esterne(t: str) -> list:
    """I testi interni delle sostituzioni piu' esterne di `t`, nell'ordine in cui
    `_maschera` le sostituisce con `\\x02`."""
    out, pos = [], 0
    for a, b, inner in sorted(_scansiona_sost(t)):
        if a < pos:
            continue
        out.append(inner)
        pos = b
    return out


def _radice_git(cwd):
    """La cartella di lavoro del repository che contiene `cwd` (l'antenato piu'
    vicino con un `.git`), senza lanciare git; None se non c'e'."""
    d = cwd
    while d and d != "/":
        if os.path.exists(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    return None


def _arg_sost(a: str, sost, cwd, locali, env, prof: int):
    """Un argomento di un comando dentro una sostituzione, con le variabili e le
    sostituzioni annidate espanse; None se non si sa."""
    if "\x02" in a:
        pezzi = a.split("\x02")
        if len(pezzi) - 1 > len(sost):
            return None
        r = pezzi[0]
        for k, resto in enumerate(pezzi[1:]):
            v = _valuta_sost(sost[k], cwd, locali, env, prof + 1)
            if v is None:
                return None
            r += v + resto
        a = r
    e = _espandi_var(a, env, locali)
    return None if e is None else e


def _valuta_sost(inner: str, cwd, locali, env, prof: int = 0):
    """Cio' che una sostituzione di comando (`$(...)`) stampa, quando si sa senza
    lanciarla: `pwd`, `dirname X`, `realpath X`, `readlink -f X`, `echo X`,
    `git rev-parse --show-toplevel` (l'antenato con un `.git`), `cd X && pwd`. Con
    argomenti che si sanno (senza variabili non definite ne' `$0`). None altrimenti:
    la cartella e' sconosciuta."""
    if prof > 4 or not inner or len(inner) > 1000:
        return None
    inner = inner.strip()
    m = re.match(r"^cd\s+(.+?)\s*(?:&&|;)\s*pwd(?:\s+-[LP])?\s*(?:2>&1|2>/dev/null)?$", inner)
    if m:
        alvo = m.group(1)
        parole = _token(_maschera(alvo))
        if len(parole) != 1:
            return None
        v = _arg_sost(parole[0], _sost_esterne(alvo), cwd, locali, env, prof + 1)
        if not v:
            return None
        r = _risolvi_cd(v, cwd, locali, env)
        return None if r == _IGNOTA else r
    sost = _sost_esterne(inner)
    tok = _token(_maschera(inner))
    if not tok or any(_punt(t) for t in tok):
        return None
    nome, args = os.path.basename(tok[0]), tok[1:]
    valori = [a for a in args if not (a.startswith("-") and len(a) > 1)]
    if nome == "pwd":
        return cwd if cwd and cwd != _IGNOTA else None
    if nome == "git" and args[:1] == ["rev-parse"] and "--show-toplevel" in args:
        return _radice_git(cwd) if cwd and cwd != _IGNOTA else None
    if nome == "echo":
        parole = [_arg_sost(a, sost, cwd, locali, env, prof) for a in valori]
        return None if not parole or None in parole else " ".join(parole)
    if len(valori) != 1:
        return None
    v = _arg_sost(valori[0], sost, cwd, locali, env, prof)
    if v is None:
        return None
    if nome == "dirname":
        return os.path.dirname(v.rstrip("/")) or "."
    if nome in ("realpath", "readlink"):
        if nome == "readlink" and not any(a in ("-f", "-e", "-m") for a in args):
            return None
        base = cwd if cwd and cwd != _IGNOTA else None
        if not v.startswith(("/", "~")) and base is None:
            return None
        return _norm(v, base) or None
    return None


def _risolvi_cd(target: str, cwd, locali, env, sost=()):
    """La cartella in cui porta `cd target` da `cwd`, o `_IGNOTA`. Una destinazione
    costruita con una sostituzione di comando si risolve quando il comando si sa
    valutare senza lanciarlo (`$(pwd)`, `$(dirname X)`, `$(git rev-parse
    --show-toplevel)`, `$(realpath X)`: `_valuta_sost`); altrimenti, e con le graffe
    che portano a piu' cartelle (`cd alfa-{uno,due}`), e' sconosciuta."""
    if "\x02" in target or "$(" in target or "`" in target:
        if "\x02" in target and sost:
            r = _arg_sost(target, sost, cwd, locali, env, 0)
            if r is None or not r or "\x02" in r:
                return _IGNOTA
            target = r
        else:
            return _IGNOTA
    e = _espandi_var(target, env, locali)
    if not e:
        return _IGNOTA
    if "{" in e:
        voci = set(_espandi_graffe(e))
        if len(voci) > 1:
            return _IGNOTA
        e = next(iter(voci))
    if _ha_glob(e):
        base = cwd if cwd and cwd != _IGNOTA else None
        if not (e.startswith(("/", "~")) or base):
            return _IGNOTA
        veri = [x for x in _espandi_glob(e, base) if os.path.isdir(x)]
        if len(veri) != 1:
            return _IGNOTA
        e = veri[0]
    if cwd == _IGNOTA and not e.startswith(("/", "~")):
        return _IGNOTA
    n = _norm(e, cwd if cwd != _IGNOTA else None)
    if not n:
        return _IGNOTA
    if not os.path.isdir(n) and not e.startswith(("/", "~")):
        # un `cd` relativo verso una cartella che non c'e' fallisce e la cartella
        # resta quella di prima (`cd comune; grep -rn x .` cerca dove era);
        # uno assoluto si segue: puo' essere creata dallo stesso comando
        return cwd if cwd is not None else (_norm(".") or _IGNOTA)
    return n


def _nuova_cwd(nome, args, cwd, dirs, locali, env, prima, dopo, sost=()):
    """`(cwd, dirs)` dopo un `cd`, `pushd` o `popd`. Un `cd -`, una destinazione
    che non si sa risolvere, un `cd` dopo un `||` (forse non e' stato eseguito)
    danno `_IGNOTA`: piu' avanti un percorso relativo non si sa dove porta, e si
    nega per prudenza. Un comando in background o in una pipe gira in una
    sottoshell: non sposta niente."""
    if dopo in ("&", "|", "|&"):
        return cwd, dirs
    nuova = cwd
    if nome == "cd":
        op = _operandi_cd(args)
        if not op:
            nuova = os.path.expanduser("~")
        elif op[0] == "-":
            nuova = _IGNOTA
        else:
            nuova = _risolvi_cd(op[0], cwd, locali, env, sost)
    elif nome == "pushd":
        op = _operandi_cd(args)
        if not op or op[0].startswith(("+", "-")):
            nuova = _IGNOTA
        else:
            nuova = _risolvi_cd(op[0], cwd, locali, env, sost)
            dirs = dirs + [cwd]
    elif nome == "popd":
        if dirs:
            nuova, dirs = dirs[-1], dirs[:-1]
        else:
            nuova = _IGNOTA
    if prima == "||":
        nuova = _IGNOTA
    return nuova, dirs


_RX_FD = re.compile(r"^(?:\d+|-)$")


def _uscite(tok) -> list:
    """I bersagli delle redirezioni di uscita: `> f`, `>> f`, `>| f`, `&> f`, `>& f`
    (con un file: `>&2` e `>&-` duplicano un descrittore) e `<> f` (apre il file
    anche in scrittura)."""
    out, prec = [], ""
    for t in tok:
        if _punt(t):
            prec = t
            continue
        if ">" in prec and ("<" not in prec or prec == "<>") and (
                not prec.endswith("&") or not _RX_FD.match(t)):
            out.append(t)
        prec = ""
    return out


_RX_PWD = re.compile(r"\$\(\s*pwd\s*\)|`\s*pwd\s*`")
_MAX_VALORI_CICLO = 20
_MAX_VARIANTI = 60
# Le variabili che cambiano dove stanno i file del guardiano, e il segno che un `source` (o un
# `eval`) puo' averle cambiate: non e' un nome di variabile, non si confonde con nessuna.
_VAR_SPIATE = ("PLANCIA_HOME", "HOME", "CLAUDE_CONFIG_DIR")
_FONTE = "\x03fonte"
# Il valore di una variabile assegnata a `$(mktemp ...)`: una cartella nuova, che non e' e non
# contiene nessun file del guardiano. Non esiste, e qui basta che non sia un'altra.
_DIR_FRESCA = "/tmp/.plancia-cartella-nuova-di-mktemp"


def _valori_ciclo(args, cwd, vs, env):
    """I valori che `for VAR in PAROLE...` da' a VAR, o None se non si sanno (una
    sostituzione di comando, una variabile non definita): le parole si espandono
    con le variabili, le graffe e i glob (sul disco)."""
    valori = []
    for w in args[2:]:
        if _punt(w):
            break
        if "\x02" in w:
            continue
        e = _espandi_var(w, env, vs)
        if e is None:
            continue
        for b in _espandi_graffe(e):
            if _ha_glob(b):
                g = _espandi_glob(b, cwd if cwd != _IGNOTA else None)
                valori.extend(g if g else [b])
            else:
                valori.append(b)
    return valori[:_MAX_VALORI_CICLO] or None


def _fase_a(testo: str, st: dict, env):
    """I segmenti di `testo` con la cartella e le variabili di quando partono. Un
    ciclo `for VAR in PAROLE; do ...; done` con parole note si SVOLGE: il segmento
    che usa `$VAR` compare una volta per valore, con quel valore."""
    cwd, vs, dirs = st["cwd"], st["vars"], list(st["dirs"])
    if cwd and cwd != _IGNOTA and vs.get("PWD") != cwd:
        vs = dict(vs)
        vs["PWD"] = cwd
    pila, segs, prima, cicli = [], [], "", []
    for it in _dividi_segmenti(testo):
        if it[0] == "(":
            pila.append((cwd, vs, list(dirs)))
            continue
        if it[0] == ")":
            if pila:
                cwd, vs, dirs = pila.pop()
            continue
        _, seg, dopo = it
        seg2 = _RX_PWD.sub("$PWD", _RX_WHICH.sub(lambda m: m.group(1) or m.group(2), seg))
        tok = _token(_maschera(seg2))
        pre, ass, cmd0, nome, args = _spezza(tok)
        if cmd0.startswith("$") and cmd0 not in ("$", "$(") and "(" not in cmd0:
            e = _espandi_var(cmd0, env, vs)
            if e:
                nome = os.path.basename(e)
        s = {"nome": nome, "args": args, "token": tok, "testo": seg, "pre": pre,
             "cmd0": cmd0, "cwd": cwd, "vars": vs, "prima": prima, "dopo": dopo, "ass": ass,
             "hd": [int(m.group(1)) for m in (_RX_MARCA_HD.match(t) for t in tok) if m]}
        varianti = [s]
        for var, valori in cicli:
            if valori is not None and re.search(r"\$\{?%s\b" % re.escape(var), seg):
                nuove = []
                for base in varianti:
                    for v in valori:
                        s2 = dict(base)
                        s2["vars"] = dict(base["vars"])
                        s2["vars"][var] = v
                        nuove.append(s2)
                varianti = nuove[:_MAX_VARIANTI]
        segs.extend(varianti)
        # effetti sullo stato, DOPO aver fissato quello con cui il segmento parte
        if nome == "" and ass:
            vs = dict(vs)
            for a in ass:
                k, v = a.split("=", 1)
                vs[k] = _valore_var(v, env, vs, k, seg)
        elif nome in ("export", "declare", "typeset", "local", "readonly"):
            vs = dict(vs)
            for a in args:
                if _RX_ASSEGNA.match(a):
                    k, v = a.split("=", 1)
                    vs[k] = _valore_var(v, env, vs, k, seg)
        elif nome == "unset":
            vs = {k: v for k, v in vs.items() if k not in args}
        elif nome in ("source", ".", "eval"):
            # un file (o una stringa) che non si sa cosa assegna: da qui in poi il valore di
            # PLANCIA_HOME, HOME, CLAUDE_CONFIG_DIR non si sa piu' (vedi `_var_del_comando`)
            vs = dict(vs)
            for k in _VAR_SPIATE:
                if k in vs:
                    vs[k] = None
            vs[_FONTE] = True
        elif nome in ("cd", "pushd", "popd"):
            cwd, dirs = _nuova_cwd(nome, args, cwd, dirs, vs, env, prima, dopo,
                                   _sost_esterne(seg2))
            vs = dict(vs)
            vs["PWD"] = cwd if cwd and cwd != _IGNOTA else None
        elif nome == "for" and len(args) >= 3 and args[1] == "in":
            cicli.append((args[0], _valori_ciclo(args, cwd, vs, env)))
        elif nome == "done" and cicli:
            cicli.pop()
        prima = dopo
    return segs


def _e_esecutore(s: dict) -> bool:
    """Il segmento USA il testo che riceve: una shell, un interprete, `xargs`..."""
    return (s["nome"] in _ESECUTORI or "xargs" in s["pre"]
            or _e_codice(s["nome"]))


def _consumo_testo(c) -> bool:
    """Il comando che consuma una sostituzione la usa come TESTO (il messaggio di
    `git commit -m "$(cat <<EOF ...)"`), non come percorso o come comando."""
    if not c or c["nome"] not in ("git", "gh"):
        return False
    return not any(a in ("-F", "--file", "--body-file", "-f") or a.startswith("-F")
                   for a in c["args"])


def _testo_echo(s: dict) -> str:
    """Il testo che `echo`/`printf` stampano: gli argomenti che non sono opzioni
    ne' redirezioni."""
    out, prec = [], ""
    for t in s["token"][1:]:
        if _punt(t):
            prec = t
            continue
        if prec:
            prec = ""
            continue
        if t.startswith("-") and not out and len(t) <= 3:
            continue
        out.append(t)
    return " ".join(out)


def _copia_stato(s: dict) -> dict:
    return {"cwd": s["cwd"], "vars": s["vars"], "dirs": []}


def _analizza(cmd: str, cwd0=None, env=None, prof: int = 0, st=None, cons=None,
              hd=None) -> dict:
    """`{"segmenti": [{"nome", "args", "token", "testo", "pre", "cwd", "vars",
    "prima", "dopo", "hd", "muto", "aqui", "catena"}, ...], "corpi": [...]}`
    del comando e di tutto quello che contiene (sostituzioni, `sh -c`, `eval`,
    heredoc e testi che arrivano a un esecutore). `cwd` e' la cartella in cui il
    segmento parte (simulata lungo i `cd`), o `_IGNOTA`; `ass` le assegnazioni che lo
    precedono (`VAR=x cmd`). `corpi` sono testi di codice in cui cercare percorsi, come
    `(testo, cartella, segmento)`: la cartella da cui parte chi li esegue e il segmento
    stesso (con le sue variabili)."""
    chiave = None
    if prof == 0:
        chiave = (cmd, cwd0, tuple(sorted(env.items())) if env else None)
        if chiave in _CACHE_ANALISI:
            return _CACHE_ANALISI[chiave]
    ris = {"segmenti": [], "corpi": [], "hd": []}
    if cmd and prof <= 4:
        # anche nei testi delle sostituzioni: un heredoc dentro `"$(...)"` non
        # si vede finche' il testo non e' estratto dalle virgolette
        testo, hd = _togli_heredoc(cmd, hd)
        ris["hd"] = hd
        if st is None:
            st = {"cwd": cwd0, "vars": {}, "dirs": []}
        segs = _fase_a(testo, st, env)
        _fase_b(segs, ris, cwd0, env, prof, cons, hd)
    if prof == 0:
        if len(_CACHE_ANALISI) > 64:
            _CACHE_ANALISI.clear()
        _CACHE_ANALISI[chiave] = ris
    return ris


def _sotto(ris: dict, testo: str, s: dict, cwd0, env, prof, hd, cons=None):
    """Analizza `testo` (una sostituzione, un `sh -c`, un heredoc) con la
    cartella e le variabili del segmento `s`, e ne aggiunge i segmenti."""
    r = _analizza(testo, cwd0, env, prof + 1, _copia_stato(s), cons, hd)
    ris["segmenti"].extend(r["segmenti"])
    ris["corpi"].extend(r["corpi"])


def _chiave_simbolica(t: str) -> str:
    """Un token che e' solo una variabile (`$f`, `${f}`, `"$f"`), normalizzato:
    serve a riconoscere il file `$f` scritto e poi usato quando il valore della
    variabile non si sa (`f=$(mktemp)`). Stringa vuota se non lo e'."""
    m = re.match(r"^\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))$", t or "")
    return ("$" + (m.group(1) or m.group(2))) if m else ""


def _riferisce(t: str, s2: dict, dn: str, chiave: str, env) -> bool:
    """Il token `t` del segmento `s2` indica il file `dn` (percorso risolto) o la
    variabile simbolica `chiave`."""
    if not t or _punt(t) or t.startswith("-") or _RX_MARCA_HD.match(t):
        return False
    if chiave and _chiave_simbolica(t) == chiave:
        return True
    if not dn:
        return False
    e = _espandi_var(t, env, s2["vars"])
    if not e:
        return False
    n = _norm(e, s2["cwd"] if s2["cwd"] != _IGNOTA else None)
    return bool(n) and n.lower() == dn.lower()


def _dopo_pipe_esecutore(segs: list, k: int) -> bool:
    """Il testo del segmento `k` arriva, lungo la pipe, a un esecutore."""
    j = k
    while j < len(segs) and segs[j]["dopo"] in ("|", "|&"):
        j += 1
        if j < len(segs) and _e_esecutore(segs[j]):
            return True
    return False


def _legge_il_file(s2: dict, segs: list, k2: int, dn: str, chiave: str, env) -> bool:
    """Il segmento `s2` USA il contenuto del file `dn` come comando o come elenco di
    argomenti: lo esegue (`sh f`, `. f`, `bash < f`, `./f`), lo legge dentro una
    sostituzione (`$(cat f)`, `$(<f)`, apici inversi) che non e' solo un testo (un
    messaggio di `git commit -m`), o lo legge e lo manda a un esecutore lungo la
    pipe (`cat f | xargs cat`)."""
    toks = [t for t in s2["token"]]
    if _e_esecutore(s2) and any(_riferisce(t, s2, dn, chiave, env) for t in toks):
        return True
    if s2.get("cmd0") and _riferisce(s2["cmd0"], s2, dn, chiave, env) and (
            not s2["cmd0"].startswith("-")):
        return True
    if not _consumo_testo(s2):
        for interno in _sostituzioni(s2["testo"]):
            for t in _token(_maschera(interno)):
                if _riferisce(t, s2, dn, chiave, env):
                    return True
    if _dopo_pipe_esecutore(segs, k2) and any(
            _riferisce(t, s2, dn, chiave, env) for t in toks):
        return True
    return False


def _fase_b(segs: list, ris: dict, cwd0, env, prof: int, cons, hd: list) -> None:
    # le catene: segmenti collegati da pipe
    catena = None
    for k, s in enumerate(segs):
        if catena is None or segs[k - 1]["dopo"] not in ("|", "|&"):
            _CONTATORE[0] += 1
            catena = _CONTATORE[0]
        s["catena"] = catena
    differiti = []
    for k, s in enumerate(segs):
        nome = s["nome"]
        pipe_out = s["dopo"] in ("|", "|&")
        # il testo di questo segmento arriva a un esecutore lungo la pipe?
        pipe_esec = _dopo_pipe_esecutore(segs, k)
        catturato = cons is not None
        # echo/printf: inerti solo se stampano su un terminale o in un file,
        # senza pipe e fuori da una sostituzione (la regola e' quella)
        s["muto"] = nome in _MUTI and not pipe_out and not catturato
        flusso = (pipe_out and pipe_esec) or (catturato and not _consumo_testo(cons))
        esec = _e_esecutore(s)
        s["aqui"] = esec or flusso or nome == "read"
        s["aqui_testo"] = []
        ris["segmenti"].append(s)
        # sostituzioni (il loro output e' consumato da questo segmento), `sh -c`
        for interno in _sostituzioni(s["testo"]):
            r = _analizza(interno, cwd0, env, prof + 1, _copia_stato(s), s, hd)
            ris["segmenti"].extend(r["segmenti"])
            ris["corpi"].extend(r["corpi"])
        if nome in _SHELL:
            for i, a in enumerate(s["args"]):
                if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", a) and i + 1 < len(s["args"]):
                    _sotto(ris, s["args"][i + 1], s, cwd0, env, prof, hd)
                    break
        if nome == "eval":
            _sotto(ris, " ".join(s["args"]), s, cwd0, env, prof, hd)
        if nome == "trap" and s["args"] and not s["args"][0].startswith("-"):
            _sotto(ris, s["args"][0], s, cwd0, env, prof, hd)
        for cs in _script_azioni(s)[2]:
            _sotto(ris, cs, s, cwd0, env, prof, hd)
        # il testo di echo/printf che una pipe porta a un esecutore, o che una
        # sostituzione porta a un comando che lo esegue (`eval "$(echo 'cat x')"`,
        # `bash <(echo 'cat x')`), e' un comando (`echo "cat /x" | sh`): si analizza
        # come tale
        if nome in _MUTI and ((pipe_out and pipe_esec)
                              or (catturato and _e_esecutore(cons))):
            testo_e = _testo_echo(s)
            _sotto(ris, testo_e, s, cwd0, env, prof, hd)
            ris["corpi"].append((testo_e, s["cwd"], s))
        # echo/printf mandato a `tee file`: il testo finisce nel file
        if nome in _MUTI and pipe_out and k + 1 < len(segs) and segs[k + 1]["nome"] == "tee":
            dest_tee = _operandi(segs[k + 1])
            if dest_tee:
                differiti.append((k, _testo_echo(s), dest_tee[0]))
        # here-string: `read f <<< testo`, `sh <<< 'cmd'`
        prec = ""
        for t in s["token"]:
            if _punt(t):
                prec = t
                continue
            if prec == "<<<" and s["aqui"]:
                s["aqui_testo"].append(t)
                ris["corpi"].append((t, s["cwd"], s))
                if nome in _SHELL or nome == "eval":
                    _sotto(ris, t, s, cwd0, env, prof, hd)
            prec = ""
        # heredoc
        uscite = _uscite(s["token"])
        dest_hd = uscite[0] if uscite else None
        if dest_hd is None and nome == "tee":
            op_tee = _operandi(s)
            dest_hd = op_tee[0] if op_tee else None
        for hid in s["hd"]:
            if hid >= len(hd):
                continue
            corpo, quotato = hd[hid]["corpo"], hd[hid]["quotato"]
            if esec or flusso:
                _sotto(ris, corpo, s, cwd0, env, prof, hd)
                ris["corpi"].append((corpo, s["cwd"], s))
            elif _e_codice(nome):
                ris["corpi"].append((corpo, s["cwd"], s))
            else:
                if not quotato:
                    # un heredoc senza virgolette espande `$(...)` e gli apici
                    # inversi del suo corpo: quei comandi girano davvero
                    for interno in _sostituzioni(corpo):
                        _sotto(ris, interno, s, cwd0, env, prof, hd)
                if dest_hd:
                    differiti.append((k, corpo, dest_hd))
        if s["muto"] and uscite:
            differiti.append((k, _testo_echo(s), uscite[0]))
    # un testo scritto in un file e poi usato nello stesso comando come comando o
    # come elenco di percorsi
    for k, testo, dest in differiti:
        d = _espandi_var(dest, env, segs[k]["vars"])
        dn = _norm(d, segs[k]["cwd"] if segs[k]["cwd"] != _IGNOTA else None) if d else ""
        chiave = "" if dn else _chiave_simbolica(dest)
        if not dn and not chiave:
            continue
        for k2 in range(k + 1, len(segs)):
            s2 = segs[k2]
            if _legge_il_file(s2, segs, k2, dn, chiave, env):
                _sotto(ris, testo, s2, cwd0, env, prof, hd)
                ris["corpi"].append((testo, s2["cwd"], s2))
                break


def _parole_segmento_i(s: dict) -> list:
    """I token di un segmento che possono essere percorsi o nomi, come `(indice,
    token, redirezione)`: senza la punteggiatura, senza la parola che segue un
    heredoc (e' il segnaposto del delimitatore), senza il testo di una here-string
    che nessuno usa, e per `echo`/`printf` inerti solo i bersagli delle
    redirezioni (gli altri argomenti si stampano e basta). `redirezione` e' vero
    per il bersaglio di una redirezione: e' sempre un file."""
    muto = s.get("muto")
    out, prec = [], ""
    for i, t in enumerate(s["token"]):
        if _punt(t):
            prec = t
            continue
        heredoc = "<<" in prec and "<<<" not in prec
        aqui = "<<<" in prec
        redirezione = (">" in prec or "<" in prec) and not heredoc and not aqui
        prec = ""
        if heredoc or _RX_MARCA_HD.match(t):
            continue
        if aqui and not s.get("aqui"):
            continue
        if muto and not redirezione:
            continue
        out.append((i, t, redirezione))
    return out


def _parole_segmento(s: dict) -> list:
    return [t for _, t, _ in _parole_segmento_i(s)]


# Comandi i cui argomenti (non opzioni) sono FILE: un argomento a uno di questi e'
# sempre un percorso da controllare, anche se non esiste ancora (`mkdir`, `touch`,
# `cp x /nuovo/y`). Per un comando che non e' qui un argomento `/...` e' un
# percorso solo se esiste o se sta sotto una cartella che esiste (`_plausibile`):
# una regex, un tag HTML (`</article>`), un endpoint (`gh api /repos/x`) non lo sono.
_FILE_CMD = frozenset((
    "cat", "tac", "nl", "less", "more", "head", "tail", "wc", "cp", "mv", "rm",
    "rmdir", "ls", "ln", "touch", "mkdir", "chmod", "chown", "chgrp", "chflags",
    "find", "tar", "zip", "unzip", "gzip", "gunzip", "zcat", "bzip2", "bunzip2",
    "xz", "unxz", "stat", "file", "du", "df", "tee", "diff", "cmp", "sort", "uniq",
    "cut", "paste", "od", "xxd", "hexdump", "strings", "base64", "md5", "md5sum",
    "shasum", "sha1sum", "sha256sum", "sha512sum", "cksum", "realpath", "readlink",
    "basename", "dirname", "truncate", "install", "rsync", "scp", "ditto", "patch",
    "ed", "ex", "vi", "vim", "nano", "emacs", "code", "open", "bat", "tree",
    "source", ".", "cd", "pushd", "popd", "rev", "fold", "fmt", "join", "comm",
    "split", "csplit", "mktemp", "mkfifo", "dd", "shred", "unlink", "sponge",
    "grep", "egrep", "fgrep", "rg", "ag", "ack", "sed", "awk", "gawk", "mawk",
    "nawk", "jq", "perl", "sqlite3", "xattr", "stat", "qlmanage", "pbcopy"))
# Interpreti: `-c CODICE`, `-e CODICE`: il codice non e' un file.
_OPZ_CODICE = ("-c", "-e", "-E", "-p", "-r", "--eval", "--print")
# Opzioni di grep e rg che prendono un valore che e' testo o un modello, non un file.
_GREP_VALORE = frozenset((
    "-A", "-B", "-C", "-m", "-g", "-t", "-T", "-d", "-D", "-M", "-j", "--glob",
    "--iglob", "--type", "--type-not", "--include", "--exclude", "--exclude-dir",
    "--include-dir", "--max-depth", "--max-count", "--context", "--after-context",
    "--before-context", "--threads", "--max-columns", "--label"))
_FIND_VALORE = frozenset((
    "-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex",
    "-iregex", "-lname", "-ilname", "-type", "-xtype", "-perm", "-user", "-group",
    "-size", "-mtime", "-mmin", "-atime", "-amin", "-ctime", "-cmin", "-fstype",
    "-maxdepth", "-mindepth", "-links", "-uid", "-gid", "-newerXY"))
_GIT_VALORE_TESTO = frozenset((
    "-m", "--message", "--grep", "-S", "-G", "--author", "--committer", "--format",
    "--pretty", "--since", "--until", "--after", "--before", "-e", "--date",
    "--oneline-format", "-L"))
# `-F`/`--field` non ci sono: dipendono dal sottocomando (`_classi_token`). Con `gh api`
# `-F chiave=@file` legge il file, `-f` mai; per gli altri (`gh issue create -F f`,
# `gh pr create -F f`) `-F` e' il file del corpo.
_GH_VALORE_TESTO = frozenset((
    "-b", "--body", "-t", "--title", "-m", "--message", "-f",
    "--raw-field", "-H", "--header", "-q", "--jq", "--template", "-X", "--method",
    "-R", "--repo", "-d", "--description", "--notes", "-n", "--limit"))


def _operandi_indicizzati(s: dict, i0: int) -> list:
    """`(indice, token)` degli argomenti dopo il comando (indice `i0`), senza
    punteggiatura ne' bersagli di redirezione."""
    out, prec = [], ""
    for i in range(i0 + 1, len(s["token"])):
        t = s["token"][i]
        if _punt(t):
            prec = t
            continue
        if prec:
            prec = ""
            continue
        if _RX_MARCA_HD.match(t):
            continue
        out.append((i, t))
    return out


def _indice_comando(tok) -> int:
    """L'indice del token che e' il comando (dopo prefissi, assegnazioni, parole di
    controllo e opzioni dei prefissi): la stessa regola di `_spezza`."""
    return _scandisci_prefissi(list(tok))[0]


def _classi_token(s: dict):
    """`(testo, file)` di `_classi_token_x`: vedi li'."""
    return _classi_token_x(s)[:2]


def _classi_token_x(s: dict):
    """`(testo, file, extra)`: gli indici dei token di `s["token"]` che un comando NOTO usa
    come TESTO e non come file (il modello di `grep` e `rg`, lo script di `sed` e
    `awk`, il filtro di `jq`, il codice di `python -c`/`perl -e`, il formato di
    `date`, un endpoint di `gh api`, i valori di `find -name`, il messaggio di
    `git commit -m`), e quelli che sono SEMPRE un percorso (`git -C DIR`). Un
    token `/...` di testo non e' un percorso: `sed -n '/^## Parte 1/,/^## Parte
    2/p'`, `grep '</article>'`, `awk -F/ ...`, `gh api /repos/x/y/pulls`.

    `extra` dice dove stanno gli script di `sed` e `awk` (`"script"`: indici dei
    token) e le variabili di `awk -v` (`"vars"`): `_script_azioni` li legge per i
    file che lo script scrive, legge o lancia."""
    nome = (s["nome"] or "").lower()
    testo, file_ = set(), set()
    extra = {"script": [], "vars": []}
    if not nome:
        return testo, file_, extra
    i0 = _indice_comando(s["token"])
    el = _operandi_indicizzati(s, i0)
    n = len(el)
    if nome in ("sed", "gsed"):
        dato, k = False, 0
        while k < n:
            i, a = el[k]
            if a == "--":
                for i2, _ in el[k + 1:]:
                    if not dato:
                        testo.add(i2)
                        extra["script"].append(i2)
                        dato = True
                break
            if a in ("-e", "--expression") and k + 1 < n:
                testo.add(el[k + 1][0])
                extra["script"].append(el[k + 1][0])
                dato = True
                k += 2
                continue
            if a.startswith("--expression="):
                testo.add(i)
                extra["script"].append(i)
                dato = True
            elif a in ("-f", "--file"):
                dato = True
                k += 2
                continue
            elif a.startswith("--file="):
                dato = True
            elif a == "-i" and k + 1 < n and el[k + 1][1] == "":
                k += 2
                continue
            elif a.startswith("-") and a != "-":
                if re.match(r"^-[A-Za-z]*e$", a) and k + 1 < n:
                    testo.add(el[k + 1][0])
                    extra["script"].append(el[k + 1][0])
                    dato = True
                    k += 2
                    continue
                if re.match(r"^-[A-Za-z]*f$", a) and k + 1 < n:
                    # `sed -nf script`: il file dello script, non lo script
                    file_.add(el[k + 1][0])
                    dato = True
                    k += 2
                    continue
            elif not dato:
                testo.add(i)
                extra["script"].append(i)
                dato = True
            k += 1
    elif nome in ("awk", "gawk", "mawk", "nawk"):
        dato, k = False, 0
        while k < n:
            i, a = el[k]
            if a == "-F" or a == "-v":
                testo.add(i)
                if k + 1 < n:
                    testo.add(el[k + 1][0])
                    if a == "-v":
                        extra["vars"].append(el[k + 1][0])
                k += 2
                continue
            if a.startswith("-F") or a.startswith("-v"):
                testo.add(i)
                if a.startswith("-v"):
                    extra["vars"].append(i)
            elif a in ("-f", "--file"):
                dato = True
                k += 2
                continue
            elif a.startswith("--file="):
                dato = True
            elif a in ("-e", "--source") and k + 1 < n:
                testo.add(el[k + 1][0])
                extra["script"].append(el[k + 1][0])
                dato = True
                k += 2
                continue
            elif a.startswith("-") and a != "-":
                pass
            elif not dato:
                testo.add(i)
                extra["script"].append(i)
                dato = True
            k += 1
    elif nome in ("grep", "egrep", "fgrep", "rg", "ag", "ack", "zgrep", "pgrep"):
        dato, k = False, 0
        if any(a == "--files" for _, a in el):
            dato = True
        valori = _GREP_VALORE | (frozenset(("-r", "--replace")) if nome == "rg"
                                 else frozenset())
        while k < n:
            i, a = el[k]
            if a in ("-e", "--regexp") and k + 1 < n:
                testo.add(el[k + 1][0])
                dato = True
                k += 2
                continue
            if a.startswith("--regexp="):
                testo.add(i)
                dato = True
            elif a in ("-f", "--file") or (
                    re.match(r"^-[A-Za-z]*f$", a) and k + 1 < n):
                # `-f FILE` e `-rf FILE` (opzioni corte unite): il file dei modelli
                # si legge, non e' il modello
                if k + 1 < n:
                    file_.add(el[k + 1][0])
                dato = True
                k += 2
                continue
            elif a in valori and k + 1 < n:
                testo.add(el[k + 1][0])
                k += 2
                continue
            elif a.startswith("--") and "=" in a and a.split("=", 1)[0] in valori:
                testo.add(i)
            elif a.startswith("-") and a != "-":
                if re.match(r"^-[A-Za-z]*e$", a) and k + 1 < n:
                    testo.add(el[k + 1][0])
                    dato = True
                    k += 2
                    continue
            elif not dato:
                testo.add(i)
                dato = True
            k += 1
    elif nome == "jq":
        dato, k = False, 0
        while k < n:
            i, a = el[k]
            if a in ("--arg", "--argjson", "--slurpfile", "--rawfile") and k + 2 < n + 0:
                testo.add(el[k + 1][0])
                if a in ("--arg", "--argjson"):
                    testo.add(el[k + 2][0])
                k += 3
                continue
            if a in ("-f", "--from-file"):
                dato = True
                k += 2
                continue
            if a == "--args" or a == "--jsonargs":
                for i2, _ in el[k + 1:]:
                    testo.add(i2)
                break
            if a.startswith("-") and a != "-":
                pass
            elif not dato:
                testo.add(i)
                dato = True
            k += 1
    elif nome == "tr":
        testo.update(i for i, _ in el)
    elif nome == "date":
        testo.update(i for i, a in el if a.startswith("+"))
    elif nome == "find":
        k = 0
        while k < n:
            if el[k][1] in _FIND_VALORE and k + 1 < n:
                testo.add(el[k + 1][0])
                k += 2
                continue
            k += 1
    elif nome == "gh":
        sotto, k = None, 0
        while k < n:
            i, a = el[k]
            if not a.startswith("-") and sotto is None:
                sotto = a
            elif a in ("-F", "--field") and k + 1 < n:
                # `gh api -F chiave=@file` legge il file (con `=@`), altrimenti e'
                # testo; con un altro sottocomando `-F` e' il file del corpo
                v = el[k + 1][1]
                (file_ if sotto != "api" or "=@" in v else testo).add(el[k + 1][0])
                k += 2
                continue
            elif a.startswith("--field="):
                v = a.split("=", 1)[1]
                (file_ if sotto != "api" or v.startswith("@") or "=@" in v
                 else testo).add(i)
            elif a in _GH_VALORE_TESTO and k + 1 < n:
                testo.add(el[k + 1][0])
                k += 2
                continue
            elif a.startswith("--") and "=" in a and a.split("=", 1)[0] in _GH_VALORE_TESTO:
                testo.add(i)
            elif a == "--input" and k + 1 < n:
                file_.add(el[k + 1][0])
                k += 2
                continue
            elif sotto == "api" and not a.startswith("-"):
                testo.add(i)
            k += 1
    elif nome == "git":
        k, sotto = 0, None
        while k < n:
            i, a = el[k]
            if a == "-C" and k + 1 < n:
                file_.add(el[k + 1][0])
                k += 2
                continue
            if a in ("-c",) and k + 1 < n:
                # `-c include.path=/x` (e `core.excludesFile`, `core.hooksPath`...):
                # un valore che e' un percorso si legge o si esegue
                valore = el[k + 1][1].split("=", 1)[1] if "=" in el[k + 1][1] else ""
                (file_ if valore.startswith(("/", "~", "./", "../")) else testo).add(
                    el[k + 1][0])
                k += 2
                continue
            if a.startswith(("--git-dir=", "--work-tree=")):
                file_.add(i)
            elif a in ("--git-dir", "--work-tree") and k + 1 < n:
                file_.add(el[k + 1][0])
                k += 2
                continue
            elif not a.startswith("-") and sotto is None:
                sotto = a
            elif (a in _GIT_VALORE_TESTO or re.match(r"^-[A-Za-z]+m$", a)) and k + 1 < n:
                testo.add(el[k + 1][0])      # `-m msg`, `-am msg`
                k += 2
                continue
            elif a.startswith("--") and "=" in a and a.split("=", 1)[0] in _GIT_VALORE_TESTO:
                testo.add(i)
            elif re.match(r"^-[SG].", a):
                testo.add(i)
            elif sotto == "grep" and not a.startswith("-") and not any(
                    x == "--" for _, x in el[:k]) and k == next(
                        (j for j, (_, y) in enumerate(el) if y == "grep"), -1) + 1:
                testo.add(i)
            k += 1
    elif _e_interprete(nome):
        k = 0
        while k < n:
            i, a = el[k]
            if (a in _OPZ_CODICE or (nome == "perl" and re.match(r"^-[A-Za-z0-9.]*[eE]$", a))) \
                    and k + 1 < n:
                testo.add(el[k + 1][0])
                k += 2
                continue
            if not a.startswith("-"):
                break
            k += 1
    return testo, file_, extra


# --- gli script di sed e di awk ---------------------------------------------
#
# Il testo di uno script di `sed` o `awk` non e' un percorso, ma puo' SCRIVERE un file
# (`sed -n 'w f'`, `s/a/b/w f`, `awk '{print > "f"}'`), leggerne uno (`sed 'r f'`,
# `getline < "f"`) o lanciare un comando (`sed 'e cmd'`, `system("cmd")`, `print |
# "cmd"`, `"cmd" | getline`). Si leggono qui: i file tornano come percorsi e come
# scritture, i comandi si analizzano come un comando qualsiasi. Euristico: uno script
# che costruisce il nome a pezzi (`print > d "/x"`) non si vede.

def _sed_azioni(script: str):
    """`(scritti, letti, comandi)` di uno script di sed: i file dei comandi `w`/`W`
    e del flag `w` di `s///w`, quelli di `r`/`R`, il testo dei comandi `e`."""
    w, r, e = [], [], []
    i, n = 0, len(script)

    def resto(j):
        k = script.find("\n", j)
        k = n if k == -1 else k
        return script[j:k].strip(), k

    def fino_a(j, d):
        while j < n and script[j] != d:
            j += 2 if script[j] == "\\" else 1
        return j + 1

    while i < n:
        c = script[i]
        if c in " \t\n;{}!" or c.isdigit() or c in "$,~+":
            i += 1
        elif c in "/\\":
            d = "/"
            if c == "\\":
                if i + 1 >= n:
                    break
                d = script[i + 1]
                i += 1
            i = fino_a(i + 1, d)
            while i < n and script[i] in "IM":
                i += 1
        elif c == "#":
            i = resto(i)[1]
        elif c in "wWrRe":
            nome, i = resto(i + 1)
            if nome:
                (w if c in "wW" else r if c in "rR" else e).append(nome)
        elif c in "sy":
            if i + 1 >= n:
                break
            d = script[i + 1]
            j = fino_a(fino_a(i + 2, d), d)
            i = j
            if c == "s":
                while i < n and script[i] not in " \t\n;}":
                    if script[i] == "w":
                        nome, i = resto(i + 1)
                        if nome:
                            w.append(nome)
                        break
                    i += 1
        elif c in "aic":
            _, i = resto(i + 1)
            while script[:i].endswith("\\") and i < n:
                _, i = resto(i + 1)
        elif c in ":btT":
            i = resto(i + 1)[1]
        else:
            i += 1
    return w, r, e


_RX_AWK_STR = r'"((?:[^"\\]|\\.)*)"'


def _awk_azioni(script: str, variabili=None):
    """`(scritti, letti, comandi)` di un programma awk: i file di `> "f"` e `>> "f"`,
    quelli di `getline < "f"`, le stringhe di `system("...")`, `print | "cmd"` e `"cmd"
    | getline`. `variabili` e' `{nome: valore}` di `-v`: una variabile usata come
    bersaglio (`> f`, `< f`) vale come il file."""
    def s_(x):
        return re.sub(r"\\(.)", r"\1", x)
    w = [s_(m.group(1)) for m in re.finditer(r">>?\s*" + _RX_AWK_STR, script)]
    r = [s_(m.group(1)) for m in re.finditer(
        r"getline\b[^<>|;\n}]*?<\s*" + _RX_AWK_STR, script)]
    cmd = [s_(m.group(1)) for m in re.finditer(r"\|&?\s*" + _RX_AWK_STR, script)]
    cmd += [s_(m.group(1)) for m in re.finditer(
        _RX_AWK_STR + r"\s*\|\s*getline\b", script)]
    for m in re.finditer(r"\bsystem\s*\(", script):
        j, prof, lit = m.end(), 1, []
        while j < len(script) and prof:
            ch = script[j]
            if ch == '"':
                mm = re.compile(_RX_AWK_STR).match(script, j)
                if not mm:
                    break
                lit.append(s_(mm.group(1)))
                j = mm.end()
                continue
            prof += 1 if ch == "(" else -1 if ch == ")" else 0
            j += 1
        if lit:
            cmd.append("".join(lit))
    for nome, valore in (variabili or {}).items():
        if re.search(r">>?\s*\(?\s*%s\b" % re.escape(nome), script):
            w.append(valore)
        if re.search(r"<\s*\(?\s*%s\b" % re.escape(nome), script):
            r.append(valore)
    return w, r, cmd


def _script_azioni(s: dict):
    """`(scritti, letti, comandi)` dello script di un segmento `sed` o `awk` (vuoti
    per ogni altro comando). Si calcola una volta per segmento."""
    if "_azioni" in s:
        return s["_azioni"]
    nome = (s["nome"] or "").lower()
    ris = ([], [], [])
    if nome in ("sed", "gsed", "awk", "gawk", "mawk", "nawk"):
        try:
            _, _, ex = _classi_token_x(s)
            tok = s["token"]
            testi = [tok[i] for i in ex["script"] if i < len(tok)]
            if nome in ("sed", "gsed"):
                pezzi = [_sed_azioni(t.split("=", 1)[1] if t.startswith("--expression=")
                                     else t) for t in testi]
            else:
                var = {}
                for i in ex["vars"]:
                    v = tok[i] if i < len(tok) else ""
                    v = v[2:] if v.startswith("-v") else v
                    if "=" in v:
                        k, x = v.split("=", 1)
                        var[k] = x
                pezzi = [_awk_azioni(t, var) for t in testi]
            ris = tuple([x for p in pezzi for x in p[j]] for j in range(3))
        except (ValueError, IndexError, RecursionError):
            ris = ([], [], [])
    s["_azioni"] = ris
    return ris


def _plausibile(c: str) -> bool:
    """Un token `/...` (o `~/...`) che un comando NON noto riceve, o un percorso
    trovato in un testo di codice, e' un percorso da controllare solo se esiste o
    se una cartella che lo contiene, diversa dalla radice, esiste: `/script`,
    `/^## Parte 1/,...`, `/article>`, `/api/users` non sono percorsi. Un relativo
    si tiene (si risolve sulla cartella del comando, che esiste)."""
    e = os.path.expanduser(c) if c.startswith("~") else c
    if not e.startswith("/"):
        # un relativo si tiene (si risolve sulla cartella del comando), tranne una parola con
        # spazi o un `=` che non comincia con `./` o `../`: `generic/platform=iOS Simulator`
        # (l'argomento di `xcodebuild -destination`) non e' un file, e dopo un `cd` che non si
        # sa dove porta faceva negare un comando onesto
        return e.startswith(("./", "../")) or not re.search(r"[\s=]", e)
    q = re.sub(r"/{2,}", "/", e).rstrip("/")
    while q and q != "/":
        if os.path.lexists(q):
            return True
        q = os.path.dirname(q)
    return False


def _file_url(u: str):
    """Il percorso di un url `file:`, o None se non lo e' (o e' di un altro host)."""
    if not isinstance(u, str) or not u[:5].lower() == "file:":
        return None
    from urllib.parse import unquote, urlparse
    try:
        p = urlparse(u)
    except ValueError:
        return None
    if p.netloc not in ("", "localhost"):
        return None
    return unquote(p.path) or None


_RX_VAR_LISTA = re.compile(r"\$\{?[A-Za-z_]*(?:PATH|DIRS)\b")


def _varianti_token(t: str, env=None, locali=None):
    """Da un token di shell: se stesso e la parte dopo ogni `=`
    (`--dir=/x`, `chiave=@/x`), e senza la `@` iniziale (`curl -d @/x`, `gh api -F
    k=@/x` leggono il file). Torna `(percorsi, nomi_semplici)`: i primi sembrano un
    percorso (iniziano con `/`, `~`, `./`, `../` o contengono `/`), i secondi
    sono nomi senza barre (`cd cartella`, `git -C cartella`), che hanno senso
    solo risolti sulla cwd (vedi `_percorsi_da_comando`). Un url `file:` e' un
    percorso. Un elenco a due punti (`/a:/b`) vale come due percorsi solo se i due
    punti sono scritti nel comando (`docker -v $PWD:/app`): l'elenco che viene dal
    valore di una variabile (`$PATH`) o e' un'assegnazione a una variabile di elenco
    (`PATH=/x:$PATH cmd`) non e' un percorso."""
    if not t:
        return [], []
    if re.match(r"^[A-Za-z_]*PATH=", t):
        return [], []
    if t.startswith("-") and "=" not in t:
        # un'opzione (`-rf`), salvo che porti un percorso: `-I/usr/include`,
        # `-o/dest` (il percorso attaccato), o sia un nome che comincia con `-`
        # con una barra (le cartelle codificate di `~/.claude/projects` sono cosi':
        # `cat -Users-x-dir/memory/f`)
        if "/" not in t or t.startswith("--"):
            return [], []
        cand = [t]
        if len(t) > 2 and t[1].isalpha() and t[2] in "/~.":
            cand.append(t[2:])
    else:
        cand = [t]
        pos = t.find("=")
        while pos != -1:
            cand.append(t[pos + 1:])
            pos = t.find("=", pos + 1)
    cand.extend(c[1:] for c in list(cand) if c.startswith("@") and len(c) > 1)
    perc, nomi = [], []
    for c in cand:
        c = c.lstrip("<>&|(").strip()
        if not c or "$(" in c or "`" in c or "\x02" in c or "\n" in c or len(c) > 4096:
            continue
        f = _file_url(c)
        if f:
            perc.append(f)
            continue
        if _RX_URL.match(c):
            continue
        orig = c
        c = _espandi_var(c, env, locali)
        if not c:
            continue
        for c in _espandi_graffe(c):
            if c.startswith("/") and ":" in c:
                if ":" not in orig or _RX_VAR_LISTA.search(orig):
                    continue
                pezzi = [x for x in c.split(":") if x]
            else:
                pezzi = [c]
            for c in pezzi:
                if c == ".." or c.startswith(("/", "~", "./", "../")) or "/" in c:
                    perc.append(c)
                elif (not c.startswith("-") and len(c) <= 255
                      and not any(x.isspace() for x in c)):
                    nomi.append(c)
    return perc, nomi


def _trova_percorsi_in_testo(testo: str) -> list:
    out = []
    for m in re.finditer(r"""file:[^\s'"`;|&<>()\\]+""", testo, re.I):
        f = _file_url(m.group(0))
        if f:
            out.append(f)
    for m in _RX_ASSOLUTO.finditer(_RX_URL.sub(" ", testo)):
        c = m.group(1)
        if _solo_radice(c):
            continue
        out.append(c)
        c2 = c.rstrip(".,:")
        if c2 != c and not _solo_radice(c2):
            out.append(c2)
    return out


def _solo_radice(c: str) -> bool:
    """`c` (un candidato percorso trovato in un testo di codice) vale la radice `/`, o
    non e' altro che barre e punti: `//` e `///` sono i commenti di Swift, JS, C (e
    `///` la documentazione di Swift), `/.` e `/..` il resto di un'espressione. Nessuno e'
    la radice. Se restassero, la radice conterrebbe OGNI file protetto, e uno script di
    Python che modifica un sorgente Swift (`.replace(...)` piu' un commento `//`) sarebbe
    "una scrittura di settings.json" (348 falsi positivi in un giorno, 29/09/2026)."""
    return os.path.normpath(c).strip("/") == ""


_RX_RELATIVO_STR = re.compile(r"""['"]([^'"\s/~$][^'"\s]*/[^'"\s]*)['"]""")


def _trova_relativi_in_testo(testo: str) -> list:
    """Le stringhe fra virgolette che sembrano un percorso RELATIVO (`'a/b.txt'`)
    dentro il codice di un interprete: si risolvono sulla cartella del comando."""
    return [m.group(1) for m in _RX_RELATIVO_STR.finditer(testo)
            if "://" not in m.group(1) and "\x02" not in m.group(1)]


def _candidati_an(an: dict, env=None) -> list:
    """Percorsi e nomi che un comando Bash potrebbe toccare, come
    `(testo, tipo, cwd, segmento)`: `tipo` e' `p` (sembra un percorso) o `n` (un
    nome semplice), `cwd` la cartella in cui il segmento lo legge (simulata
    lungo i `cd`), `segmento` il dizionario di `_analizza` (None per il testo di
    un codice, dove si cercano solo percorsi assoluti).

    Un argomento e' un percorso candidato solo se sta nella posizione di un file:
    non il modello di `grep`/`rg`, non lo script di `sed`/`awk`, non il codice di
    un interprete (`_classi_token`); e per un comando che non e' fra quelli che
    operano su file (`_FILE_CMD`) un `/...` che non esiste e non sta sotto una
    cartella esistente non e' un percorso (`_plausibile`). Lo stesso per i
    percorsi cercati dentro un testo di codice."""
    trovati = []

    def plaus(lista):
        return [c for c in lista if _plausibile(c)]

    for s in an["segmenti"]:
        testo_i, file_i = _classi_token(s)
        noto = (s["nome"] or "").lower() in _FILE_CMD
        for i, t, redir in _parole_segmento_i(s):
            if i in testo_i:
                continue
            perc, semplici = _varianti_token(t, env, s["vars"])
            if not (noto or redir or i in file_i):
                perc = plaus(perc)
            trovati.extend((c, "p", s["cwd"], s) for c in perc)
            trovati.extend((c, "n", s["cwd"], s) for c in semplici)
        if _e_interprete(s["nome"]):
            for t in s["args"]:
                trovati.extend((c, "p", None, s) for c in plaus(_trova_percorsi_in_testo(t)))
                trovati.extend((c, "p", s["cwd"], s) for c in _trova_relativi_in_testo(t))
        w_, r_, _ = _script_azioni(s)
        for f in w_ + r_:
            # un file di uno script di sed o awk e' sempre un file (anche un nome
            # semplice, relativo alla cartella del segmento)
            perc, semplici = _varianti_token(f, env, s["vars"])
            trovati.extend((c, "p", s["cwd"], s) for c in perc + semplici)
        for t in s.get("aqui_testo") or ():
            trovati.extend((c, "p", None, s) for c in plaus(_trova_percorsi_in_testo(t)))
    for corpo, cw, _ in an["corpi"]:
        trovati.extend((c, "p", None, None) for c in plaus(_trova_percorsi_in_testo(corpo)))
        trovati.extend((c, "p", cw, None) for c in _trova_relativi_in_testo(corpo))
    visti, out = set(), []
    for c, tipo, cw, s in trovati:
        k = (c, tipo, cw, id(s))
        if c and k not in visti:
            visti.add(k)
            out.append((c, tipo, cw, s))
    return out


def _espandi_glob(c: str, cwd) -> list:
    """Le voci del disco che un token con un glob di shell (`cartella/*`,
    `PR-?.md`) espanderebbe, rispetto alla cwd. Vuoto se non c'e' glob o non
    combacia niente: il token letterale si controlla comunque."""
    if not _ha_glob(c):
        return []
    modello = os.path.expanduser(c)
    if not os.path.isabs(modello):
        modello = os.path.join(cwd or os.getcwd(), modello)
    try:
        return sorted(_glob_disco(modello))[:MAX_ESPANSIONE_GLOB]
    except (OSError, ValueError, re.error, RecursionError, OverflowError):
        return []


def _glob_disco(modello: str) -> list:
    """Le voci del disco che un glob ASSOLUTO espande, come `glob.glob`: `*`, `?` e le
    classi valgono dentro un componente, i nomi nascosti solo se il componente comincia
    con un punto, un componente senza glob deve esistere (anche un link rotto). Non usa
    `glob.glob`, che passa da `fnmatch.translate`: un token come `t[i-2:i+2]` (lo slicing
    di uno script Python nel comando) o `a[[-1]` ne uscirebbe come `re.error`, cioe' come
    un errore interno del guardiano. Qui un intervallo invertito o una `[` senza `]` sono
    caratteri letterali (`_classe_glob`). Una barra finale tiene solo le cartelle."""
    comp = [z for z in modello.split("/") if z]
    solo_dir = modello.endswith("/")
    percorsi = ["/"]
    for z in comp:
        nuovi = []
        if not _ha_glob(z):
            for base in percorsi:
                p = (base.rstrip("/") + "/" + z)
                if os.path.lexists(p):
                    nuovi.append(p)
        else:
            rx = _rx_glob(z, False)
            nascosti = z.startswith(".")
            for base in percorsi:
                try:
                    nomi = os.listdir(base)
                except OSError:
                    continue
                for nome in nomi:
                    if nome.startswith(".") and not nascosti:
                        continue
                    if rx.fullmatch(nome):
                        nuovi.append(base.rstrip("/") + "/" + nome)
        percorsi = nuovi
        if not percorsi:
            return []
    if solo_dir:
        return [p + "/" for p in percorsi if os.path.isdir(p)]
    return percorsi


def _percorsi_da_comando(cmd: str, cwd, nomi_semplici=False, env=None, avvisi=None):
    """I percorsi di un comando Bash, risolti, come `(testo, percorso,
    segmento)`. Ogni percorso relativo si risolve sulla cartella in cui il suo
    segmento parte (simulata lungo i `cd`); se quella non si sa
    (`cd -`, una variabile non definita) il percorso relativo vale `_IGNOTA`.
    Con `nomi_semplici` anche i token senza barre (`cd cartella`) risolti sulla
    cwd: solo per il predefinito, dove servono a vedere `cd cartella-di-un-nominato`
    da una cwd che sta sopra. Non per un nominato: con la cwd fuori dai suoi
    permessi ogni parola (`echo`, `ls`) risolverebbe fuori (ma vedi `valuta`: per
    un nominato la cwd stessa e' un percorso toccato da ogni comando). I token
    con un glob si espandono sul disco (`cat cartella/*`). Se un tetto (vedi
    `MAX_PERCORSI_COMANDO`) ferma l'analisi, lo si dice aggiungendo un testo alla
    lista `avvisi`."""
    an = _analizza(cmd, cwd, env)
    out, visti = [], set()
    n_nomi, n_glob = 0, 0

    def aggiungi(testo, n, s):
        k = (n, id(s))
        if n and k not in visti:
            visti.add(k)
            out.append((testo, n, s))

    for c, tipo, cw, s in _candidati_an(an, env):
        if tipo == "n":
            if not nomi_semplici:
                continue
            if n_nomi >= MAX_PERCORSI_COMANDO:
                if avvisi is not None and "nomi" not in avvisi:
                    avvisi.append("nomi")
                continue
            n_nomi += 1
        base = cw if cw is not None else cwd
        if base == _IGNOTA and not c.startswith(("/", "~")):
            if tipo == "p":
                aggiungi(c, _IGNOTA, s)
            continue
        aggiungi(c, _norm(c, base), s)
        if s is not None and s["nome"] == "du" and not any(
                re.match(r"^-[A-Za-z]*a", a) or a == "--all" for a in s["args"]):
            # `du -sh *` da una cartella che ha sotto una vietata mostra solo
            # dimensioni, non nomi ne' contenuti (con -a i nomi si vedono)
            continue
        for e in _espandi_glob(c, base):
            if n_glob >= MAX_ESPANSIONE_TOTALE:
                if avvisi is not None and "glob" not in avvisi:
                    avvisi.append("glob")
                break
            n_glob += 1
            aggiungi(e, _norm(e, base), s)
        if len(out) >= MAX_PERCORSI_DURO:
            if avvisi is not None:
                avvisi.append("percorsi")
            break
    return out


# I comandi che camminano un albero intero. Riconosciuti dal NOME del comando
# (il primo token di ogni segmento, dopo i prefissi `sudo`, `xargs`,
# `VAR=x`...), non da una parola qualsiasi nel testo: `echo find` non e' una
# ricerca.
_RICORSIVI_SEMPRE = ("ag", "ack", "zip", "rsync", "tar")


def _num_dopo(args, opzioni):
    for k, a in enumerate(args):
        for o in opzioni:
            if a == o and k + 1 < len(args) and args[k + 1].isdigit():
                return int(args[k + 1])
            if a.startswith(o + "=") and a.split("=", 1)[1].isdigit():
                return int(a.split("=", 1)[1])
            if len(o) == 2 and a.startswith(o) and a[2:].isdigit():
                return int(a[2:])
    return None


def _ricorsivita(s: dict):
    """Se il segmento cerca o copia ricorsivamente: `None` (no), `True` (senza
    limite) o un intero, la profondita' massima a cui puo' arrivare una cartella
    vietata perche' i suoi file siano letti (`find . -maxdepth 1`: nessuna;
    `tree -L 2`: le cartelle direttamente sotto la radice). Riconosce grep -r, rg,
    find, ls -R, tree, tar, zip, cp -r, rsync, git grep."""
    nome, args = s["nome"], s["args"]
    if not nome:
        return None
    if nome == "find":
        n = _num_dopo(args, ("-maxdepth",))
        if n is None:
            return True
        esegue = any(a in ("-exec", "-execdir", "-ok", "-okdir") for a in args)
        return n if esegue else n - 1
    if nome == "tree":
        n = _num_dopo(args, ("-L",))
        return True if n is None else n - 1
    if nome in ("rg", "fd"):
        n = _num_dopo(args, ("--max-depth", "-d"))
        if n is None:
            return True
        if nome == "fd" and not any(a in ("-x", "--exec", "-X", "--exec-batch")
                                    for a in args):
            return n - 1
        return n
    if nome in _RICORSIVI_SEMPRE:
        return True
    if nome in ("grep", "egrep", "fgrep"):
        if any(re.match(r"^-[A-Za-z]*[rR][A-Za-z]*$", a) or a in (
                "--recursive", "--dereference-recursive",
                "--directories=recurse") for a in args):
            return True
        if "-d" in args and "recurse" in args:
            return True
    elif nome == "ls":
        if any(re.match(r"^-[A-Za-z]*R", a) or a == "--recursive" for a in args):
            return True
    elif nome == "cp":
        if any(re.match(r"^-[A-Za-z]*[rRa][A-Za-z]*$", a) or a in (
                "--recursive", "--archive") for a in args):
            return True
    elif nome == "git":
        salta = False
        for a in args:
            if salta:
                salta = False
            elif a in ("-C", "-c", "--git-dir", "--work-tree"):
                salta = True
            elif not a.startswith("-"):
                if a == "grep":
                    return True
                break
    return None


def _ric_attiva(r) -> bool:
    """Una ricerca che entra in almeno una cartella."""
    return r is True or (isinstance(r, int) and not isinstance(r, bool) and r > 0)


def _ric(r, prof: int) -> bool:
    """La ricerca `r` (None, True o un limite) arriva a un percorso `prof`
    livelli sotto la sua radice?"""
    return r is True or (isinstance(r, int) and not isinstance(r, bool)
                         and 0 < prof <= r)


def _max_ric(a, b):
    if a is True or b is True:
        return True
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _ric_catene(an: dict) -> dict:
    """Per ogni catena di pipe di un comando, la ricerca piu' larga che contiene."""
    d = {}
    for s in an["segmenti"]:
        r = _ricorsivita(s)
        if r is not None:
            d[s["catena"]] = _max_ric(d.get(s["catena"]), r)
    return d


def percorsi_richiesti(nome: str, ti: dict, cwd, nomi_semplici=False, env=None,
                       avvisi=None):
    """Tutti i percorsi che una chiamata di strumento vuole toccare, come
    `(testo, percorso_risolto, ricorsivo)`. `ricorsivo` e' `None` (no), `True`
    (una ricerca che entra in tutto quello che sta sotto) o un intero (una
    ricerca a profondita' limitata): Grep e Glob sono ricerche, e una ricerca che
    parte da una cartella entra in tutto quello che ci sta sotto, compresa una
    cartella vietata. Grep senza `path` cerca nella cwd; Glob senza `path` con un
    modello assoluto no. `env` e' l'ambiente del payload (se c'e'), per le
    variabili dei comandi Bash. Il percorso `_IGNOTA` vale "un percorso relativo
    che non si sa dove porta"."""
    out = []
    corto = _nome_corto(nome)
    ricerca = corto in ("Grep", "Glob")

    # `Artifact` risolve i file sorgente rispetto a `root`, se c'e'.
    root = ti.get("root")
    base_file = _norm(root, cwd) if isinstance(root, str) and root else None

    def aggiungi(testo, ricorsivo=None, base=None):
        n = _norm(testo, base or cwd)
        if n:
            out.append((testo, n, ricorsivo))

    for k in CHIAVI_PERCORSO:
        v = ti.get(k)
        if isinstance(v, str) and v:
            aggiungi(v, True if ricerca and k == "path" else None)
    for k in CHIAVI_URL:
        f = _file_url(ti.get(k))
        if f:
            aggiungi(f)
    for k in CHIAVI_LISTA_PERCORSI:
        v = ti.get(k)
        if isinstance(v, list):
            for x in v:
                if isinstance(x, str) and x:
                    aggiungi(x, base=base_file)
                elif isinstance(x, dict):
                    for kk in CHIAVI_PERCORSO:
                        if isinstance(x.get(kk), str) and x[kk]:
                            aggiungi(x[kk], base=base_file)
    # `files` come mappa {percorso pubblicato: sorgente} (Artifact): il valore
    # e' il file locale, stringa o {"from": ...}. Il percorso pubblicato (la
    # chiave) non e' un file locale. Un valore {"artifact", "path"} copia da
    # un altro artifact e non tocca il disco.
    fm = ti.get("files")
    if isinstance(fm, dict):
        for val in fm.values():
            src = val if isinstance(val, str) else (
                val.get("from") if isinstance(val, dict) else None)
            if isinstance(src, str) and src:
                aggiungi(src, base=base_file)
    if ricerca:
        pth = ti.get("path")
        base = pth if isinstance(pth, str) and pth else (cwd or os.getcwd())
        pat = ti.get("pattern") if corto == "Glob" else None
        assoluto = (isinstance(pat, str) and pat.startswith(("/", "~")))
        if not (isinstance(pth, str) and pth) and not assoluto:
            aggiungi(base, True)
        if isinstance(pat, str) and pat:
            if pat.startswith(("/", "~")):
                d = _prefisso_glob_dir(os.path.expanduser(pat))
                if d:
                    aggiungi(d, True if _ha_glob(pat) else None)
            else:
                d = _prefisso_glob_dir(pat)
                if d:
                    aggiungi(os.path.join(os.path.expanduser(base), d), True)
    cmd = ti.get("command")
    if isinstance(cmd, str) and cmd:
        an = _analizza(cmd, cwd, env)
        ric_c = _ric_catene(an)
        trovati = _percorsi_da_comando(cmd, cwd, nomi_semplici, env, avvisi)
        for testo, n, s in trovati:
            r = ric_c.get(s["catena"]) if s is not None else None
            # Una `/` da sola non e' un percorso da negare (`ls /`), salvo che
            # una ricerca ricorsiva del SUO stesso segmento parta proprio da li'
            # (`find / -name x`): non basta che sia nella stessa pipe (`find . |
            # awk -F/ ...`, `... | tr '/' _`).
            if n == "/" and not (s is not None and _ric_attiva(_ricorsivita(s))):
                continue
            out.append((testo, n, r))
        for s in an["segmenti"]:
            r = _ricorsivita(s)
            if r is None:
                continue
            # Una ricerca senza una cartella o un file operando che esista
            # (`rg x`, `git grep x`) parte dalla cartella del suo segmento. Con
            # un operando che esiste (`grep -r x progetto`) parte da li', e la
            # cartella non c'entra. (`x`, il modello, non e' un percorso che
            # esiste: risolto sulla cartella non combacia con niente.)
            mie = [n for _, n, ss in trovati if ss is s]
            if any(n != _IGNOTA and os.path.exists(n) for n in mie):
                continue
            base = s["cwd"] if s["cwd"] is not None else cwd
            if base == _IGNOTA:
                out.append((base, _IGNOTA, r))
            elif base:
                n = _norm(base)
                if n:
                    out.append((base, n, r))
    return out


# --------------------------------------------------------------------------
# sessioni: da id a compartimento
# --------------------------------------------------------------------------

def _gruppo(nomi) -> list:
    return list(nomi) or [PREDEFINITO]


def _gruppo_da_tabella(chiave: str, ambito: Ambito, data_dir: str) -> list:
    """I gruppi di compartimenti delle sessioni che la tabella `sessions` di
    Plancia conosce sotto `chiave` (un `session_id` o un titolo), uno per
    sessione. Sola lettura (`mode=ro`), aperta solo qui per non pagare sqlite
    a ogni strumento. Un database bloccato o assente e' "nessuna riga"."""
    db = os.path.join(data_dir, "plancia.db")
    if not os.path.exists(db):
        return []
    try:
        import sqlite3
        from urllib.parse import quote
        try:
            conn = sqlite3.connect("file:%s?mode=ro" % quote(db), uri=True,
                                   timeout=0.3)
            conn.execute("SELECT 1 FROM sessions LIMIT 1")
        except sqlite3.OperationalError:
            # Misurato: con un database in WAL chiuso pulito (nessun file
            # -wal/-shm, cioe' Plancia non e' in esecuzione) un SQLite recente
            # non apre in `mode=ro` ("unable to open database file"). Senza un
            # -wal da leggere tutto e' nel file principale, e `immutable=1` e'
            # sicuro; con un -wal presente NON si ripiega (si perderebbero le
            # ultime scritture): la sessione resta "sconosciuta".
            if os.path.exists(db + "-wal"):
                raise
            conn = sqlite3.connect("file:%s?mode=ro&immutable=1" % quote(db),
                                   uri=True, timeout=0.3)
        try:
            righe = conn.execute(
                "SELECT cwd, file FROM sessions WHERE session_id=? LIMIT 1",
                (chiave,)).fetchall()
            if not righe and not _UUID.match(chiave):
                righe = conn.execute(
                    "SELECT cwd, file FROM sessions WHERE lower(title)=lower(?) "
                    "LIMIT 20", (chiave,)).fetchall()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - un db illeggibile e' "nessuna riga"
        return []
    gruppi = []
    for cwd_raw, file_ in righe:
        cwd = _norm(cwd_raw) if cwd_raw else ""
        gruppi.append(_gruppo(_nomi_da_segnali(
            ambito, (), (cwd,), (_da_trascrizione(file_)[1],))))
    return gruppi


def compartimenti_sessione(chiave: str, ambito: Ambito, data_dir: str):
    """I compartimenti della sessione (o delle sessioni) che `chiave` indica:
    una lista di GRUPPI, uno per sessione trovata, ciascuno la lista dei nomi
    nominati a cui la sessione appartiene (`[PREDEFINITO]` se la conosce solo
    Plancia). `None` se non se ne trova nessuna (sconosciuta).

    `chiave` e' quello che gli strumenti veri mandano: un id `local_<uuid>`
    dell'app, un nome (il titolo della sessione), oppure un `session_id`
    dell'hook. Le fonti, tutte:

    1. `X.sessioni` (per `session_id` o per id `local_` come scritto);
    2. il registro dell'app (`_voci_app`): un id `local_` si traduce nel
       `cliSessionId`, e la cwd e la cartella di apertura di quella sessione
       danno l'appartenenza per cartella; un nome si cerca fra i titoli;
    3. la tabella `sessions` di Plancia (cwd e file della sessione), per un
       `session_id` o un titolo. Un id `local_` non ci compare mai.

    Con piu' sessioni dello stesso titolo valgono tutte: chi decide le vuole
    tutte compatibili."""
    gruppi = []
    diretto = _nomi_da_segnali(ambito, (chiave,))
    if diretto:
        gruppi.append(diretto)
    if chiave.startswith("local_"):
        voci = _voci_app(ambito.home, chiave=chiave)
    elif not _UUID.match(chiave):
        voci = _voci_app(ambito.home, titolo=chiave)
    else:
        # un `session_id` crudo: la sessione e' nel registro dell'app col suo
        # `cliSessionId`, anche se non e' in nessuna lista `sessioni`
        voci = _voci_app(ambito.home, cli=chiave)
    for v in voci:
        gruppi.append(_gruppo(_nomi_da_segnali(
            ambito, (v["local"], v["cli"], chiave),
            (_norm(v["cwd"]), _norm(v["origine"])),
            (_codifica(os.path.expanduser(v["cwd"])) if v["cwd"] else "",
             _codifica(os.path.expanduser(v["origine"])) if v["origine"] else ""))))
    if not chiave.startswith("local_"):
        gruppi += _gruppo_da_tabella(chiave, ambito, data_dir)
    return gruppi or None


def _e_proprio(chiave: str, chi: dict, ambito: Ambito) -> bool:
    """`chiave` indica la sessione che chiama (o la sua madre).

    Oltre agli id dell'hook: `self`, che gli strumenti di sessione accettano
    per "questa sessione"; `main`, che un subagente usa per parlare alla
    sessione che l'ha lanciato (e' il modo documentato di SendMessage); e un id
    `local_` il cui `cliSessionId` e' quello di chi chiama."""
    mie = (chi["sessione"], chi["madre"])
    if chiave in mie or chiave == "self":
        return True
    if chiave == "main" and chi["subagente"]:
        return True
    if chiave.startswith("local_"):
        return any(v["cli"] and v["cli"] in mie
                   for v in _voci_app(ambito.home, chiave=chiave))
    return False


def _agente_proprio(chiave: str, chi: dict) -> bool:
    """`chiave` e' un subagente della sessione che chiama (un file
    `<madre>/subagents/agent-<chiave>.jsonl`): un nominato deve poter scrivere
    ai propri subagenti."""
    prog, madre = chi["cartella_progetto"], chi["madre"]
    if not (prog and madre) or "/" in chiave or chiave in ("", ".", ".."):
        return False
    pieno = chiave if chiave.startswith("agent-") else "agent-" + chiave
    return os.path.exists(os.path.join(prog, madre, "subagents", pieno + ".jsonl"))


# --------------------------------------------------------------------------
# la decisione
# --------------------------------------------------------------------------

def _stringhe(ti, chiavi):
    return [ti[k] for k in chiavi if isinstance(ti.get(k), str) and ti[k]]


def _nome_corto(tool: str) -> str:
    return tool.split("__")[-1] if tool.startswith("mcp__") else tool


def _env_payload(payload: dict):
    """L'ambiente del payload, se l'hook ne riceve uno (un dizionario di
    stringhe): serve a espandere le variabili di un comando Bash. Nessun hook
    di Claude Code lo manda, per quanto si e' visto: senza, le variabili si
    espandono con l'ambiente dell'hook e una non definita si ignora."""
    e = payload.get("env")
    if not isinstance(e, dict):
        return None
    return {k: v for k, v in e.items() if isinstance(k, str) and isinstance(v, str)}


def valuta(payload: dict, ambito: Ambito, chi: dict, data_dir: str):
    """La prima violazione di una chiamata, o None se e' ammessa. Torna
    `{"bersaglio", "motivo", "proprietario"}`."""
    nome = payload.get("tool_name")
    ti = payload.get("tool_input")
    if not isinstance(nome, str) or not nome:
        return None
    if not isinstance(ti, dict):
        ti = {}
    nominato = bool(chi["nomi"])
    mio = ",".join(chi["nomi"]) if nominato else PREDEFINITO

    # 0) i file del guardiano stesso: nessuna sessione li modifica
    v = _valuta_protetti(nome, ti, ambito, chi, data_dir, mio, _env_payload(payload))
    if v:
        return v
    # 1) sessioni: strumenti dell'app che leggono o scrivono altre sessioni
    v = _valuta_sessioni(nome, ti, ambito, chi, data_dir, mio)
    if v:
        return v
    # 2) Drive
    v = _valuta_drive(nome, ti, ambito, chi, mio)
    if v:
        return v
    # 3) comandi vietati (predefinito): rami git condivisi e simili
    cmd = ti.get("command")
    if not nominato and isinstance(cmd, str):
        for s in ambito.comandi_vietati:
            if s in cmd:
                return {"bersaglio": s, "proprietario": "un compartimento nominato",
                        "motivo": "compartimento %s: il comando nomina %r, che "
                                  "appartiene a un compartimento nominato" % (mio, s)}
    # 3b) un nominato con la cwd fuori dai suoi permessi: ogni comando parte da
    # li' e legge la cwd con parole senza barre (`cat nota.txt`, `ls`,
    # `grep -r x .`, `head *`) che l'estrazione dei percorsi non vede. La cwd e'
    # quindi un percorso toccato da ogni comando: se sta fuori, il comando si
    # nega e si dice come rientrare. (Una sessione e' di un nominato "solo per
    # id" proprio quando e' aperta fuori dalle sue cartelle: e' il caso normale.)
    # La cwd e' quella SIMULATA lungo il comando (`cd dentro && ls` parte da
    # dentro), e un `cd` da solo non legge niente: il suo bersaglio si controlla
    # fra i percorsi.
    if nominato and isinstance(cmd, str) and cmd:
        v = _valuta_cwd_nominato(cmd, chi, ambito, mio, _env_payload(payload))
        if v:
            return v
    # 3c) un nominato non scrive in una cartella di codice condivisa
    if nominato and ambito.condivise and isinstance(cmd, str) and cmd:
        v = _valuta_condivise(cmd, chi, ambito, mio, _env_payload(payload))
        if v:
            return v
    # 4) percorsi
    scrittura = _nome_corto(nome) in STRUMENTI_SCRITTURA
    avvisi = []
    for testo, p, ricorsivo in percorsi_richiesti(nome, ti, chi["cwd"] or None,
                                                  nomi_semplici=not nominato,
                                                  env=_env_payload(payload),
                                                  avvisi=avvisi):
        if p == _IGNOTA:
            if not nominato and _nome_semplice(testo) and not _ric_attiva(ricorsivo):
                # il predefinito: un nome semplice (`cp a b`, `git add .`) dopo una cartella
                # sconosciuta non nega, come `cat nota.txt` (vedi `_scrive_un_protetto` per il
                # nome di un file del guardiano); una ricerca o una copia RICORSIVA (`grep -r
                # x .`, `cp -r . x`, `tar`) da una cartella che non si sa resta negata
                continue
            return {"bersaglio": testo, "proprietario": "sconosciuto",
                    "motivo": "compartimento %s: il comando cambia cartella con una "
                              "destinazione che non si sa determinare (`cd -`, una "
                              "variabile non definita) e poi usa un percorso "
                              "relativo: scrivi percorsi assoluti" % mio}
        if nominato:
            v = _percorso_nominato(p, chi, ambito, mio, ricorsivo, scrittura)
        else:
            v = _percorso_predefinito(p, ricorsivo, ambito, mio)
        if v:
            return v
    if avvisi:
        # un tetto ha fermato l'analisi: il resto del comando non e' stato guardato
        if nominato:
            return {"bersaglio": "", "proprietario": "sconosciuto",
                    "motivo": "compartimento %s: il comando nomina troppi percorsi "
                              "(oltre il tetto dell'analisi: %s) per controllarli "
                              "tutti: spezzalo" % (mio, ", ".join(avvisi))}
        return {"bersaglio": "", "proprietario": "sconosciuto", "solo_nota": True,
                "motivo": "compartimento %s: il comando nomina troppi percorsi (oltre "
                          "il tetto dell'analisi: %s): il resto non e' stato "
                          "controllato" % (mio, ", ".join(avvisi))}
    return None


def _valuta_condivise(cmd, chi, ambito, mio, env):
    """Un comando Bash di un nominato che scrive, cancella o sposta dentro una
    cartella di codice condivisa (e non dentro i suoi permessi): negato. La
    lettura e l'esecuzione sono ammesse (vedi `_percorso_nominato`)."""
    for tipo, val, _ in _bersagli_scrittura(cmd, chi["cwd"] or None, env):
        if tipo in ("file", "contiene", "stato", "repo") and ambito.in_condivisa(val):
            if ambito.proprietari_percorso(val):
                continue        # dentro la cartella di un nominato: si decide li'
            return {"bersaglio": val, "proprietario": "condivisa",
                    "motivo": _MOTIVO_CONDIVISA % (mio, val)}
    return None


def _valuta_cwd_nominato(cmd, chi, ambito, mio, env):
    """Per un nominato: la cartella da cui parte ogni segmento del comando (la
    cwd simulata) deve stare nei suoi permessi. Un segmento `cd`/`pushd`/`popd`
    o di sole assegnazioni non legge la cartella; una cartella sconosciuta non nega
    (vedi sotto)."""
    for s in _analizza(cmd, chi["cwd"] or None, env)["segmenti"]:
        if not s["nome"] or s["nome"] in ("cd", "pushd", "popd"):
            continue
        cw = s["cwd"] if s["cwd"] is not None else (chi["cwd"] or None)
        if not cw:
            continue
        if cw == _IGNOTA:
            # una cartella che non si sa (`cd -`, una sostituzione che non si sa
            # valutare): un comando con un nome semplice (`ls`, `git status`, `cat
            # nota.txt`) non si nega, sarebbe il falso positivo di ogni script; un
            # percorso relativo con una barra si nega a parte (`valuta`, passo 4)
            continue
        v = _percorso_nominato(cw, chi, ambito, mio)
        if v:
            cartelle = [f for n in chi["nomi"] for f in ambito.nominati[n]["cartelle"]]
            return {"bersaglio": cw, "proprietario": v["proprietario"],
                    "motivo": "compartimento %s: la cartella di lavoro %s e' fuori "
                              "dai permessi di %s, e un comando da li' leggerebbe "
                              "file fuori dai permessi: sposta la sessione con "
                              "change_directory in una cartella del compartimento "
                              "(%s)" % (mio, cw, mio,
                                        ", ".join(cartelle) or "nessuna configurata")}
    return None


# Le chiavi di config.json che tengono acceso o configurano il guardiano.
CHIAVI_GUARDIANO = ("guardiano", "compartimenti", "strumenti_drive", "condivise")

# Scritture "per altre vie" dentro il codice di un interprete
# (`python3 -c "open(f, 'w')"`, `Path(f).write_text`, `os.remove`, `os.chmod`,
# `shutil`, `fs.writeFileSync`, `fs.rmSync`, `fs.renameSync`, `File.write`,
# `open(F, ">...")` di perl, `rename`, `config.save_config`, ...): se il testo nomina
# un file del guardiano E ha uno di questi segni, e' una scrittura.
# `json.load(open(f))` no.
_RX_CODICE_SCRIVE = re.compile(
    r"write|dump\(|os\.(?:replace|rename|remove|unlink|truncate|link|symlink|chmod|chown"
    r"|rmdir|removedirs)"
    r"|unlink|rmtree|shutil|truncate|save_config|appendFile|File\.open|File\.delete"
    r"|rmdir|removedirs|symlink|rimraf|rm_rf|rm_r\b|remove_entry|remove_tree|removeSync|\.rm\("
    r"|File\.rename|FileUtils|\bmv\b|\bcopyfile|\bcopy2?\("
    r"|\.replace\(\s*(?:[^(),]|\([^()]*\))+\)"
    r"|rmSync|renameSync|rmdirSync|copyFileSync|createWriteStream|\bchmod|\bchown|\brename\b"
    r"|\.move\("
    r"|open\s*\((?:[^()]|\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\))*?,\s*['\"](?:[wax]|r\+)[bt+]*['\"]"
    r"""|mode\s*=\s*['"][wax+]|open\s*\(?[^;\n]*['"]\s*\+?>""",
    re.I)
# Il codice che lancia un comando di shell (`os.system('rm x')`, `subprocess.run(
# ['rm', 'x'])`, `execSync`, `system(...)` di perl e ruby, `do shell script`): le
# stringhe del codice si analizzano come comandi (`_comandi_nel_codice`).
_RX_ESEGUE = re.compile(
    r"system|subprocess|popen|\bexec|spawn|shell script|shell_exec|passthru|\bqx\b|`"
    r"|Kernel|check_call|check_output|\.call\(|\bcall\(", re.I)
_RX_UNISCI = re.compile(r"""['"]\s*\+\s*['"]""")
_RX_STRINGA = re.compile(r"""'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)\"""")
# Operazioni di codice che colpiscono una CARTELLA (i permessi, lo spostamento, la
# rimozione): con il nome della cartella dei dati di Plancia nel testo bastano.
# `replace` nudo NO: `s.replace(vecchio, nuovo)` e' il metodo delle stringhe (un giro di
# modifica di un sorgente ne ha decine), non lo spostamento di una cartella. Restano
# `os.replace` e il `Path.replace(destinazione)` con UN argomento semplice (le stringhe
# ne vogliono almeno due, con la virgola).
_RX_DIR_OPS = re.compile(
    r"chmod|chown|rmtree|rmdir|removedirs|rename|os\.replace|\.replace\(\s*(?:[^(),]|\([^()]*\))+\)|"
    r"symlink|\.move\(|shutil|rmSync|renameSync|rmdirSync|"
    r"rm_rf|rm_r\b|remove_entry|remove_dir|remove_tree|rimraf|removeSync|\.rm\(", re.I)
_RX_SED_SUL_POSTO = re.compile(r"^(?:-[A-Za-z]*i|--in-place)")
# Il pacchetto di Plancia importato da un interprete, e cio' che lo usa per
# cambiare la config: `main([...])` della CLI, `save_config`, `sys.argv`.
_RX_PKG_PLANCIA = re.compile(
    r"\bfrom\s+plancia\b|\bimport\s+plancia\b|plancia\.(?:cli|config|compartimenti)\b"
    r"""|require\(\s*['"][^'"]*plancia""")
_RX_USA_CLI = re.compile(r"\bmain\s*\(|save_config|\bsys\.argv\b")
# La cartella dei dati di Plancia nominata per NOME (`os.environ['HOME'] + '/.plancia'`,
# `PLANCIA_HOME`), senza un percorso assoluto che l'espressione regolare dei
# percorsi possa vedere, insieme a uno dei file o delle chiavi del guardiano.
_RX_DATI_NOMINATI = re.compile(r"\.plancia\b|PLANCIA_HOME")
_RX_DATI_FILE = re.compile(r"config\.json|compartimenti|guardiano", re.I)

_MOTIVO_A_MANO = ("le impostazioni del guardiano le cambia il proprietario della "
                  "macchina a mano, fuori da una sessione")
_MOTIVO_SETTINGS = ("il file di impostazioni di Claude Code tiene acceso il guardiano: "
                    "si modifica con Edit o Write (che controllano che la voce "
                    "PreToolUse di plancia-guardiano resti e che non ci sia "
                    "disableAllHooks), non da Bash")
# Comandi di `find -exec` che non scrivono.
_LETTURA_ESEC = frozenset((
    "cat", "grep", "egrep", "fgrep", "head", "tail", "wc", "ls", "stat", "file", "md5",
    "md5sum", "shasum", "sha256sum", "du", "echo", "less", "more", "jq", "basename",
    "dirname", "readlink", "realpath", "printf", "test", "[", "true"))
# Sottocomandi di git che riscrivono l'albero di lavoro.
_GIT_SCRIVE = frozenset((
    "checkout", "restore", "reset", "clean", "stash", "switch", "merge", "rebase",
    "pull", "apply", "am", "cherry-pick", "revert", "rm", "mv", "checkout-index",
    "read-tree", "worktree", "submodule"))
# Sottocomandi di git che scrivono solo dentro `.git` (o crearlo): non toccano l'albero
# di lavoro, quindi non i file protetti, ma per una cartella condivisa sono scritture.
_GIT_SCRIVE_REPO = frozenset((
    "commit", "add", "fetch", "gc", "update-ref", "init", "push", "prune", "repack",
    "pack-refs", "commit-tree", "mktag", "replace", "filter-branch", "notes",
    "maintenance", "update-index", "symbolic-ref", "reflog", "bisect"))
# Opzioni di `git branch` e `git tag` che ELENCANO (e i loro operandi sono modelli o
# commit, non nomi da creare) e quelle che scrivono. Un raggruppamento corto (`-vl`, `-n5`)
# vale per ogni lettera.
_GIT_BRANCH_ELENCA = frozenset(("--list", "--contains", "--no-contains", "--merged",
                                "--no-merged", "--points-at"))
_GIT_BRANCH_SCRIVE = frozenset(("--delete", "--move", "--copy", "--force", "--track",
                                "--no-track", "--set-upstream-to", "--unset-upstream",
                                "--edit-description", "--create-reflog"))
_GIT_TAG_ELENCA = frozenset(("--list", "--contains", "--no-contains", "--merged",
                             "--no-merged", "--points-at", "--verify"))
_GIT_TAG_SCRIVE = frozenset(("--delete", "--force", "--annotate", "--sign", "--local-user",
                             "--message", "--file", "--edit"))
_GIT_NOTES_SCRIVE = frozenset(("add", "copy", "append", "edit", "merge", "remove", "prune"))


def _git_e_lettura(sotto, resto: list, opzioni: list) -> bool:
    """`git SOTTO ...` SOLO LEGGE, anche se un operando sembra un nome da scrivere:
    `branch --contains abc`, `branch --list 'x*'`, `tag -l 'v*'`, `reflog`, `notes list`,
    `notes show HEAD`, `fetch --dry-run`, `stash list`, `worktree list`, `submodule status`.
    `resto` sono le parole senza `-` dopo il sottocomando, `opzioni` quelle con `-`. Una
    scrittura (`branch nuovo`, `tag v1`, `tag -a v1 -m m`, `notes add`, `reflog expire`,
    `stash`, `fetch`) non e' una lettura; nel dubbio si tratta come scrittura."""
    corte = "".join(o[1:] for o in opzioni if not o.startswith("--"))
    lunghe = {o.split("=", 1)[0] for o in opzioni if o.startswith("--")}
    if sotto == "branch":
        if set(corte) & set("dDmMcCfut") or lunghe & _GIT_BRANCH_SCRIVE:
            return False
        return not resto or "l" in corte or bool(lunghe & _GIT_BRANCH_ELENCA)
    if sotto == "tag":
        if set(corte) & set("dasfmuFe") or lunghe & _GIT_TAG_SCRIVE:
            return False
        return (not resto or bool(set(corte) & set("lnv"))
                or bool(lunghe & _GIT_TAG_ELENCA))
    if sotto == "notes":
        return not (set(resto) & _GIT_NOTES_SCRIVE)
    if sotto == "reflog":
        return not (set(resto) & {"expire", "delete"})
    if sotto == "fetch":
        return "--dry-run" in opzioni
    if sotto == "stash":
        return resto[:1] in (["list"], ["show"])
    if sotto == "worktree":
        return resto[:1] == ["list"]
    if sotto == "submodule":
        return not resto or resto[0] in ("status", "summary")
    return False


# Comandi che con `-o FILE` scrivono FILE (per `ssh -o`, `grep -o`, `unzip -o`,
# `tar -o`, `ls -o`, `pytest -o` la stessa opzione vuol dire altro).
_OUT_O_CMD = frozenset((
    "gcc", "g++", "cc", "c++", "clang", "clang++", "ld", "rustc", "pandoc",
    "wkhtmltopdf", "swiftc", "javac", "go", "nvcc"))
_RX_GIT_LETTURA_CONFIG = re.compile(
    r"^(?:--get|--get-all|--get-regexp|--get-urlmatch|--list|-l|--show-origin|"
    r"--show-scope|--name-only|--default|--type)")


class _Protetti:
    """Cio' che tiene in piedi il guardiano, e che nessuna sessione tocca:

    - i file di stato: la config, la copia dell'ultima valida, il registro, il
      manifesto dei divieti;
    - il codice dell'hook: `bin/plancia-guardiano`, `plancia/__init__.py`,
      `plancia/compartimenti.py`, `plancia/config.py`, e ogni file `.py` (o
      modulo caricabile) in `bin/` e nella radice del checkout da cui gira
      l'hook: sono sul `sys.path` dell'hook, e un `json.py` li' gli
      toglierebbe il modulo di sistema (il wrapper si difende, ma non si lascia
      la porta aperta);
    - i file di impostazioni di Claude Code (`settings.json`,
      `settings.local.json`, ovunque stiano sotto una cartella `.claude`, e
      nella cartella di configurazione): qui la protezione e' MIRATA, non un
      divieto in blocco (`_controlla_settings`)."""

    def __init__(self, ambito: Ambito, data_dir: str):
        qui = os.path.realpath(__file__)
        self.radice = os.path.dirname(os.path.dirname(qui))
        self.bin = os.path.join(self.radice, "bin")
        self.dati = _norm(data_dir)
        elenco = [os.path.join(data_dir, "config.json"), _percorso_copia(data_dir),
                  _percorso_registro(data_dir), _percorso_registro(data_dir) + ".1",
                  os.path.join(data_dir, "guardiano.non-parte"),
                  os.path.join(self.bin, "plancia-guardiano"), qui,
                  os.path.join(self.radice, "plancia", "__init__.py"),
                  os.path.join(self.radice, "plancia", "config.py")]
        if ambito.manifesto:
            elenco.append(os.path.expanduser(ambito.manifesto))
        self.esatti = {n.lower() for n in (_norm(p) for p in elenco) if n}
        self.settings_utente = {
            n.lower() for n in (_norm(os.path.join(d, f))
                                for d in {ambito.claude_dir,
                                          os.path.join(ambito.home, ".claude")}
                                for f in ("settings.json", "settings.local.json")) if n}
        # le cartelle che li contengono: scriverci dentro "in massa" (find
        # -delete, un `cp -r` su tutta la cartella, un `tar x`) li tocca
        self.cartelle = {os.path.dirname(p) for p in self.esatti | self.settings_utente}
        # i loro NOMI, senza la cartella: dopo un `cd` che non si sa dove porta un nome
        # semplice puo' essere uno di questi (`cd $(cat lista) && rm config.json`)
        self.nomi = {os.path.basename(p) for p in self.esatti | self.settings_utente} | {
            "settings.json", "settings.local.json"}
        self.radice_l = self.radice.lower()
        self.bin_l = self.bin.lower()
        self.pycache_l = os.path.join(self.radice, "plancia", "__pycache__").lower()

    def tag(self, n: str):
        """`file` (protetto del tutto), `settings` (protetto in modo mirato) o
        None, per un percorso gia' risolto."""
        low = n.lower()
        if low in self.esatti:
            return "file"
        d = os.path.dirname(low)
        if d in (self.radice_l, self.bin_l) and low.endswith((".py", ".pyc", ".so", ".pth")):
            return "file"
        if (d == self.pycache_l and low.endswith(".pyc")
                and os.path.basename(low).split(".")[0] in ("__init__", "compartimenti", "config")):
            return "file"       # il codice gia' compilato: un pyc costruito a mano si esegue
        if (os.path.basename(low) == "__init__.py" and os.path.dirname(d) == self.radice_l
                and os.path.basename(d) != "plancia"):
            return "file"       # un pacchetto nuovo nella radice: `json/__init__.py`
        if low in self.settings_utente or (
                os.path.basename(low) in ("settings.json", "settings.local.json")
                and os.path.basename(d) == ".claude"):
            return "settings"
        return None

    def contiene(self, n: str):
        """`(percorso, tag)` di un file protetto dentro la cartella `n` (o `n`
        stesso), o None."""
        for p in sorted(self.esatti | self.settings_utente):
            if _dentro(p, n):
                return p, self.tag(p) or "file"
        return None

    def cartella_stato(self, n: str) -> bool:
        """`n` e' una cartella che contiene direttamente file protetti."""
        return n.lower().rstrip("/") in self.cartelle


def _voci_guardiano(testo: str):
    """Le voci PreToolUse di un settings che nominano `plancia-guardiano`, come
    dizionari `{command, matcher, timeout, async, if, type}`, o None se il testo non
    e' JSON."""
    try:
        d = json.loads(testo)
    except (ValueError, RecursionError):
        return None
    out = []
    hooks = d.get("hooks") if isinstance(d, dict) else None
    pre = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    for voce in pre if isinstance(pre, list) else ():
        if not isinstance(voce, dict):
            continue
        for h in voce.get("hooks") or ():
            c = h.get("command") if isinstance(h, dict) else None
            if isinstance(c, str) and "plancia-guardiano" in c:
                cond = h.get("if") if h.get("if") is not None else voce.get("if")
                out.append({"command": c, "matcher": voce.get("matcher"),
                            "timeout": h.get("timeout"), "async": h.get("async"),
                            "if": cond, "type": h.get("type")})
    return out


def _voce_efficace(v: dict) -> bool:
    """La voce del guardiano gira davvero su ogni strumento: nessun `matcher` che la
    restringe, nessun `if`, non e' `async` (non puo' negare), non ha un `timeout`
    che la uccide (meno di un secondo), e' un comando."""
    if v["matcher"] not in (None, "", "*", ".*"):
        return False
    if v["if"]:
        return False
    if v["async"] in (True, "true"):
        return False
    t = v["timeout"]
    if t is not None and not (isinstance(t, (int, float)) and not isinstance(t, bool)
                              and t >= 1):
        return False
    return v["type"] in (None, "command")


# Variabili d'ambiente che, messe nella chiave `env` di un settings, arrivano al
# processo dell'hook e lo fanno partire altrove o senza le sue librerie: il
# guardiano legge la config da PLANCIA_HOME (o HOME), importa moduli da PYTHONPATH,
# e parte con il python che trova in PATH. PLANCIA_PIATTAFORMA fa fingere una
# piattaforma alle prove di Plancia: gli script del guardiano e dell'hook non la
# guardano (decidono da `os.name`), ma resta fra le negate, perche' una riga che
# la mette in `env` non ha altro scopo che spegnere i confini.
_ENV_PERICOLOSE = frozenset((
    "PLANCIA_HOME", "PLANCIA_PIATTAFORMA", "HOME", "CLAUDE_CONFIG_DIR", "PYTHONPATH",
    "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONEXECUTABLE",
    "PYTHONINSPECT", "PYTHONBREAKPOINT", "PATH", "LD_PRELOAD", "LD_LIBRARY_PATH"))


def _env_pericolose(testo: str) -> dict:
    """Le voci di `env` di un settings che neutralizzerebbero il guardiano."""
    try:
        d = json.loads(testo)
    except (ValueError, RecursionError):
        return {}
    e = d.get("env") if isinstance(d, dict) else None
    if not isinstance(e, dict):
        return {}
    return {k: v for k, v in e.items() if isinstance(k, str)
            and (k in _ENV_PERICOLOSE or k.startswith(("DYLD_", "PYTHON")) and
                 k not in ("PYTHONIOENCODING", "PYTHONUTF8", "PYTHONDONTWRITEBYTECODE",
                           "PYTHONUNBUFFERED", "PYTHONWARNINGS"))}


def _testo_dopo_scrittura(corto: str, ti: dict, attuale: str):
    """Il contenuto che il file avra' dopo lo strumento di scrittura, o None se
    non si sa (parametri strani, un `old_string` che non c'e': lo strumento
    stesso fallira')."""
    if corto == "Write":
        c = ti.get("content")
        return c if isinstance(c, str) else None
    modifiche = []
    if corto == "Edit":
        modifiche = [ti]
    elif corto == "MultiEdit" and isinstance(ti.get("edits"), list):
        modifiche = [e for e in ti["edits"] if isinstance(e, dict)]
    else:
        return None
    testo = attuale
    for e in modifiche:
        vecchio, nuovo = e.get("old_string"), e.get("new_string")
        if not isinstance(vecchio, str) or not isinstance(nuovo, str) or vecchio not in testo:
            return None
        testo = testo.replace(vecchio, nuovo) if e.get("replace_all") else testo.replace(vecchio, nuovo, 1)
    return testo


def _controlla_settings(n: str, corto: str, ti: dict, P: _Protetti):
    """Il motivo per cui una scrittura su un file di impostazioni di Claude
    Code e' negata, o None. Ammessa SOLO se il contenuto risultante non ha
    `disableAllHooks` a vero e, quando il file ha oggi la voce PreToolUse del
    guardiano (lo stesso comando), la ha ancora: chi modifica settings.json per
    altri motivi non inciampa. Da Bash la scrittura si nega in blocco (non se ne
    vede il risultato)."""
    try:
        with open(n, "r", encoding="utf-8") as f:
            attuale = f.read()
    except (OSError, UnicodeDecodeError):
        attuale = ""
    nuovo = _testo_dopo_scrittura(corto, ti, attuale)
    if nuovo is None:
        return None
    try:
        d = json.loads(nuovo)
        spento = isinstance(d, dict) and d.get("disableAllHooks") in (True, "true")
    except (ValueError, RecursionError):
        spento = bool(re.search(r'"disableAllHooks"\s*:\s*"?true', nuovo))
    if spento:
        return ("scrive `disableAllHooks` a vero: spegnerebbe tutti gli hook, "
                "guardiano compreso")
    nuove_env = _env_pericolose(nuovo)
    vecchie_env = _env_pericolose(attuale)
    cambiate = sorted(k for k, v in nuove_env.items()
                      if k not in vecchie_env or vecchie_env[k] != v)
    if cambiate:
        return ("mette in `env` %s: arriverebbe al processo del guardiano e lo farebbe "
                "partire senza la sua config o le sue librerie" % ", ".join(cambiate))
    prima = _voci_guardiano(attuale)
    if prima:
        dopo = _voci_guardiano(nuovo)
        if dopo is None:
            ok = all(json.dumps(v["command"])[1:-1] in nuovo or v["command"] in nuovo
                     for v in prima)
        else:
            ok = all(any(x["command"] == v["command"] and _voce_efficace(x)
                         for x in dopo) for v in prima)
        if not ok:
            return ("toglie o cambia la voce PreToolUse di plancia-guardiano (il "
                    "comando, l'evento, un `matcher` che la restringe, un `if`, "
                    "`async`, un `timeout` troppo corto): spegnerebbe il guardiano")
    return None


def _protetti(ambito: Ambito, data_dir: str) -> list:
    """I file di stato e di codice del guardiano (elenco esatto, senza le zone)."""
    return sorted(_Protetti(ambito, data_dir).esatti)


def _operandi(s: dict) -> list:
    """Gli argomenti di un segmento che non sono opzioni, redirezioni ne' i
    loro bersagli (i file su cui il comando opera)."""
    out, prec = [], ""
    for t in s["token"][1:] if s["token"] and s["token"][0] == s["nome"] else s["args"]:
        if _punt(t):
            prec = t
            continue
        redir = bool(prec)
        prec = ""
        if redir or not t or (t.startswith("-") and len(t) > 1) or _RX_MARCA_HD.match(t):
            continue
        out.append(t)
    return out


def _cli_config_guardiano(s: dict):
    """La chiave del guardiano che un segmento imposta con la CLI di Plancia
    (`plancia config guardiano spento`, `python3 -m plancia.cli config ...`,
    `python3 bin/plancia config ...`, `$(which plancia) config ...`), o None.
    Senza un valore e' una lettura."""
    nome, args = s["nome"], s["args"]
    resto = None
    if nome == "plancia":
        resto = args
    elif _e_interprete(nome):
        for k, a in enumerate(args):
            if a == "-m" and k + 1 < len(args) and args[k + 1] in (
                    "plancia.cli", "plancia", "plancia.__main__"):
                resto = args[k + 2:]
                break
            if not a.startswith("-"):
                base = os.path.basename(a)
                if base == "plancia" or (base == "cli.py" and os.path.basename(
                        os.path.dirname(a)) == "plancia"):
                    resto = args[k + 1:]
                break
    if resto is None:
        return None
    parole = [a for a in resto if not _punt(a) and not a.startswith("-")]
    if len(parole) >= 3 and parole[0] == "config" and parole[1] in CHIAVI_GUARDIANO:
        return parole[1]
    return None


def _tar_estrae(args) -> bool:
    """`tar` estrae (`x`): con l'opzione lunga o corta, o nel gruppo all'antica
    (`tar xzf a.tgz`, `tar -xzf a.tgz`)."""
    if any(a in ("-x", "--extract", "--get") for a in args):
        return True
    if args and re.match(r"^-?[A-Za-z]+$", args[0]) and "x" in args[0]:
        return True
    return any(re.match(r"^-[A-Za-z]*x[A-Za-z]*$", a) for a in args)


def _comandi_nel_codice(t: str) -> list:
    """Le stringhe di un codice (`os.system('rm x')`, `subprocess.run(['rm', 'x'])`,
    `execSync("rm x")`, `do shell script "rm x"`) lette come comandi di shell: ogni
    stringa da sola, le stringhe di ogni lista `[...]` unite con lo spazio, e tutte
    insieme (con lo spazio e senza: `'rm '+'x'`). Al massimo una trentina."""
    lit = [m.group(1) if m.group(1) is not None else m.group(2)
           for m in _RX_STRINGA.finditer(t)]
    cand = []
    for m in re.finditer(r"\[([^\]]*)\]", t):
        parti = [x.group(1) if x.group(1) is not None else x.group(2)
                 for x in _RX_STRINGA.finditer(m.group(1))]
        if parti:
            cand.append(" ".join(parti))
    cand.append(" ".join(lit))
    cand.append("".join(lit))
    cand.extend(x for x in lit if " " in x or "/" in x)
    visti, out = set(), []
    for c in cand:
        if c and c not in visti and len(c) < 4096:
            visti.add(c)
            out.append(c)
    return out[:30]


def _link_creati(segs: list, cwd, env) -> list:
    """I collegamenti simbolici che il comando crea (`ln -s DESTINAZIONE COLLEGAMENTO`),
    come `(indice del segmento, percorso del collegamento, destinazione risolta)`: al
    momento dell'analisi non esistono ancora, e un `touch collegamento/f` dopo
    scriverebbe nella destinazione."""
    out = []
    for k, s in enumerate(segs):
        if s["nome"] != "ln":
            continue
        args = s["args"]
        if not any(a in ("-s", "--symbolic") or re.match(r"^-[A-Za-z]*s", a)
                   for a in args if a.startswith("-")):
            continue
        op = _operandi(s)
        if not op or len(op) > 2:
            continue
        b = s["cwd"] if s["cwd"] is not None else cwd
        if b == _IGNOTA:
            continue
        dest = _espandi_var(op[0], env, s["vars"])
        nome = _espandi_var(op[-1], env, s["vars"]) if len(op) == 2 else os.path.basename(
            (dest or "").rstrip("/"))
        if not dest or not nome:
            continue
        cartella = _norm(os.path.dirname(nome.rstrip("/")) or ".", b)
        if not cartella:
            continue
        link = os.path.join(cartella, os.path.basename(nome.rstrip("/")))
        if len(op) == 2 and os.path.isdir(link):
            link = os.path.join(link, os.path.basename(dest.rstrip("/")))
        alvo = _norm(dest, cartella)
        if alvo:
            out.append((k, link, alvo))
    return out


def _segui_link(n: str, links: list, k: int) -> str:
    """`n` dopo aver seguito i collegamenti creati dai segmenti PRIMA di `k`: un
    percorso sotto un collegamento appena creato e' nella sua destinazione."""
    for _ in range(4):
        cambiato = False
        for j, link, alvo in links:
            if j < k and _dentro(n, link) and n.lower() != link.lower().rstrip("/"):
                n = _norm(alvo + n[len(link.rstrip("/")):]) or n
                cambiato = True
        if not cambiato:
            break
    return n


def _dir_destinazione(args):
    """La cartella di `-t DIR`, `-tDIR`, `-rt DIR` (opzioni corte unite) e
    `--target-directory[=]DIR` di `cp`, `mv`, `install`, `ln`, o None."""
    for i, a in enumerate(args):
        if a in ("-t", "--target-directory") or re.match(r"^-[A-Za-z]*t$", a):
            if i + 1 < len(args):
                return args[i + 1]
        elif a.startswith("--target-directory="):
            return a.split("=", 1)[1]
        elif re.match(r"^-t.", a):
            return a[2:]
    return None


# --------------------------------------------------------------------------
# dove stanno i file del guardiano, per un codice che li costruisce da una variabile
# --------------------------------------------------------------------------
_RX_SETTINGS_NOMI = re.compile(r"settings(?:\.local)?\.json")
_RX_STR_NOME = re.compile(r"""['"]([^'"\s]+)['"]""")


def _var_del_comando(s, nome: str, env):
    """Cosa il COMANDO stesso dice della variabile `nome` per il segmento `s`: `("noto",
    valore)` se la assegna a un valore che si sa (`PLANCIA_HOME=/x python3 ...`, `env
    PLANCIA_HOME=/x python3 ...`, `export PLANCIA_HOME=/x; python3 ...`, un `PLANCIA_HOME=/x`
    prima); `("ignoto", None)` se la assegna a un valore che non si sa (una sostituzione di
    comando, una variabile non definita) o se prima c'e' un `source`/`eval` che potrebbe averla
    cambiata; `("nessuna", None)` se il comando non la assegna (allora vale quella con cui
    gira la sessione, che qui non si conosce come dato del comando)."""
    if not s:
        return "nessuna", None
    trovato = None
    for a in s.get("ass") or ():
        k, v = a.split("=", 1)
        if k == nome:
            val = _valore_var(v, env, s["vars"], k, s["testo"])
            trovato = ("noto", val) if isinstance(val, str) else ("ignoto", None)
    if trovato:
        return trovato
    vs = s["vars"]
    if nome in vs:
        return ("noto", vs[nome]) if isinstance(vs[nome], str) else ("ignoto", None)
    if vs.get(_FONTE):
        return "ignoto", None
    return "nessuna", None


def _casa_del_comando(s, env):
    """La HOME che il comando assegna a un valore noto (`HOME=/x python3 -c ...`), o None."""
    stato, v = _var_del_comando(s, "HOME", env)
    return v.rstrip("/") if stato == "noto" and v and v.rstrip("/") else None


def _cartelle_dati_nel_codice(t: str, s, env, cw, via_modulo: bool = False):
    """Le cartelle dei dati di Plancia che il codice `t` costruisce da una VARIABILE
    (`os.environ['PLANCIA_HOME'] + '/config.json'`, `Path.home() / '.plancia'`), risolte con
    quello che il comando assegna (`_var_del_comando`): `[cartella]`, o None se non si sa.
    Con `PLANCIA_HOME=/x` nello stesso comando la cartella e' `/x`, non quella vera; se la
    variabile non e' assegnata dal comando, o lo e' a un valore ignoto (dopo un `source` di un
    file sconosciuto, con una sostituzione), il bersaglio resta ignoto e vale la regola
    prudente. `via_modulo`: il codice importa `plancia.config` (`CONFIG_FILE`), che legge
    PLANCIA_HOME e poi HOME da solo, senza nominarli."""
    base_ = None if cw is None or cw == _IGNOTA else cw
    if via_modulo or "PLANCIA_HOME" in t:
        stato, v = _var_del_comando(s, "PLANCIA_HOME", env)
        if stato == "noto" and v:
            n = _norm(v, base_)
            return [n] if n else None
        if not (via_modulo and stato == "nessuna"):
            return None
    if via_modulo or re.search(r"\.plancia\b", t):
        stato, v = _var_del_comando(s, "HOME", env)
        if stato == "noto" and v:
            n = _norm(os.path.join(v, ".plancia"), base_)
            return [n] if n else None
    return None


def _dati_nel_codice(t: str, s, env, cw, chiave: str, scrive_file: bool, cartella: bool):
    """I bersagli che un codice `t` colpisce nella cartella dei dati di Plancia nominata per
    NOME (`PLANCIA_HOME`, `.plancia`): `scrive_file` (scrive il file di config o i suoi
    fratelli) e `cartella` (operazioni su una cartella: permessi, spostamento, rimozione).
    Se la cartella si sa (`_cartelle_dati_nel_codice`) il bersaglio e' quella, e lo decide chi
    consuma (e' la vera, o un'altra?); se non si sa, `("dati", chiave)`: la regola prudente."""
    if not (scrive_file or cartella):
        return
    cartelle = _cartelle_dati_nel_codice(t, s, env, cw, via_modulo=(chiave == "CONFIG_FILE"))
    if cartelle is None:
        yield ("dati", chiave, None)
        return
    for d in cartelle:
        yield ("stato", d, None)
        if cartella:
            yield ("contiene", d, None)


def _nomi_relativi_nel_codice(t: str, nomi) -> list:
    """Le stringhe di un codice che sono il nome (o un percorso relativo che finisce con il
    nome) di uno dei file `nomi` (minuscoli): `open('settings.json', 'w')`, `Path('sub/config.json')`.
    Al massimo una ventina."""
    out = []
    for m in _RX_STR_NOME.finditer(t):
        lit = m.group(1).lstrip("<>+|&=")
        if (not lit or lit.startswith(("/", "~")) or len(lit) > 255 or "$" in lit
                or "\x02" in lit):
            continue
        if os.path.basename(lit.rstrip("/")).lower() in nomi:
            out.append(lit)
            if len(out) >= 20:
                break
    return out


# --------------------------------------------------------------------------
# un percorso nominato in un testo di codice: e' un operando o solo una parola?
# --------------------------------------------------------------------------
# Le funzioni (di Python, Node, Ruby, Perl, PHP) che scrivono, cancellano, spostano o cambiano
# i permessi di quello che ricevono come argomento. Il nome si confronta minuscolo, senza
# l'eventuale `_` iniziale e senza il suffisso `Sync` (`rmSync` -> `rm`). `replace` non c'e':
# `s.replace(a, b)` e' il metodo delle stringhe, si valuta a parte (`_e_replace_di_file`).
# `write_text` e `write_bytes` neanche: come argomento sono il CONTENUTO, non il percorso.
_OP_ARGOMENTO = frozenset((
    "rmtree", "rmdir", "removedirs", "remove", "unlink", "rm", "rm_rf", "rm_r", "rm_f", "rimraf",
    "remove_entry", "remove_entry_secure", "remove_dir", "remove_tree", "del", "delete", "trash",
    "shred", "chmod", "lchmod", "chmod_r", "chown", "lchown", "chown_r", "chgrp", "chflags",
    "rename", "renames", "move", "mv", "copy", "copy2", "copyfile", "copytree", "copymode",
    "copystat", "cp", "cp_r", "copyfileobj", "symlink", "link", "truncate", "mkdir", "mkdirs",
    "mkdir_p", "makedirs", "mkpath", "make_path", "mkdirp", "ensuredir", "emptydir", "touch",
    "extractall", "extract", "unpack_archive", "make_archive", "writefile", "appendfile",
    "createwritestream", "outputfile", "outputjson", "writejson", "save_config", "cpsync"))
# I metodi di un oggetto-percorso (`Path('/x').rmdir()`, `.chmod(0)`, `.rename(dest)`): qui il
# percorso e' il RICEVENTE, non un argomento.
_OP_RICEVENTE = frozenset((
    "rmdir", "unlink", "rename", "chmod", "lchmod", "chown", "touch", "mkdir", "write_text",
    "write_bytes", "symlink_to", "hardlink_to", "link_to", "rmtree"))
_RX_NOME_CHIAMATA = re.compile(r"(?:([A-Za-z_$][\w$]*)\s*\.\s*)?([A-Za-z_$][\w$]*)\s*$")
_RX_CHIAMATA = re.compile(r"(?:([A-Za-z_$][\w$]*)\s*\.\s*)?([A-Za-z_$][\w$]*)\s*\(")
_RX_ATTRIBUTO = re.compile(r"\s*\.\s*([A-Za-z_$][\w$]*)")
_RX_LEGA_ASSEGNA = re.compile(
    r"^\s*(?:(?:const|let|var|export|local|final)\s+)?([A-Za-z_$][\w$.]*)\s*"
    r"(?<![=!<>])(?::?=|\+=)(?!=)")
_RX_LEGA_PER = re.compile(
    r"^\s*(?:async\s+)?for\s*\(?\s*(?:(?:const|let|var)\s+)?([A-Za-z_$][\w$]*)"
    r"(?:\s*,\s*[A-Za-z_$][\w$]*)*\s+(?:in|of)\b")
_RX_LEGA_AGGIUNGI = re.compile(r"([A-Za-z_$][\w$]*)\s*\.\s*(?:append|add|push|extend|insert|unshift)$")


def _nome_op(n: str, prefisso=None) -> str:
    """Il nome di una funzione per il confronto con `_OP_ARGOMENTO`: minuscolo, senza `_`
    iniziale e senza il suffisso `Sync` (`rmSync` -> `rm`); `rimraf.sync` e' `rimraf`."""
    n = n.lower().lstrip("_")
    if n == "sync" and prefisso:
        return _nome_op(prefisso)
    return n[:-4] if n.endswith("sync") and len(n) > 4 else n


def _fine_gruppo(t: str, p: int, tetto: int = 2000):
    """`(indice della chiusura, numero di virgole al primo livello)` del gruppo che si apre in
    `t[p]` (`(`, `[` o `{`), o `(-1, virgole)` se non si chiude entro il tetto. Le stringhe fra
    virgolette si saltano."""
    chiude = {"(": ")", "[": "]", "{": "}"}
    pila = [chiude[t[p]]]
    virgole, i, n = 0, p + 1, min(len(t), p + tetto)
    while i < n:
        c = t[i]
        if c in "'\"":
            j = i + 1
            while j < n and t[j] != c:
                j += 2 if t[j] == "\\" else 1
            i = j + 1
            continue
        if c in "([{":
            pila.append(chiude[c])
        elif c in ")]}":
            if c != pila[-1]:
                return -1, virgole
            pila.pop()
            if not pila:
                return i, virgole
        elif c == "," and len(pila) == 1:
            virgole += 1
        i += 1
    return -1, virgole


def _aperture_intorno(t: str, i: int, indietro: int = 800, livelli: int = 6) -> list:
    """Le parentesi (`(`, `[`, `{`) ancora aperte in `t[i]`, dalla piu' interna: `(posizione,
    carattere)`. Solo un tratto di testo prima di `i`, e al massimo `livelli` parentesi."""
    fuori, pila, j = [], 0, i - 1
    stop = max(0, i - indietro)
    while j >= stop and len(fuori) < livelli:
        c = t[j]
        if c in ")]}":
            pila += 1
        elif c in "([{":
            if pila:
                pila -= 1
            else:
                fuori.append((j, c))
        j -= 1
    return fuori


def _inizio_frase(t: str, i: int) -> int:
    return max(t.rfind("\n", 0, i), t.rfind(";", 0, i)) + 1


def _e_replace_di_file(t: str, p: int, prima: str) -> bool:
    """`replace(` che si apre in `t[p]` e' lo spostamento di un file e non il metodo delle
    stringhe: `os.replace(a, b)`, o `Path(x).replace(destinazione)` (un solo argomento)."""
    m = _RX_NOME_CHIAMATA.search(prima)
    if m and m.group(1) == "os":
        return True
    return _fine_gruppo(t, p)[1] == 0


def _catena_operativa(t: str, k: int) -> bool:
    """Dopo una chiusura (`Path('/x')` finisce in `t[k-1]`) segue un metodo che scrive o
    cancella il percorso (`.rmdir()`, `.chmod(0)`, `.rename(d)`, con in mezzo `.resolve()`,
    `.parent`...)?"""
    for _ in range(5):
        m = _RX_ATTRIBUTO.match(t, k)
        if not m:
            return False
        nome, k = _nome_op(m.group(1)), m.end()
        if nome == "replace" and k < len(t) and t[k] == "(":
            if _fine_gruppo(t, k)[1] == 0:
                return True
        elif nome in _OP_RICEVENTE and k < len(t) and t[k] == "(":
            return True
        if k < len(t) and t[k] == "(":
            fine = _fine_gruppo(t, k)[0]
            if fine < 0:
                return False
            k = fine + 1
    return False


def _legato_a(frase: str) -> set:
    """I nomi di variabile a cui la `frase` (il tratto di una istruzione prima di un percorso)
    lega quello che segue: `d = `, `for d in `, `lista.append(`."""
    nomi = set()
    m = _RX_LEGA_ASSEGNA.match(frase)
    if m:
        nomi.add(m.group(1))
    m = _RX_LEGA_PER.match(frase)
    if m:
        nomi.add(m.group(1))
    return nomi


def _nome_operante(t: str, nome: str, giri: int = 1) -> bool:
    """La variabile `nome` finisce come argomento di una funzione che scrive o cancella
    (`shutil.rmtree(nome)`, `os.chmod(nome, 0)`), o riceve un suo metodo (`nome.rmdir()`), o
    e' la variabile di un ciclo (`for x in nome`) che a sua volta lo fa."""
    esc = r"(?<![\w$.])" + re.escape(nome) + r"(?![\w$])"
    for m in _RX_CHIAMATA.finditer(t):
        n = _nome_op(m.group(2), m.group(1))
        if n not in _OP_ARGOMENTO and n != "replace":
            continue
        p = m.end() - 1
        fine, virgole = _fine_gruppo(t, p)
        if n == "replace" and not (m.group(1) == "os" or virgole == 0):
            continue
        if re.search(esc, t[p + 1:fine if fine > 0 else min(len(t), p + 400)]):
            return True
    if re.search(esc + r"(?:\s*\.\s*\w+(?:\s*\([^()]*\))?)*\s*\.\s*(?:" + "|".join(
            sorted(_OP_RICEVENTE)) + r")\s*\(", t):
        return True
    if giri:
        for m in re.finditer(
                r"\bfor\s*\(?\s*(?:(?:const|let|var)\s+)?([A-Za-z_$][\w$]*)(?:\s*,\s*"
                r"[A-Za-z_$][\w$]*)*\s+(?:in|of)\s+[^\n]*?" + esc, t):
            if _nome_operante(t, m.group(1), giri - 1):
                return True
        # `lista.forEach(p => fs.rmSync(p))`: il parametro della funzione e' l'elemento
        for m in re.finditer(esc + r"\s*\.\s*(?:forEach|map|flatMap|filter|some|every)\s*\(\s*"
                             r"(?:async\s+)?\(?\s*([A-Za-z_$][\w$]*)", t):
            if _nome_operante(t, m.group(1), giri - 1):
                return True
    return False


def _operando_di_scrittura(t: str, c: str) -> bool:
    """Il candidato `c` (un percorso trovato in un testo di codice) compare in `t` come un
    OPERANDO di una scrittura, di una cancellazione, di uno spostamento o di un cambio di
    permessi, e non come una parola del testo (una regex, un elenco, una stringa da
    sostituire)? Lo e' se sta fra le parentesi di una chiamata di `_OP_ARGOMENTO`
    (`shutil.rmtree('/x')`, `os.chmod(os.path.join('/x', d), 0)`), se e' il ricevente di un
    metodo di `_OP_RICEVENTE` (`Path('/x').rename(d)`), o se e' legato a una variabile che poi
    lo e' (`p = '/x'; shutil.rmtree(p)`, `for d in ['/x']: os.rmdir(d)`). Euristico: cerca in un
    tratto corto di testo attorno a ogni comparsa (le prime 120); se `c` non si trova in `t`
    (un percorso ricavato da un `file:///...`), vale come operando: la regola prudente."""
    k, visti, memo = t.find(c), 0, {}
    if k < 0:
        return True
    while k >= 0 and visti < 120:
        visti += 1
        legati = _legato_a(t[_inizio_frase(t, k):k])
        for p, ch in _aperture_intorno(t, k):
            prima = t[max(0, p - 80):p]
            if ch == "(":
                m = _RX_NOME_CHIAMATA.search(prima)
                if m:
                    n = _nome_op(m.group(2), m.group(1))
                    if n == "replace":
                        if _e_replace_di_file(t, p, prima):
                            return True
                    elif n in _OP_ARGOMENTO:
                        return True
                    elif re.match(r"^(?:append|add|push|extend|insert|unshift)$", n) and m.group(1):
                        legati.add(m.group(1))
                fine = _fine_gruppo(t, p)[0]
                if fine > 0 and _catena_operativa(t, fine + 1):
                    return True
            legati |= _legato_a(t[_inizio_frase(t, p):p])
        for nome in sorted(legati)[:6]:
            if nome not in memo:
                memo[nome] = _nome_operante(t, nome)
            if memo[nome]:
                return True
        k = t.find(c, k + 1)
    return False


def _bersagli_scrittura(cmd: str, cwd, env=None, prof: int = 0, nomi_rel=None):
    """Ogni posto in cui un comando Bash SCRIVE, cancella, sposta o cambia i
    permessi, come `(tipo, valore, segmento)`: `file` (un percorso risolto),
    `contiene` (una cartella di cui si cancella o sposta il contenuto: `rm -r`),
    `stato` (una cartella in cui si scrive in massa o si cambiano i permessi),
    `ignota` (un percorso relativo dopo un `cd` che non si sa dove porta),
    `cli` (una chiave di config del guardiano impostata con la CLI di Plancia) e
    `dati` (il file di config nominato per nome dentro un codice, quando la cartella dei dati
    che il codice costruisce da una variabile non si sa: se si sa e' un `stato`/`contiene`
    su quella cartella). Con `nomi_rel` (i nomi dei file protetti, minuscoli) anche le stringhe
    di un codice che sono uno di quei nomi (`open('settings.json', 'w')`) contano come `file`,
    risolti sulla cartella da cui parte il segmento. Chi lo usa
    decide cosa e' protetto (`_scrive_un_protetto`) o in sola lettura
    (`_valuta_condivise`).

    EURISTICO, dichiarato: chi vuole aggirarlo ci riesce (un percorso costruito a
    pezzi dentro uno script). Chiude il caso ordinario: `plancia config guardiano
    spento`, `sed -i`, `tee`, una redirezione, `cp x config.json`, `python3 -c` che
    scrive il file o lancia `rm` con `os.system`/`subprocess`, `rm`/`mv` del file o
    della cartella che lo contiene (anche con graffe, glob, variabili, cicli `for`,
    sostituzioni `$(...)`, `xargs`), `find -delete`, `curl -o`, `tar x -C`, `git
    checkout` nella cartella. I percorsi relativi si risolvono sulla cartella
    SIMULATA del segmento. La lettura non compare."""
    an = _analizza(cmd, cwd, env)
    segs = an["segmenti"]
    hdl = an.get("hd") or []
    pos = {id(x): i for i, x in enumerate(segs)}
    links = _link_creati(segs, cwd, env) if any(x["nome"] == "ln" for x in segs) else []

    def base(s):
        return s["cwd"] if s["cwd"] is not None else cwd

    def risolvi(x, s):
        """I percorsi risolti a cui punta `x` (anche con graffe e glob di shell), o
        None se `x` e' relativo e la cartella non si sa."""
        x = _espandi_var(x, env, s["vars"])
        if not x:
            return []
        b = base(s)
        if b == _IGNOTA and not x.startswith(("/", "~")):
            return None
        out = []
        for xx in _espandi_graffe(x):
            for c in [xx] + _espandi_glob(xx, b):
                n = _norm(c, b)
                if n:
                    out.append(_segui_link(n, links, pos.get(id(s), 0)) if links else n)
        return out

    def tipo_(t, x, s):
        r = risolvi(x, s)
        if r is None:
            # il testo GIA' espanso (`f=sub/f; cd - && touch $f` nomina `sub/f`): chi
            # decide guarda se ha una barra
            yield ("ignota", _espandi_var(x, env, s["vars"]) or x, s)
            return
        for n in r:
            yield (t, n, s)

    def destinazione(operandi, s):
        """Il file che un `cp`/`mv`/`install`/`rsync` scrive: l'ultimo operando, o
        (se e' una cartella) la cartella piu' il nome di ogni sorgente."""
        if not operandi:
            return
        yield from tipo_("file", operandi[-1], s)
        r = risolvi(operandi[-1], s) or []
        if len(operandi) >= 2 and r and (operandi[-1].endswith("/") or os.path.isdir(r[0])):
            for src in operandi[:-1]:
                n = _norm(os.path.join(r[0], os.path.basename(src.rstrip("/"))))
                if n:
                    yield ("file", n, s)

    def valore_opzione(args, brevi, lunghe):
        """Il valore di un'opzione (`-o x`, `-ox`, `--output x`, `--output=x`)."""
        for i, a in enumerate(args):
            for o in brevi:
                if a == o and i + 1 < len(args):
                    return args[i + 1]
                if a.startswith(o) and len(a) > len(o) and not a.startswith("--"):
                    return a[len(o):]
            for o in lunghe:
                if a == o and i + 1 < len(args):
                    return args[i + 1]
                if a.startswith(o + "="):
                    return a.split("=", 1)[1]
        return None

    def parole_utili(tokens):
        return [t for t in tokens if t and not _punt(t) and not t.startswith("-")
                and not _RX_MARCA_HD.match(t)]

    def parole_testo(testo):
        return [w for w in re.split(r"\s+", testo) if w]

    def extra(s):
        """Gli operandi che un comando riceve senza scriverli fra i suoi argomenti:
        l'output di una sostituzione (`rm $(ls x)`), il testo che arriva a
        `xargs` (da una pipe, da un heredoc o da una here-string), e, se un
        operando e' una variabile che non si sa (`while read f; do rm $f; done`),
        i percorsi nominati altrove nello stesso comando."""
        ex = []
        if not _consumo_testo(s):
            for interno in _sostituzioni(s["testo"]):
                ex.extend(parole_utili(_token(_maschera(interno))[1:]))
        if "xargs" in s["pre"] or s["nome"] == "parallel":
            ex.extend(w for t in (s.get("aqui_testo") or []) for w in parole_testo(t))
            for hid in s["hd"]:
                if hid < len(hdl):
                    ex.extend(parole_testo(hdl[hid]["corpo"]))
            k = pos.get(id(s), 0)
            for s0 in segs[:k]:
                if s0["catena"] == s["catena"]:
                    ex.extend(parole_utili(s0["token"][1:]))
                    ex.extend(w for t in (s0.get("aqui_testo") or []) for w in parole_testo(t))
                    for hid in s0["hd"]:
                        if hid < len(hdl):
                            ex.extend(parole_testo(hdl[hid]["corpo"]))
        if any(t.startswith("$") and _espandi_var(t, env, s["vars"]) is None
               for t in _operandi(s)):
            for s0 in segs:
                if s0 is not s:
                    ex.extend(parole_utili(s0["token"][1:]))
                    ex.extend(w for t in (s0.get("aqui_testo") or []) for w in parole_testo(t))
            for h in hdl:
                ex.extend(parole_testo(h["corpo"]))
        return ex[:300]

    codice = False
    for s in segs:
        nome, args = s["nome"], s["args"]
        n = nome.lower()
        # 1) la CLI di Plancia
        chiave = _cli_config_guardiano(s)
        if chiave:
            yield ("cli", chiave, s)
        if _e_interprete(nome):
            codice = True
        # 2) redirezioni: `> file`, `>> file`, `>| file`, `>& file`, `<> file`
        for t in _uscite(s["token"]):
            yield from tipo_("file", t, s)
        op = _operandi(s)
        # 2b) gli script di sed (`w f`, `s///w f`) e di awk (`print > "f"`), e i
        # comandi che lanciano (`system("...")`, `sed 'e ...'`)
        w_, _, cmd_scr = _script_azioni(s)
        for f in w_:
            yield from tipo_("file", f, s)
        if prof < 2:
            for cs in cmd_scr:
                yield from _bersagli_scrittura(cs, base(s), env, prof + 1, nomi_rel)
        # 2c) `-o FILE`, `--output FILE`: scrivono il file (per `-o` solo i comandi
        # che lo intendono cosi')
        if n in _OUT_O_CMD:
            dest = valore_opzione(args, ("-o",), ("--output",))
        elif n not in ("sort", "curl", "wget"):
            dest = valore_opzione(args, (), ("--output",))
        else:
            dest = None
        if dest:
            yield from tipo_("file", dest, s)
        # 2d) `-t DIR` / `--target-directory`: i file vanno DENTRO la cartella
        tdir = _dir_destinazione(args) if n in ("cp", "mv", "install", "ln", "ditto") else None
        if tdir:
            op = [x for x in op if x != tdir]
            yield from tipo_("file", tdir, s)
            r = risolvi(tdir, s) or []
            for src in op:
                for rr in r:
                    m_ = _norm(os.path.join(rr, os.path.basename(src.rstrip("/"))))
                    if m_:
                        yield ("file", m_, s)
            if n == "mv":
                for x in op:
                    yield from tipo_("contiene", x, s)
                    yield from tipo_("file", x, s)
            continue
        if n in ("tee", "truncate", "rm", "chmod", "chown", "chgrp", "chflags", "ed",
                 "ex", "vi", "vim", "nano", "emacs", "sponge", "unlink", "shred", "mv",
                 "touch", "mkdir", "rmdir", "patch", "gzip", "gunzip", "bzip2", "bunzip2",
                 "xz", "unxz", "compress", "uncompress"):
            if n in ("gzip", "gunzip", "bzip2", "bunzip2", "xz", "unxz") and any(
                    a in ("-c", "--stdout", "--to-stdout") for a in args):
                continue        # `gzip -c f` scrive su stdout, non nel file
            ex = extra(s)
            for x in op + ex:
                yield from tipo_("file", x, s)
            if n == "mv":
                yield from destinazione(op, s)
            if n in ("rm", "mv", "unlink", "shred"):
                for x in (op[:-1] if n == "mv" else op) + ex:
                    yield from tipo_("contiene", x, s)
            if n in ("chmod", "chown", "chgrp", "chflags"):
                # anche senza -R: `chmod 000 ~/.plancia` toglie l'accesso alla cartella
                for x in op + ex:
                    yield from tipo_("stato", x, s)
                if any(re.match(r"^-[A-Za-z]*R", a) or a == "--recursive" for a in args):
                    for x in op + ex:
                        yield from tipo_("contiene", x, s)
        elif n in ("sed", "perl") and any(_RX_SED_SUL_POSTO.match(a) for a in args):
            for x in op + extra(s):
                yield from tipo_("file", x, s)
        elif n in ("awk", "gawk") and "inplace" in args:
            for x in op:
                yield from tipo_("file", x, s)
        elif n == "sort":
            dest = valore_opzione(args, ("-o",), ("--output",))
            if dest:
                yield from tipo_("file", dest, s)
        elif n in ("cp", "install", "rsync", "ln", "ditto"):
            yield from destinazione(op, s)
            if n == "rsync" and "--remove-source-files" in args:
                # cancella i file di origine dopo la copia
                for x in op[:-1]:
                    yield from tipo_("file", x, s)
                    yield from tipo_("contiene", x, s)
            if n == "ln" and op and any(re.match(r"^-[A-Za-z]*[fn]", a) for a in args):
                # `ln -sfn x ~/.plancia`: sostituisce la cartella con un collegamento
                yield from tipo_("stato", op[-1], s)
            ricorsivo = n in ("rsync", "ditto") or any(
                re.match(r"^-[A-Za-z]*[rRa]", a) or a in ("--recursive", "--archive")
                for a in args)
            if ricorsivo and n != "ln" and op:
                # una copia ricorsiva dentro la cartella dei file protetti li puo'
                # sovrascrivere (`cp -r x/. ~/.plancia/`, `rsync -a x/ ~/.plancia/`)
                yield from tipo_("stato", op[-1], s)
        elif n == "dd":
            for a in args:
                if a.startswith("of="):
                    yield from tipo_("file", a[3:], s)
        elif n == "find":
            radici = []
            for a in args:
                if a.startswith(("-", "(", "!")):
                    break
                radici.append(a)
            esegue = next((os.path.basename(args[i + 1]) for i, a in enumerate(args)
                           if a in ("-exec", "-execdir", "-ok", "-okdir")
                           and i + 1 < len(args)), None)
            if "-delete" in args or (esegue is not None and esegue not in _LETTURA_ESEC):
                for x in radici or ["."]:
                    yield from tipo_("stato", x, s)
                    yield from tipo_("file", x, s)
            for i, a in enumerate(args):
                if a in ("-fprint", "-fprint0", "-fprintf", "-fls") and i + 1 < len(args):
                    yield from tipo_("file", args[i + 1], s)
        elif n == "curl":
            dest = valore_opzione(args, ("-o",), ("--output",))
            if dest:
                yield from tipo_("file", dest, s)
            if any(a in ("-O", "--remote-name", "--remote-name-all") for a in args) or any(
                    re.match(r"^-[A-Za-z]*O[A-Za-z]*$", a) for a in args):
                cartella = valore_opzione(args, (), ("--output-dir",)) or "."
                yield from tipo_("stato", cartella, s)
                for a in args:
                    if _RX_URL.match(a):
                        nome_file = os.path.basename(a.split("?", 1)[0].rstrip("/"))
                        yield from tipo_("file", os.path.join(cartella, nome_file), s)
        elif n == "wget":
            dest = valore_opzione(args, ("-O",), ("--output-document",))
            if dest:
                yield from tipo_("file", dest, s)
            cartella = valore_opzione(args, ("-P",), ("--directory-prefix",)) or "."
            urls = [a for a in args if _RX_URL.match(a)]
            if urls:
                yield from tipo_("stato", cartella, s)
                for a in urls:
                    nome_file = os.path.basename(a.split("?", 1)[0].rstrip("/"))
                    yield from tipo_("file", os.path.join(cartella, nome_file), s)
        elif n == "tar":
            estrae = _tar_estrae(args)
            cartella = valore_opzione(args, ("-C",), ("--directory",))
            if estrae:
                yield from tipo_("stato", cartella or ".", s)
            else:
                dest = valore_opzione(args, (), ("--file",))
                if dest is None and args and re.match(r"^-?[A-Za-z]*f[A-Za-z]*$", args[0]):
                    dest = args[1] if len(args) > 1 else None
                if dest:
                    yield from tipo_("file", dest, s)
        elif n == "unzip":
            if not any(a in ("-l", "-p", "-t", "-v", "-Z", "-z") for a in args):
                yield from tipo_("stato", valore_opzione(args, ("-d",), ()) or ".", s)
        elif n == "zip":
            if op and op[0] != "-":
                yield from tipo_("file", op[0], s)
        elif n == "split":
            if len(op) >= 2:
                yield from tipo_("file", op[1], s)
        elif n in ("mktemp", "gmktemp"):
            cartella = valore_opzione(args, ("-p",), ("--tmpdir",))
            if cartella:
                yield from tipo_("stato", cartella, s)
        elif n in ("mkfifo", "mknod"):
            for x in op[:1] if n == "mknod" else op:
                yield from tipo_("file", x, s)
        elif n == "xattr":
            if any(re.match(r"^-[A-Za-z]*[wdc]", a) for a in args if a.startswith("-")) and op:
                yield from tipo_("file", op[-1], s)
        elif n == "ffmpeg":
            if len(op) >= 2:
                yield from tipo_("file", op[-1], s)
        elif n == "git":
            salta, dir_git, sotto, k_sotto = False, None, None, -1
            for i, a in enumerate(args):
                if salta:
                    salta = False
                elif a == "-C" and i + 1 < len(args):
                    dir_git = args[i + 1]
                    salta = True
                elif a in ("-c", "--git-dir", "--work-tree"):
                    salta = True
                elif not a.startswith("-"):
                    sotto, k_sotto = a, i
                    break
            resto = [a for a in args[k_sotto + 1:] if not a.startswith("-")] if sotto else []
            opzioni = [a for a in args[k_sotto + 1:] if a.startswith("-")] if sotto else []
            if _git_e_lettura(sotto, resto, opzioni):
                pass        # una lettura: `branch --contains x`, `tag -l 'v*'`, `notes list`...
            elif sotto in _GIT_SCRIVE:
                yield from tipo_("stato", dir_git or ".", s)
            elif sotto in _GIT_SCRIVE_REPO:
                yield from tipo_("repo", dir_git or ".", s)
            elif sotto == "config" and not any(_RX_GIT_LETTURA_CONFIG.match(a) for a in opzioni) \
                    and (len(resto) >= 2 or any(a in ("--unset", "--unset-all", "--add",
                                                      "--replace-all", "--edit", "-e",
                                                      "--remove-section", "--rename-section")
                                                for a in opzioni)):
                yield from tipo_("repo", dir_git or ".", s)
            elif sotto == "branch" and (resto or any(re.match(
                    r"^-(?:d|D|m|M|c|C|f|u)$|^--(?:delete|move|copy|set-upstream-to|unset-upstream|force)",
                    a) for a in opzioni)):
                yield from tipo_("repo", dir_git or ".", s)
            elif sotto == "tag" and (resto or any(re.match(r"^-(?:d|a|s|f|m|u)$|^--(?:delete|force)", a)
                                                  for a in opzioni)):
                yield from tipo_("repo", dir_git or ".", s)
            elif sotto == "remote" and resto[:1] and resto[0] in (
                    "add", "remove", "rm", "rename", "set-url", "set-head", "prune", "update",
                    "set-branches"):
                yield from tipo_("repo", dir_git or ".", s)
            elif sotto == "clone" and resto:
                # `git clone URL [DIR]`: scrive DIR, o una cartella col nome del deposito
                # nella cartella corrente
                if len(resto) >= 2:
                    dest = resto[1]
                else:
                    dest = re.sub(r"\.git$", "", os.path.basename(
                        resto[0].rstrip("/").rsplit(":", 1)[-1]))
                if dest:
                    yield from tipo_("file", os.path.join(dir_git, dest) if dir_git and
                                     not os.path.isabs(dest) else dest, s)
    # 3) codice dato a un interprete. Ogni testo porta il segmento che lo esegue (le variabili
    # che il comando assegna) e la cartella da cui parte (per i nomi relativi)
    if codice:
        testi = [(t, s, base(s)) for s in segs if _e_interprete(s["nome"]) for t in s["args"]]
        testi += [(t, s_, cw if cw is not None else cwd) for t, cw, s_ in an["corpi"]]
        # `'~/.plan' + 'cia/config.json'`: le stringhe attaccate con `+` si uniscono
        note = {t for t, _, _ in testi}
        for t, s_, cw in list(testi):
            u = _RX_UNISCI.sub("", t)
            if u not in note:
                note.add(u)
                testi.append((u, s_, cw))
        for t, s_, cw in testi:
            scrive = bool(_RX_CODICE_SCRIVE.search(t))
            if _RX_PKG_PLANCIA.search(t):
                if "save_config" in t:
                    yield ("cli", "config.save_config", None)
                if re.search(r"\bmain\s*\(|\bsys\.argv\b", t):
                    yield ("cli", "plancia.cli", None)
                if "CONFIG_FILE" in t and scrive:
                    yield from _dati_nel_codice(t, s_, env, cw, "CONFIG_FILE", True, False)
            if _RX_DATI_NOMINATI.search(t):
                yield from _dati_nel_codice(
                    t, s_, env, cw, "config.json",
                    bool(scrive and _RX_DATI_FILE.search(t)), bool(_RX_DIR_OPS.search(t)))
            if scrive and "CLAUDE_CONFIG_DIR" in t and _RX_SETTINGS_NOMI.search(t):
                # `os.environ['CLAUDE_CONFIG_DIR'] + '/settings.json'`: i settings della
                # cartella che la variabile nomina (quella assegnata nel comando, o quella
                # con cui gira la sessione)
                stato_, v = _var_del_comando(s_, "CLAUDE_CONFIG_DIR", env)
                if stato_ == "nessuna":
                    v = (env or {}).get("CLAUDE_CONFIG_DIR") or os.environ.get("CLAUDE_CONFIG_DIR")
                if isinstance(v, str) and v:
                    for f in ("settings.json", "settings.local.json"):
                        n_ = _norm(os.path.join(v, f), None if cw == _IGNOTA else cw)
                        if n_:
                            yield ("file", n_, None)
            if scrive:
                dir_ops = bool(_RX_DIR_OPS.search(t))
                casa = _casa_del_comando(s_, env)
                for c in _trova_percorsi_in_testo(t):
                    # con `HOME=/x python3 -c "...'~/.claude/...'..."` la tilde vale /x
                    c_ = casa + c[1:] if casa and (c == "~" or c.startswith("~/")) else c
                    n_ = _norm(c_, cwd)
                    if n_:
                        yield ("file", n_, None)
                        if n_.count("/") > 1 or n_ == "/" or _operando_di_scrittura(t, c):
                            # una cartella di primo livello nominata in un TESTO di codice
                            # (`'/home/'` in una regex, `'/srv/' in p`) non e' una cartella
                            # su cui il codice opera: conterrebbe ogni file protetto. Lo e'
                            # se sta come operando di una chiamata che scrive o cancella
                            # (`shutil.rmtree('/srv')`, `Path('/srv').rename(x)`). Da shell
                            # (`rm -r /home`) si valuta a parte.
                            yield ("stato", n_, None)
                            if dir_ops:
                                yield ("contiene", n_, None)
                if nomi_rel and cw and cw != _IGNOTA:
                    # un nome RELATIVO nel codice (`open('settings.json', 'w')`) si risolve
                    # sulla cartella da cui parte il segmento, come per la shell
                    for lit in _nomi_relativi_nel_codice(t, nomi_rel):
                        n_ = _norm(lit, cw)
                        if n_:
                            yield ("file", n_, None)
            if prof < 2 and _RX_ESEGUE.search(t):
                for c in _comandi_nel_codice(t):
                    yield from _bersagli_scrittura(c, cw if cw is not None else cwd, env,
                                                   prof + 1, nomi_rel)
    if "save_config" in cmd and codice:
        yield ("cli", "config.save_config", None)


def _nome_semplice(x: str) -> bool:
    """`x` e' un nome senza barra (`f`, `.`, `nota.txt`, `*.txt`): non `..`, non un
    percorso (`sub/f`, `../x`), non una `~`."""
    return "/" not in x and x != ".." and not x.startswith("~")


def _scrive_un_protetto(cmd: str, cwd, P: _Protetti, env=None, semplici_ok=False):
    """`(bersaglio, come)` se il comando Bash scrive, cancella o sposta un file
    del guardiano, cambia i permessi della sua cartella, o imposta una sua chiave
    con la CLI; altrimenti None. `come` e' `cli`, `scrive`, `settings` (un file di
    impostazioni di Claude Code) o `ignota` (una scrittura relativa dopo un `cd` che
    non si sa dove porta). Con `semplici_ok` (il PREDEFINITO) la scrittura `ignota` di un
    nome semplice (`git init`, `git add .`, `touch f`, `echo x > f`) non nega, come una
    lettura: negarla sarebbe il falso positivo di ogni script; nega ancora un percorso con
    una barra (`sub/f`, `../x`) e il nome di un file del guardiano (`rm config.json`).
    Vedi `_bersagli_scrittura` per l'elenco dei casi."""
    for tipo, val, _ in _bersagli_scrittura(cmd, cwd, env, nomi_rel=P.nomi):
        if tipo == "cli":
            return val, "cli"
        if tipo == "ignota":
            if semplici_ok and _nome_semplice(val) and val.lower() not in P.nomi:
                continue
            return val, "ignota"
        if tipo == "dati":
            return val, "scrive"
        if tipo == "file":
            t = P.tag(val)
            if t:
                return val, ("settings" if t == "settings" else "scrive")
        elif tipo == "contiene":
            c = P.contiene(val)
            if c:
                return c[0], ("settings" if c[1] == "settings" else "scrive")
        elif tipo == "stato":
            if P.cartella_stato(val):
                return val, "scrive"
    return None


def _valuta_protetti(nome, ti, ambito, chi, data_dir, mio, env=None):
    """Scrivere (o cancellare, o spostare) un file del guardiano, o cambiarne le
    impostazioni con la CLI di Plancia (`plancia config guardiano ...`), e'
    negato a TUTTE le sessioni, predefinito compreso. Leggere resta ammesso. Con
    Bash e' euristico (vedi `_scrive_un_protetto`). Vale solo in `bloccante`,
    come ogni diniego: chi vuole cambiare la config con l'aiuto di una sessione
    deve prima passare a `solo-registro`, o cambiarla a mano. Il file di
    impostazioni di Claude Code (settings.json, settings.local.json) e' protetto
    in modo MIRATO: Write/Edit/MultiEdit passano se il risultato ha ancora la
    voce del guardiano (vedi `_controlla_settings`), Bash no."""
    corto = _nome_corto(nome)
    cwd = chi["cwd"] or None
    cmd = ti.get("command")
    scrittura = corto in STRUMENTI_SCRITTURA
    if not scrittura and not (isinstance(cmd, str) and cmd):
        return None     # nessuno strumento che scrive e nessun comando: niente da guardare
    P = _Protetti(ambito, data_dir)
    if scrittura:
        for k in ("file_path", "notebook_path", "path"):
            if isinstance(ti.get(k), str):
                n = _norm(ti[k], cwd)
                t = P.tag(n) if n else None
                if t == "file":
                    return {"bersaglio": n, "proprietario": "il guardiano",
                            "motivo": "compartimento %s: %s e' un file del guardiano "
                                      "dei compartimenti: %s" % (mio, n, _MOTIVO_A_MANO)}
                if t == "settings":
                    perche = _controlla_settings(n, corto, ti, P)
                    if perche:
                        return {"bersaglio": n, "proprietario": "il guardiano",
                                "motivo": "compartimento %s: la modifica di %s %s"
                                          % (mio, n, perche)}
        return None
    r = _scrive_un_protetto(cmd, cwd, P, env, semplici_ok=not chi["nomi"])
    if not r:
        return None
    bersaglio, come = r
    if come == "cli":
        return {"bersaglio": bersaglio, "proprietario": "il guardiano",
                "motivo": "compartimento %s: il comando imposta la chiave %r di "
                          "config.json, che governa il guardiano dei compartimenti: %s"
                          % (mio, bersaglio, _MOTIVO_A_MANO)}
    if come == "settings":
        return {"bersaglio": bersaglio, "proprietario": "il guardiano",
                "motivo": "compartimento %s: il comando scrive %s: %s"
                          % (mio, bersaglio, _MOTIVO_SETTINGS)}
    if come == "ignota":
        return {"bersaglio": bersaglio, "proprietario": "il guardiano",
                "motivo": "compartimento %s: il comando scrive %s dopo un `cd` che non "
                          "si sa dove porta: scrivi percorsi assoluti" % (mio, bersaglio)}
    return {"bersaglio": bersaglio, "proprietario": "il guardiano",
            "motivo": "compartimento %s: %s e' un file del guardiano dei "
                      "compartimenti: %s" % (mio, bersaglio, _MOTIVO_A_MANO)}


def _percorso_nominato(p, chi, ambito, mio, ricorsivo=None, scrittura=False):
    """Un percorso contro i permessi di TUTTI i compartimenti della sessione
    (di solito uno). Una cartella e' del nominato piu' specifico che la
    contiene: dentro `/w/alfa/beta` alfa non entra, anche se ha `/w/alfa`. Una
    cartella di codice CONDIVISA (`condivise`) si legge e vi si esegue; con
    `scrittura` no, salvo dentro i propri permessi (la scrittura da Bash si
    controlla a parte: `_valuta_condivise`)."""
    for nome in chi["nomi"]:
        c = ambito.nominati[nome]
        prop = ambito.proprietari_percorso(p)
        if prop == [nome]:
            # una ricerca che parte da qui entra anche nelle cartelle annidate
            # di un altro nominato
            for altro, ca in ambito.nominati.items():
                if altro == nome:
                    continue
                for f in ca["cartelle"]:
                    if _dentro(f, p) and _ric(ricorsivo, _prof(f, p)):
                        return {"bersaglio": p, "proprietario": altro,
                                "motivo": "compartimento %s: la ricerca in %s include "
                                          "%s, che appartiene a %s: restringi il "
                                          "percorso" % (mio, p, f, altro)}
            continue
        if len(prop) > 1 and nome in prop:
            return {"bersaglio": p, "proprietario": ",".join(prop),
                    "motivo": "compartimento %s: %s e' assegnata a piu' di un "
                              "compartimento (%s) dalla configurazione: incerta, "
                              "negata finche' non si ripara" % (mio, p, ",".join(prop))}
        if prop:
            return {"bersaglio": p, "proprietario": prop[0],
                    "motivo": "compartimento %s: %s appartiene a %s (fuori dai "
                              "permessi di %s)" % (mio, p, prop[0], nome)}
        if any(_dentro(p, n) for n in ambito.neutri()):
            continue
        if _scratch_ok(p, chi, ambito):
            continue
        if _progetto_ok(p, chi, nome in chi["da_codifica"]):
            continue
        prop = ambito.proprietario_specchio(p)
        if prop is None and not scrittura and ambito.in_condivisa(p):
            # una ricerca ricorsiva che parte da una cartella condivisa non entra mai
            # nella cartella dei dati di Plancia ne' in `<claude>/projects`
            riservata = ambito.riservata_inclusa(p, ricorsivo)
            if riservata:
                return {"bersaglio": p, "proprietario": "il guardiano",
                        "motivo": "compartimento %s: la ricerca in %s include %s, che non "
                                  "e' mai condivisa: restringi il percorso"
                                  % (mio, p, riservata)}
            # una ricerca che parte da una cartella condivisa entra anche nella
            # cartella di un altro nominato che ci sta dentro
            for altro, ca in ambito.nominati.items():
                if altro in chi["nomi"]:
                    continue
                for f in ca["cartelle"]:
                    if _dentro(f, p) and _ric(ricorsivo, _prof(f, p)):
                        return {"bersaglio": p, "proprietario": altro,
                                "motivo": "compartimento %s: la ricerca in %s include "
                                          "%s, che appartiene a %s: restringi il "
                                          "percorso" % (mio, p, f, altro)}
            continue
        if prop is None and scrittura and ambito.in_condivisa(p):
            return {"bersaglio": p, "proprietario": "condivisa",
                    "motivo": _MOTIVO_CONDIVISA % (mio, p)}
        if prop is None and _e_temporaneo(p, ambito):
            return {"bersaglio": p, "proprietario": "nessuno",
                    "motivo": "compartimento %s: %s e' nella cartella temporanea "
                              "condivisa, che non e' di nessun compartimento ma che "
                              "un compartimento nominato non usa (e' un posto dove "
                              "passarsi file): usa la sua cartella di sessione in "
                              "/private/tmp/claude-%s/ (fuori dai permessi di %s)"
                              % (mio, p, ambito.uid, nome)}
        if prop is None and p == "/":
            return {"bersaglio": p, "proprietario": "nessuno",
                    "motivo": "compartimento %s: la radice del disco non e' di nessun "
                              "compartimento ma e' fuori dai permessi di %s"
                              % (mio, nome)}
        prop = prop or PREDEFINITO
        return {"bersaglio": p, "proprietario": prop,
                "motivo": "compartimento %s: %s appartiene a %s (fuori dai "
                          "permessi di %s)" % (mio, p, prop, nome)}
    return None


_MOTIVO_CONDIVISA = ("compartimento %s: %s e' in una cartella di codice condivisa "
                     "(`condivise` di config): si legge e ci si esegue, non ci si "
                     "scrive fuori dai propri permessi")

_TEMPORANEI = ("/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp",
               "/var/folders", "/private/var/folders")


def _e_temporaneo(p: str, ambito: Ambito) -> bool:
    """`p` sta in una cartella temporanea condivisa (`/tmp` e la TMPDIR per
    utente di macOS): non e' di nessun compartimento."""
    return any(_dentro(p, t) or _dentro(p, _norm(t)) for t in _TEMPORANEI)


def _divieto(p, mio, extra=""):
    return {"bersaglio": p, "proprietario": "un compartimento nominato",
            "motivo": "compartimento %s: %s appartiene a un compartimento "
                      "nominato%s" % (mio, p, (" (" + extra + ")") if extra else "")}


_RICERCA_INCLUDE = "la ricerca include un percorso vietato: restringi il percorso"


def _percorso_predefinito(p, ricorsivo, ambito, mio):
    """Un percorso contro i divieti del predefinito. Una ricerca ricorsiva che
    parte da un antenato di un percorso vietato lo include: negata (se e'
    a profondita' limitata, solo se arriva fin li': `find . -maxdepth 1` no)."""
    for nome in ambito.proprietari_percorso(p)[:1]:
        return {"bersaglio": p, "proprietario": nome,
                "motivo": "compartimento %s: %s appartiene a %s" % (mio, p, nome)}
    for nome, c in ambito.nominati.items():
        for f in c["cartelle"]:
            if _dentro(f, p) and _ric(ricorsivo, _prof(f, p)):
                return {"bersaglio": p, "proprietario": nome,
                        "motivo": "compartimento %s: la ricerca in %s include %s, "
                                  "che appartiene a %s: restringi il percorso"
                                  % (mio, p, f, nome)}
    # Lo specchio delle cartelle dei nominati in `<claude>/projects`:
    # trascrizioni, memoria, cartelle di sessione e dei subagenti. E' lavoro
    # loro (i canali 5 e 7 della specifica) come le cartelle stesse.
    prop = ambito.proprietario_specchio(p)
    if prop:
        return {"bersaglio": p, "proprietario": prop,
                "motivo": "compartimento %s: %s (trascrizioni e memoria) appartiene "
                          "a %s" % (mio, p, prop)}
    prop = ambito.specchio_incluso(p, ricorsivo)
    if prop:
        return {"bersaglio": p, "proprietario": prop,
                "motivo": "compartimento %s: la ricerca in %s include le "
                          "trascrizioni e la memoria di %s sotto %s: restringi "
                          "il percorso" % (mio, p, prop, ambito.progetti)}
    for letterale, glob in ambito.divieti():
        if glob is None and "/" not in letterale:
            # un nome semplice (senza barre): vale come modello di nome
            if _combacia_glob(letterale, p):
                return _divieto(p, mio)
        elif glob is None:
            if _dentro(p, letterale):
                return _divieto(p, mio)
            if _dentro(letterale, p) and _ric(ricorsivo, _prof(letterale, p)):
                return _divieto(p, mio, _RICERCA_INCLUDE)
        else:
            if _combacia_glob(glob, p):
                return _divieto(p, mio)
            # Una ricerca che parte proprio dal prefisso letterale del modello
            # (`<cartella>/PR-*`, ricerca in `<cartella>`) include i file che
            # combaciano: negata anche con p == letterale.
            if letterale and _dentro(letterale, p) and _ric(ricorsivo, _prof(letterale, p)):
                return _divieto(p, mio, _RICERCA_INCLUDE)
    return None


def _valuta_sessioni(nome, ti, ambito, chi, data_dir, mio):
    nominato = bool(chi["nomi"])
    if nome == "ListAgents":
        if nominato:
            return {"bersaglio": "ListAgents", "proprietario": "altri compartimenti",
                    "motivo": "compartimento %s: ListAgents elenca sessioni di altri "
                              "compartimenti" % mio}
        return _misura(ambito, "ListAgents", mio)
    if nome == "SendMessage":
        a = ti.get("to")
        if not isinstance(a, str) or not a:
            if not nominato:
                return None
            return {"bersaglio": "SendMessage", "proprietario": "sconosciuto",
                    "motivo": "compartimento %s: SendMessage senza un destinatario "
                              "verificabile" % mio}
        return _sessione_bersaglio(
            a, ambito, chi, data_dir, mio,
            proprio=_e_proprio(a, chi, ambito) or _agente_proprio(a, chi))
    if not nome.startswith(PREFISSO_SESSIONI):
        return None
    corto = _nome_corto(nome)
    if corto in SESSIONI_RICERCA and ambito.nominati:
        # Anche con un filtro di sessione nel tool_input: la ricerca e' nel
        # contenuto delle trascrizioni, che sono lavoro dei compartimenti.
        return {"bersaglio": corto, "proprietario": "altri compartimenti",
                "motivo": "compartimento %s: %s cerca nelle trascrizioni di tutte "
                          "le sessioni, anche di un compartimento nominato" % (mio, corto)}
    ids = _stringhe(ti, CHIAVI_ID_SESSIONE)
    for k in CHIAVI_LISTA_SESSIONI:
        if isinstance(ti.get(k), list):
            ids += [x for x in ti[k] if isinstance(x, str) and x]
    if not ids:
        if nominato and corto not in SESSIONI_SENZA_BERSAGLIO_OK:
            return {"bersaglio": corto, "proprietario": "altri compartimenti",
                    "motivo": "compartimento %s: %s senza una sessione bersaglio "
                              "elenca o cerca fra sessioni di altri compartimenti "
                              "(per questa sessione passa session_id \"self\": senza "
                              "un id non e' certo che lo strumento agisca su di lei)"
                              % (mio, corto)}
        if corto in SESSIONI_DA_MISURARE:
            return _misura(ambito, corto, mio)
        return None
    for i in ids:
        v = _sessione_bersaglio(i, ambito, chi, data_dir, mio,
                                proprio=_e_proprio(i, chi, ambito))
        if v:
            return v
    return None


def _misura(ambito, strumento, mio):
    """Una chiamata che il predefinito puo' fare senza un bersaglio
    (`list_sessions`, `search_session_transcripts`, `ListAgents`): non si puo'
    negare (limite dichiarato nel docstring), ma se esistono compartimenti
    nominati si fa scrivere una riga in `solo-registro`, per sapere quanto si
    usa prima di decidere. Non nega mai, nemmeno in `bloccante`."""
    if not ambito.nominati:
        return None
    return {"bersaglio": strumento, "proprietario": "un compartimento nominato",
            "solo_misura": True,
            "motivo": "compartimento %s: %s cerca o elenca fra tutte le sessioni, "
                      "anche di un compartimento nominato (solo misura, non si "
                      "nega)" % (mio, strumento)}


def _sessione_bersaglio(chiave, ambito, chi, data_dir, mio, proprio):
    """La sessione `chiave` e' raggiungibile da chi chiama?

    Un nominato raggiunge solo sessioni che sono almeno dei suoi stessi
    compartimenti; una sessione sconosciuta e' negata. Il predefinito
    raggiunge le sessioni predefinite e quelle sconosciute (id sconosciuto:
    ammesso, come da specifica), non quelle di un nominato. `chiave` puo'
    indicare piu' sessioni (titolo ripetuto): tutte devono essere raggiungibili."""
    if proprio:
        return None
    nominato = bool(chi["nomi"])
    gruppi = compartimenti_sessione(chiave, ambito, data_dir)
    if gruppi is None:
        if not nominato:
            return None
        return {"bersaglio": chiave, "proprietario": "sconosciuto",
                "motivo": "compartimento %s: la sessione %s e' sconosciuta a un "
                          "compartimento nominato" % (mio, chiave)}
    for comp in gruppi:
        ok = set(chi["nomi"]) <= set(comp) if nominato else comp == [PREDEFINITO]
        if not ok:
            return {"bersaglio": chiave, "proprietario": ",".join(comp),
                    "motivo": "compartimento %s: la sessione %s appartiene a %s"
                              % (mio, chiave, ",".join(comp))}
    return None


def _valuta_drive(nome, ti, ambito, chi, mio):
    corto = _nome_corto(nome)
    if not nome.startswith("mcp__") or (
            corto not in ambito.strumenti_drive and nome not in ambito.strumenti_drive):
        return None
    ids = _stringhe(ti, CHIAVI_ID_DRIVE)
    for k in ("fileIds", "file_ids"):
        if isinstance(ti.get(k), list):
            ids += [x for x in ti[k] if isinstance(x, str) and x]
    if chi["nomi"]:
        if corto in STRUMENTI_DRIVE_ELENCO:
            return {"bersaglio": corto, "proprietario": "altri compartimenti",
                    "motivo": "compartimento %s: %s elenca tutto il Drive"
                              % (mio, corto)}
        if not ids:
            return {"bersaglio": corto, "proprietario": "sconosciuto",
                    "motivo": "compartimento %s: %s senza un id Drive verificabile"
                              % (mio, corto)}
        for i in ids:
            for n in chi["nomi"]:
                if i not in ambito.nominati[n]["drive_ids"]:
                    prop = next((k for k, c in ambito.nominati.items()
                                 if i in c["drive_ids"]), PREDEFINITO)
                    return {"bersaglio": i, "proprietario": prop,
                            "motivo": "compartimento %s: l'id Drive %s appartiene a "
                                      "%s (non e' fra i drive_ids di %s)"
                                      % (mio, i, prop, n)}
        return None
    for i in ids:
        for n, c in ambito.nominati.items():
            if i in c["drive_ids"]:
                return {"bersaglio": i, "proprietario": n,
                        "motivo": "compartimento %s: l'id Drive %s appartiene a %s"
                                  % (mio, i, n)}
    return None


# --------------------------------------------------------------------------
# l'hook
# --------------------------------------------------------------------------

def uscita_negata(motivo: str) -> str:
    """Il diniego di un PreToolUse, come JSON su stdout con uscita 0.

    Formato scelto: `hookSpecificOutput` con `hookEventName: "PreToolUse"`,
    `permissionDecision: "deny"` e `permissionDecisionReason`, l'uscita JSON
    strutturata dei PreToolUse di Claude Code: il motivo arriva a Claude come
    spiegazione del rifiuto. Il ripiego piu' vecchio (uscita 2 con il motivo
    su stderr) non serve: gli altri hook PreToolUse gia' in uso su questa
    macchina rifiutano con questo stesso formato JSON. NON e' stato provato
    dentro un Claude Code vero da questo lotto (la documentazione non era
    raggiungibile): le prove lanciano l'hook come sottoprocesso e leggono lo
    stdout."""
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": motivo}}, ensure_ascii=False)


# Cio' che `hook` sa della chiamata in corso, per l'allarme dei due secondi di
# `bin/plancia-guardiano`: se scatta DENTRO `hook`, quel wrapper chiede qui cosa fare
# (`uscita_tempo_scaduto`) invece di trattarlo come un guasto del guardiano.
_STATO_HOOK = {"modo": None, "chi": None, "sid": "", "strumento": ""}

_MOTIVO_TEMPO = ("comando troppo complesso da controllare in tempo: spezzalo in comandi "
                 "piu' semplici")


def uscita_tempo_scaduto(data_dir: str):
    """Lo stdout da scrivere quando l'allarme dei due secondi scatta MENTRE `hook`
    decideva; `None` se non si sa in che modo il guardiano girava (l'allarme e'
    scattato prima di leggere la config: e' il guasto di sempre, `guardiano-non-parte`).

    Un comando che non si riesce a controllare in tempo non e' "ammesso" per tutti:
    - `spento`: niente;
    - chiamante NON ANCORA STABILITO (l'allarme e' scattato prima di sapere a che
      compartimento appartiene la sessione: un disco che si ferma mentre si leggono le
      cartelle configurate): NON e' "incerto" (segnali discordanti), e' un dato che
      manca, e negare per questo chiuderebbe TUTTE le sessioni, anche il predefinito che
      legge un file proprio. Ammesso, in `bloccante` e in `solo-registro`, con il
      `systemMessage` OGNI volta e una riga `tempo-scaduto` senza compartimento, come per
      il predefinito;
    - `bloccante`, sessione GIA' STABILITA come di un NOMINATO o come INCERTA (due
      compartimenti sulla stessa cartella): NEGATO, con il motivo "comando troppo
      complesso da controllare in tempo: spezzalo";
    - `bloccante`, sessione del predefinito: ammesso (il predefinito non si blocca per un
      guasto), ma con il `systemMessage` OGNI volta, e una riga nel registro (nessun
      limite di tempo, nessun silenzio dopo la prima);
    - `solo-registro`: ammesso, con la riga (`avrebbe-negato` per un nominato o un
      incerto, `tempo-scaduto` per gli altri) e il `systemMessage`."""
    st = _STATO_HOOK
    modo = st.get("modo")
    if modo is None:
        return None
    if modo == "spento":
        return ""
    chi = st.get("chi")
    sid, strumento = st.get("sid") or "", st.get("strumento") or ""
    if chi is None:
        motivo = "chiamante non ancora stabilito: %s" % _MOTIVO_TEMPO
        scrivi_registro(data_dir, {
            "modalita": modo, "sessione": sid, "compartimento": "", "strumento": strumento,
            "bersaglio": "", "motivo": motivo, "esito": "tempo-scaduto"})
        return json.dumps({"systemMessage": (
            "plancia-guardiano: il controllo non e' finito in tempo prima di sapere a che "
            "compartimento appartiene la sessione (%s). Il comando e' stato ammesso senza "
            "il controllo dei compartimenti." % _MOTIVO_TEMPO)}, ensure_ascii=False)
    nominato = bool(chi["nomi"])
    nome = ",".join(chi["nomi"]) if nominato else PREDEFINITO
    motivo = "compartimento %s: %s" % (nome, _MOTIVO_TEMPO)
    blocca = modo == "bloccante" and nominato
    esito = "negato" if blocca else ("avrebbe-negato" if nominato else "tempo-scaduto")
    scrivi_registro(data_dir, {
        "modalita": modo, "sessione": sid, "compartimento": nome, "strumento": strumento,
        "bersaglio": "", "motivo": motivo, "esito": esito})
    if blocca:
        return uscita_negata(motivo)
    return json.dumps({"systemMessage": (
        "plancia-guardiano: %s (%s). Il comando e' stato ammesso senza il controllo dei "
        "compartimenti." % (_MOTIVO_TEMPO, "sessione del predefinito" if not nominato
                            else "solo-registro"))}, ensure_ascii=False)


def hook(testo: str, data_dir: str) -> str:
    """Decide una chiamata di strumento. `testo` e' lo stdin dell'hook.
    Torna lo stdout da scrivere ("" = nessuna uscita = ammessa). Non solleva
    mai.

    Regola dei guasti: stdin vuoto o non JSON = ammessa. In `spento` e
    `solo-registro` qualunque eccezione = ammessa, niente output. In
    `bloccante` un'eccezione DOPO aver capito che chi chiama e' un nominato
    nega per prudenza (fail-closed per i nominati); prima di saperlo, o per il
    predefinito, ammette. Una config che non si legge per PERMESSI (la cartella
    dei dati con `chmod 000`) non e' silenziosa: torna `{"systemMessage": ...}`
    (al massimo ogni dieci minuti, sempre se non si riesce a scrivere la marca).
    Un tetto dell'analisi superato lascia una riga `nota` per il predefinito e nega
    un nominato."""
    try:
        payload = json.loads(testo)
    except (ValueError, RecursionError, TypeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    ev = payload.get("hook_event_name")
    if isinstance(ev, str) and ev and ev != "PreToolUse":
        return ""
    modo, chi, v, avviso_out = "spento", None, None, ""
    _sid0 = payload.get("session_id")
    _STATO_HOOK.update(modo=None, chi=None, sid=_sid0 if isinstance(_sid0, str) else "",
                       strumento=str(payload.get("tool_name") or ""))
    try:
        cfg = carica(data_dir)
        modo = cfg["modo"]
        _STATO_HOOK["modo"] = modo
        if modo == "spento":
            return ""
        if cfg["nota"] and _nota_config_dovuta(data_dir):
            sid = payload.get("session_id")
            scrivi_registro(data_dir, {
                "modalita": modo, "sessione": sid if isinstance(sid, str) else "",
                "compartimento": "", "strumento": "", "bersaglio": "",
                "motivo": cfg["nota"], "esito": "nota"})
        if cfg.get("avviso") and _nota_config_dovuta(data_dir, "guardiano.permessi-avviso"):
            avviso_out = json.dumps({"systemMessage": cfg["avviso"]}, ensure_ascii=False)
        if not cfg["compartimenti"]:
            return avviso_out
        ambito = Ambito(cfg["compartimenti"], cfg["strumenti_drive"],
                        data_dir=data_dir, condivise=cfg["condivise"])
        if ambito.note and _nota_config_dovuta(data_dir, "guardiano.condivise-nota"):
            sid = payload.get("session_id")
            scrivi_registro(data_dir, {
                "modalita": modo, "sessione": sid if isinstance(sid, str) else "",
                "compartimento": "", "strumento": "", "bersaglio": "",
                "motivo": "; ".join(ambito.note), "esito": "nota"})
        chi = chiamante(payload, ambito)
        _STATO_HOOK["chi"] = chi
        v = valuta(payload, ambito, chi, data_dir)
    except Exception as exc:  # noqa: BLE001 - un hook globale non rompe niente
        if modo == "bloccante" and chi is not None and chi["nomi"]:
            v = {"bersaglio": "", "proprietario": "",
                 "motivo": "compartimento %s: errore interno del guardiano (%s), "
                           "negato per prudenza" % (",".join(chi["nomi"]),
                                                    type(exc).__name__)}
        else:
            # ammessa, ma non in silenzio: senza questo un guardiano che solleva per
            # ogni chiamata del predefinito (o in solo-registro) sarebbe spento per
            # tutti e nessuno lo saprebbe
            if modo == "spento":
                return avviso_out
            nome = ",".join(chi["nomi"]) if chi is not None and chi["nomi"] else (
                PREDEFINITO if chi is not None else "incerto")
            scrivi_registro(data_dir, {
                "modalita": modo, "sessione": _STATO_HOOK["sid"],
                "compartimento": nome if chi is not None else "",
                "strumento": _STATO_HOOK["strumento"], "bersaglio": "",
                "motivo": "errore interno del guardiano (%s: %s): ammessa"
                          % (type(exc).__name__, str(exc)[:200]),
                "esito": "errore-interno"})
            return json.dumps({"systemMessage": (
                "plancia-guardiano: errore interno (%s): il comando e' stato ammesso senza "
                "il controllo dei compartimenti. Vedi `plancia guardiano --registro`."
                % type(exc).__name__)}, ensure_ascii=False)
    if not v:
        return avviso_out
    if v.get("solo_misura") and modo != "solo-registro":
        return avviso_out
    solo_nota = bool(v.get("solo_nota"))
    blocca = modo == "bloccante" and not v.get("solo_misura") and not solo_nota
    sid = payload.get("session_id")
    scrivi_registro(data_dir, {
        "modalita": modo, "sessione": sid if isinstance(sid, str) else "",
        "compartimento": ",".join(chi["nomi"]) if chi and chi["nomi"] else PREDEFINITO,
        "strumento": str(payload.get("tool_name") or ""),
        "bersaglio": v["bersaglio"], "motivo": v["motivo"],
        "esito": "negato" if blocca else ("nota" if solo_nota else "avrebbe-negato")})
    return uscita_negata(v["motivo"]) if blocca else avviso_out
