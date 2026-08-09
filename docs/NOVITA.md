# Cosa è cambiato, e perché

Onboarding scritto, da leggere una volta. Le stesse cose l'app te le fa provare
al primo avvio, e restano sotto "Guida".

## La riga corta

Prima Plancia era un archivio che guardavi. Adesso è un posto da cui lavori: c'è
una lavagna con tutto quello che è aperto, di tutti gli agenti; da ogni riga puoi
mandare il lavoro a Claude o a Codex; il riepilogo finisce con la cosa che
conviene fare, e a voce dici "fallo".

## Cercare dentro quello che è stato detto (1.0)

`#/cerca` nell'app o lo slash da qualsiasi vista, `plancia cerca` da terminale,
`plancia_search` dentro Claude Code e Codex.

Fino alla 0.3 l'indice teneva, di ogni sessione, il solo primo prompt: 0,80 MB su
979 di transcript, lo 0,08% del materiale. Ed è il motivo per cui quel tool era
stato chiamato cinque volte in tutto, non perché fosse nascosto ma perché non
trovava.

Adesso l'indice sta sulla prosa di ogni turno, tuoi e dell'agente, di tutti e due
gli agenti. I risultati dei tool restano fuori di proposito: sono il grosso dei
byte e quasi mai la cosa che si ricorda.

Due cose da sapere:

- **Ogni risultato dice da quale riga di quale file viene.** Un risultato che non
  si può riaprire vale la metà: quello che si vuole è tornare al momento, non
  leggerne un riassunto.
- **I chip contano su tutto l'indice, non sulla pagina.** Trenta risultati
  mostrati non dicono niente sui trecento che restano fuori. I chip dicono quanti
  ne vengono da ogni progetto, e cliccarli stringe.

## Meno token, a ogni richiesta (1.0)

Gli schemi dei tool non si pagano una volta per sessione: stanno nel contesto di
ogni singola richiesta. Venti tool erano venti schemi, sempre.

Adesso ne restano esposti sei, quelli che vengono usati davvero, e gli altri
stanno dietro a un tool solo, `plancia`, che si chiama con `azione`. I nomi
vecchi rispondono ancora, per i client già avviati.

Misurato: 1195 token per sessione di Claude Code contro 2870, e 1020 per una di
Codex contro 2196. È lo stesso binario per tutti e due, quindi il risparmio è lo
stesso risparmio.

## La lavagna

`#/lavagna` nell'app, `plancia lavagna` da terminale.

Claude Code tiene la sua lista di task in `~/.claude/tasks/<sessione>/`, Codex i
suoi obiettivi in `~/.codex/goals_1.sqlite`, Plancia i suoi nel database. Nessuno
dei tre sapeva degli altri due. La lavagna li legge tutti e riporta gli stati agli
stessi cinque: aperto, in corso, bloccato, fatto, sparito.

Due cose da sapere:

- **Le voci che una fonte non riporta più spariscono.** Se cancelli un task in
  Claude Code non resta lì a fare finta di esistere.
- **I filtri in alto sono due assi diversi**: a sinistra la fonte, a destra lo
  stato. "aperti" comprende anche quelli in corso e bloccati, perché sono tutti
  lavoro che non è finito.

## Mandare un lavoro a un agente

Dal bottone "Manda a un agente", o da `manda` su una qualsiasi riga.

Si apre un compositore: il lavoro, come lo vuoi fatto, su quale progetto, a quale
agente, in che modo. Il campo "come lo voglio fatto" è quello che conta: finisce
nel prompt insieme al contesto del progetto, quindi è il posto dove scrivere
"senza riscrivere il modulo" o "prima dimmi cosa cambieresti".

**Il modo predefinito è `proposta`.** L'agente legge, ragiona e ti riferisce, e
non tocca nessun file. `esegui` lo lascia scrivere, e va scelto ogni volta: il
riquadro diventa rosso quando lo scegli, apposta.

Il task si chiude da solo solo se il lancio era in `esegui` ed è andato bene. Un
lancio in proposta non chiude niente, perché non ha fatto niente.

Da terminale:

```bash
plancia manda "rilancia l'ablation con lo split grande" --agente codex --progetto atlas
```

E per vedere com'è andata:

```bash
plancia lanci
```

## Il riepilogo che finisce con una decisione

Il riepilogo non si ferma più ai fatti. Dopo il racconto della giornata arrivano
le proposte, in ordine di urgenza, ognuna con l'azione già pronta.

Le proposte nascono **solo da segnali che stanno nei dati**:

| segnale | proposta |
|---|---|
| un lancio fallito nelle ultime 72 ore | lo riprovo? |
| un obiettivo di Codex bloccato o senza quota | ci mando Claude a vedere? |
| file modificati e non committati da ieri | guardo cosa sono? |
| un post approvato e mai uscito | lo pubblichiamo? |
| un task in corso da più di tre giorni | lo riprendo? |
| il prossimo passo di un progetto fermo da due giorni | lo mando a un agente? |
| oggi hai generato 2,5 volte la tua media di trenta giorni | tienila d'occhio |

