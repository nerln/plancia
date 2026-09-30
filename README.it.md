# Plancia

[![collaudo](https://github.com/nerln/plancia/actions/workflows/prova.yml/badge.svg)](https://github.com/nerln/plancia/actions/workflows/prova.yml)

Claude Code e Codex si scrivono già tutto, in file sul tuo disco. Solo che non
li legge nessuno insieme. Plancia sì: una riga per progetto ti dice cosa fare,
Riprendi riapre la conversazione che ha scritto il task, e un riepilogo
parlato della giornata finisce con la cosa che conviene fare. Il resto sta
ripiegato, a un clic di distanza.

Sito: [plancia](https://nerln.github.io/plancia/).

Tutto in locale: nessuna telemetria, nessun account, nessun nostro server.
L'unica cosa che esce è il lavoro che affidi tu a un agente, e passa dal comando
`claude` o `codex` che hai già, con il tuo abbonamento. Nessuna dipendenza da
installare: Python 3 con la sua libreria standard, Swift per l'app.

[English](README.md)

![La dashboard](docs/dashboard.png)

## Cosa raccoglie

| fonte | dove | cosa ne ricava |
|---|---|---|
| sessioni di Claude Code | `~/.claude/projects/**/*.jsonl` | data, progetto, primo messaggio, scambi, tool, token |
| memoria di Claude | `~/.claude/projects/*/memory/*.md` | descrizione dei progetti, collegamenti `[[wiki]]` |
| skill, plugin, routine | `~/.claude/skills`, `plugins`, `scheduled-tasks` | cosa sa fare il tuo Claude Code |
| GitHub | `gh repo list`, commit recenti | repo, commit, materiale vero per i post |
| git locale | le tue cartelle di codice | branch, modifiche non committate |
| sessioni e obiettivi di Codex | `~/.codex/sessions`, `goals_1.sqlite` | gli stessi, più su cosa Codex si è bloccato |
| liste di task di Claude Code | `~/.claude/tasks/<sessione>/*.json` | cosa è aperto adesso, sessione per sessione |
| hook di sessione | `SessionStart`, `SessionEnd` | quali sessioni sono aperte adesso |

Le fonti non vengono mai modificate. Plancia le legge e sta da parte.

Cosa è cambiato di recente e perché: [docs/NOVITA.md](docs/NOVITA.md).

## Installazione

```bash
cd ~/dev/plancia
./bin/plancia install      # comando, server MCP, hook, skill, avvio automatico
./bin/plancia init         # costruisce la mappa dei progetti dai tuoi dati
./mac/build.sh --install   # costruisce Plancia.app in /Applications (macOS 26 o più recente)
```

`plancia uninstall` rimette tutto com'era. I dati restano in `~/.plancia/`.

## Windows e Linux

Prima viene macOS: è lì che vive l'app nativa. Tutto il resto di Plancia è Python
e un server web locale, quindi gira anche su Windows e Linux, con la dashboard nel
browser. Servono Python 3.9+ e Claude Code o Codex.

Windows (PowerShell):

```powershell
git clone https://github.com/nerln/plancia.git $HOME/plancia
cd $HOME/plancia
python bin/plancia install       # comando, server MCP, hook, skill, avvio automatico
python bin/plancia init          # costruisce la mappa dei progetti
python bin/plancia serve --open  # la dashboard, nel browser
```

Linux:

```bash
git clone https://github.com/nerln/plancia.git ~/dev/plancia
cd ~/dev/plancia
python3 bin/plancia install
python3 bin/plancia init
python3 bin/plancia serve --open
```

`install` scrive anche il comando `plancia`. Su Windows è uno shim `plancia.cmd` in
`%LOCALAPPDATA%\Plancia\bin`, e ti dice di aggiungere quella cartella al PATH se
non c'è ancora; `bin/plancia.cmd` fa lo stesso lavoro da dentro il clone. Su Linux
è un collegamento in `~/.local/bin`. `plancia uninstall` rimette tutto com'era.
Se `python` non è nel PATH (l'installer di python.org non ce lo mette per
impostazione predefinita, e `python` può essere lo stub del Microsoft Store),
usa `py -3 bin/plancia install`. `pip install` non è ancora una strada supportata: il pacchetto non porta i file
della dashboard né gli script di `bin/`, quindi si usa il clone.

Cosa funziona uguale: la dashboard, i tool MCP `plancia_*` in Claude Code e Codex,
gli hook di sessione e il richiamo della memoria, le skill, la ricerca, il
riepilogo, Riprendi (apre un terminale nella cartella giusta) e la partenza del
server a ogni accesso.

Cosa usa ciascun sistema sotto il cofano:

| | macOS | Windows | Linux |
|---|---|---|---|
| partenza all'accesso, riepilogo giornaliero | launchd | Task Scheduler, o la cartella Esecuzione automatica se lo rifiuta | systemd `--user`, o `~/.config/autostart` |
| Riprendi apre | Terminale | Windows Terminal, altrimenti una nuova finestra di console | il primo tra x-terminal-emulator, gnome-terminal, konsole, xterm |
| appunti | `pbcopy` | `clip` | wl-copy, xclip o xsel |
| riepilogo a voce | `say` | il sintetizzatore vocale di Windows | espeak-ng (o espeak) e un lettore audio |
| notifica | `osascript` | notifica di PowerShell | `notify-send`, se c'è |

Su Windows e Linux l'app nativa non c'è: apri http://127.0.0.1:7773 in Chrome o
Edge e scegli Installa Plancia. Ha la sua finestra e la sua icona, e si apre
anche con il server spento, con l'ultimo stato che aveva visto. Safari su macOS fa
lo stesso con Aggiungi al Dock.

Cosa non esiste fuori da macOS: l'app nativa, la sua voce nella barra dei menu, le
azioni `plancia://` e il pannello vocale a mani libere. `plancia jarvis "..."` da
terminale funziona comunque. Se sulla tua macchina manca un pezzo il resto va
avanti: senza strumento per le notifiche niente notifica, senza strumento per gli
appunti niente copia. Senza un motore vocale, `plancia say`, `plancia voice prova`
e `plancia recap --speak`, `plancia ask --speak` e `plancia jarvis --speak` lo dicono e
dicono cosa installare, l'azione MCP `speak`
risponde `letto: false` con il motivo e `plancia doctor` segnala la voce come
mancante. Anche la dashboard continua a funzionare: il riepilogo, "Chiedi" e Jarvis
rispondono col testo e con un campo `voce: null` più una `nota_voce` che spiega che
manca il motore vocale, e si salta solo l'ascolto («Ascolta» mostra quella nota invece
di un errore generico). Fuori da macOS il motore vocale ha il suo nome vero
(`System.Speech`, `espeak-ng`) e l'elenco delle voci lo chiede a lui. Su Windows Riprendi ha bisogno di
Windows Terminal per un task perso quando `claude` è un file `.cmd` (installazione
con npm): il suo prompt su più righe non si può passare a `cmd.exe` in sicurezza, e
Riprendi lo dice invece di aprire un comando rotto. Su Windows il server parte all'accesso ma non riparte dopo un
crash, e i suoi errori non finiscono in un log (su macOS lo riavvia launchd, su
Linux systemd). Un secondo `plancia serve` mentre gira quello dell'accesso lo dice (e
con `--open` apre il browser su quello) invece di cadere sulla porta occupata.
`plancia esporta --apri` apre il file con l'apritore del sistema (`open -R`,
`os.startfile`, `xdg-open`). Le cartelle che contengono progetti senza esserlo (un disco
esterno, un'altra cartella dei progetti) si scrivono in `config.json` alla chiave
`contenitori`, una lista di percorsi, accanto a quelle che Plancia riconosce da sola
(`~/dev`, `~/Siti`, le cartelle di Google Drive). Su macOS vale anche per i dischi che
prima si scrivevano a mano: un disco esterno è un contenitore solo se sta lì
(`"contenitori": ["/Volumes/Disco/dev"]`), e `plancia doctor` stampa i contenitori in
uso. L'avvio automatico e il riepilogo giornaliero non caricano mai lavori di launchd,
del Task Scheduler o di systemd da un ambiente finto: se la `HOME` del processo non è
la casa vera dell'utente (o `PLANCIA_HOME` punta fuori) i file si scrivono ma non si
caricano («file scritti, non caricati (HOME di prova)»). `PLANCIA_AUTOSTART_FORZA=1`
forza i comandi, per una macchina dove sono finti. I comandi che Plancia costruisce per ogni sistema sono coperti
dalla suite, ma Windows e Linux hanno avuto molto meno uso reale di macOS: `plancia doctor`
dice cosa è collegato.

## Le tre porte

**L'app.** Finestra nativa in SwiftUI (2.0, macOS 26 o più recente): barra
laterale con Oggi, Task, Progetti, Social, Memoria e Archivio, il campo di
ricerca di sistema, un Inspector a destra per quello che selezioni, e le
Impostazioni per lingua e aspetto. Più la voce nella barra dei menu. Tiene su
il backend da sola. Su macOS 13-15 l'ultima app che gira è la 1.1.0; la
dashboard nel browser funziona ovunque. `plancia://recap`, `plancia://jarvis`, `plancia://ask?q=…`, `plancia://open?view=progetti` e
`plancia://pdf` sono azioni da legare a una scorciatoia di sistema, a
Raycast o a Comandi rapidi.

**Claude Code e Codex.** Sette tool `plancia_*` in ogni sessione di tutti e due,
un hook `SessionStart` che passa a Claude il tuo stato attuale come contesto
iniziale, e due skill che gli dicono quando leggere da Plancia e quando
scriverci. Sette e non venti: restano esposti i sei che vengono usati davvero,
gli altri stanno dietro a un tool solo, `plancia`, che si chiama con `azione`.
Gli schemi dei tool si pagano a ogni richiesta di una sessione, quindi la
superficie è il conto. Misurato: 1195 token per sessione di Claude Code e 1020
per una di Codex, contro 2870 e 2196.

**Il terminale.** `plancia recap --speak`, `plancia ask "cosa ho spedito questa
settimana?"`, `plancia task add`, `plancia cerca "una frase che ricordi"`,
`plancia projects`.

## Cercare dentro quello che è stato detto

I transcript sono la cosa più grossa che hai e la più difficile da riaprire. Il
titolo di una sessione non dice niente sei settimane dopo, e la frase che stai
cercando sta in mezzo a una conversazione.

Plancia tiene un indice FTS5 sulla prosa di ogni turno, tuoi e dell'agente, di
Claude Code e di Codex. I risultati dei tool restano fuori di proposito: sono il
grosso dei byte e quasi mai la cosa che si ricorda. Su questa macchina fanno
13.000 turni da 1.287 transcript, 20 MB indicizzati su 979 di disco, ricostruiti
da zero in 5 secondi e tenuti aggiornati in modo incrementale, che costa una
`stat` per file non cambiato.

Ogni risultato torna com'era scritto, con il file e la riga da cui viene, così si
riapre il momento invece di leggerne un riassunto.

![La ricerca](docs/cerca.png)

```bash
plancia cerca "il denominatore del blending"
plancia cerca "cookie" --project molo
```

Nella dashboard `/` apre la ricerca da qualsiasi vista, e i chip sopra i
risultati contano quanti ne vengono da ogni progetto su tutto l'indice, non sulla
pagina. In Claude Code e in Codex è `plancia_search`.

## Il richiamo della memoria

Cercare funziona solo se ti ricordi di cercare. Ma le cose che vorresti sapere
sono proprio quelle che hai dimenticato di sapere.

Claude Code tiene la memoria per cartella: carica il `MEMORY.md` di dove sei e
basta. Così quello che hai imparato su un progetto smette di esistere appena ne
apri un altro. Su questa macchina si vedeva: la stessa memoria scritta due volte
in due cartelle diverse, otto volte su quarantasette, perché la prima era
invisibile da dove stavi.

Il richiamo è un hook `UserPromptSubmit` che a ogni messaggio guarda le memorie
di *tutte* le cartelle e mette in contesto le poche che c'entrano. Costa 30 ms e
non tocca la rete: bm25 sull'indice che c'è già, nessun modello da caricare.

Richiama solo i tipi che viaggiano: `feedback`, `user`, `reference`. Una memoria
di progetto no: dentro quel progetto la carica già Claude Code, e fuori il
briefing ha già dato stato e prossimo passo. Ripeterla sarebbe rumore travestito
da aiuto.

Quattro modi di tacere, che è la parte difficile:

- niente che sia già in contesto (le memorie della cartella corrente);
- niente due volte nella stessa sessione;
- niente sotto soglia, e niente quando il secondo risultato vale quasi quanto il
  primo, perché senza un vincitore chiaro non ha capito di cosa si parla;
- niente che sia solo un titolo. Questa è una regola di correttezza, non di
  igiene: bm25 normalizza per lunghezza, quindi un file di quaranta caratteri
  che contiene esattamente le parole cercate batte qualunque memoria vera.
  Due avanzi di un vecchio test, «codici di verifica del progetto», rispondevano
  con punteggio 15 a frasi come «verifica che il progetto funzioni» e sarebbero
  entrati in contesto ogni volta.

```bash
plancia ricorda "quanta ram serve al mio mac per un modello in locale"
plancia ricorda "aggiungi un bottone al form" --tutto   # anche gli scartati
```

Il primo trova `mac-16gb-no-swap`, che sta in un'altra cartella. Il secondo non
trova niente, ed è la risposta giusta: un richiamo che si accende sempre è un
richiamo che si impara a saltare.

Che la frase debba nominare il Mac perché quella memoria vinca dice cos'è questo
richiamo e cosa non è. Confronta parole, non significati: `ram` e `memoria`
funzionano tutte e due perché stanno scritte nel testo, ma una domanda sul
consumo che non nomini né la macchina né la memoria non la trova. Provare a
inseguire le coniugazioni tagliando le parole alla radice è stato provato e ha
fatto danno, perché in italiano "collaborare" e "collaudo" cadono sulla stessa.
Meglio perdere un richiamo che darne uno sbagliato.

## Guardare la memoria

`#/memoria` nella dashboard. L'elenco delle memorie stava già in Archivio e
diceva cosa c'è; questa vista dice com'è messo.

La mappa disegna il grafo dei `[[link]]`, un colore per tipo e la dimensione per
quanti legami ha. Il riempimento porta l'unica affermazione che conta: **pieno
vuol dire che il richiamo può portarla in contesto**. Su questa macchina sono 13
su 44, e vedere quarantaquattro pallini di cui trentuno vuoti dice in un colpo
d'occhio una cosa che nessun elenco diceva.

Il grafo va letto sapendo cos'è: i legami sono quelli scritti a mano, quindi
è un'opinione, non una misura. Due memorie sullo stesso argomento senza un
`[[link]]` fra loro qui sembrano estranee. E i wikilink non contano niente per
il richiamo, che lavora su bm25 del testo: la mappa mostra come hai organizzato
il sapere, non come la macchina lo trova.

Sotto c'è la casella che vale il viaggio: scrivi una frase e vedi cosa ti
richiamerebbe, con i punteggi e con quello che ha scartato. È l'unico modo di
guardare da fuori una cosa che scrive nel contesto senza farsi vedere. Ed è così
che si è scoperto che due file di scarto rispondevano a mezzo vocabolario.

Accanto, le poche cose contabili: quante memorie vivono in due cartelle, quante
non sono legate a niente, quanti link puntano al vuoto, quante sono rimaste un
titolo. Se non c'è niente, il riquadro resta quasi bianco, ed è il premio.

## Portarselo in tasca

```bash
plancia esporta
```

Scrive un file HTML unico che contiene l'archivio dentro di sé e sa cercarselo:
le memorie per intero, i progetti attivi col prossimo passo, i task aperti. Su
questa macchina sono 247 KB.

Non chiede niente alla rete. Niente font, niente fogli di stile, niente
immagini, nessuna chiamata: è tutto dentro, e il collaudo controlla che resti
così. Aprirlo non dice a nessuno che l'hai aperto, ed è l'unico requisito che
conta davvero per un archivio personale.

Sul telefono ci va a mano: AirDrop, che è un collegamento diretto fra i due
dispositivi, oppure il Wi-Fi di casa, che di casa non esce. In tutt'e due i casi
il file non tocca internet e non passa da nessun servizio. Poi «Aggiungi a
schermata Home» e si comporta come un'app, senza App Store e senza certificati
di sviluppatore.

Da lì funziona da solo: in aereo, in montagna, col Mac spento. Per aggiornarlo
si rifà e si rimanda, e serve essere vicini al Mac una volta ogni tanto, non
avere una VPN sempre accesa. Il piè di pagina dice di quando è la copia, perché
un archivio che non dichiara la propria età è un archivio di cui fidarsi troppo.

## Il progetto su cui una sessione ha lavorato davvero

Una sessione finiva nel progetto della cartella da cui era stata aperta. Per
Codex funziona, perché Codex si apre dentro il progetto. Per Claude Code no:
misurato su questa macchina, 199 sessioni su 587 erano aperte dalla radice del
Drive, da `~/dev` o dalla casa, cartelle da cui si lavora a tutto.

Adesso Plancia guarda anche cosa la sessione ha toccato: i file dei `tool_use` e
i percorsi assoluti dentro i comandi Bash, contati per cartella di progetto. Se
la cartella di apertura non dice niente vince la cartella toccata di più; se
invece è già un progetto si tiene quella, a meno che il 70 per cento dei percorsi
non stia da un'altra parte. Ogni riga porta con sé la cartella dedotta e il
perché, quindi l'attribuzione si può controllare invece di doverci credere.

```bash
plancia sessioni                         # il catalogo, per progetto
plancia sessioni --progetto molo --giorni 30
plancia sync --riattribuisci             # ricalcola tutto l'archivio
```

La tilde in fondo a una riga, e la scritta «dedotta dai percorsi» nella
dashboard, segnano le sessioni attribuite così. Le chiamate interne di Plancia e
le sessioni temporanee restano da parte: `--tutte` le mostra.

## Il riepilogo giornaliero

Plancia mette insieme la giornata dai dati veri (sessioni, commit, task aperti e
chiusi, post, cosa aspetta ogni progetto) e ne fa un testo scritto per essere
ascoltato: frasi corte, niente elenchi, niente markdown, niente percorsi di file
letti a voce.

Due motori per il testo. Quello a modelli è deterministico, non costa niente e
funziona sempre. L'altro passa gli stessi dati a Claude Code in modalità non
interattiva (`claude -p`) e restituisce una versione raccontata meglio in otto
secondi circa. Se Claude non risponde in tempo si usa il primo e non te ne
accorgi.

Due motori per la voce. [Voicebox](https://github.com/jamiepine/voicebox) se il
suo backend locale risponde, così esce la tua voce clonata. Altrimenti le voci di
sistema di macOS, che ci sono sempre, non chiedono niente e partono subito. Tutte
e due reggono italiano, inglese, spagnolo, francese, tedesco e portoghese.

```bash
plancia recap --speak            # oggi, ad alta voce
plancia recap --lang en          # in inglese
plancia ask "dove ero rimasto con la pipeline di trascrizione?" --speak
plancia daily on 08:45           # ogni mattina, come notifica
plancia daily on 08:45 --voce    # ogni mattina, letto
```

Le domande passano da Claude Code con il contesto di Plancia già allegato, quindi
la risposta sta su quello che è successo davvero e non su un'ipotesi.

### E finisce con una decisione

Il riepilogo non si ferma ai fatti. Plancia cerca i segnali nei dati e li
trasforma in proposte, ognuna con un'azione già pronta: un lancio fallito da
riprovare, un obiettivo di Codex senza quota, file non committati da ieri, un
post approvato e mai uscito, un progetto il cui prossimo passo dichiarato è
rimasto lì. Le proposte nascono solo dai segnali, mai dall'intuizione di un
modello, così una giornata tranquilla ti dà un riepilogo corto invece di un
consiglio inventato. Dici "fallo", o "la seconda", e parte.

## Prossimi

Una riga per progetto attivo, dentro Oggi, accanto al riepilogo: il primo
task aperto, o il suo prossimo passo dichiarato se non ce n'è nessuno,
raggruppate per area, ordinate per scadenza e poi per ultima attività. Ne
compaiono al massimo sette per gruppo; il resto sta dietro un "altri N".
Per raggrupparsi per area invece che restare una lista piatta serve la mappa
di `plancia riordina`.

## Jarvis

Non tieni premuto niente. `⌥Spazio` da qualsiasi app, oppure `plancia://jarvis`,
apre un pannello che ascolta di continuo e capisce dal silenzio che hai finito di
parlare, non da un tasto tenuto giù.

Quello che sente prende due strade. Le frasi che riconosce con certezza (apri una
vista, segna un task, chiudilo, rileggi le fonti, leggimi il riepilogo) partono in
un decimo di secondo, in locale. Tutto il resto va a Claude Code in modalità non
interattiva con i tool `plancia_*` aperti, quindi il task lo aggiunge davvero, il
progetto lo aggiorna davvero, l'archivio lo cerca davvero.

In fondo al pannello c'è un campo per scrivere: serve quando il microfono non è
disponibile e per correggere una frase capita male senza ripeterla.

Il microfono resta aperto anche mentre risponde, quindi lo puoi interrompere
ricominciando a parlare. È la cancellazione dell'eco sul nodo di ingresso a
renderlo possibile: senza, si sente da solo e si interrompe da solo. "Annulla"
ferma un lavoro partito, "basta" chiude il pannello. Quando un lancio finisce te
lo dice a voce anche se nel frattempo stavi facendo altro.

```bash
plancia jarvis "ricordami di scrivere la nota di migrazione"   # lo stesso, scritto
```

Claude Code ha la voce [da marzo 2026](https://claudefa.st/blog/guide/mechanics/voice-mode):
tieni premuta la barra spaziatrice e detti. È solo dettatura in ingresso, e una
modalità a mani libere non c'è per scelta. Questa è l'altra metà: risponde e
agisce.

## Tutti i task

![Tutti i task](docs/board.png)

Claude Code tiene la sua lista di task in una cartella, Codex i suoi obiettivi in
un altro database, Plancia ha i suoi. Nessuno dei tre sa degli altri due. Questa
vista li legge tutti, riporta gli stati a `aperto`, `in corso`, `bloccato`,
`fatto`, `sparito`, e mostra una lista sola.

**Riprendi è la prima cosa che offre una riga.** Un task porta con sé l'id
della sessione che l'ha scritto, quindi il bottone sulla sua riga non
rilancia niente da zero: riapre la conversazione vera, in uno dei tre stati.
Viva, e Riprendi copia negli appunti il messaggio da incollare nella
conversazione che sta già girando (`riprendi il task 42 di Plancia: <titolo>`):
non c'è niente da lanciare. Chiusa, e premere Riprendi apre da solo un
Terminale visibile, con `claude --resume <id>` (o `codex resume <id>`) nella
cartella del task: Plancia non tocca mai una trascrizione da un secondo
processo. Persa, perché la sessione non è mai stata registrata o è scaduta,
e allora lo dice invece di fingere, e ripartire da capo, col contesto scritto
a mano, è l'unica strada che resta.

```bash
plancia lavagna                          # tutti i task aperti, da terminale
plancia riprendi 42                      # riprende il task 42, nel suo stato
plancia riprendi 42 --apri               # lo fa subito, come fa il bottone
plancia lanci                            # com'è andato un lancio in background
```

Mandare un lavoro in background è l'altra strada, secondaria, per quando
riprendere non è quello che vuoi: `plancia riprendi 42 --background --scrive
--istruzioni "rilancia l'ablation"` lo lancia senza sorveglianza, sulla
sessione di quel task, e ne registra l'esito. Il modo predefinito è di sola
lettura; `--scrive` lo lascia scrivere, ed è una scelta che fai ogni volta.
`plancia manda "rilancia l'ablation" --agente codex --progetto atlas` è il
vecchio alias per la stessa cosa senza un id di task: funziona ancora ma
stampa un avviso di deprecazione su stderr e sparirà in un prossimo rilascio.
Dentro Claude Code e Codex la stessa ripresa sta dietro al tool `plancia` con
`azione="riprendi"` e l'`id` del task.

## Il registro degli eventi

Gli altri strumenti non devono stare a interrogare un database per sapere che è
successo qualcosa. Ogni evento che conta finisce in coda a
`~/.plancia/eventi.jsonl`, una riga JSON, schema `plancia.evento/1`:

```json
{"schema":"plancia.evento/1","id":"9f2c…","ts":"2026-08-02T09:14:22Z",
 "tipo":"lavoro.completato","titolo":"Rilancia l'ablation","progetto":"atlas",
 "origine":"cantiere","dati":{"agente":"codex","modo":"esegui","token":22800}}
```

Tipi: `lavoro.avviato|completato|fallito`, `task.creato|chiuso`,
`post.pubblicato`, `progetto.archiviato|aggiornato`, `riepilogo.pronto`. Chi
legge tiene l'id dell'ultimo evento visto e chiede quello che è venuto dopo, con
`plancia eventi --dopo <id>` o `GET /api/eventi`. Il file si scrive solo in coda
e ruota a 5 MB.

## Due agenti, un archivio solo

Plancia legge le sessioni di Codex da `~/.codex/sessions` insieme a quelle di
Claude Code, e registra il proprio server MCP dentro `~/.codex/config.toml`. I due
agenti vedono gli stessi progetti, gli stessi task, gli stessi tool. La
sezione Agenti dell'Archivio mostra chi ha lavorato su cosa e quando si sono
passati il lavoro.

## Dove se ne va il tempo

Ogni `claude -p` costa cinque secondi di avvio prima ancora di pensare. In una
conversazione a voce sono cinque secondi di silenzio a domanda. Plancia prende
tre strade, in quest'ordine:

| strada | quando | costo |
|---|---|---|
| comandi | apri una vista, segna un task, chiudilo, annulla un lancio, archivia | 0,1 s |
| risposte dai dati | quanti task, cosa riprendo, quanto ho lavorato | 0,1 s |
| Claude, tenuto caldo | tutto il resto, con i tool `plancia_*` aperti | 2,7 s |

Il processo Claude resta vivo fra una domanda e l'altra invece di ripartire ogni
volta, quindi solo la prima paga l'avvio, e il pannello lo scalda appena lo apri.
Il riepilogo si prepara alla fine di ogni giro freddo: chiederlo costa 20
millisecondi invece di dieci secondi.

`bin/plancia-hook --prova` stampa quello che passerebbe a Claude senza mettere
in coda niente: provarlo non deve sporcare l'archivio con una sessione mai
esistita.

## Il flusso dei dati

```
fonti ──▶ sync ──▶ SQLite ──▶ briefing.md · riepilogo · REST · voce
```

Due ritmi, perché rileggere venti repo per sapere che hai appena aperto una
sessione è tempo buttato:

- **caldo**, ogni due minuti, ~40 ms: la coda degli hook e la coda nuova dei
  transcript. Quello che stai facendo adesso.
- **freddo**, ogni trenta minuti, ~1,5 s: memoria, skill, repo, git locale,
  manutenzione dei progetti, i due indici di ricerca, riepilogo.

Il giro freddo ci metteva quaranta secondi, e venti erano una cartella sola.
`git status` dentro una cartella sincronizzata deve far verificare ogni file
tracciato al file provider: misurato a freddo su un repo da 681 file, due minuti
e 51 secondi, contro dieci millisecondi per un repo sul disco. Adesso le cartelle
si leggono otto alla volta, una che non risponde entro quattro secondi viene
ricordata e lasciata stare per sei ore, e uno stato mai arrivato si scrive come
ignoto invece che come pulito.

`plancia flusso` stampa ogni fonte, da dove arriva, quale giro la legge e quanto
è fresca.

## I progetti finiscono

Un progetto nato da una cartella dove hai lavorato una volta tre settimane fa non
è un progetto attivo: è un ricordo. Plancia lo archivia da solo dopo due
settimane se non ha né un repo né un file di memoria e ha meno di tre sessioni.
Quelli che hai dichiarato tu non li tocca mai. A voce: "archivia il progetto
video", oppure "il filmato ard è finito".


## Progetti

![Progetti](docs/projects.png)

Un progetto è quello che dici tu: un repo, una cartella, un file di memoria, o
tutti e tre. `plancia init` propone una mappa da quello che trova, tu la correggi
in `~/.plancia/seed.json`. Le sessioni aperte da una cartella generica vengono
attribuite per parole chiave, e riattribuite a ogni sync man mano che affini le
parole.

## Aree

Una mappa dei progetti serve solo se si può correggere, e correggere 122
progetti uno per uno non succede mai. `plancia riordina --proponi` calcola
una mappa dei padri per ogni progetto (un'area come una tesi, o un repo vero
con i suoi worktree) e la scrive in un file invece che nel database, così la
leggi prima che cambi qualcosa.

```bash
plancia riordina --proponi                    # scrive la mappa proposta in un file
plancia riordina --mostra <file>              # la stampa in tabella
plancia riordina --applica <file>             # assegna padri, stati e inglobamenti che contiene
plancia riordina --annulla <batch>            # rimette esattamente quello che ha cambiato
```

Il file è JSON semplice, una riga per progetto, e lo correggi a mano o lo fai
scrivere a un agente che ha studiato i tuoi progetti. Oltre a `padre` (la
chiave del padre) una riga può portare:

```json
[
  {"chiave": "vecchio-esperimento", "inglobato_in": "atlante",
   "motivo": "il codice vive ora dentro la cartella di atlante"},
  {"chiave": "bozza-tesi", "stato": "concluso",
   "motivo": "consegnata a giugno"}
]
```

- `stato`: `attivo`, `archiviato` o `concluso`. Assente vuol dire che lo stato
  non si tocca.
- `inglobato_in`: il progetto dentro cui questo è confluito. Vale come padre =
  quel progetto, stato `archiviato`, e una riga "Inglobato in atlante:
  <motivo>" in coda al sommario del progetto.
- `motivo`: il perché, in una frase. È obbligatorio in ogni riga che ha uno
  `stato` o un `inglobato_in`; `--applica` rifiuta la riga che ne è priva e
  `--mostra` la segna `[DA CORREGGERE]`.

`--mostra` fa vedere tutto in una tabella sola (chiave, padre, regola, stato,
motivo). Una riga è tutto o niente: se il padre viene rifiutato, lo stato non
cambia. Un progetto manuale si tocca solo con una riga che lo nomina con un
padre, uno stato o un `inglobato_in`; un progetto che nel file non c'è non si
tocca mai. Il formato è documentato per intero in cima a
`plancia/riordina.py`.

Applicare è un batch solo, e annullarlo rimette padre, stato e sommario di
prima di ogni progetto, non un padre vuoto. L'annullamento va campo per campo
e solo dove il campo è ancora quello lasciato dal batch: uno stato cambiato a
mano dopo, o da un batch successivo, non viene scavalcato. Oggi (il riepilogo) e Prossimi raggruppano i
progetti per area appena questa mappa esiste; prima che esista, ripiegano su
una lista piatta, così su un'installazione nuova non si rompe niente.

## Compartimenti

Due gruppi di lavoro sulla stessa macchina che non devono vedersi: un progetto
condiviso con un altro e tutto il resto. `compartimenti` in
`~/.plancia/config.json` nomina uno o piu' compartimenti (ognuno con le sue
`cartelle` e `sessioni`); tutto il resto e' il predefinito. Senza, Plancia fa
quello che ha sempre fatto.

Con, ogni oggetto ha un compartimento ricavato dai dati che ha gia': una sessione
dal suo id, dalla sua cartella e dalla sua trascrizione; un task dalla sessione
che l'ha creato o dal suo progetto; un progetto dai suoi percorsi e dalle memorie
collegate; una memoria dal file in cui sta (la memoria automatica di Claude Code
di una cartella e' del compartimento di quella cartella). Poi ogni superficie
mostra solo il suo. Il briefing di sessione e il richiamo delle memorie "scritte
in altre cartelle" lasciano fuori gli altri compartimenti. Il server MCP filtra
quello che legge, e una scrittura su un progetto, un task o un post di un altro
compartimento e' rifiutata con un messaggio chiaro. La dashboard e' la tua vista,
non quella di un agente, quindi mostra tutto ma separato: un selettore in alto
sceglie il compartimento (prima il predefinito), ogni vista lo segue, e quello che
crei li' resta li'. `?compartimento=nome` nell'indirizzo la apre su uno.

Una sessione con segni di due compartimenti non vede niente. Questo decide cosa
mostra Plancia; non e' un confine di sicurezza, stesso utente e stesso disco.

Il comando `plancia` da terminale capisce il suo compartimento come il server
MCP, da `CLAUDE_CODE_SESSION_ID` e dalla cartella corrente: un comando lanciato da
una sessione di un compartimento nominato vede solo quel compartimento (lavagna,
eventi, lanci, briefing, ricerca, sessioni, riepilogo, domande, jarvis, export e
il resto), e una scrittura su un progetto o un task di un altro compartimento e'
rifiutata. Un terminale umano senza id di sessione e con la cartella corrente
fuori da ogni nominato e' il predefinito e vede il predefinito; dentro la cartella
di un nominato vede quel nominato. L'assistente vocale della dashboard lavora dal
compartimento scelto nel selettore, e da un nominato una domanda libera si
risponde con i dati di quel compartimento nel prompt, non con il processo caldo e
i tool di Plancia. Un lancio partito da un compartimento e' di quel compartimento,
anche se il suo progetto non ha una cartella. I comandi che amministrano tutta
Plancia (`init`, `riordina --applica`, `riprendi --backfill`) da un nominato sono
rifiutati. Con i compartimenti attivi `briefing.md` non si scrive (c'e' un file
per compartimento) e torna quando li si toglie.

Limiti da sapere: le regole sulle cartelle confrontano percorsi POSIX (che
iniziano con `/` o `~`), quindi i compartimenti e il guardiano qui sotto sono solo per
macOS e Linux. Su Windows sono spenti, apposta e nel codice: una voce `compartimenti`
o `guardiano` in `config.json` e' ignorata, ogni sessione vede tutto (il briefing e'
quello di sempre), il guardiano esce subito senza negare niente e dice "non supportato
su Windows" una volta per sessione, e `plancia doctor` e `plancia guardiano` lo dicono.
Il riepilogo giornaliero lanciato da un pianificatore non ha una sessione, quindi
e' quello del predefinito.

## Due scelte non ovvie

**I transcript si leggono a byte, non a righe.** Sono centinaia di megabyte e
crescono. Plancia tiene l'offset di ogni file e rilegge solo la coda nuova; le
righe sopra 256 KB (i risultati dei tool) non vengono mai parsate, solo sondate.
Una rilettura completa di 430 sessioni costa 1,5 secondi, e rifare da zero
l'indice dei turni sopra ci mette altri 5.

**Il tipo di un record si cerca per intero.** Dentro `message.content` ci sono
altri campi `type` (`text`, `tool_use`, `tool_result`) che vengono prima di quello
vero: cercare `"type":"` dà la risposta sbagliata. Plancia cerca
`"type":"assistant"` e `"type":"user"` per esteso.

## Struttura

```
bin/plancia            comando
bin/plancia-mcp        server MCP (stdio)
bin/plancia-hook       hook di sessione, 20 ms
plancia/store.py       schema e accesso ai dati
plancia/ingest.py      lettura delle fonti
plancia/turni.py       l'indice sul testo di quello che e' stato detto
plancia/recap.py       il riepilogo
plancia/voice.py       sintesi, riproduzione, ascolto
plancia/briefing.py    quello che vede Claude
plancia/compartimenti_viste.py  quello che vede ogni compartimento
plancia/actions.py     le scritture, condivise fra HTTP e MCP
plancia/api.py         server locale e REST
plancia/mcp.py         JSON-RPC su stdio
plancia/lavagna.py     la lavagna unificata
plancia/cantiere.py    mandare un lavoro a un agente
plancia/proposte.py    cosa conviene fare, dai segnali
plancia/eventi.py      il registro in append
site/                  il sito, pubblicato su GitHub Pages
mac/Sources/          l'app macOS (SwiftUI, macOS 26 o più recente)
web/                   dashboard, nessun framework, nessun build
```

Dati in `~/.plancia/`: `plancia.db` (SQLite), `seed.json`, `token`,
`briefing.md`, `audio/`. Tienili fuori da qualsiasi cartella sincronizzata: un
file SQLite dentro Drive o Dropbox si corrompe.

## Sette superfici

Oggi (il riepilogo, il ritmo, le proposte, e Prossimi: una riga per progetto,
raggruppate per area, con cosa riprendere), Cerca, Tutti i task, Progetti,
Social, Memoria, Archivio (sessioni, agenti, capacità). Tutto il resto passa
da ⌘K. Al primo avvio una guida spiega le parti non ovvie, e resta lì sotto
"Guida".

## Cosa serve

Python 3.9+ e Claude Code, su macOS 13 o più recente, Windows o Linux (vedi sopra). L'app nativa per Mac
richiede macOS 26 o più recente e gli strumenti da riga di comando di Xcode per costruirla. `gh` è facoltativo e serve solo a
leggere i tuoi repo.

L'app nativa per Mac 2.0 è in SwiftUI e richiede macOS 26 o più recente. Su macOS 13-15 resta la 1.1.0, oppure
la dashboard nel browser (si installa come app web). La dashboard web non cambia nella 2.0.

## Sicurezza

Il server ascolta solo su loopback. Le scritture via HTTP chiedono il token in
`~/.plancia/token`, che la dashboard riceve dal server dentro la pagina. Le
letture sono libere: sono dati tuoi, già sul tuo disco.

### Il guardiano dei compartimenti, e cosa non vede

`bin/plancia-guardiano` è un hook PreToolUse facoltativo che tiene separati due gruppi
di lavoro sulla stessa macchina (vedi `plancia/compartimenti.py`). Legge percorsi e
comandi di shell POSIX, quindi su Windows non fa niente (vedi i limiti sopra). È un analizzatore
euristico di ciò che una chiamata di strumento dice di voler toccare: un guardiano di
incidenti, non un confine di sicurezza. Ferma quello che un agente fa senza pensarci:
leggere i file dell'altro gruppo, riscrivere la config del guardiano stesso, una
ricerca ricorsiva che attraversa una cartella vietata. Non ferma chi lo aggira apposta,
e non lo pretende: un confine vero è un utente del sistema operativo separato, o un
contenitore. Si accende in `solo-registro` (scrive soltanto), si legge il registro, poi
si decide.

Cosa non vede, onestamente: i percorsi costruiti a runtime dentro programmi e script
già esistenti (uno script scritto in una chiamata e lanciato in un'altra, una
compilazione, un test che apre file); il codice scaricato o generato e poi eseguito; i
processi figli che si lanciano da soli e vivono oltre il comando (un demone, un lavoro
pianificato, un watcher); gli strumenti MCP di terzi con argomenti di file che non
conosce per nome; i percorsi che passano per un altro canale (gli appunti, la rete
locale, un database); un comando che non finisce di analizzare in due secondi (una
sessione di un nominato è negata con "comando troppo complesso da controllare in
tempo: spezzalo", quella del predefinito è ammessa con un avviso ogni volta). L'elenco
completo sta nel docstring di `plancia/compartimenti.py`.

## Contribuire

```bash
git config core.hooksPath .githooks
```

Accende il gancio che fa girare `python3 tools/prova.py` prima di ogni push:
4183 controlli in pochi minuti, su un archivio finto che non tocca
il tuo.

## Licenza

GPL-3.0-or-later. Vedi [LICENSE](LICENSE) e [COPYRIGHT](COPYRIGHT). Le versioni
fino alla 0.2.0 erano MIT e restano MIT.

Compilarlo dal sorgente è gratis e lo resterà. Una build firmata e notarizzata,
che si apre con un doppio clic, si paga quanto vuoi da 5 euro sul
[sito](https://nerln.github.io/plancia/#prezzo). È lo stesso programma:
quello che paghi è il certificato Apple, la notarizzazione e la manutenzione.
Come si taglia una release sta in [docs/RILASCIO.md](docs/RILASCIO.md).