Se il segnale non c'è, la proposta non c'è. Una giornata tranquilla ti dà un
riepilogo corto invece di un consiglio inventato: è voluto.

A voce funzionano "fallo", "la seconda", "eseguilo". "Eseguilo" è l'unico modo
per far partire una proposta in modo esecutivo: "fallo" tiene il modo che la
proposta aveva, e quasi sempre è proposta.

## La voce

Quello che è cambiato sotto:

- **Il microfono non si spegne fra un turno e l'altro.** Prima si fermava e
  riavviava a ogni frase, e la frase dopo perdeva le prime sillabe.
- **Puoi interromperlo.** Ricomincia a parlare mentre risponde e si zittisce. È
  la cancellazione dell'eco sul nodo di ingresso a renderlo possibile: senza, si
  sentirebbe da solo e si interromperebbe da solo.
- **I nomi dei tuoi progetti** vanno al riconoscitore come vocabolario. Senza,
  "Voicebox" diventava "voice books".
- **L'attesa del silenzio si adatta**: più corta sui comandi, più lunga quando
  stai ragionando ad alta voce.
- **Gli errori si sentono.** A mani libere un messaggio scritto non esiste.
- **"Annulla" ferma un lavoro partito**, "basta" chiude il pannello.
- **"Ripeti"**, o "non ho capito", ridice l'ultima cosa uguale. Chi non ha
  sentito vuole quella, non una riformulazione che confonde di più.
- **"Più piano" e "più veloce"** cambiano la velocità della voce, e resta com'era
  anche dopo aver chiuso.
- **Quando un lancio finisce te lo dice**, anche se nel frattempo stavi facendo
  altro. Un agente che lavora tre minuti in silenzio ti riporta a guardare lo
  schermo, che è esattamente quello da evitare.
- **Dopo tre minuti che non parli il microfono si chiude da solo.** Un programma
  che si vanta di non mandare niente fuori non può tenerlo aperto tutto il
  giorno perché ti sei alzato senza dire niente. Tocca l'orbita per riprendere.

- **In fondo al pannello c'è un campo per scrivere.** Serve quando il microfono
  non c'è, e serve quando una frase viene capita male: la correggi scrivendo
  invece di ripeterla tutta, che è il momento in cui di solito si molla.

- **Quello che si legge e quello che si dice non sono più la stessa cosa.** Un
  indirizzo letto ad alta voce diventa "acca ti ti pi due punti barra barra", un
  percorso una filastrocca di cartelle, uno sha quaranta lettere a caso. Adesso
  sulla strada della voce gli indirizzi diventano "su GitHub", dei percorsi resta
  l'ultimo pezzo, e gli sha spariscono. Sullo schermo il testo resta intero.

### Se c'è Pocket-TTS acceso, Plancia lo usa

Misurato su questo Mac, in italiano, con il modello caricato: **111 millisecondi**
al primo audio contro i 42 secondi di Voicebox. Stessa macchina, stessa frase.

Non c'è niente da configurare: Plancia guarda se qualcuno risponde su
`127.0.0.1:8811` e se sì lo usa, altrimenti prova Voicebox, altrimenti la voce di
sistema. Per accenderlo:

```bash
python3 -m venv ~/.pocket-tts && ~/.pocket-tts/bin/pip install pocket-tts
~/.pocket-tts/bin/pocket-tts serve --port 8811 --language italian_24l
```

Il modello pesa 673 MB e si scarica da solo la prima volta. Clona da un wav come
Voicebox: basta metterne il percorso in `voce_campione` dentro
`~/.plancia/config.json`.

### La voce clonata ha una scadenza

Misurato sul tuo Mac: Voicebox mette **42 secondi** a sintetizzare anche una
frase corta. Vanno benissimo per il riepilogo della mattina, dove nessuno sta
aspettando davanti allo schermo. In una conversazione sono la fine della
conversazione.

Adesso, quando qualcuno sta aspettando di sentire, la voce clonata ha cinque
secondi: passati quelli parla la voce di sistema, che è istantanea. Il pannello
vocale non ci passa nemmeno, perché sintetizza da sé con la voce di sistema.

Vale la pena guardarlo: l'obiettivo di Codex che hai fermo sulla lavagna, "posso
usare le API di fish.audio s2.1pro", è esattamente questo problema.

### Le domande che non passano da un modello

Tre nuove famiglie di domande rispondono in meno di un millesimo di secondo,
leggendo il database e basta: **cosa c'è aperto sulla lavagna**, **come sono
andati i lanci**, **quanto ho speso oggi**. Prima costavano quasi tre secondi
ciascuna, ed è il tipo di cosa che si chiede dieci volte al giorno.

Insieme a quelle che c'erano già (quanti task, da dove riparto, cosa ho fatto
oggi e ieri, quanto ho lavorato questa settimana, come va con Codex, quanti
progetti, quanti post) sono le domande che a voce si fanno davvero. Funzionano in
italiano, inglese e spagnolo, e se la domanda non combacia con certezza si torna
al modello: meglio lento che sbagliato.

### La prima volta

macOS chiede microfono e dettatura. Se la finestra non compare, usa **"Attiva la
voce…"** nel menu di Plancia in alto a destra: quella la fa comparire davvero. La
richiesta partita dal pannello vocale spesso non mostra niente, perché quel
pannello è fatto apposta per non attivare l'app, e il sistema mostra quelle
finestre solo a un'app che sta davanti.

Finché non l'hai fatto il pannello resta comunque utile: scrivi nel campo in
fondo e ti risponde a voce.

Se ricompili spesso, `./tools/certificato.sh` ti fa un certificato di firma
stabile: senza, l'identità dell'app cambia a ogni compilazione e il consenso
viene chiesto di nuovo ogni volta. Chiede la password del Mac una volta; se il
portachiavi non lo prende, ti lascia il file sulla Scrivania con i quattro passi
per farlo a mano.

## Quanto costa ogni progetto

Ogni scheda di progetto dice quanti token ha generato negli ultimi trenta
giorni. Non sono euro: sono la cosa che finisce davvero, perché i limiti si
prendono lì.

In Oggi il numero grande dei token diventa ambra quando la giornata è sopra due
volte e mezzo la tua media di trenta giorni, e dice di quanto. Prima quel
segnale esisteva solo dentro una proposta, quindi lo vedevi solo se leggevi il
riepilogo fino in fondo.

## Da quale conversazione è uscito un commit

Un commit non dice mai da dove viene. Ma se alle 14:32 hai committato su un
repo, e fra le 14:05 e le 14:40 c'era aperta una sessione su quel progetto, è
quasi sempre quella. Plancia lo scrive, e nella scheda del progetto ogni commit
recente dice "da" con il titolo della conversazione.

Si accetta anche mezz'ora dopo la fine, perché si committa quando la sessione è
già chiusa. Se il progetto non basta, si prova con la cartella. Non è una prova,
è un indizio: serve a risalire dal commit alla conversazione senza cercare a
mano. Sul tuo archivio ne lega 36 su 97, e sono quelli in cui avevi Claude Code
aperto dentro il repo.

## Il registro degli eventi

`~/.plancia/eventi.jsonl`, una riga JSON per evento, schema `plancia.evento/1`,
solo in coda, ruota a 5 MB.

```json
{"schema":"plancia.evento/1","id":"9f2c…","ts":"2026-08-02T09:14:22Z",
 "tipo":"lavoro.completato","titolo":"Rilancia l'ablation","progetto":"atlas",
 "origine":"cantiere","dati":{"agente":"codex","modo":"esegui","token":22800}}
```

Serve a far sapere agli altri strumenti cosa è successo senza farli interrogare
il database. Chi legge tiene l'id dell'ultimo evento visto e chiede quello che è
venuto dopo:

```bash
plancia eventi --dopo <id>
```

Per gli agenti social il tipo che conta è `lavoro.completato`: da lì esce il
materiale vero per un post, con il progetto già attaccato.

## I venti tool MCP

Ai sedici di prima si aggiungono `plancia_lavagna`, `plancia_manda`,
`plancia_lanci`, `plancia_eventi`. Li vedono sia Claude Code sia Codex.

La skill `plancia` dice a Claude quando usarli, e una regola in particolare:
`plancia_manda` va in proposta se non gli hai detto tu di eseguire.

## Il sito e il prezzo

Il sito sta in `site/` e si pubblica da solo su GitHub Pages a ogni push:
**https://nerln.github.io/plancia/**

Il modello: sorgente completo e gratuito sotto GPL, build firmata a pagamento
(quanto vuoi, da 5 euro). È quello di Ardour e Krita. Quello che si paga è il
certificato Apple, la notarizzazione e la manutenzione, non il software.

Niente chiavi di licenza e niente attivazione: sotto GPL sarebbero una
restrizione ulteriore, vietata dal paragrafo 10. Chi compra può anche
ridistribuire il binario gratis, ed è parte del patto.

I numeri verificati stanno in [MONETIZZAZIONE.md](MONETIZZAZIONE.md), la
procedura in [RILASCIO.md](RILASCIO.md).

## Due bug che ti riguardavano

**Il riepilogo mostrava sempre l'attesa.** Il testo in cache veniva letto prima
di essere stato recuperato, quindi si dipingeva "preparo il riepilogo" e il testo
compariva solo al giro dopo. Adesso appare subito.

**L'interfaccia in inglese parlava italiano a metà**: le domande suggerite e le
proposte seguivano la lingua della configurazione invece di quella scelta con il
selettore.

## Il collaudo

```bash
python3 tools/prova.py
```

Quarantuno controlli in dieci secondi, su un archivio finto che non tocca il tuo.
Non è una suite completa: è la lista delle cose che si sono rotte almeno una
volta. Da far girare prima di ogni release.
