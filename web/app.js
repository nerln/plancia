/* Plancia, interfaccia. Nessun framework: fetch, template literal, delega eventi. */

const TOKEN = document.querySelector('meta[name=plancia-token]').content;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = { overview: null, view: null, filters: {}, sel: {}, compartimenti: null, compartimento: null };


/* ---------------------------------------------------------------- lingue */
const EN = {
  "lavoro con l'IA": 'work with AI',
  'Oggi': 'Today', 'Riepilogo': 'Recap', 'Progetti': 'Projects', 'Task': 'Tasks',
  'Social': 'Social', 'Sessioni': 'Sessions', 'Conoscenza': 'Knowledge', 'Capacità': 'Skills',
  'Tema': 'Theme', 'Aggiorna': 'Refresh', 'Briefing': 'Briefing',
  'Cerca in tutto il lavoro': 'Search everything',
  'Cerca sessioni, memorie, task, post, commit…': 'Search sessions, notes, tasks, posts, commits…',
  'progetti attivi': 'active projects', 'task aperti': 'open tasks', 'task aperto': 'open task',
  'sessioni 7 giorni': 'sessions, 7 days', 'commit 30 giorni': 'commits, 30 days',
  'post in coda': 'posts queued', 'post pubblicati': 'posts published',
  'token 30 giorni': 'tokens, 30 days', 'oggi': 'today', 'la media': 'the average',
  'token generati negli ultimi 30 giorni': 'tokens generated in the last 30 days', 'memorie': 'memory notes',
  'Ritmo di lavoro · 30 giorni': 'Work rhythm · 30 days',
  'sessioni': 'sessions', 'commit': 'commits',
  // 'Task aperti' come chiave del dizionario è sparita con lei (residuo dei
  // tester dell'ondata 2, punto 6, 16/09/2026): il pannello che la usava come
  // titolo è diventato 'Prossimi' da LOTTO-L2-VISTA, e il ramo morto del
  // listener che la citava nel commento (il vecchio "tutti i task" di Oggi,
  // sparito con L2-VISTA) è tolto insieme a lei - è l'unico rinomino o
  // rimozione di questo tipo che il lotto consente, perché quel markup non
  // esiste più da nessuna parte.
  'Progetti attivi': 'Active projects',
  'Attività recente': 'Recent activity', 'Social in coda': 'Social queue',
  'tutti': 'all', 'Aggiungi un task e premi invio': 'Add a task and press enter',
  'nessun progetto': 'no project', 'nessun task aperto': 'no open tasks',
  'nessun progetto attivo': 'no active project', 'niente da mostrare': 'nothing to show',
  'inizia': 'start', 'chiudi': 'close', 'riapri': 'reopen',
  'Nuovo task': 'New task', 'Aggiungi': 'Add', 'alta': 'high', 'media': 'medium', 'bassa': 'low',
  'aperto': 'open', 'in corso': 'in progress', 'bloccato': 'blocked', 'fatto': 'done',
  'archiviato': 'archived', 'aperti': 'open',
  'attivo': 'active', 'in pausa': 'paused', 'concluso': 'finished', 'idea': 'idea',
  'idee': 'ideas', 'bozza': 'draft', 'bozze': 'drafts', 'approvato': 'approved',
  'approvati': 'approved', 'programmato': 'scheduled', 'programmati': 'scheduled',
  'pubblicato': 'published', 'pubblicati': 'published', 'scartato': 'dropped',
  'Idee': 'Ideas', 'Bozze': 'Drafts', 'Approvati': 'Approved',
  'Programmati': 'Scheduled', 'Pubblicati': 'Published',
  'ogni post è legato al lavoro che lo ha prodotto': 'every post traces back to real work',
  'Nuova bozza': 'New draft', 'Il testo del post': 'The post text',
  'fonte: commit, repo, sessione': 'source: commit, repo, session',
  'Salva bozza': 'Save draft', 'fonte': 'source', 'apri': 'open', 'vuoto': 'empty',
  // LOTTO-L2-VISTA, punto 2: la riga di Prossimi senza task né next_action
  // dice "niente in coda", non "vuoto" (docs/CONSIGLIO-2026-09-16-verdetto.md
  // riga 56: "altrimenti 'niente in coda' e la riga va in fondo").
  'niente in coda': 'nothing queued',
  // Il motore che ha scritto il riepilogo: "modello" vuol dire il testo a
  // modelli, senza chiamare nessun modello linguistico.
  'modello': 'template', 'cache': 'cache',
  'conversazioni con Claude Code': 'conversations with Claude Code',
  'cerca nel primo messaggio…': 'search the opening message…',
  'tutti i progetti': 'all projects', 'quando': 'when', 'di cosa': 'about',
  'progetto': 'project', 'tool': 'tools', 'riprendi': 'resume',
  'nessuna sessione': 'no sessions', 'senza titolo': 'untitled',
  'dedotta dai percorsi': 'inferred from paths',
  'progetto dedotto dai file che la sessione ha toccato, non dalla cartella di apertura':
    'project inferred from the files the session touched, not from the folder it was opened in',
  'memorie indicizzate da Claude': 'memory notes indexed by Claude',
  'cosa sa fare il tuo Claude Code': 'what your Claude Code can do',
  'Skill': 'Skills', 'Plugin': 'Plugins', 'Routine programmate': 'Scheduled routines',
  'Chi sei': 'About you', 'Come lavorare': 'How to work', 'Riferimenti': 'References',
  'Progetti': 'Projects', 'Altro': 'Other',
  'quello che ogni nuova sessione di Claude riceve': 'what every new Claude session receives',
  'Copia': 'Copy', 'Governo': 'Control', 'prossimo passo concreto': 'concrete next step',
  'Salva': 'Save', 'nessuno': 'none', 'Memoria': 'Memory', 'Repository': 'Repositories',
  'Commit recenti': 'Recent commits', 'da': 'from', 'Post': 'Posts', 'Cronologia': 'History',
  'priorità': 'priority', 'attivo ': 'active ', 'modifiche': 'changes',
  'la tua giornata, raccontata come la diresti a voce': 'your day, told the way you would say it',
  'Rigenera': 'Regenerate', 'Ascolta': 'Listen', 'Ferma': 'Stop', 'Chiedi': 'Ask',
  'in ascolto': 'playing', 'voce': 'voice',
  'preparo il riepilogo, ci vogliono pochi secondi…': 'building the recap, a few seconds…',
  'preparo il riepilogo…': 'building the recap…',
  'Chiedi qualcosa sul tuo lavoro': 'Ask something about your work',
  'carico…': 'loading…', 'errore: ': 'error: ', 'niente': 'nothing',
  'task aggiunto': 'task added', 'task chiuso': 'task closed', 'bozza salvata': 'draft saved',
  'progetto aggiornato': 'project updated', 'comando copiato': 'command copied',
  'briefing copiato': 'briefing copied', 'riepilogo aggiornato': 'recap updated',
  'aggiornamento avviato': 'refresh started', 'audio non pronto': 'audio not ready',
  'aggiornamento già in corso': 'refresh already running',
  'non riesco a riprodurre': 'cannot play the audio', 'tema: ': 'theme: ',
  'aggiornato ': 'updated ', 'aggiorno': 'refreshing',
  'server non raggiungibile': 'server unreachable', 'tracciati': 'tracked',
  'in elenco': 'listed', 'nessuna descrizione': 'no description',
  'adesso': 'just now', 'ieri': 'yesterday', 'mai': 'never',
  ' min fa': ' min ago', ' ore fa': ' hours ago', ' giorni fa': ' days ago',
  ' mesi fa': ' months ago', 'un mese fa': 'a month ago',
  'Cosa dovrei riprendere adesso?': 'What should I pick up now?',
  'pipeline': 'pipeline', 'sessione': 'session', 'hook': 'hook', 'memoria': 'note',
  'task': 'task', 'post': 'post', 'nota': 'note', 'agente': 'agent',
  'in ritardo': 'overdue', 'da': 'by', 'pubblicati': 'published',
  'sessioni con scambi': 'sessions with handoffs', 'riprese': 'resumes',
  'Codex e Claude si sono parlati': 'Codex and Claude talked', 'decisione': 'decision',
  'milestone': 'milestone', 'problema': 'problem', 'infra': 'infra',
  'ricerca': 'research', 'personale': 'personal', 'metodo': 'method',
  'sessione aperta': 'session opened', 'sessione chiusa': 'session closed',
  'Agenti': 'Agents', 'scambio': 'handoff', 'scambi': 'handoffs',
  'Archivio': 'Archive', 'turni': 'turns',
  'Cerca': 'Search', 'riga': 'line', 'tu': 'you',
  'dentro quello che è stato detto, non solo nei titoli':
    'inside what was actually said, not just the titles',
  'una frase, un nome di file, un numero…': 'a phrase, a file name, a number…',
  'Scrivi qualcosa che ricordi di aver detto, o letto.':
    'Type something you remember saying, or reading.',
  'nessun turno contiene quelle parole': 'no turn contains those words',
  // 'Lavagna' e' la chiave data-t del menu (web/index.html, non di questo
  // lotto): il testo che mostra cambia qui e in IT_TESTI (sotto), non la
  // chiave. Vedi LOTTO-L2-VISTA.md punto 5: "Lavagna" diventa "Tutti i task".
  'Lavagna': 'All tasks', 'Guida': 'Guide', 'tutti': 'all', 'tutte': 'all', 'dettaglio': 'detail', 'esito': 'outcome',
  'fonte': 'source',
  // LOTTO-L3-RITOCCO punto 1/2: "manda"/"dispatch" e "proposta"/"esegui"
  // ("plan only"/"do it") non sono più testo visibile da nessuna parte (il
  // bottone di riga ora dice T('Riprendi'), e "Lanci recenti"/il drawer del
  // lancio usano Tmodo() sotto, non più T(r.modo) diretto sulle chiavi
  // interne del backend) - le tre chiavi spariscono dal dizionario invece di
  // restare morte.
  'Come lo voglio fatto': 'How I want it done',
  'guarda e propone, non tocca niente': 'reads and plans, touches nothing',
  'può modificare i file del progetto': 'can modify the project files',
  'In lavorazione': 'Running', 'Lanci recenti': 'Recent runs',
  'riuscito': 'done', 'fallito': 'failed', bloccato: 'blocked', 'in coda': 'queued', 'annullato': 'cancelled',
  'Cosa converrebbe fare': 'What is worth doing',
  // LOTTO-L3-RIPRENDI-UI: il pulsante Riprendi coi suoi tre stati (drawer del
  // task, dove prima c'era il vecchio compositore per mandare a un agente -
  // quel titolo e "fallo" spariscono dai testi, vedi apriRiprendi/
  // bottoneRiprendi più sotto) e il modulo "In background" che lo sostituisce.
  // Le chiavi con
  // un segnaposto (viva/chiusa/persa, {cwd}/{data}/{motivo}) stanno anche in
  // IT_TESTI perché l'ordine delle parole intorno al segnaposto cambia da
  // una lingua all'altra, come 'dopo_conta' di LOTTO-L2-VISTA.
  'Riprendi': 'Resume', 'Rilancia': 'Relaunch', 'Apri': 'Open',
  'aggiorno': 'Checking…',
  'in_background': 'In the background',
  'riprendi_viva': 'Open in the app, {cwd}',
  'riprendi_chiusa': 'Resume in Claude Code, session from {data}',
  'riprendi_chiusa_codex': 'Resume in Codex, session from {data}',
  'riprendi_persa': 'Start from scratch: {motivo}',
  'riprendi_avviato': 'Started',
  // Il piano di "In background", detto PRIMA di partire (plancia/riprendi.py,
  // piano()): riprende la sessione originale, ne fa una copia, ne apre una
  // nuova, oppure non tocca niente. Il testo lo compone pianoTesto() da modo e
  // motivo (non dall'avviso italiano del server), cosi' segue la lingua scelta.
  'piano_riprendi': 'Resumes the original session ({sid}) in its own folder: the work continues there, not in a new session.',
  'piano_copia': 'Session {sid} is open elsewhere: a COPY with the same history starts, and the open one receives nothing.',
  'piano_nuova': 'There is no session to resume ({motivo}): a NEW session starts, with the context written by hand.',
  'piano_niente': 'Session {sid} is open: I will not touch it from here. Paste the message straight into it.',
  'piano_niente_codex': 'Session {sid} looks open ({motivo}): I will not touch it from here. Paste the message straight into it.',
  'piano_da_zero': 'A new session starts: there is no session to resume.',
  'copia_sessione': 'work on a copy of the session (the open one is not touched)',
  'continua_riprendi': 'in the original session', 'continua_copia': 'on a copy of the session',
  'continua_nuova': 'in a NEW session',
  'non partito': 'not started',
  'copia il messaggio qui sotto': 'copy the message below by hand',
  'non sono riuscito a lanciarlo': 'could not launch it',
  'modo_proposta': 'read only', 'modo_esegui': 'can edit files',
  'sync disattivato per questa sessione (--no-sync)': 'sync disabled for this session (--no-sync)',
  'copiato: incollalo nella sessione': 'copied: paste it into the session',
  'progetti_n': '{n} projects', 'progetti_1': '1 project',
  'niente in sospeso': 'nothing pending', 'nessun task aperto da nessuna parte': 'no open task anywhere',
  'Il lavoro': 'The work', 'annulla': 'cancel', 'apri il registro': 'open the log',
  'lanci': 'runs', 'avviato in background': 'started in the background',
  "tutto quello che è già successo": 'everything that already happened',
  'i due agenti sullo stesso archivio': 'both agents, one archive',
  'sessioni tue': 'your turns', 'token generati': 'tokens out',
  'chiamate a tool': 'tool calls', 'primo lavoro': 'first seen',
  'ultimo lavoro': 'last seen', 'Chi ha lavorato su cosa': 'Who worked on what',
  'Quando si sono parlati': 'When they talked to each other',
  'nessuno scambio registrato': 'no handoff recorded',
  'Codex non è collegato': 'Codex is not connected',
  'tool condivisi': 'shared tools', 'oggi': 'today',
  'sessioni oggi': 'sessions today', 'commit oggi': 'commits today',
  'Ritmo · 30 giorni': 'Rhythm · 30 days',
  'sopra la linea le sessioni, sotto i commit': 'sessions above the line, commits below',
  // la mappa della memoria
  'Memoria': 'Memory',
  'che forma ha quello che Claude si ricorda di te': 'the shape of what Claude remembers about you',
  'fatti': 'facts', 'di cui': 'of which',
  "che il richiamo può andare a prendere da un'altra cartella":
    'that recall can fetch from another folder',
  'tutte': 'all', 'preferenze': 'preferences', 'chi sei': 'who you are',
  'riferimenti': 'references', 'progetti': 'projects',
  'in due cartelle': 'in two folders', 'senza legami': 'unlinked',
  'link rotti': 'broken links', 'quasi vuote': 'nearly empty',
  'niente da sistemare': 'nothing to fix',
  'pieno vuol dire che il richiamo può portarla in contesto':
    'filled means recall can bring it into context',
  'Cosa ti direbbe': 'What it would tell you',
  'scrivi una frase e guarda cosa ti richiamerebbe':
    'type a phrase and see what it would recall',
  'Prova': 'Try', 'una frase qualsiasi, come la scriveresti a Claude':
    'any phrase, the way you would write it to Claude',
  'va in contesto': 'goes into context', 'scartate': 'discarded',
  'niente sopra la soglia, e va bene così': 'nothing above threshold, and that is fine',
  'troppo corta per dire di cosa parla': 'too short to say what it is about',
  'nessuna memoria': 'no memory notes', 'grado': 'degree',
  'Da sistemare': 'To fix', 'soglia': 'threshold', 'da scrivere': 'still to write',
  'le citi in altre memorie ma non le hai mai scritte':
    'you cite them in other notes but never wrote them',
  'i legami sono i doppi quadri che hai scritto a mano: due memorie sullo stesso argomento senza un legame, qui sembrano estranee':
    'the links are the double brackets you wrote by hand: two notes on the same topic without one look unrelated here',

  // LOTTO-L2-VISTA: pannello Prossimi (Oggi), albero dei Progetti, cassetto
  // Dopo (drawer) e "Tutti i task" (ex Lavagna). Le chiavi sono quelle
  // concordate con L2-GLASS in LOTTO-L2-VISTA.md; il loro testo italiano
  // non è la chiave stessa (a differenza del resto di questo dizionario) e
  // si legge da IT_TESTI, poco sotto: qui c'è solo l'inglese.
  'prossimi': 'Next up', 'prossimi_altri': 'Show {n} more',
  'prossimi_vuoto': 'Nothing coming up', 'area_senza': 'No area',
  'cartelle_viste': 'Folders seen', 'tutti_i_task': 'All tasks',
  'tutti_i_task_nota': 'Plancia, Claude Code and Codex',
  'dopo': 'After', 'dopo_conta': 'After ({n})', 'next_action': 'next step',

  // LOTTO-L4-MEMORIA punto 4: la spia in topbar. Segue la stessa convenzione
  // di 'prossimi'/'dopo_conta' qui sopra (chiave breve, non l'italiano) per
  // lo stesso motivo: portano un segnaposto ({ora}) il cui posto nella frase
  // cambia da una lingua all'altra.
  'spia_titolo': 'data status',
  'spia_aggiornato': 'updated at {ora}',
  'spia_memoria': 'server unreachable, data from {ora}',
  'spia_aggiorno': 'updating…',
  // E1-PLANCIA: il selettore di compartimento in alto.
  'compartimento_etichetta': 'Compartment',
  'compartimento_predefinito': 'Default',

  // Seconda passata del design (Plancia 2.0 per Mac): le stringhe delle viste nuove.
  'Leggi': 'Read aloud',
  'Proposte': 'Suggestions',
  'Tutte le fonti': 'All sources',
  'Aperti': 'Open',
  'Fatti': 'Done',
  'Tutti': 'All',
  'Stato': 'Status',
  'Fonte': 'Source',
  'Titolo': 'Title',
  'Progetto': 'Project',
  'Scadenza': 'Due',
  'Aggiornato': 'Updated',
  'Scegli un task': 'Pick a task',
  'Scegli un post': 'Pick a post',
  'Scegli una memoria': 'Pick a note',
  'Indietro': 'Back',
  'Fatto': 'Done',
  'Apri progetto': 'Open project',
  'Mostra': 'Show',
  'Tipo': 'Type',
  'Attivo': 'Active',
  'Prossima azione': 'Next action',
  'Aggiorna prossima azione': 'Update next action',
  'nessun post': 'no posts',
  'Piattaforma': 'Platform',
  'Immagine': 'Image',
  'Programmato': 'Scheduled',
  'Pubblicato': 'Published',
  'Aggiungi indirizzo': 'Add link',
  'Elenco': 'List',
  'Grafo': 'Graph',
  'Vista': 'View',
  'Livello': 'Level',
  'Livello 1': 'Level 1',
  'Livello 2': 'Level 2',
  'Tutto': 'All',
  'Ingrandisci': 'Zoom in',
  'Riduci': 'Zoom out',
  'Adatta': 'Fit',
  'Grafo della memoria': 'Memory graph',
  'Prova la memoria': 'Test the memory',
  'Aggiornata': 'Updated',
  'Cartella': 'Folder',
  'Usata in': 'Used in',
  'il richiamo può portarla in contesto': 'recall can bring it into context',
  'nessuno, troppo corta': 'none, too short',
  'Legami': 'Links',
  'Nessun legame.': 'No links.',
  'link rotto': 'broken link',
  'Mostra nel grafo': 'Show in graph',
  'Nessun testo oltre alla descrizione.': 'No text beyond the description.',
  'Registro': 'Log',
  'Ambito': 'Scope',
  'Ricerca': 'Search',
  'cerco…': 'searching…',
  'Nessun risultato': 'No results',
  'Aspetto': 'Appearance',
  'Sistema': 'System',
  'Chiaro': 'Light',
  'Scuro': 'Dark',
  'Lingua': 'Language',
  'Dimensione del testo': 'Text size',
  'Guida di Plancia': 'Plancia guide',
  'Impostazioni': 'Settings',
  'Lanci': 'Runs',
  'appuntato': 'pinned',
  'post_n': '{n} posts', 'fatti_n': '{n} notes',
};

// Il testo italiano delle chiavi qui sopra che non sono già, loro stesse, la
// frase italiana da mostrare (il resto del dizionario segue quella
// convenzione: la chiave passata a T() è l'italiano; qui invece la chiave è
// un nome breve concordato con L2-GLASS, vedi LOTTO-L2-VISTA.md, perché
// alcune di queste frasi portano un "{n}" da sostituire dopo, e l'ordine
// delle parole intorno al numero cambia da una lingua all'altra: "altri {n}"
// in italiano, "{n} more" in inglese. 'Lavagna' non è una chiave nuova: è
// l'esistente data-t del menu, il cui testo cambia qui (punto 5 del lotto),
// non il nome). T() qui sotto guarda prima questa tabella, poi EN, poi la
// chiave stessa: così il resto del file, che già passa la frase italiana a
// T(), continua a funzionare senza cambiare una riga.
const IT_TESTI = {
  'Lavagna': 'Tutti i task',
  'prossimi': 'Prossimi', 'prossimi_altri': 'Mostra altri {n}',
  'prossimi_vuoto': 'Niente in arrivo', 'area_senza': 'Senza area',
  'cartelle_viste': 'cartelle viste', 'tutti_i_task': 'Tutti i task',
  'tutti_i_task_nota': 'Plancia, Claude Code e Codex',
  'dopo': 'Dopo', 'dopo_conta': 'Dopo ({n})',
  'next_action': 'prossimo passo',

  // LOTTO-L3-RIPRENDI-UI: vedi il commento in EN, poco più sopra.
  'aggiorno': 'Verifico…',
  'in_background': 'In background',
  'riprendi_viva': 'Aperta nell’app, {cwd}',
  'riprendi_chiusa': 'Riprendi in Claude Code, sessione del {data}',
  'riprendi_chiusa_codex': 'Riprendi in Codex, sessione del {data}',
  'riprendi_persa': 'Avvia da capo: {motivo}',
  'riprendi_avviato': 'Avviato',
  'piano_riprendi': 'Riprende la sessione originale ({sid}) nella sua cartella: il lavoro continua lì, non in una sessione nuova.',
  'piano_copia': 'La sessione {sid} è aperta altrove: parte una COPIA con la stessa storia, e quella aperta non riceve niente.',
  'piano_nuova': 'Non c’è una sessione da riprendere ({motivo}): parte una sessione NUOVA, con il contesto scritto a mano.',
  'piano_niente': 'La sessione {sid} è aperta: da qui non la tocco. Incolla il messaggio direttamente lì.',
  'piano_niente_codex': 'La sessione {sid} sembra aperta ({motivo}): da qui non la tocco. Incolla il messaggio direttamente lì.',
  'piano_da_zero': 'Parte una sessione nuova: non c’è una sessione da riprendere.',
  'copia_sessione': 'lavora su una copia della sessione (quella aperta non si tocca)',
  'continua_riprendi': 'nella sessione originale', 'continua_copia': 'su una copia della sessione',
  'continua_nuova': 'in una sessione NUOVA',
  'non partito': 'non partito',
  'copia il messaggio qui sotto': 'copia a mano il messaggio qui sotto',
  'progetti_n': '{n} progetti',
  'modo_proposta': 'solo lettura', 'modo_esegui': 'può modificare i file',
  'progetti_1': '1 progetto',

  // LOTTO-L4-MEMORIA punto 4: vedi il commento in EN, poco più sopra.
  'spia_titolo': 'stato dei dati',
  'spia_aggiornato': 'aggiornato alle {ora}',
  'spia_memoria': 'server non raggiungibile, dati delle {ora}',
  'spia_aggiorno': 'aggiorno…',

  // E1-PLANCIA: il selettore di compartimento in alto (vedi conCompartimento).
  'compartimento_etichetta': 'Compartimento',
  'compartimento_predefinito': 'Predefinito',
  'post_n': '{n} post', 'fatti_n': '{n} fatti',
};

// Gli eventi li scrive Plancia stessa, quindi si possono tradurre a vista.
const PREFISSI = [
  ['memoria aggiornata: ', 'note updated: '], ['task creato: ', 'task created: '],
  ['task chiuso: ', 'task closed: '], ['post bozza: ', 'post draft: '],
  ['post idea: ', 'post idea: '], ['pubblicato su ', 'published on '],
  ['sessione: ', 'session: '],
];
function Tev(titolo) {
  if (UILANG !== 'en' || !titolo) return titolo || '';
  if (EN[titolo]) return EN[titolo];
  for (const [it, en] of PREFISSI) {
    if (titolo.startsWith(it)) return en + titolo.slice(it.length);
  }
  return titolo;
}

// Il "motivo" di /api/riprendi/<id> lo scrive plancia/riprendi.py, che questo
// lotto non tocca (regola del lotto): è italiano fisso, un piccolo insieme di
// frasi finite (vedi il docstring di quel modulo). Stessa idea di Tev() per i
// titoli degli eventi: si prova a tradurre i pezzi statici, e quello che
// resta dinamico (un cwd, un nome host) passa intatto.
const MOTIVI_PREFISSI = [
  ["mai registrata", "never recorded"],
  ["sessione scaduta", "session expired"],
  ["aperta in un'altra sessione", "open in another session"],
  ["aperta in ", "open in "],
  ["creato su ", "created on "],
  ["non sono riuscito a interrogare le sessioni aperte", "could not check open sessions"],
  ["il rollout è stato modificato negli ultimi 10 minuti",
    "the rollout was touched in the last 10 minutes"],
  ["la trascrizione c'è, ma il rollout è fermo da più di 10 minuti",
    "the transcript exists, but the rollout has been idle for over 10 minutes"],
  ["la trascrizione c'è, ma la sessione non risulta più aperta",
    "the transcript exists, but the session no longer looks open"],
  ["la cartella della sessione non c'è più", "the session's folder no longer exists"],
  ["della sessione non si sa la cartella", "the session's folder is unknown"],
  ["il rollout è stato toccato da un lancio di Plancia appena finito",
    "the rollout was touched by a Plancia run that just finished"],
  // L3-RIPRENDI-UI-4 (obbligatoria del critico): `apri()` (plancia/riprendi.py)
  // mette in `errore` un'altra frase italiana fissa, diversa da `motivo` ma
  // con lo stesso schema a prefisso: il toast la incollava intatta dopo un
  // prefisso inglese ("could not launch it: il lanciatore non ha risposto
  // entro 0.3s"). Tmot() traduce qualunque prefisso conosciuto, non solo
  // quelli di `motivo`, quindi basta aggiungerlo qui.
  ["il lanciatore non ha risposto entro ", "the launcher did not respond within "],
];
function Tmot(motivo) {
  if (UILANG !== 'en' || !motivo) return motivo || '';
  for (const [it, en] of MOTIVI_PREFISSI) {
    if (motivo === it) return en;
    if (motivo.startsWith(it)) return en + motivo.slice(it.length);
  }
  return motivo;
}
// LOTTO-L3-RITOCCO punto 2: "Lanci recenti" e il drawer del lancio
// mostravano T(r.modo)/T(d.modo) con le chiavi interne del backend
// ("proposta"/"esegui", runs.modo) passate dritte a T() - il verdetto le
// vuole fuori dai testi. Le stesse parole dell'interruttore "può modificare
// i file del progetto" del modulo In background (punto 2 di
// LOTTO-L3-RIPRENDI-UI): "solo lettura" quando non scrive, "può modificare i
// file" quando scrive. `r.modo`/`d.modo` restano "proposta"/"esegui" nel
// backend (runs.modo, la colonna del db): questa è solo la lettura.
// Consigliata del critico (L3-RIPRENDI-UI-4): qualunque valore diverso da
// 'esegui' (compreso null/undefined, o un modo futuro non ancora previsto)
// cade su 'solo lettura' - va bene per runs.modo di oggi (che è sempre
// l'uno o l'altro), ma un run il cui modo non si conoscesse per davvero
// mostrerebbe comunque "solo lettura", non un terzo stato "non so".
const Tmodo = (modo) => T(modo === 'esegui' ? 'modo_esegui' : 'modo_proposta');

/* LOTTO-L4-MEMORIA: localStorage può mancare (navigazione privata più severa
   di certi browser) o essere disabilitato per davvero (il tester del lotto
   lo prova con un oggetto che lancia su ogni accesso) - ogni lettura o
   scrittura, non solo quella della memoria delle viste (poco più sotto),
   passa da qui. Prima di questo lotto UILANG e il tema leggevano
   localStorage senza guardia: un localStorage che lancia già al primo
   getItem fermava l'intero script prima ancora che iniziasse a disegnare,
   che è esattamente la schermata morta che questo lotto vuole togliere di
   mezzo, non solo quando il vuoto viene dal server. */
function storageGet(chiave) { try { return localStorage.getItem(chiave); } catch (e) { return null; } }
function storageSet(chiave, valore) { try { localStorage.setItem(chiave, valore); } catch (e) { /* pazienza */ } }

const UIPARAM = new URLSearchParams(location.search).get('ui');
let UILANG = UIPARAM || storageGet('plancia-ui') ||
  (navigator.language.startsWith('it') ? 'it' : 'en');
if (UIPARAM) storageSet('plancia-ui', UIPARAM);
const T = (s) => {
  const it = IT_TESTI[s] !== undefined ? IT_TESTI[s] : s;
  return (UILANG === 'en' && EN[s] !== undefined) ? EN[s] : it;
};
// Un T() con un numero da sostituire dopo (LOTTO-L2-VISTA: "altri {n}",
// "Dopo ({n})"): la sostituzione è qui e non dentro T() perché non tutte le
// chiavi la usano, e T() resta quello che il resto del file già chiama.
const conN = (chiave, n) => T(chiave).replace('{n}', n);
// Un T() con più di un segnaposto ({cwd}, {data}, {motivo}...): usato dal
// pulsante Riprendi (LOTTO-L3-RIPRENDI-UI), che ne porta più di uno secondo
// lo stato. `vals` è un oggetto {nomeSegnaposto: valore}.
const fmt = (chiave, vals) => Object.entries(vals).reduce(
  (s, [k, v]) => s.replace('{' + k + '}', () => v), T(chiave));
/* Il piano di un lavoro in background (modo, stato, motivo, origine da
   plancia/riprendi.py piano()) come frase nella lingua della pagina, da
   incollare in innerHTML: i valori dinamici sono gia' scappati. */
function pianoTesto(p) {
  if (!p || !p.modo) return '';
  const chiave = (p.modo === 'niente' && p.agent === 'codex') ? 'piano_niente_codex' : 'piano_' + p.modo;
  return fmt(chiave, { sid: esc((p.origine || '').slice(0, 8)), motivo: esc(Tmot(p.motivo || '')) });
}
// "1 progetto"/"1 project" ha una forma singolare diversa dal template con
// {n} (LOTTO-L3-RIPRENDI-UI punto 3 dei residui): il plurale resta conN.
// LOTTO-L3-RITOCCO punto 3: prima la scelta it/en era scritta a mano qui
// dentro, invece di passare da T()/IT_TESTI/EN come ogni altra stringa del
// dizionario - la chiave 'progetti_1' la porta lì, dove la prova front la
// controlla insieme a tutte le altre.
const progettiN = (n) => n === 1 ? T('progetti_1') : conN('progetti_n', n);
const LOC = () => (UILANG === 'en' ? 'en-GB' : 'it-IT');

function traduciShell() {
  $$('[data-t]').forEach((el) => {
    const chiave = el.dataset.t;
    if (el.tagName === 'INPUT') el.placeholder = T(chiave);
    else if (el.firstChild && el.firstChild.nodeType === 3) el.firstChild.nodeValue = T(chiave);
  });
  const sync = $('#btn-sync'), imp = $('#btn-imp');
  if (sync) { sync.title = T('Aggiorna'); sync.setAttribute('aria-label', T('Aggiorna')); }
  if (imp) { imp.title = T('Impostazioni'); imp.setAttribute('aria-label', T('Impostazioni')); }
  document.documentElement.lang = UILANG;
}

/* ---------------------------------------------------------------- utilità */
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function ago(ts) {
  if (!ts) return T('mai');
  const t = new Date(ts.length <= 10 ? ts + 'T12:00:00Z' : ts);
  if (isNaN(t)) return ts.slice(0, 10);
  const s = (Date.now() - t.getTime()) / 1000;
  if (s < 60) return T('adesso');
  if (s < 3600) return Math.floor(s / 60) + T(' min fa');
  if (s < 86400) return Math.floor(s / 3600) + T(' ore fa');
  const d = Math.floor(s / 86400);
  if (d === 1) return T('ieri');
  if (d < 30) return d + T(' giorni fa');
  const m = Math.floor(d / 30);
  if (d < 365) return m === 1 ? T('un mese fa') : m + T(' mesi fa');
  return t.toLocaleDateString(LOC());
}
const dateIt = (ts) => ts ? new Date(ts).toLocaleDateString(LOC(),
  { day: '2-digit', month: 'short', year: 'numeric' }) : '';
const num = (n) => (n ?? 0).toLocaleString(LOC());
// Di una cartella interessa il nome, non la strada per arrivarci: dentro il
// Drive un percorso completo occupa una riga intera per dire "Voicebox-Fish".
const cartellaCorta = (p) => {
  if (!p) return '';
  const pezzi = String(p).replace(/\/+$/, '').split('/');
  return pezzi[pezzi.length - 1] || p;
};

const kilo = (n) => n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1000 ? Math.round(n / 1000) + 'k' : String(n ?? 0);

function toast(msg, bad, ms) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast' + (bad ? ' bad' : '');
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, ms || 2600);
}

// LOTTO-L4-MEMORIA (correzione del critico, punto "la spia"): route() deve
// sapere se durante il disegno di una vista è PARTITA una richiesta di rete
// o no - lo scopre confrontando questo contatore prima e dopo. Serve perché
// alcune viste (views.progetti, views.benvenuto) riusano state.overview se
// c'è già, senza richiamare l'API: in quel caso quello che si vede a
// schermo non è stato preso ora, è la stessa istantanea di prima.
let apiChiamateOk = 0;

/* Compartimenti (E1-PLANCIA): con dei compartimenti nominati in config.json la
   dashboard, che e' la vista di una persona e non di un agente, mostra tutto ma
   SEPARATO: un compartimento alla volta, scelto dal selettore in alto (di
   default il predefinito). Ogni chiamata all'API porta `?compartimento=`, cosi'
   il server filtra le letture e assegna al compartimento quello che nasce qui.
   Senza compartimenti (`/api/compartimenti` dice `attivo: false`) non si
   aggiunge niente e non compare nessun selettore. */
function conCompartimento(path) {
  const c = state.compartimenti;
  if (!c || !c.attivo || !path.startsWith('/api/') || path.startsWith('/api/compartimenti')) return path;
  if (/[?&]compartimento=/.test(path)) return path;
  return path + (path.includes('?') ? '&' : '?')
    + 'compartimento=' + encodeURIComponent(state.compartimento || c.predefinito);
}

async function api(path, opts = {}) {
  path = conCompartimento(path);
  const res = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', 'X-Plancia-Token': TOKEN, ...(opts.headers || {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const ctype = res.headers.get('content-type') || '';
  const data = ctype.includes('json') ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.errore) || res.statusText);
  apiChiamateOk++;
  return data;
}

function md(src) {
  let out = esc(src || '');
  const blocks = [];
  out = out.replace(/```(\w*)\n([\s\S]*?)```/g, (_, l, code) =>
    `@@B${blocks.push(`<pre><code>${code.replace(/\n$/, '')}</code></pre>`) - 1}@@`);
  out = out
    .replace(/^#{3,6} (.*)$/gm, '<h3>$1</h3>')
    .replace(/^## (.*)$/gm, '<h2>$1</h2>')
    .replace(/^# (.*)$/gm, '<h1>$1</h1>')
    .replace(/^&gt; (.*)$/gm, '<blockquote>$1</blockquote>')
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[\[([^\]]+)\]\]/g, '<span class="wl" data-memory="$1">$1</span>')
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/^[-*] (.*)$/gm, '<li>$1</li>')
    .replace(/(<li>[\s\S]*?<\/li>)(?!\s*<li>)/g, '<ul>$1</ul>');
  out = out.split(/\n{2,}/).map((p) =>
    /^\s*(<(h\d|ul|ol|pre|blockquote)|@@B)/.test(p) ? p : `<p>${p.replace(/\n/g, '<br>')}</p>`
  ).join('\n');
  return out.replace(/@@B(\d+)@@/g, (_, i) => blocks[+i]);
}

const prioTag = (p) => T(['', 'alta', 'media', 'bassa'][p] || 'media');
const statusClass = {
  attivo: 'ok', 'in pausa': 'warn', concluso: '', idea: 'info',
  aperto: '', 'in corso': 'accent', bloccato: 'danger', fatto: 'ok', archiviato: '',
  bozza: '', approvato: 'info', programmato: 'warn', pubblicato: 'ok', scartato: '',
};

/* ---------------------------------------------------------------- viste */
const views = {};
const DETTAGLI = {};

/* ---------------------------------------------------------------- oggi */
/* Una colonna di lettura, larga quanto una riga di testo e non di piu': il
   riepilogo della giornata, i prossimi passi per progetto, le proposte. Non
   si allarga con la finestra e non porta riquadri dentro riquadri. */
const CHEV = '<svg class="chev" viewBox="0 0 8 12" aria-hidden="true"><path d="M1.5 1.5L6.5 6l-5 4.5"/></svg>';
const CHEV_GIU = '<svg class="chev" viewBox="0 0 12 8" width="10" height="7" aria-hidden="true"><path d="M1.5 1.5L6 6.5l4.5-5"/></svg>';

const isoOggi = () => {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
};
const scaduta = (iso) => !!iso && String(iso).slice(0, 10) < isoOggi();
const dataBreve = (iso) => iso
  ? new Date(String(iso).slice(0, 10) + 'T12:00:00').toLocaleDateString(LOC(), { day: 'numeric', month: 'short' }).replace(/\.$/, '')
  : '';
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : '');

views.oggi = async () => {
  const d = state.overview = await api('/api/overview?lang=' + UILANG);
  state.overviewQuando = new Date(); // vedi spiaAggiorna in route(): l'ora dei DATI, non del disegno
  const riepilogo = await bloccoRiepilogo();
  // Prossimi si aspetta qui, prima di restituire la vista: una vista che torna
  // con un segnaposto "carico..." per un solo pezzo e' quello che il collaudo a
  // video vede come rosso. Se l'API non risponde `prossimi` resta null e
  // panelloProssimi dice 'prossimi_vuoto' invece di rompere il resto.
  let prossimi = null;
  try { prossimi = await api('/api/prossimi'); } catch (e) { /* prossimi_vuoto sotto */ }
  const proposte = d.proposte || [];

  return `
  <div class="lettura">
    ${riepilogo}
    <section class="sez"><h2>${T('prossimi')}</h2>${panelloProssimi(prossimi)}</section>
    ${proposte.length ? `<section class="sez"><h2>${T('Proposte')}</h2>
      <div class="gruppo">${proposte.map(rigaProposta).join('')}</div></section>` : ''}
    <section class="sez"><h2>${T('Chiedi')}</h2>
      <form data-form="chiedi" class="chiedi-form">
        <input type="text" name="domanda" placeholder="${T('Chiedi qualcosa sul tuo lavoro')}" autocomplete="off">
        <button class="primary" type="submit">${T('Chiedi')}</button>
      </form>
      <div id="qa-bolle">${(state.recap.qa || []).map((b) =>
        `<div class="bolla ${b.mia ? 'mia' : 'sua'}">${esc(b.testo)}</div>`).join('')}</div>
    </section>
  </div>`;
};

/* Una proposta e un solo pulsante. "Riprendi" su una proposta "manda" apre il
   cassetto (con o senza task, come apriRiprendi gia' sa fare): il lancio parte
   solo dal click su "In background" li' dentro, mai da questo pulsante da solo.
   "Rilancia" chiama davvero cantiere.avvia (plancia/jarvis.py, _esegui_proposta):
   e' la risposta a "Il lancio e' fallito. Lo riprovo?", per questo dice
   Rilancia e non Riprendi. "Apri" segue la navigazione che jarvis risponde. */
function rigaProposta(p, i) {
  const az = p.azione || {};
  const frase = i === 0 ? 'fallo' : ['', 'la seconda', 'la terza', 'la quarta'][i] || 'fallo';
  const etichetta = az.tipo === 'manda' ? T('Riprendi') : az.tipo === 'rilancia' ? T('Rilancia') : T('Apri');
  return `
  <div class="riga">
    <div class="txt"><div class="t">${esc(p.testo)}</div></div>
    <div class="side">
      <button class="mini go riprendi" data-act="proposta" data-frase="${frase}"
        data-testo="${esc(p.testo)}" data-tipo="${esc(az.tipo || '')}"
        data-task="${az.task_id || ''}" data-titolo="${esc(az.titolo || '')}"
        data-progetto="${esc(az.progetto || '')}">${etichetta}</button>
    </div>
  </div>`;
}

/* Il pannello "Prossimi": una riga per progetto, raggruppata per area come
   /api/prossimi la manda (plancia/api.py:prossimi_raggruppati). Il tetto di 7
   righe visibili vale sul totale e si applica qui: ogni riga oltre il tetto e'
   gia' nel markup, solo nascosta, e "Mostra altri N" la rivela senza una
   seconda chiamata. Un gruppo che finisce tutto oltre il tetto resta nascosto
   con le sue righe: mai un'area con l'intestazione e niente sotto. */
const PROSSIMI_TETTO = 7;

function panelloProssimi(dati) {
  if (!dati) return `<div class="vuoto prossimi-vuoto">${T('prossimi_vuoto')}</div>`;
  const gruppi = [
    ...dati.aree.map((a) => ({
      key: a.key, name: a.key === 'cartelle-viste' ? T('cartelle_viste') : a.name, righe: a.righe,
    })),
    ...(dati.senza_area.length ? [{ key: '', name: T('area_senza'), righe: dati.senza_area }] : []),
  ].filter((g) => g.righe.length);
  if (!gruppi.length) return `<div class="vuoto prossimi-vuoto">${T('prossimi_vuoto')}</div>`;

  let mostrate = 0, nascoste = 0;
  const blocchi = gruppi.map((g) => {
    const visibili = Math.min(g.righe.length, Math.max(0, PROSSIMI_TETTO - mostrate));
    mostrate += visibili;
    nascoste += g.righe.length - visibili;
    return `
    <div class="prossimi-blocco"${visibili ? '' : ' hidden data-extra'}>
      <div class="sez-area prossimi-area"><span class="prossimi-area-nome">${esc(g.name)}</span></div>
      <div class="gruppo">${g.righe.map((r, i) => rigaProssimo(r, g.key, i >= visibili)).join('')}</div>
    </div>`;
  }).join('');
  return `<div class="prossimi">${blocchi}${nascoste ? `
    <button class="altri-out" type="button" data-act="prossimi-altri">${conN('prossimi_altri', nascoste)}</button>` : ''}</div>`;
}

function rigaProssimo(r, areaKey, nascosta) {
  return `
  <div class="riga prossimi-riga" data-project="${esc(r.key)}" data-area="${esc(areaKey)}"
       data-chiave="${esc(areaKey)}:${esc(r.key)}" tabindex="0" role="button"${nascosta ? ' hidden data-extra' : ''}>
    <div class="txt">
      <div class="t prossimi-progetto">${esc(r.name)}</div>
      <div class="s prossimi-cosa">${r.cosa ? esc(r.cosa) : T('niente in coda')}</div>
    </div>
    ${r.scadenza ? `<span class="scad prossimi-scadenza${scaduta(r.scadenza) ? ' scaduta' : ''}">${dataBreve(r.scadenza)}</span>` : ''}
    ${CHEV}
  </div>`;
}

function timeline(events) {
  if (!events.length) return `<div class="vuoto">${T('niente da mostrare')}</div>`;
  return events.map((e) => `
    <div class="ev" data-k="${esc(e.kind)}">
      <div class="when">${ago(e.ts)} · ${T(e.kind)}${e.progetto ? ' · ' + esc(e.progetto) : ''}</div>
      <div class="what truncate">${esc(Tev(e.title))}</div>
    </div>`).join('');
}

function taskRows(tasks) {
  if (!tasks.length) return `<div class="vuoto">${T('nessun task aperto')}</div>`;
  return tasks.map((t) => `
    <div class="riga" data-task="${t.id}">
      <div class="prio p${t.priority}"></div>
      <div class="main">
        <div class="title">${esc(t.title)}</div>
        <div class="sub">${[t.project && esc(t.project), t.due && 'scade ' + t.due,
          t.source !== 'manuale' ? T('da') + ' ' + esc(t.source) : ''].filter(Boolean).join(' · ') || '—'}</div>
      </div>
      <div class="side">
        ${t.status !== 'aperto' ? `<span class="tag ${statusClass[t.status] || ''}">${T(t.status)}</span>` : ''}
        <button class="mini" data-act="task-cycle" data-id="${t.id}" data-status="${esc(t.status)}">${
          t.status === 'aperto' ? T('inizia') : t.status === 'in corso' ? T('chiudi') : T('riapri')}</button>
        <button class="mini go" data-act="task-done" data-id="${t.id}">✓</button>
      </div>
    </div>`).join('');
}

/* ---------------------------------------------------------------- riepilogo */

async function bloccoRiepilogo() {
  const r = state.recap || (state.recap = { lang: '', data: null, qa: [], voce: null });
  // Una lingua sola per superficie: quella scelta nelle Impostazioni. La lingua
  // della configurazione resta per il riepilogo che parte da solo la mattina,
  // quando nessuno sta guardando l'interfaccia.
  r.lang = UILANG;
  r.qa = r.qa || [];

  // Se c'e' in cache si dipinge subito; altrimenti si genera in sottofondo.
  let daRinfrescare = false;
  if (!r.data) {
    try {
      const pronto = await api('/api/recap?solo_cache=1&lang=' + (r.lang || ''));
      if (pronto && pronto.testo) { r.data = pronto; r.audio = null; }
      daRinfrescare = !pronto || !pronto.fresco;
    } catch (e) { daRinfrescare = true; }
  }
  if (daRinfrescare) setTimeout(() => { if (!state.recap.inCorso) generaRecap(); }, 60);
  // Si legge dopo il recupero, non prima: letto prima si dipingeva sempre
  // l'attesa e il testo in cache compariva solo al giro dopo.
  const d = r.data;

  return `
  <section class="riepilogo">
    <p class="recap-testo ${d ? '' : 'attesa'}" id="recap-testo" ${d ? 'data-act="recap-espandi"' : ''}>${
      d ? esc(d.testo) : T('preparo il riepilogo, ci vogliono pochi secondi…')}</p>
    <div class="recap-bar">
      <button class="btn" data-act="recap-play" ${d ? '' : 'disabled'}>
        <span id="speak-icona">▶</span><span id="speak-testo">${T('Leggi')}</span></button>
      <button class="ghost" data-act="recap-stop">${T('Ferma')}</button>
    </div>
  </section>`;
}

async function generaRecap(rigenera) {
  const r = state.recap;
  if (r.inCorso) return;
  r.inCorso = true;
  const box = $('#recap-testo');
  if (box && !box.textContent.trim()) {
    box.classList.add('attesa');
    box.textContent = T('preparo il riepilogo…');
  }
  try {
    const lang = ($('#recap-lang') || {}).value || r.lang || 'it';
    r.lang = lang;
    const d = await api('/api/recap', { method: 'POST', body: { lang, voce: true } });
    r.data = d; r.voce = d.motore || null; r.audio = d.url || null;
    // senza un motore vocale il server risponde col testo e una nota che dice cosa
    // installare: "Ascolta" la mostra al posto di un generico "audio non pronto"
    r.notaVoce = d.nota_voce || null;
    r.inCorso = false;
    if (state.view === 'oggi') await route();
    if (rigenera) toast(T('riepilogo aggiornato'));
  } catch (err) {
    r.inCorso = false;
    if (box) box.textContent = T('errore: ') + err.message;
  }
}

function suona(url, notaVoce) {
  const p = $('#player');
  if (!url) return notaVoce ? toast(notaVoce, true, 9000) : toast(T('audio non pronto'), true);
  p.src = url;
  p.play().then(() => aggiornaBottoneVoce(true)).catch(() => toast(T('non riesco a riprodurre'), true));
  p.onended = () => aggiornaBottoneVoce(false);
}

function aggiornaBottoneVoce(attivo) {
  const icona = $('#speak-icona'), testo = $('#speak-testo');
  if (!icona || !testo) return;
  icona.innerHTML = attivo ? '<span class="wave"><i></i><i></i><i></i><i></i></span>' : '▶';
  testo.textContent = attivo ? T('in ascolto') : T('Leggi');
}

async function chiedi(domanda) {
  const r = state.recap || (state.recap = { qa: [] });
  r.qa = r.qa || [];
  r.qa.push({ mia: true, testo: domanda });
  r.qa.push({ mia: false, testo: '…' });
  const bolle = $('#qa-bolle');
  if (bolle) bolle.innerHTML = r.qa.map((b) =>
    `<div class="bolla ${b.mia ? 'mia' : 'sua'}">${esc(b.testo)}</div>`).join('');
  try {
    const lang = ($('#recap-lang') || {}).value || r.lang || 'it';
    const res = await api('/api/voice/ask', { method: 'POST', body: { domanda, lang, voce: true } });
    r.qa[r.qa.length - 1] = { mia: false, testo: res.risposta };
    if (bolle) bolle.innerHTML = r.qa.map((b) =>
      `<div class="bolla ${b.mia ? 'mia' : 'sua'}">${esc(b.testo)}</div>`).join('');
    if (res.url) suona(res.url);
  } catch (err) {
    r.qa[r.qa.length - 1] = { mia: false, testo: 'errore: ' + err.message };
    if (bolle) bolle.innerHTML = r.qa.map((b) =>
      `<div class="bolla ${b.mia ? 'mia' : 'sua'}">${esc(b.testo)}</div>`).join('');
  }
}



/* ---------------------------------------------------------------- agenti */
/* Un thread ripreso più volte produce un file per ripresa: nell'elenco è una
   riga sola, con quante volte ci sono tornati sopra. */
function raggruppa(scambi) {
  const per = new Map();
  scambi.forEach((e) => {
    const k = e.title || '?';
    if (!per.has(k)) per.set(k, { ...e, n: 0 });
    const v = per.get(k);
    v.n += 1;
    if (e.ts > v.ts) v.ts = e.ts;
  });
  return [...per.values()].sort((a, b) => (a.ts < b.ts ? 1 : -1));
}

async function bloccoAgenti(soloCorpo) {
  const d = await api('/api/agents');
  const per = Object.fromEntries(d.totali.map((a) => [a.agente, a]));
  const scheda = (nome) => {
    const a = per[nome];
    if (!a) return `<div class="agent-card ${nome}">
      <h3>${nome}</h3><div class="big" style="font-size:18px">${T('Codex non è collegato')}</div></div>`;
    return `
    <div class="agent-card ${nome}">
      <h3>${nome}</h3>
      <div class="big">${num(a.sessioni)}</div>
      <div style="font-size:11.5px;color:var(--faint)">${T('sessioni')} · ${T('primo lavoro')} ${ago(a.primo)}</div>
      <div class="agent-stats">
        <div><b>${kilo(a.token)}</b><span>${T('token generati')}</span></div>
        <div><b>${num(a.tool)}</b><span>${T('chiamate a tool')}</span></div>
        <div><b>${num(a.messaggi)}</b><span>${T('sessioni tue')}</span></div>
      </div>
    </div>`;
  };

  const maxG = Math.max(1, ...d.per_giorno.map((g) => g.n));
  const giorni = {};
  d.per_giorno.forEach((g) => {
    giorni[g.giorno] = giorni[g.giorno] || { claude: 0, codex: 0 };
    giorni[g.giorno][g.agente] = g.n;
  });
  const elenco = Object.entries(giorni).sort().slice(-30);

  return `
  ${soloCorpo ? '' : `<div class="view-head">
    <h1>${T('Agenti')}</h1><p>${T('i due agenti sullo stesso archivio')}</p>
    <span class="spacer"></span>
    <span class="tag ${d.codex.mcp ? 'ok' : 'warn'}">${d.codex.mcp ? '16 ' + T('tool condivisi') : 'MCP ' + T('Codex non è collegato')}</span>
  </div>`}

  <div class="duel" data-in="1">${scheda('claude')}${scheda('codex')}</div>

  <div class="grid cols-2" data-in="2" style="margin-top:var(--s3)">
    <div class="panel">
      <header><h3>${T('Chi ha lavorato su cosa')}</h3></header>
      <div class="panel-body">
        ${d.per_progetto.map((p) => {
          const tot = p.claude + p.codex;
          return `<div style="margin-bottom:var(--s4)">
            <div style="display:flex;gap:8px;align-items:baseline;margin-bottom:6px">
              <span style="font-size:13px" data-project="${esc(p.chiave)}" role="button">${esc(p.progetto)}</span>
              <span class="spacer" style="margin-left:auto"></span>
              <span class="mono" style="font-size:10.5px;color:var(--faint)">${p.claude} · ${p.codex}</span>
            </div>
            <div class="split">
              <i class="c" style="width:${(p.claude / tot) * 100}%"></i>
              <i class="x" style="width:${(p.codex / tot) * 100}%"></i>
            </div>
          </div>`;
        }).join('') || `<div class="vuoto">${T('niente da mostrare')}</div>`}
      </div>
    </div>

    <div style="display:flex;flex-direction:column;gap:var(--s3)">
      <div class="panel">
        <header><h3>${T('Ritmo · 30 giorni')}</h3></header>
        <div class="panel-body">
          <div class="ribbon" style="height:74px">
            ${elenco.map(([g, v]) => {
              const su = ((v.claude || 0) / maxG) * 32;
              const giu = ((v.codex || 0) / maxG) * 32;
              return `<div class="day" title="${g}: ${v.claude || 0} claude, ${v.codex || 0} codex">
                ${v.claude ? `<div class="up" style="height:${su}px"></div>` : ''}
                ${v.codex ? `<div class="down" style="height:${giu}px;background:var(--codex);opacity:.85"></div>` : ''}
                ${(!v.claude && !v.codex) ? '<div class="tick"></div>' : ''}
              </div>`;
            }).join('')}
          </div>
          <div class="ribbon-legend">
            <span><i style="background:var(--claude)"></i>claude</span>
            <span><i style="background:var(--codex)"></i>codex</span>
          </div>
        </div>
      </div>

      <div class="panel">
        <header><h3>${T('Quando si sono parlati')}</h3><span class="spacer"></span>
          <span class="tag mono">${d.scambi.length}</span></header>
        <div class="panel-body tight">
          ${raggruppa(d.scambi).slice(0, 8).map((e) => `
            <div class="riga"><div class="main">
              <div class="title truncate">${esc(e.title)}</div>
              <div class="sub">${ago(e.ts)} · ${e.n > 1 ? e.n + ' ' + T('riprese') + ' · ' : ''}${esc(e.detail || '')}${e.progetto ? ' · ' + esc(e.progetto) : ''}</div>
            </div></div>`).join('') || `<div class="vuoto">${T('nessuno scambio registrato')}</div>`}
        </div>
      </div>
    </div>
  </div>`;
};

/* ---------------------------------------------------------------- archivio */
/* Tutto quello che e' gia' successo: le sessioni in una tabella che si ordina,
   i due agenti, le capacita, e il registro degli eventi. Le memorie hanno la
   loro vista. */
const SEGMENTI = [['sessioni', 'Sessioni'], ['agenti', 'Agenti'],
                  ['capacita', 'Capacità'], ['registro', 'Registro']];

views.archivio = async () => {
  const f = state.filters.archivio || (state.filters.archivio = { seg: 'sessioni' });
  const corpo = f.seg === 'agenti' ? await bloccoAgenti(true)
    : f.seg === 'capacita' ? await bloccoCapacita(true)
    : f.seg === 'registro' ? await bloccoRegistro(true)
    : await bloccoSessioni(true);
  return `
  <div class="view-tools">
    <div class="seg" role="group" aria-label="${T('Archivio')}">${SEGMENTI.map(([k, etichetta]) =>
      `<button class="${f.seg === k ? 'on' : ''}" data-filter="archivio.seg" data-value="${k}">${T(etichetta)}</button>`).join('')}</div>
  </div>
  <div class="scheda-pagina">${corpo}</div>`;
};

/* Il registro degli eventi (/api/eventi): quello che Plancia ha visto fare, in
   ordine, con il tipo e il progetto. */
async function bloccoRegistro() {
  const d = await api('/api/eventi?limite=200');
  const righe = d.eventi || [];
  return righe.length ? `
  <table class="tabella">
    <thead><tr><th>${T('quando')}</th><th>${T('Tipo')}</th><th>${T('Titolo')}</th><th class="c-nascondi">${T('progetto')}</th></tr></thead>
    <tbody>${righe.slice().reverse().map((e) => `
      <tr><td class="c-sec">${esc(ago(e.ts))}</td>
        <td><span class="tag">${esc(e.tipo)}</span></td>
        <td class="c-tit">${esc(Tev(e.titolo || ''))}</td>
        <td class="c-sec c-nascondi">${esc(e.progetto || '')}</td></tr>`).join('')}</tbody>
  </table>` : `<div class="vuoto">${T('niente da mostrare')}</div>`;
}
const ORD_SESS = {
  quando: (s) => s.started_at || '', di_cosa: (s) => (s.title || s.first_prompt || '').toLowerCase(),
  agente: (s) => s.agent || 'claude', progetto: (s) => (s.progetto || '').toLowerCase(),
  turni: (s) => s.n_user || 0, tool: (s) => s.n_tools || 0,
};

async function bloccoSessioni(soloCorpo) {
  const f = state.filters.sessioni || (state.filters.sessioni = { q: '', project: '', agent: '' });
  const ord = state.ordSess || (state.ordSess = { col: 'quando', dir: -1 });
  const [rows0, projects] = await Promise.all([
    api(`/api/sessions?limit=150${f.q ? '&q=' + encodeURIComponent(f.q) : ''}${f.project ? '&project=' + encodeURIComponent(f.project) : ''}${f.agent ? '&agent=' + f.agent : ''}`),
    api('/api/projects'),
  ]);
  const chiave = ORD_SESS[ord.col] || ORD_SESS.quando;
  const rows = rows0.slice().sort((a, b) => {
    const x = chiave(a), y = chiave(b);
    return (x < y ? -1 : x > y ? 1 : 0) * ord.dir;
  });
  const th = (col, etichetta, cls = '') => `<th class="ord ${cls}" data-act="ordina" data-col="${col}"
    aria-sort="${ord.col === col ? (ord.dir > 0 ? 'ascending' : 'descending') : 'none'}">${etichetta}${
      ord.col === col ? (ord.dir > 0 ? ' ▲' : ' ▼') : ''}</th>`;
  return `
  <div class="filters">
    <input type="search" data-filter-input="sessioni.q" value="${esc(f.q)}" placeholder="${T('cerca nel primo messaggio…')}"
      aria-label="${T('cerca nel primo messaggio…')}" style="min-width:240px;width:auto">
    <div class="seg">${['', 'claude', 'codex'].map((a) =>
      `<button class="${f.agent === a ? 'on' : ''}" data-filter="sessioni.agent" data-value="${a}">${a ? cap(a) : T('tutti')}</button>`).join('')}</div>
    <select data-filter-select="sessioni.project" aria-label="${T('progetto')}">
      <option value="">${T('tutti i progetti')}</option>
      ${projects.map((p) => `<option value="${esc(p.key)}" ${f.project === p.key ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}
    </select>
    <span class="faint sub">${rows.length} ${T('conversazioni con Claude Code')}</span>
  </div>
  <table class="tabella">
    <thead><tr>${th('quando', T('quando'))}${th('di_cosa', T('di cosa'))}${th('agente', T('agente'), 'c-nascondi')}${th('progetto', T('progetto'), 'c-nascondi')}${th('turni', T('turni'), 'destra c-nascondi')}${th('tool', T('tool'), 'destra c-nascondi')}<th></th></tr></thead>
    <tbody>${rows.map((s) => `
      <tr>
        <td class="c-sec">${esc(dateIt(s.started_at))}<div class="sub">${esc(ago(s.started_at))}</div></td>
        <td class="c-tit"><div>${esc(s.title || (s.prompt || s.first_prompt || '').slice(0, 90)) || T('senza titolo')}</div>
          <div class="sub clamp2">${esc((s.first_prompt || '').slice(0, 190))}</div></td>
        <td class="c-nascondi"><span class="tag agente ${s.agent === 'codex' ? 'codex' : ''}">${esc(cap(s.agent || 'claude'))}</span></td>
        <td class="c-sec c-nascondi">${s.progetto ? esc(s.progetto) : '-'}${
          s.dedotto_da === 'percorsi' ? `<div class="sub" title="${esc(s.dir_dedotta || '')}">${T('dedotta dai percorsi')}</div>` : ''}</td>
        <td class="destra num c-nascondi">${num(s.n_user)}</td>
        <td class="destra num c-nascondi">${num(s.n_tools)}</td>
        <td class="destra"><button class="mini" data-act="copy-resume" data-id="${esc(s.session_id)}" data-cwd="${esc(s.cwd || '')}">${T('riprendi')}</button></td>
      </tr>`).join('') || `<tr><td colspan="7" class="vuoto">${T('nessuna sessione')}</td></tr>`}
    </tbody>
  </table>`;
}

/* ------------------------------------------------------------------- ricerca */
/* Il campo in alto cerca subito: appena si scrive, la vista Risultati prende il
   posto del contenuto finche' il campo non e' vuoto. Prima il filtro locale sui
   dati gia' caricati (nessuna attesa), poi /api/search con un po' di calma
   (200 ms) e la richiesta di prima annullata; i risultati del server si
   aggiungono senza far saltare la lista. Fino al 9 agosto 2026 la ricerca
   vedeva il solo primo prompt di ogni sessione; adesso guarda dentro i turni
   veri, con la riga esatta da cui vengono. */
const AMBITI = [['tutto', 'Tutto'], ['task', 'Task'], ['progetti', 'Progetti'],
                ['sessioni', 'Sessioni'], ['memoria', 'Memoria']];
const GRUPPI_RIC = [['task', 'Task'], ['progetti', 'Progetti'], ['sessioni', 'Sessioni'],
                    ['memoria', 'Memoria'], ['altro', 'Altro']];
const ric = { q: '', ambito: 'tutto', indiceP: null, indice: null, server: null, aperta: false,
              ctl: null, timer: null, cerca: 0 };

const marca = (frammento) => esc(frammento || '')
  .split('«').join('<mark>').split('»').join('</mark>');

/* Il testo con i termini cercati in evidenza. Si scappa prima e si marca dopo,
   o un titolo che contiene "<" diventa markup. */
function evidenzia(testo, q) {
  const t = String(testo || '');
  const i = q ? t.toLowerCase().indexOf(q.toLowerCase()) : -1;
  if (i < 0) return esc(t);
  return esc(t.slice(0, i)) + '<mark>' + esc(t.slice(i, i + q.length)) + '</mark>' + esc(t.slice(i + q.length));
}

const ICONA_RIC = {
  task: '<path d="M4 6.5l1.6 1.6L8.4 5M4 12.5l1.6 1.6 2.8-3.1M12 6.5h8M12 12.5h8M4 18.5h4M12 18.5h8"/>',
  progetti: '<path d="M3 7.5a2 2 0 0 1 2-2h4l2 2.2h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  sessioni: '<rect x="3" y="4.5" width="18" height="4.5" rx="1"/><path d="M5 9v9a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 18V9M10 13h4"/>',
  memoria: '<circle cx="6" cy="7" r="2.2"/><circle cx="18" cy="8" r="2.2"/><circle cx="12" cy="17.5" r="2.4"/><path d="M8 7.6l7.8.3M7.2 9l3.6 6.3M16.7 10l-3.6 5.3"/>',
  altro: '<circle cx="12" cy="12" r="8"/><path d="M8.5 12h.01M12 12h.01M15.5 12h.01"/>',
};
const iconaRic = (g) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${ICONA_RIC[g] || ICONA_RIC.altro}</svg>`;

/* I dati su cui filtrare subito. Si caricano la prima volta che si mette il
   dito sul campo (focus) o si scrive, e si buttano quando i dati cambiano. */
function caricaIndice() {
  if (ric.indiceP) return ric.indiceP;
  const ok = (p, vuoto) => p.catch(() => vuoto);
  ric.indiceP = Promise.all([
    ok(api('/api/lavagna?stato=tutti&limite=400'), { voci: [] }),
    ok(api('/api/projects'), []),
    ok(api('/api/knowledge'), []),
    ok(api('/api/sessions?limit=300'), []),
  ]).then(([lav, prog, mem, ses]) => {
    ric.indice = { task: lav.voci || [], progetti: prog, memoria: mem, sessioni: ses };
    return ric.indice;
  });
  return ric.indiceP;
}

function filtraLocale(q) {
  const ix = ric.indice;
  if (!ix || !q) return [];
  const t = q.toLowerCase();
  const punteggio = (titolo, ...altri) => {
    const a = String(titolo || '').toLowerCase();
    if (a === t) return 4;
    if (a.startsWith(t)) return 3;
    if (a.includes(t)) return 2;
    return altri.some((x) => x && String(x).toLowerCase().includes(t)) ? 1 : 0;
  };
  const dai = (lista, gruppo, titolo, altri, fai) => lista
    .map((x) => [punteggio(titolo(x), ...altri(x)), x])
    .filter(([p]) => p > 0).sort((a, b) => b[0] - a[0]).slice(0, 25)
    .map(([, x]) => fai(x));
  return [
    ...dai(ix.task, 'task', (v) => v.titolo, (v) => [v.dettaglio, v.progetto], (v) => ({
      gruppo: 'task', titolo: v.titolo, sec: [v.progetto, T(v.stato), ago(v.aggiornato_at)].filter(Boolean).join(' · '),
      vai: 'task:' + v.id })),
    ...dai(ix.progetti, 'progetti', (p) => p.name, (p) => [p.key, p.summary, p.next_action], (p) => ({
      gruppo: 'progetti', titolo: p.name, sec: p.next_action || p.summary || '', vai: 'progetti:' + p.key })),
    ...dai(ix.sessioni, 'sessioni', (s) => s.title || s.first_prompt, (s) => [s.first_prompt, s.progetto, s.cwd], (s) => ({
      gruppo: 'sessioni', titolo: s.title || (s.first_prompt || '').slice(0, 90) || T('senza titolo'),
      sec: [s.progetto, cap(s.agent || 'claude'), ago(s.started_at)].filter(Boolean).join(' · '), vai: 'sessioni:' + (s.title || s.first_prompt || '').slice(0, 60) })),
    ...dai(ix.memoria, 'memoria', (k) => k.name, (k) => [k.description], (k) => ({
      gruppo: 'memoria', titolo: k.name, sec: k.description || '', vai: 'memoria:' + k.name })),
  ];
}

/* Quello che risponde il server, nello stesso formato. Le schede tornano con
   un `kind`; i turni sono le frasi vere dentro le conversazioni. */
function dalServer(d, q) {
  const gruppoDi = { task: 'task', progetto: 'progetti', project: 'progetti', sessione: 'sessioni', memoria: 'memoria' };
  const schede = (d.schede || []).map((h) => {
    const g = gruppoDi[h.kind] || 'altro';
    const etichetta = g === 'altro' ? cap(T(h.kind)) : '';
    return {
      gruppo: g, titolo: h.title || T('senza titolo'), snip: h.snip || '',
      sec: [etichetta, h.project, h.ts ? ago(h.ts) : ''].filter(Boolean).join(' · '),
      vai: g === 'altro' ? '' : (g === 'memoria' ? 'memoria:' + h.title : g === 'task' ? 'task:'
        : g === 'progetti' ? 'progetti:' + (h.project || '') : 'sessioni:' + (h.title || '')),
      dallaRete: true };
  });
  const turni = (d.turni || []).map((t) => ({
    gruppo: 'sessioni', turno: t, titolo: '', snip: t.frammento || '', vai: '',
    sec: [(t.progetto || '').split('/').pop(), t.ts ? ago(t.ts) : ''].filter(Boolean).join(' · '),
    piede: `${(t.percorso || '').split('/').pop()} · ${T('riga')} ${t.riga}`, dallaRete: true }));
  return [...schede, ...turni];
}

function unisci() {
  const locali = filtraLocale(ric.q);
  const chiavi = new Set(locali.map((r) => r.gruppo + '|' + r.titolo.toLowerCase()));
  const dalla = (ric.server || []).filter((r) => r.turno || !chiavi.has(r.gruppo + '|' + r.titolo.toLowerCase()));
  return [...locali, ...dalla];
}

function rigaRisultato(r, q) {
  const attr = r.vai ? ` data-vai="${esc(r.vai)}" role="button" tabindex="0"` : '';
  if (r.turno) {
    return `<div class="risultato"${attr}>${iconaRic('sessioni')}<div style="min-width:0">
      <div class="t">${marca(r.snip)}</div>
      <div class="s">${esc(r.sec)}</div>
      <div class="s faint mono" style="font-size:var(--t-xs)">${esc(r.piede)}</div></div></div>`;
  }
  return `<div class="risultato"${attr}>${iconaRic(r.gruppo)}<div style="min-width:0">
    <div class="t">${evidenzia(r.titolo, q)}</div>
    ${r.snip ? `<div class="s">${marca(r.snip)}</div>` : (r.sec ? `<div class="s clamp2">${evidenzia(r.sec, q)}</div>` : '')}
    ${r.snip && r.sec ? `<div class="s faint">${esc(r.sec)}</div>` : ''}</div></div>`;
}

function disegnaRisultati() {
  const view = $('#view');
  if (!view) return;
  const q = ric.q.trim();
  const tutti = unisci();
  const contaPer = (g) => tutti.filter((r) => r.gruppo === g).length;
  const visibili = tutti.filter((r) => ric.ambito === 'tutto' || r.gruppo === ric.ambito
    || (ric.ambito === 'sessioni' && false));
  const gruppi = GRUPPI_RIC.filter(([g]) => visibili.some((r) => r.gruppo === g));
  const attesa = ric.cerca > 0;
  view.dataset.layout = '';
  // mentre si cerca il contenuto e' quello dei risultati: nessuna voce della
  // barra laterale e' la pagina in cui si e' (prima restava evidenziata "Oggi")
  $$('.rail nav a').forEach((a) => a.classList.remove('on'));
  view.innerHTML = `
  <div class="lettura larga risultati">
    <div class="seg ambiti" role="group" aria-label="${T('Ambito')}">${AMBITI.map(([k, l]) =>
      `<button class="${ric.ambito === k ? 'on' : ''}" data-act="ambito" data-v="${k}">${T(l)}${
        k !== 'tutto' && contaPer(k) ? ' ' + contaPer(k) : ''}</button>`).join('')}</div>
    ${gruppi.map(([g, etichetta]) => `
      <section class="sez"><h2>${T(etichetta)}</h2>
        <div>${visibili.filter((r) => r.gruppo === g).map((r) => rigaRisultato(r, q)).join('')}</div></section>`).join('')}
    ${!gruppi.length ? `<div class="vuoto">${attesa ? T('cerco…') : T('Nessun risultato')}</div>`
      : (attesa ? `<div class="ric-attesa">${T('cerco…')}</div>` : '')}
  </div>`;
  const t = $('#tb-titolo'); if (t) t.textContent = T('Ricerca');
}

async function cercaOra(q) {
  ric.q = q;
  const dritti = q.trim();
  if (!dritti) { chiudiRicerca(true); return; }
  ric.aperta = true;
  distruggiGrafo();
  disegnaRisultati();
  caricaIndice().then(() => { if (ric.q === q) disegnaRisultati(); });
  clearTimeout(ric.timer);
  if (ric.ctl) ric.ctl.abort();
  if (dritti.length < 2) { ric.server = null; return; }
  ric.cerca++;
  ric.timer = setTimeout(async () => {
    ric.ctl = new AbortController();
    try {
      const d = await api('/api/search?q=' + encodeURIComponent(dritti), { signal: ric.ctl.signal });
      if (ric.q !== q) return;
      ric.server = dalServer(d, dritti);
    } catch (e) {
      if (e && e.name === 'AbortError') return;
      ric.server = ric.server || [];
    } finally { ric.cerca = Math.max(0, ric.cerca - 1); }
    if (ric.q === q) disegnaRisultati();
  }, 200);
}

function chiudiRicerca(rifai) {
  clearTimeout(ric.timer);
  if (ric.ctl) ric.ctl.abort();
  const era = ric.aperta;
  Object.assign(ric, { q: '', aperta: false, server: null, cerca: 0, ambito: 'tutto' });
  const inp = $('#cerca-q');
  if (inp) inp.value = '';
  if (era && rifai) route();
}

function vaiA(vai) {
  const i = vai.indexOf(':');
  const tipo = vai.slice(0, i), id = vai.slice(i + 1);
  let dest = '#/oggi';
  if (tipo === 'task') {
    state.filters.lavagna = { fonte: '', stato: 'tutti' };
    dest = '#/lavagna' + (id ? '/' + encodeURIComponent(id) : '');
  } else if (tipo === 'progetti') {
    dest = '#/progetti/' + encodeURIComponent(id);
  } else if (tipo === 'memoria') {
    const f = state.filters.memoria || (state.filters.memoria = { lente: '', modo: 'elenco', livello: 0 });
    f.lente = '';
    dest = '#/memoria/' + encodeURIComponent(id);
  } else if (tipo === 'sessioni') {
    state.filters.sessioni = { q: id || '', project: '', agent: '' };
    state.filters.archivio = { seg: 'sessioni' };
    dest = '#/archivio';
  }
  chiudiRicerca(false);
  // stesso indirizzo di prima: hashchange non scatta, si ridisegna a mano
  if (location.hash === dest) route(); else location.hash = dest;
}

(function collegaRicerca() {
  const inp = $('#cerca-q');
  inp.addEventListener('focus', () => { caricaIndice(); });
  inp.addEventListener('input', () => cercaOra(inp.value));
  inp.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape') { ev.preventDefault(); chiudiRicerca(true); inp.blur(); }
  });
  // il campo svuotato con la croce del browser
  inp.addEventListener('search', () => { if (!inp.value && ric.aperta) chiudiRicerca(true); });
})();

// La scorciatoia di ricerca e' Cmd+K sul Mac e Ctrl+K altrove (il gestore accetta
// tutte e due): il suggerimento nel campo dice quella giusta.
(function suggerimentoScorciatoia() {
  const fuoriMac = !/mac|iphone|ipad/i.test(
    (navigator.userAgentData && navigator.userAgentData.platform)
    || navigator.platform || navigator.userAgent || '');
  const kbd = $('#btn-search kbd');
  if (kbd && fuoriMac) kbd.textContent = 'Ctrl+K';
})();

/* ---------------------------------------------------------------- benvenuto */
const PASSI = [
  {
    t: { it: "Plancia legge, non raccoglie", en: "Plancia reads, it does not collect" },
    c: {
      it: "Tutto quello che vedi qui viene da file che hai già sul disco: i transcript di Claude Code, quelli di Codex, la memoria, i tuoi repo. Niente esce dalla macchina, non c'è telemetria, il database è un file solo in ~/.plancia. Puoi leggerlo con qualsiasi strumento SQLite.",
      en: "Everything here comes from files already on your disk: Claude Code transcripts, Codex ones, memory, your repos. Nothing leaves the machine, there is no telemetry, and the database is a single file in ~/.plancia you can open with any SQLite tool.",
    },
    prova: null,
  },
  {
    t: { it: "Ritrovare una cosa detta sei settimane fa", en: "Finding something said six weeks ago" },
    c: {
      it: "Cerca guarda dentro i turni: il testo com'era, di Claude e tuo. Non i titoli delle sessioni, quello che è stato scritto davvero. Ogni risultato dice da quale riga di quale file viene, quindi si riapre invece di essere riassunto, e i chip sopra dicono da quali progetti arriva e quanti per uno. Lo slash apre la ricerca da qualsiasi vista.",
      en: "Search looks inside the turns: the text as it was, Claude's and yours. Not session titles, what was actually written. Every result says which line of which file it comes from, so you reopen it instead of reading a summary, and the chips above tell you which projects it came from and how many from each. Slash opens search from any view.",
    },
    prova: { etichetta: { it: "Apri la ricerca", en: "Open search" }, vista: "cerca" },
  },
  {
    t: { it: "La lavagna: tutti i task, di tutti", en: "The board: every task, every agent" },
    c: {
      it: "Claude Code tiene la sua lista di task in una cartella, Codex i suoi obiettivi in un database, Plancia i suoi. Nessuno dei tre sa degli altri. La lavagna li mette insieme e ti dice cosa è aperto davvero, adesso.",
      en: "Claude Code keeps its task list in a folder, Codex keeps its goals in a database, Plancia has its own. None of them knows about the others. The board puts them together and tells you what is actually open right now.",
    },
    prova: { etichetta: { it: "Apri la lavagna", en: "Open the board" }, vista: "lavagna" },
  },
  {
    t: { it: "Il riepilogo, e le cose da fare", en: "The recap, and what is worth doing" },
    c: {
      it: "Una volta al giorno Plancia legge cosa è successo e te lo racconta come lo diresti a voce, non come un elenco. Poi guarda i segnali (un lancio fallito, un obiettivo bloccato, modifiche non committate) e ti propone la cosa più sensata da fare. A quel punto basta dire fallo.",
      en: "Once a day Plancia reads what happened and tells it the way you would say it, not as a list. Then it looks at the signals (a failed run, a stuck goal, uncommitted changes) and suggests the most sensible next thing. Then you just say do it.",
    },
    prova: { etichetta: { it: "Vedi il riepilogo", en: "See the recap" }, vista: "oggi" },
  },
  {
    t: { it: "Parlargli: ⌥Spazio", en: "Talking to it: ⌥Space" },
    c: {
      it: "Da qualsiasi app, ⌥Spazio apre il pannello vocale. Ascolta di continuo e capisce dal silenzio quando hai finito. Le domande sui tuoi dati rispondono in un decimo di secondo senza chiamare nessun modello; il resto passa da Claude, che ha i tool di Plancia aperti e quindi può fare le cose, non solo dirle.",
      en: "From any app, ⌥Space opens the voice panel. It listens continuously and works out from the silence when you are done. Questions about your data answer in a tenth of a second with no model involved; everything else goes to Claude, which has Plancia's tools open and can actually do things, not just talk about them.",
    },
    prova: { etichetta: { it: "Attiva il microfono", en: "Turn on the microphone" },
             url: "plancia://permessi" },
  },
  {
    t: { it: "Mandare un lavoro a un agente", en: "Dispatching work to an agent" },
    c: {
      it: "Nel cassetto di ogni task c'è un pulsante il cui testo è lo stato: aperta nell'app (copia il comando negli appunti), riprendi in Claude Code o Codex (sessione di prima), oppure avvia da capo. Sotto, In background: un'istruzione e l'interruttore può modificare i file, spento di default, e va scelto ogni volta.",
      en: "The task's drawer has one button whose text is the state: open in the app (copies the command to the clipboard), resume in Claude Code or Codex (the earlier session), or start from scratch. Below that, In the background: an instruction and the can modify files switch, off by default, and you choose that every single time.",
    },
    prova: { etichetta: { it: "Prova In background", en: "Try In the background" }, azione: "manda-nuovo" },
  },
];

views.benvenuto = async () => {
  // Chi riapre la guida vuole rivederla, non ritrovarsi all'ultimo passo di
  // mesi fa. Si riparte da capo se si arriva da fuori.
  if (state.vistaPrima !== 'benvenuto') state.passo = 0;
  state.vistaPrima = 'benvenuto';
  const i = Math.min(state.passo || 0, PASSI.length - 1);
  const p = PASSI[i];
  const L = UILANG === 'en' ? 'en' : 'it';
  if (!state.overview) { state.overview = await api('/api/overview?lang=' + UILANG); state.overviewQuando = new Date(); }
  if (!state.lav) { try { state.lav = await api('/api/lavagna'); } catch (e) { state.lav = { conteggi: {} }; } }
  const c = (state.lav && state.lav.conteggi) || {};
  const o = state.overview.stats || {};
  // ogni passo mostra i tuoi numeri: cosi' l'onboarding e' anche la prova che legge davvero
  const CIFRE = [
    [[o.progetti_attivi, L === 'en' ? 'projects read' : 'progetti letti'],
     [(state.overview.agenti || []).length || 2, L === 'en' ? 'agents' : 'agenti'],
     [0, L === 'en' ? 'bytes sent out' : 'byte usciti']],
    [[(o.indice || {}).turni || 0, L === 'en' ? 'turns indexed' : 'turni indicizzati'],
     [(o.indice || {}).file || 0, L === 'en' ? 'transcripts read' : 'transcript letti'],
     [(o.indice || {}).testo_mb || 0, L === 'en' ? 'MB of prose' : 'MB di prosa']],
    [[(c.claude || {}).aperti || 0, 'claude'], [(c.codex || {}).aperti || 0, 'codex'],
     [(c.plancia || {}).aperti || 0, 'plancia']],
    null, null, null,
  ][i];
  return `
  <div class="guida">
    <div class="label">
      ${i + 1} / ${PASSI.length}
      <span class="passi">${PASSI.map((_, k) => `<i class="${k <= i ? 'fatto' : ''}" style="width:${k === i ? 18 : 6}px"></i>`).join('')}</span>
    </div>
    <h1>${p.t[L]}</h1>
    <p class="corpo">${p.c[L]}</p>
    ${CIFRE ? `<div class="cifre">
      ${CIFRE.map(([n, e]) => `<div class="kpi"><div class="num">${n}</div><div class="label">${e}</div></div>`).join('')}
    </div>` : ''}
    <div class="comandi">
      ${i > 0 ? `<button class="ghost" data-act="passo" data-n="${i - 1}">${L === 'en' ? 'Back' : 'Indietro'}</button>` : ''}
      ${p.prova ? `<button class="ghost" data-act="prova-passo"
        data-vista="${p.prova.vista || ''}" data-azione="${p.prova.azione || ''}"
        data-url="${p.prova.url || ''}">${p.prova.etichetta[L]}</button>` : ''}
      <span class="spacer"></span>
      ${i < PASSI.length - 1
        ? `<button class="primary" data-act="passo" data-n="${i + 1}">${L === 'en' ? 'Next' : 'Avanti'}</button>`
        : `<button class="primary" data-act="fine-benvenuto">${L === 'en' ? 'Start using it' : 'Comincia'}</button>`}
      <button class="mini" data-act="fine-benvenuto">${L === 'en' ? 'skip' : 'salta'}</button>
    </div>
  </div>`;
};

/* ---------------------------------------------------------------- task */
/* Tutti i task di tutti, in una tabella: stato, titolo, progetto, scadenza,
   fonte. Un click su una riga apre il dettaglio a destra. La lavagna di prima
   (/api/lavagna) e' la stessa fonte; la scadenza viene da /api/tasks, perche'
   solo i task di Plancia ne hanno una. */
const FONTI = [['', 'Tutte le fonti'], ['plancia', 'Plancia'], ['claude', 'Claude'], ['codex', 'Codex']];
const STATI_TASK = [['aperti', 'Aperti'], ['fatto', 'Fatti'], ['tutti', 'Tutti']];
const CLASSE_STATO = { aperto: '', 'in corso': 'in-corso', bloccato: 'bloccato', fatto: 'fatto' };

/* La riga scelta. Se quella ricordata non c'e' piu' (filtro cambiato, task
   chiuso) si passa alla prima; senza righe, a niente. */
function scegliSel(lista, ids) {
  const attuale = state.sel[lista];
  const scelta = (attuale != null && ids.map(String).includes(String(attuale))) ? attuale : (ids.length ? ids[0] : null);
  state.sel[lista] = scelta;
  return scelta;
}

const cerchioTask = (v) => {
  const cl = CLASSE_STATO[v.stato] || '';
  if (v.fonte === 'plancia' && v.task_id) {
    return `<button class="cerchio ${cl}" data-act="task-toggle" data-id="${v.task_id}" data-status="${esc(v.stato)}"
      title="${v.stato === 'fatto' ? T('riapri') : T('Fatto')}" aria-label="${T(v.stato)}"></button>`;
  }
  return `<span class="cerchio fisso ${cl}" title="${T(v.stato)}" role="img" aria-label="${T(v.stato)}"></span>`;
};

views.lavagna = async () => {
  const f = state.filters.lavagna || (state.filters.lavagna = { fonte: '', stato: 'aperti' });
  const [d, lanci, progetti, tasks] = await Promise.all([
    api(`/api/lavagna?stato=${f.stato}${f.fonte ? '&fonte=' + f.fonte : ''}`),
    api('/api/runs?limite=6'),
    api('/api/projects'),
    api('/api/tasks?status=tutti&limit=300'),
  ]);
  state.progetti = progetti;
  const scadenze = Object.fromEntries(tasks.map((t) => [t.id, t.due]));
  const voci = d.voci.map((v) => ({ ...v, scadenza: v.task_id ? scadenze[v.task_id] : null }));
  state.voci = Object.fromEntries(voci.map((v) => [String(v.id), v]));
  const sel = scegliSel('lavagna', voci.map((v) => v.id));
  const attivi = lanci.filter((r) => r.stato === 'in coda' || r.stato === 'in corso');

  return `
  <div class="view-tools">
    <div class="seg" role="group" aria-label="${T('Stato')}">${STATI_TASK.map(([k, l]) =>
      `<button class="${f.stato === k ? 'on' : ''}" data-filter="lavagna.stato" data-value="${k}">${T(l)}</button>`).join('')}</div>
    <select data-filter-select="lavagna.fonte" aria-label="${T('Fonte')}">${FONTI.map(([k, l]) =>
      `<option value="${k}" ${f.fonte === k ? 'selected' : ''}>${T(l)}${
        k && d.conteggi[k] ? ' (' + (d.conteggi[k].aperti || 0) + ')' : ''}</option>`).join('')}</select>
    <span class="spacer"></span>
    <button class="btn" data-act="task-nuovo-apri">＋ ${T('Nuovo task')}</button>
  </div>
  <form class="tools-form" data-form="task-quick" id="task-form" hidden>
    <input type="text" name="title" placeholder="${T('Nuovo task')}" autocomplete="off" aria-label="${T('Nuovo task')}">
    <select name="project" aria-label="${T('Progetto')}">
      <option value="">${T('nessun progetto')}</option>
      ${progetti.map((p) => `<option value="${esc(p.key)}">${esc(p.name)}</option>`).join('')}
    </select>
    <select name="priority" aria-label="${T('priorità')}">
      <option value="2">${T('media')}</option><option value="1">${T('alta')}</option><option value="3">${T('bassa')}</option>
    </select>
    <button class="primary" type="submit">${T('Aggiungi')}</button>
  </form>
  <div class="md-view" data-lista="lavagna">
    <div class="lista">
      ${attivi.length ? `<div class="in-lavoro"><div class="gruppo-testa"><span>${T('In lavorazione')}</span>
        <span class="dot busy"></span></div>${attivi.map(rigaLancio).join('')}</div>` : ''}
      ${voci.length ? `<table class="tabella">
        <thead><tr><th class="c-stato"></th><th>${T('Titolo')}</th><th class="c-nascondi">${T('Progetto')}</th>
          <th>${T('Scadenza')}</th><th class="c-nascondi">${T('Fonte')}</th></tr></thead>
        <tbody>${voci.map((v) => `
          <tr data-sel="${v.id}" tabindex="0" class="${String(v.id) === String(sel) ? 'sel' : ''}">
            <td class="c-stato">${cerchioTask(v)}</td>
            <td class="c-tit">${esc(v.titolo)}</td>
            <td class="c-sec c-nascondi">${esc(v.progetto || '')}</td>
            <td class="c-sec"><span class="${scaduta(v.scadenza) && v.stato !== 'fatto' ? 'scad scaduta' : ''}">${dataBreve(v.scadenza)}</span></td>
            <td class="c-sec c-nascondi">${esc(cap(v.fonte))}</td>
          </tr>`).join('')}</tbody></table>`
        : `<div class="vuoto">${T('nessun task aperto da nessuna parte')}</div>`}
      ${lanci.length ? `<details class="lanci"><summary>${T('Lanci recenti')}</summary>
        ${lanci.slice(0, 6).map(rigaLancio).join('')}</details>` : ''}
    </div>
    <aside class="dettaglio" id="dettaglio" aria-live="polite"></aside>
  </div>`;
};

DETTAGLI.lavagna = async (id) => {
  const v = (state.voci || {})[String(id)];
  if (!v) return `<div class="vuoto">${T('Scegli un task')}</div>`;
  const campi = [
    [T('Stato'), esc(T(v.stato))],
    [T('Progetto'), v.progetto ? esc(v.progetto) : '-'],
    [T('Fonte'), esc(cap(v.fonte))],
    v.scadenza ? [T('Scadenza'), `<span class="${scaduta(v.scadenza) && v.stato !== 'fatto' ? 'scad scaduta' : ''}">${dataBreve(v.scadenza)}</span>`] : null,
    [T('Aggiornato'), esc(ago(v.aggiornato_at))],
  ].filter(Boolean);
  return `
    <button class="ghost indietro" data-act="indietro">‹ ${T('Indietro')}</button>
    <h2>${esc(v.titolo)}</h2>
    <dl class="campi">${campi.map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('')}</dl>
    ${v.dettaglio ? `<p class="corpo">${esc(v.dettaglio)}</p>` : ''}
    <div class="azioni">
      <button class="btn riprendi" data-act="manda" data-titolo="${esc(v.titolo)}"
        data-dettaglio="${esc((v.dettaglio || '').slice(0, 600))}"
        data-progetto="${esc(v.progetto_chiave || '')}"
        data-task="${v.fonte === 'plancia' ? v.task_id || '' : ''}"
        data-sessione="${esc(v.sessione || '')}" data-agente="${esc(v.agente || '')}">▷ ${T('Riprendi')}</button>
      ${v.fonte === 'plancia' && v.task_id && v.stato !== 'fatto'
        ? `<button class="btn" data-act="task-done" data-id="${v.task_id}">${T('Fatto')}</button>` : ''}
      ${v.progetto_chiave ? `<button class="btn" data-goto="progetti/${esc(v.progetto_chiave)}">${T('Apri progetto')}</button>` : ''}
    </div>`;
};

const STATO_LANCIO = { riuscito: 'ok', fallito: 'danger', bloccato: 'warn',
                       'in corso': 'accent', 'in coda': '', annullato: '' };

const rigaLancio = (r) => `
  <div class="riga" data-act="lancio" data-id="${r.id}" style="cursor:pointer">
    <span class="tag agente ${r.agente === 'codex' ? 'codex' : ''}" style="flex:none">${esc(r.agente)}</span>
    <div class="main">
      <div class="title truncate">${esc(r.task || (r.prompt || '').split('\n').filter((x) =>
        x && !x.startsWith('#'))[1] || (r.prompt || '').slice(0, 70))}</div>
      <div class="sub" title="${esc(r.cwd || '')}">${Tmodo(r.modo)} · ${esc(cartellaCorta(r.cwd))}${r.token ? ' · ' + kilo(r.token) + ' token' : ''}</div>
    </div>
    <div class="side">
      <span class="tag ${STATO_LANCIO[r.stato] || ''}">${T(r.stato)}</span>
    </div>
  </div>`;

/* Il pulsante Riprendi (LOTTO-L3-RIPRENDI-UI punto 2): il testo è lo stato
   stesso, non un'etichetta fissa. `dati` è {stato, motivo, cwd, agent, id,
   messaggio} da GET /api/riprendi/<id> più `sessione_data` (già lì dove il
   backend l'ha trovata, o null): viva copia il messaggio negli appunti
   (data-act="riprendi-copia"), chiusa e persa lanciano la ripresa
   (data-act="riprendi", POST {apri:true}) - `apri()` (plancia/riprendi.py,
   non toccato) sa già distinguere le due dentro lo stesso comando. */
function bottoneRiprendi(dati, sessioneData) {
  const classi = 'mini go riprendi riprendi-stato';
  if (dati.stato === 'viva') {
    // LOTTO-L3-RITOCCO punto 11: il motivo (perché "viva") sta nel title,
    // tradotto con Tmot come già fa il resto della dashboard - senza,
    // "aperta in /cartella" non diceva PERCHÉ Plancia pensa che sia aperta.
    return `<button class="${classi}" data-act="riprendi-copia"
      data-messaggio="${esc(dati.messaggio)}" title="${esc(Tmot(dati.motivo))}">${fmt('riprendi_viva',
        { cwd: esc(cartellaCorta(dati.cwd)) })}</button>`;
  }
  if (dati.stato === 'chiusa') {
    const chiave = dati.agent === 'codex' ? 'riprendi_chiusa_codex' : 'riprendi_chiusa';
    return `<button class="${classi}" data-act="riprendi" data-id="${dati.id}">${
      fmt(chiave, { data: dateIt(sessioneData) })}</button>`;
  }
  return `<button class="${classi}" data-act="riprendi" data-id="${dati.id}">${
    fmt('riprendi_persa', { motivo: esc(Tmot(dati.motivo)) })}</button>`;
}

/* Il drawer del task: prima era il compositore per mandare a un agente,
   ora è il pulsante Riprendi (sopra, solo quando `dati.task` è un id vero:
   una riga della lavagna venuta da un task di Plancia, non da una proposta
   di Claude/Codex che Plancia non possiede come riga propria) più il modulo
   "In background" sotto (LOTTO-L3-RIPRENDI-UI punto 2): un'istruzione e
   l'interruttore "può modificare i file", spento di default - niente più
   "proposta"/"esegui" scelti da un menu a tendina. Senza un task (blank da
   "manda-nuovo", o una proposta senza riga propria) il modulo porta anche
   titolo/progetto/agente, perché lì non c'è nessun task da cui prenderli:
   va allo stesso /api/cantiere di sempre, solo senza il menu proposta/esegui. */
async function apriRiprendi(dati = {}) {
  const progetti = state.progetti || [];
  // Il cassetto si apre SUBITO (correzione L3-RIPRENDI-UI-2): la GET
  // /api/riprendi/<id> passa da riprendi.stato(), che per Claude senza una
  // sessione viva registrata cade su `claude agents --json` (fino a 25
  // secondi, docstring di plancia/riprendi.py). Prima di questa correzione
  // il cassetto restava chiuso, senza nessun segnale, per tutta quell'attesa:
  // ora si vede subito il titolo e il modulo "In background", con un
  // segnaposto disabilitato al posto del pulsante di stato finché la
  // risposta non arriva.
  const segnaposto = dati.task
    ? `<button class="mini go riprendi riprendi-stato" disabled>${T('aggiorno')}</button>` : '';
  $('#drawer-body').innerHTML = `
    <h2>${esc(dati.titolo || T('Il lavoro'))}</h2>
    ${dati.task ? `<div id="riprendi-stato-slot" style="margin:var(--s2) 0 var(--s4)">${segnaposto}</div>` : ''}
    <section>
      <h3>${T('in_background')}</h3>
      <form data-task="${dati.task || ''}" data-sessione="${esc(dati.sessione || '')}"
        class="riprendi-background" style="display:flex;flex-direction:column;gap:var(--s3)">
        ${!dati.task ? `
        <input type="text" name="titolo" value="${esc(dati.titolo || '')}" placeholder="${T('Il lavoro')}" required>
        <select name="progetto" style="width:190px">
          <option value="">${T('nessun progetto')}</option>
          ${progetti.map((p) => `<option value="${esc(p.key)}" ${p.key === dati.progetto ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}
        </select>
        <select name="agente" style="width:130px">
          <option value="claude" ${dati.agente === 'claude' ? 'selected' : ''}>claude</option>
          <option value="codex" ${dati.agente === 'codex' ? 'selected' : ''}>codex</option>
        </select>` : ''}
        <textarea name="istruzioni" placeholder="${T('Come lo voglio fatto')}" style="min-height:90px">${esc(dati.istruzioni || '')}</textarea>
        <label style="display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted)">
          <input type="checkbox" name="scrive"> ${T('può modificare i file del progetto')}
        </label>
        <label id="riprendi-copia" hidden style="display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted)">
          <input type="checkbox" name="copia"> ${T('copia_sessione')}
        </label>
        <div id="riprendi-piano" class="riprendi-piano" role="status">${
          dati.task || dati.sessione ? '' : T('piano_da_zero')}</div>
        <button class="primary" type="button" data-act="riprendi-background">${T('in_background')}</button>
      </form>
    </section>
    ${dati.dettaglio ? `<section><h3>${T('dettaglio')}</h3>
      <div style="font-size:12.5px;color:var(--muted);white-space:pre-wrap">${esc(dati.dettaglio)}</div></section>` : ''}`;
  $('#drawer').hidden = false;
  if (!dati.task) {
    // Una riga della lavagna con la sua sessione (Claude/Codex, nessun task di
    // Plancia): il piano si chiede lo stesso, in anteprima, prima di partire.
    if (dati.sessione) {
      try {
        const r = await api('/api/cantiere', { method: 'POST', body: {
          titolo: dati.titolo || '-', sessione: dati.sessione, anteprima: true } });
        mostraPiano(r.piano);
      } catch (err) { /* il modulo resta, senza la frase */ }
    }
    return;
  }
  // Ora la GET, con il cassetto già aperto: il segnaposto sopra si sostituisce
  // da solo quando arriva (o si toglie, nel catch, se il task non c'è più).
  try {
    const r = await api('/api/riprendi/' + dati.task);
    const slot = $('#riprendi-stato-slot');
    if (slot) slot.innerHTML = bottoneRiprendi({ ...r.riprendi, id: dati.task, messaggio: r.messaggio },
      r.sessione_data);
    mostraPiano(r.piano);
  } catch (err) {
    // Un task che GET /api/riprendi non trova (cancellato nel frattempo), o
    // l'interrogazione delle sessioni aperte fallita: il segnaposto lascia
    // il posto al modulo "In background", niente pulsante di stato.
    const slot = $('#riprendi-stato-slot');
    if (slot) slot.innerHTML = '';
  }
}

/* La frase del piano nel cassetto di "In background", e la casella "copia"
   quando la sessione e' aperta altrove (l'unico caso in cui ha senso). */
function mostraPiano(piano, messaggio) {
  const slot = $('#riprendi-piano');
  if (!slot || !piano) return;
  slot.innerHTML = pianoTesto(piano) +
    (messaggio ? `<pre class="mono">${esc(messaggio)}</pre>` : '');
  const copia = $('#riprendi-copia');
  if (copia) copia.hidden = piano.stato !== 'viva';
}

async function apriLancio(id) {
  const d = await api('/api/runs/' + id);
  $('#drawer-body').innerHTML = `
    <h2>${T('lanci')} #${d.id}</h2>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:var(--s3)">
      <span class="tag agente ${d.agente === 'codex' ? 'codex' : ''}">${esc(d.agente)}</span>
      <span class="tag">${Tmodo(d.modo)}</span>
      <span class="tag ${STATO_LANCIO[d.stato] || ''}">${T(d.stato)}</span>
      ${d.token ? `<span class="tag mono">${kilo(d.token)} token</span>` : ''}
      ${d.costo ? `<span class="tag mono">$${d.costo.toFixed(3)}</span>` : ''}
    </div>
    <p class="mono" style="font-size:11px;color:var(--faint)">${esc(d.cwd || '')}</p>
    ${d.esito ? `<section><h3>${T('esito')}</h3>
      <div style="font-size:13.5px;line-height:1.65;white-space:pre-wrap">${esc(d.esito)}</div></section>` : ''}
    ${(d.stato === 'in corso' || d.stato === 'in coda')
      ? `<section><button class="ghost" data-act="annulla-lancio" data-id="${d.id}">${T('annulla')}</button></section>` : ''}
    <section><h3>${T('Il lavoro')}</h3>
      <div style="font-size:12px;color:var(--muted);white-space:pre-wrap">${esc(d.prompt)}</div></section>`;
  $('#drawer').hidden = false;
}

/* ---------------------------------------------------------------- progetti */
/* A sinistra l'elenco, raggruppato per stato, con i figli sotto il padre; a
   destra il progetto scelto per intero. Il vecchio cassetto restava sopra a
   tutto e nascondeva l'elenco: qui i due stanno insieme. */
const chiusiAlbero = new Set(['cartelle-viste']);

/* I totali di un padre contano anche i figli: task aperti, sessioni, token
   degli ultimi 30 giorni, e l'attivita' piu' recente di tutto il sottoalbero
   (non solo quella del padre, che spesso e' ferma mentre un figlio lavora). */
function totaliAlbero(padre, figli) {
  return {
    task: (padre.task_aperti || 0) + figli.reduce((n, f) => n + (f.task_aperti || 0), 0),
    sessioni: (padre.sessioni || 0) + figli.reduce((n, f) => n + (f.sessioni || 0), 0),
    token30: (padre.token_30g || 0) + figli.reduce((n, f) => n + (f.token_30g || 0), 0),
    ultima: figli.reduce((max, f) => (f.last_activity && f.last_activity > (max || '')) ? f.last_activity : max,
      padre.last_activity),
  };
}

views.progetti = async () => {
  // Quando non c'e' niente in cassa il fetch va salvato in state.overview: la
  // prossima vista che lo legge non rifa' la richiesta, e senza
  // state.overviewQuando la spia non saprebbe l'ora di QUESTI dati.
  if (!state.overview) { state.overview = await api('/api/overview?lang=' + UILANG); state.overviewQuando = new Date(); }
  const list = state.overview.progetti;
  const gruppi = [['attivo', T('attivo')], ['idea', T('idea')], ['in pausa', T('in pausa')], ['concluso', T('concluso')]];
  // Un figlio non compare mai da solo nel proprio gruppo di stato: resta
  // sempre dentro il padre, qualunque sia il suo stato (parent_id arriva gia'
  // in /api/overview, quindi il nido si costruisce senza un'altra chiamata).
  const figliDi = {};
  list.forEach((p) => { if (p.parent_id) (figliDi[p.parent_id] = figliDi[p.parent_id] || []).push(p); });
  const eFiglio = new Set(list.filter((p) => p.parent_id).map((p) => p.id));
  const visibili = list.filter((p) => !eFiglio.has(p.id));
  const ordine = gruppi.flatMap(([st]) => visibili.filter((p) => p.status === st).map((p) => p.key));
  // la prima e' quella di partenza; anche un figlio, raggiunto da un indirizzo, e' una scelta valida
  const sel = scegliSel('progetti', [...ordine, ...list.map((p) => p.key).filter((k) => !ordine.includes(k))]);

  const padreSel = list.find((p) => p.key === sel && p.parent_id);
  if (padreSel) { const pa = list.find((p) => p.id === padreSel.parent_id); if (pa) chiusiAlbero.delete(pa.key); }
  const riga = (p, extra = '', figli = null) => {
    const conFigli = !!(figli && figli.length);
    const tot = conFigli ? totaliAlbero(p, figli) : { task: p.task_aperti || 0, ultima: p.last_activity };
    const nome = p.key === 'cartelle-viste' ? T('cartelle_viste') : p.name;
    return `<div class="riga ${extra} ${p.key === sel ? 'sel' : ''}" data-sel="${esc(p.key)}" data-chiave="${esc(p.key)}" tabindex="0">
      ${!extra && !conFigli ? '<span class="disclosure vuoto-slot"></span>' : ''}${conFigli ? `<button class="disclosure" data-act="albero-toggle" data-key="${esc(p.key)}" aria-label="${T('Mostra')}">${CHEV_GIU}</button>` : ''}
      <div class="txt"><div class="t">${esc(nome)}${p.pinned ? ' <span class="faint" title="' + T('appuntato') + '">★</span>' : ''}</div>
        <div class="s truncate">${conFigli ? esc(progettiN(figli.length)) + ' · ' : ''}${esc(p.next_action || p.summary || '') || '-'}</div></div>
      <div class="side">${tot.task ? `<span class="tag warn" title="${T('task aperti')}">${tot.task}</span>` : ''}
        <span class="scad">${esc(ago(tot.ultima))}</span></div>
    </div>`;
  };
  const blocco = (p) => {
    const figli = figliDi[p.id] || [];
    if (!figli.length) return riga(p);
    const chiusa = chiusiAlbero.has(p.key);
    return `<div class="albero-padre${chiusa ? ' chiusa' : ''}" data-key="${esc(p.key)}">
      ${riga(p, '', figli)}
      <div class="albero-figli"${chiusa ? ' hidden' : ''}>${figli.map((f) => riga(f, 'figlio')).join('')}</div>
    </div>`;
  };

  return `
  <div class="md-view" data-lista="progetti">
    <div class="lista">
      ${gruppi.map(([st, label]) => {
        const items = visibili.filter((p) => p.status === st);
        if (!items.length) return '';
        return `<div class="gruppo-testa"><span>${cap(label)}</span><span class="n">${items.length}</span></div>
          <div class="lista-righe">${items.map(blocco).join('')}</div>`;
      }).join('') || `<div class="vuoto">${T('nessun progetto attivo')}</div>`}
    </div>
    <aside class="dettaglio" id="dettaglio" aria-live="polite"></aside>
  </div>`;
};

DETTAGLI.progetti = async (key) => {
  const d = await api('/api/projects/' + encodeURIComponent(key));
  const p = d.progetto;
  const campi = [
    [T('Stato'), `<span class="tag ${statusClass[p.status] || ''}">${esc(T(p.status))}</span>`],
    [T('Tipo'), esc(T(p.kind))],
    [cap(T('priorità')), esc(cap(prioTag(p.priority)))],
    [T('Attivo'), esc(ago(p.last_activity))],
  ];
  return `
    <button class="ghost indietro" data-act="indietro">‹ ${T('Indietro')}</button>
    <h2>${esc(p.name)}</h2>
    ${p.summary ? `<p class="corpo">${esc(p.summary)}</p>` : ''}
    <dl class="campi">${campi.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>

    <h3>${T('Prossima azione')}</h3>
    <form data-form="project-edit" data-key="${esc(p.key)}">
      <input type="text" name="next_action" value="${esc(p.next_action || '')}" placeholder="${T('prossimo passo concreto')}"
        aria-label="${T('Prossima azione')}">
      <div class="qui">
        <select name="status" aria-label="${T('Stato')}">${['attivo', 'in pausa', 'idea', 'concluso']
          .map((s) => `<option value="${s}" ${p.status === s ? 'selected' : ''}>${T(s)}</option>`).join('')}</select>
        <select name="priority" aria-label="${T('priorità')}">${[[1, 'alta'], [2, 'media'], [3, 'bassa']]
          .map(([v, l]) => `<option value="${v}" ${p.priority === v ? 'selected' : ''}>${T(l)}</option>`).join('')}</select>
        <button class="primary" type="submit">${T('Aggiorna prossima azione')}</button>
      </div>
    </form>

    ${section(T('Task'), sezioneTaskDrawer(d.task))}
    ${cassettoDopo(p, d.task)}

    ${d.memoria.length ? section(T('Memoria'), `<div class="elenco">${d.memoria.map((k) =>
      `<div class="riga" data-memory="${esc(k.name)}"><div class="txt"><div class="t">${esc(k.name)}</div>
        <div class="s clamp2">${esc(k.description || '')}</div></div>${CHEV}</div>`).join('')}</div>`) : ''}

    ${d.repo.length ? section(T('Repository'), `<div class="elenco">${d.repo.map((r) =>
      `<div class="riga"><div class="txt"><div class="t mono">${esc(r.name)}</div>
        <div class="s">${esc(r.description || cartellaCorta(r.local_path) || '')}</div></div>
        <div class="side">${r.visibility ? `<span class="tag">${esc(r.visibility)}</span>` : ''}
        ${r.dirty ? `<span class="tag warn">${r.dirty} ${T('modifiche')}</span>` : ''}
        ${r.url ? `<a class="mini" href="${esc(r.url)}" target="_blank" rel="noopener">github</a>` : ''}</div>
      </div>`).join('')}</div>`) : ''}

    ${d.commit.length ? section(T('Commit recenti'), `<div class="elenco">${
      d.commit.slice(0, 12).map((c) => `<div class="riga"><div class="txt">
        <div class="t truncate">${esc(c.message)}</div>
        <div class="s mono truncate">${esc(c.repo)} · ${esc((c.sha || '').slice(0, 7))} · ${esc(ago(c.date))}${
          c.sessione_titolo ? ` · ${T('da')} ${esc(c.sessione_titolo.slice(0, 46))}` : ''}</div>
      </div></div>`).join('')}</div>`) : ''}

    ${d.sessioni.length ? section(T('Sessioni'), `<div class="elenco">${
      d.sessioni.slice(0, 12).map((s) => `<div class="riga"><div class="txt">
        <div class="t truncate">${esc(s.title || (s.prompt || '').slice(0, 80)) || T('senza titolo')}</div>
        <div class="s">${esc(dateIt(s.started_at))} · ${s.n_user} ${T('scambi')} · ${s.n_tools} tool${
          s.dedotto_da === 'percorsi' ? ' · ' + T('dedotta dai percorsi') : ''}</div>
      </div><div class="side"><button class="mini" data-act="copy-resume" data-id="${esc(s.session_id)}" data-cwd="">${T('riprendi')}</button></div></div>`).join('')}</div>`) : ''}

    ${d.post.length ? section(T('Post'), `<div class="elenco">${d.post.map((o) =>
      `<div class="riga"><div class="txt"><div class="t clamp2">${esc(o.text)}</div>
        <div class="s">${esc(o.platform)}</div></div>
        <span class="tag ${statusClass[o.status] || ''}">${T(o.status)}</span></div>`).join('')}</div>`) : ''}

    ${section(T('Cronologia'), `<div class="tl">${timeline(d.eventi.slice(0, 30))}</div>`)}
  `;
};

const section = (title, html) => `<section><h3>${title}</h3>${html}</section>`;

/* La sezione "Task" del dettaglio mostra solo il primo task aperto (quello che
   slot.prossimi() usa come "cosa") piu' quelli chiusi: gli altri aperti stanno
   nel cassetto "Dopo" qui sotto, senza righe ripetute fra le due. */
function sezioneTaskDrawer(task) {
  const aperti = task.filter((t) => ['aperto', 'in corso', 'bloccato'].includes(t.status));
  const resto = task.filter((t) => !['aperto', 'in corso', 'bloccato', 'archiviato'].includes(t.status));
  const mostrati = (aperti.length ? [aperti[0]] : []).concat(resto);
  return mostrati.length
    ? `<div class="elenco">${taskRows(mostrati)}</div>`
    : `<p class="faint">${T('nessuno')}</p>`;
}

/* Il cassetto "Dopo": chiuso, un titolo con il conteggio; il contenuto si carica
   al click da /api/tasks?dopo=1, per non portare a video una lista che nessuno
   apre mai. */
function cassettoDopo(p, task) {
  const aperti = task.filter((t) => ['aperto', 'in corso', 'bloccato'].includes(t.status));
  const conta = Math.max(0, aperti.length - 1);
  if (!conta) return '';
  return `
  <section class="cassetto-dopo">
    <h3 data-act="cassetto-dopo" data-key="${esc(p.key)}" role="button" tabindex="0">${conN('dopo_conta', conta)}</h3>
    <div class="cassetto-dopo-lista elenco" hidden></div>
  </section>`;
}

/* ---------------------------------------------------------------- social */
const LANES = [['idea', 'Idee'], ['bozza', 'Bozze'], ['approvato', 'Approvati'],
  ['programmato', 'Programmati'], ['pubblicato', 'Pubblicati']];  // etichette tradotte in vista
const NEXT = { idea: 'bozza', bozza: 'approvato', approvato: 'programmato', programmato: 'pubblicato' };

views.social = async () => {
  const [posts, projects] = await Promise.all([api('/api/posts'), api('/api/projects')]);
  state.posts = Object.fromEntries(posts.map((p) => [String(p.id), p]));
  const ordine = LANES.flatMap(([st]) => posts.filter((p) => p.status === st).map((p) => p.id));
  const sel = scegliSel('social', ordine);
  return `
  <div class="view-tools">
    <span class="muted">${posts.length ? conN('post_n', posts.length) : ''}</span>
    <span class="spacer"></span>
    <button class="btn" data-act="post-new">＋ ${T('Nuova bozza')}</button>
  </div>
  <form class="tools-form" data-form="post-new" id="post-form" hidden>
    <textarea name="text" placeholder="${T('Il testo del post')}" required aria-label="${T('Il testo del post')}" style="flex-basis:100%"></textarea>
    <select name="platform" aria-label="${T('Piattaforma')}"><option value="x">x</option><option value="linkedin">linkedin</option><option value="bluesky">bluesky</option><option value="mastodon">mastodon</option><option value="hn">hn</option><option value="reddit">reddit</option></select>
    <select name="project" aria-label="${T('Progetto')}"><option value="">${T('nessun progetto')}</option>
      ${projects.map((p) => `<option value="${esc(p.key)}">${esc(p.name)}</option>`).join('')}</select>
    <input type="text" name="source_ref" placeholder="${T('fonte: commit, repo, sessione')}">
    <button class="primary" type="submit">${T('Salva bozza')}</button>
  </form>
  <div class="md-view" data-lista="social">
    <div class="lista">
      ${posts.length ? LANES.map(([st, label]) => {
        const items = posts.filter((p) => p.status === st);
        if (!items.length) return '';
        return `<div class="gruppo-testa"><span>${T(label)}</span><span class="n">${items.length}</span></div>
          <div class="lista-righe">${items.map((p) => `
            <div class="riga ${String(p.id) === String(sel) ? 'sel' : ''}" data-sel="${p.id}" data-chiave="${p.id}" tabindex="0">
              <div class="txt"><div class="t clamp2">${esc(p.text)}</div>
                <div class="s">${esc(p.platform)}${p.project ? ' · ' + esc(p.project) : ''}</div></div>
              <span class="tag ${statusClass[p.status] || ''}">${T(p.status)}</span>
            </div>`).join('')}</div>`;
      }).join('') : `<div class="vuoto">${T('nessun post')}</div>`}
    </div>
    <aside class="dettaglio" id="dettaglio" aria-live="polite"></aside>
  </div>`;
};

DETTAGLI.social = async (id) => {
  const p = (state.posts || {})[String(id)];
  if (!p) return `<div class="vuoto">${T('Scegli un post')}</div>`;
  const campi = [
    [T('Stato'), `<span class="tag ${statusClass[p.status] || ''}">${esc(T(p.status))}</span>`],
    [T('Piattaforma'), esc(p.platform)],
    [T('Progetto'), p.project ? esc(p.project) : '-'],
    p.source_ref ? [T('Fonte'), `<span class="mono">${esc(p.source_ref)}</span>`] : null,
    p.media ? [T('Immagine'), `<span class="mono">${esc(cartellaCorta(p.media))}</span>`] : null,
    p.scheduled_for ? [T('Programmato'), esc(dateIt(p.scheduled_for))] : null,
    p.published_at ? [T('Pubblicato'), esc(dateIt(p.published_at))] : null,
    [T('Aggiornato'), esc(ago(p.updated_at))],
  ].filter(Boolean);
  return `
    <button class="ghost indietro" data-act="indietro">‹ ${T('Indietro')}</button>
    <h2>${T('Post')}</h2>
    <p class="corpo" style="color:var(--text)">${esc(p.text)}</p>
    <dl class="campi">${campi.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>
    <div class="azioni">
      ${NEXT[p.status] ? `<button class="btn primary" data-act="post-next" data-id="${p.id}" data-next="${NEXT[p.status]}">→ ${T(NEXT[p.status])}</button>` : ''}
      ${p.status !== 'pubblicato' ? `<button class="btn" data-act="post-edit" data-id="${p.id}">${T('Aggiungi indirizzo')}</button>` : ''}
      ${p.url ? `<a class="btn" href="${esc(p.url)}" target="_blank" rel="noopener">${T('apri')}</a>` : ''}
    </div>`;
};

/* ------------------------------------------------------------------ memoria */
/* Due modi sugli stessi fatti. L'elenco raggruppato per tipo, con il fatto per
   intero a destra. Il grafo, dove le memorie si muovono con una fisica vera:
   si trascinano, si zooma, si passa da "un legame" a "due legami" a "tutto"
   attorno a quella scelta. Nessuna libreria: un canvas e poche forze. */

const TIPI_MEM = [['feedback', 'preferenze'], ['user', 'chi sei'],
                  ['reference', 'riferimenti'], ['project', 'progetti']];

const LENTI = [['', 'tutte'], ['doppie', 'in due cartelle'], ['orfane', 'senza legami'],
               ['rotti', 'link rotti'], ['vuote', 'quasi vuote']];

/* Chi finisce sotto la lente. Nell'elenco gli altri spariscono; nel grafo
   restano ma spenti: togliere il resto farebbe perdere il punto di riferimento. */
function accesiMem(m, lente) {
  const d = m.diagnosi;
  if (lente === 'doppie') return new Set(d.doppie.map((x) => x.nome));
  if (lente === 'orfane') return new Set(d.orfane);
  if (lente === 'vuote') return new Set(d.vuote);
  if (lente === 'rotti') return new Set(d.rotti.map((x) => x.da));
  return null;
}

/* Le poche cose contabili, e niente di piu': quando non c'e' niente da
   sistemare la sezione resta quasi bianca, ed e' il premio. */
function guaiMem(d) {
  const voci = [];
  if (d.doppie.length) voci.push([d.doppie.length, 'in due cartelle', 'doppie', 'copy']);
  if (d.orfane.length) voci.push([d.orfane.length, 'senza legami', 'orfane']);
  if (d.rotti.length) voci.push([d.rotti.length, 'link rotti', 'rotti']);
  if (d.vuote.length) voci.push([d.vuote.length, 'quasi vuote', 'vuote']);
  const righe = voci.map(([quante, etichetta, lente]) => `
    <div class="riga" data-act="mem-lente" data-value="${lente}" role="button" tabindex="0">
      <div class="txt"><div class="t">${cap(T(etichetta))}</div></div>
      <span class="scad">${quante}</span>${CHEV}</div>`).join('');
  // Un rinvio a una memoria che non c'e', ma verso un progetto che esiste, non
  // e' un guasto: e' una memoria che varrebbe la pena scrivere. Si dice con
  // un'altra voce, se no un invito si legge come un errore.
  const invito = (d.da_scrivere || []).length ? `
    <div class="riga"><div class="txt"><div class="t">${cap(T('da scrivere'))}</div>
      <div class="s clamp2">${esc(d.da_scrivere.join(', '))} · ${T('le citi in altre memorie ma non le hai mai scritte')}</div></div>
      <span class="scad">${d.da_scrivere.length}</span></div>` : '';
  if (!righe && !invito) return `<div class="riga"><div class="txt"><div class="s">${T('niente da sistemare')}</div></div></div>`;
  return righe + invito;
}

views.memoria = async () => {
  const f = state.filters.memoria || (state.filters.memoria = { lente: '', modo: 'elenco', livello: 0 });
  const m = state.mappa = await api('/api/memoria/mappa');
  const d = m.diagnosi;
  if (!d.totale) return `<div class="vuoto">${T('nessuna memoria')}</div>`;
  const acceso = accesiMem(m, f.lente);
  const nodi = m.nodi.filter((n) => !acceso || acceso.has(n.nome));
  const ordinati = TIPI_MEM.flatMap(([tipo]) => nodi.filter((n) => n.tipo === tipo)
    .sort((a, b) => (a.aggiornata < b.aggiornata ? 1 : -1)));
  const sel = scegliSel('memoria', ordinati.map((n) => n.nome));
  const conta = {};
  m.nodi.forEach((n) => { conta[n.tipo] = (conta[n.tipo] || 0) + 1; });

  const riga = (n) => `
    <div class="riga ${n.nome === sel ? 'sel' : ''}" data-sel="${esc(n.nome)}" data-memory="${esc(n.nome)}" tabindex="0">
      <span class="punto mnodo ${esc(n.tipo)}"></span>
      <div class="txt"><div class="t">${esc(n.nome)}</div><div class="s clamp">${esc(n.descrizione || '')}</div></div>
      <span class="scad">${dataBreve(n.aggiornata)}</span>
    </div>`;
  const elenco = TIPI_MEM.map(([tipo, etichetta]) => {
    const items = nodi.filter((n) => n.tipo === tipo)
      .sort((a, b) => (a.aggiornata < b.aggiornata ? 1 : -1));
    if (!items.length) return '';
    return `<div class="gruppo-testa"><span>${cap(T(etichetta))}</span><span class="n">${items.length}</span></div>
      <div class="lista-righe">${items.map(riga).join('')}</div>`;
  }).join('') + `
    <div class="gruppo-testa"><span>${T('Da sistemare')}</span></div>
    <div class="lista-righe">${guaiMem(d)}</div>`;

  const grafo = `
    <div class="grafo-box" id="grafo-box">
      <div class="grafo-comandi">
        <div class="seg" role="group" aria-label="${T('Livello')}">
          ${[[1, T('Livello 1')], [2, T('Livello 2')], [0, T('Tutto')]].map(([v, l]) =>
            `<button class="${+f.livello === v ? 'on' : ''}" data-act="grafo-livello" data-v="${v}">${l}</button>`).join('')}
        </div>
        <button class="icona-btn" data-act="grafo-zoom" data-v="1" aria-label="${T('Ingrandisci')}">＋</button>
        <button class="icona-btn" data-act="grafo-zoom" data-v="-1" aria-label="${T('Riduci')}">－</button>
        <button class="icona-btn" data-act="grafo-zoom" data-v="0" aria-label="${T('Adatta')}" title="${T('Adatta')}">⤢</button>
      </div>
      <div class="grafo-legenda">${TIPI_MEM.map(([k, etichetta]) =>
        `<span class="${k}"><i></i>${cap(T(etichetta))} ${conta[k] || 0}</span>`).join('')}
        <span>${T('pieno vuol dire che il richiamo può portarla in contesto')}</span></div>
    </div>`;

  return `
  <div class="view-tools">
    <div class="seg" role="group" aria-label="${T('Vista')}">
      <button class="${f.modo !== 'grafo' ? 'on' : ''}" data-filter="memoria.modo" data-value="elenco">${T('Elenco')}</button>
      <button class="${f.modo === 'grafo' ? 'on' : ''}" data-filter="memoria.modo" data-value="grafo">${T('Grafo')}</button>
    </div>
    <select data-filter-select="memoria.lente" aria-label="${T('Mostra')}">${LENTI.map(([k, etichetta]) =>
      `<option value="${k}" ${f.lente === k ? 'selected' : ''}>${cap(T(etichetta))}</option>`).join('')}</select>
    <span class="faint">${conN('fatti_n', d.totale)}</span>
    <span class="spacer"></span>
    <button class="btn" data-act="mem-prova-apri">${T('Prova la memoria')}</button>
  </div>
  <div class="prova-mem" id="prova-mem" hidden>
    <div class="sub" style="margin-bottom:6px">${T('scrivi una frase e guarda cosa ti richiamerebbe')}</div>
    <div class="inline-form">
      <input type="text" id="mfrase" autocomplete="off" aria-label="${T('Prova la memoria')}"
        placeholder="${T('una frase qualsiasi, come la scriveresti a Claude')}">
      <button class="primary" data-act="mprova">${T('Prova')}</button>
    </div>
    <div id="mesito"></div>
  </div>
  <div class="md-view" data-lista="memoria">
    ${f.modo === 'grafo' ? grafo : `<div class="lista">${elenco}</div>`}
    <aside class="dettaglio" id="dettaglio" aria-live="polite"></aside>
  </div>`;
};

DETTAGLI.memoria = async (nome) => {
  const n = ((state.mappa || {}).nodi || []).find((x) => x.nome === nome);
  if (!n) return `<div class="vuoto">${T('Scegli una memoria')}</div>`;
  let corpo = '';
  try { corpo = (await api('/api/knowledge?name=' + encodeURIComponent(nome))).body || ''; } catch (e) { /* solo la descrizione */ }
  // il corpo di una memoria comincia spesso con il titolo che qui e' gia' sopra
  corpo = corpo.replace(/^\s*#{1,3}\s+[^\n]*\n/, '');
  const archi = state.mappa.archi;
  const verso = archi.filter((a) => a.da === nome).map((a) => a.a);
  const da = archi.filter((a) => a.a === nome).map((a) => a.da);
  const legami = [...new Set([...verso, ...da])];
  const esiste = new Set(state.mappa.nodi.map((x) => x.nome));
  const tipoEt = (TIPI_MEM.find(([k]) => k === n.tipo) || [])[1];
  return `
    <button class="ghost indietro" data-act="indietro">‹ ${T('Indietro')}</button>
    <div class="sub"><span class="punto mnodo ${esc(n.tipo)}" style="display:inline-block;margin-right:6px"></span>${
      esc(cap(T(tipoEt || 'memoria')))}</div>
    <h2>${esc(n.nome)}</h2>
    ${n.descrizione ? `<p class="corpo">${esc(n.descrizione)}</p>` : ''}
    ${corpo.trim() && corpo.trim() !== (n.descrizione || '').trim() ? `<div class="md" style="margin-top:12px">${md(corpo)}</div>`
      : `<p class="faint" style="margin-top:12px">${T('Nessun testo oltre alla descrizione.')}</p>`}
    <dl class="campi">
      <div><dt>${T('Aggiornata')}</dt><dd>${esc(ago(n.aggiornata))}</dd></div>
      <div><dt>${T('Cartella')}</dt><dd>${esc((n.dove || n.cartelle || []).join(', ') || '-')}</dd></div>
      <div><dt>${T('Usata in')}</dt><dd>${n.richiamabile ? T('il richiamo può portarla in contesto') : T('nessuno, troppo corta')}</dd></div>
    </dl>
    <h3>${T('Legami')}</h3>
    ${legami.length ? `<div class="elenco legami">${legami.map((x) => esiste.has(x)
      ? `<div class="riga" data-memory="${esc(x)}"><div class="txt"><div class="t">${esc(x)}</div></div>${CHEV}</div>`
      : `<div class="riga"><div class="txt"><div class="t faint">${esc(x)}</div><div class="s">${T('link rotto')}</div></div></div>`).join('')}</div>`
      : `<p class="faint">${T('Nessun legame.')}</p>`}
    ${(state.filters.memoria || {}).modo === 'grafo' ? '' : `<div class="azioni"><button class="btn" data-act="mem-grafo" data-nome="${esc(n.nome)}">${T('Mostra nel grafo')}</button></div>`}`;
};

/* ---------------------------------------------------------------- grafo */
/* Le forze sono quattro: i nodi si respingono, un legame e' una molla, i tipi
   si tirano verso il proprio angolo (senza questo un archivio senza legami e'
   una nuvola), tutto e' tenuto vicino al centro. Il calore cala da solo e il
   disegno si ferma; trascinare un nodo lo riaccende. Le posizioni iniziali
   vengono da un generatore deterministico (dal nome), quindi lo stesso archivio
   parte sempre uguale. */
function seme(testo) {
  let h = 2166136261;
  for (let i = 0; i < testo.length; i++) { h ^= testo.charCodeAt(i); h = Math.imul(h, 16777619); }
  return () => { h = Math.imul(h ^ (h >>> 15), 2246822507); h ^= h >>> 13; return ((h >>> 0) % 100000) / 100000; };
}

function montaGrafo(host, m, opz) {
  const cv = document.createElement('canvas');
  cv.setAttribute('role', 'img');
  cv.setAttribute('aria-label', T('Grafo della memoria'));
  host.prepend(cv);
  const ctx = cv.getContext('2d');
  let W = 0, H = 0, dpr = 1, vivo = true, rAF = 0;
  const ridotto = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  const nodi = m.nodi.map((n) => ({
    id: n.nome, n, tipo: n.tipo, x: 0, y: 0, vx: 0, vy: 0, fisso: false, vis: 1, visT: 1, r: 6,
    spento: false,
  }));
  const per = new Map(nodi.map((n) => [n.id, n]));
  const archi = m.archi.map((a) => ({ a: per.get(a.da), b: per.get(a.a) }))
    .filter((e) => e.a && e.b && e.a !== e.b);
  const vicini = new Map(nodi.map((n) => [n.id, new Set()]));
  archi.forEach((e) => { vicini.get(e.a.id).add(e.b.id); vicini.get(e.b.id).add(e.a.id); });
  nodi.forEach((n) => { n.grado = Math.max(n.n.grado || 0, vicini.get(n.id).size); n.r = 5.5 + Math.min(n.grado, 14) * 0.9; });

  // un angolo per tipo presente
  const tipi = TIPI_MEM.map(([k]) => k).filter((k) => nodi.some((n) => n.tipo === k));
  nodi.forEach((n) => { if (!tipi.includes(n.tipo)) tipi.push(n.tipo); });
  const R_CL = tipi.length > 1 ? 300 : 0;
  const centro = {};
  tipi.forEach((t, i) => {
    const a = -Math.PI / 2 + (i / tipi.length) * Math.PI * 2 + 0.4;
    centro[t] = { x: Math.cos(a) * R_CL, y: Math.sin(a) * R_CL * 0.8 };
  });
  nodi.forEach((n) => {
    const r = seme(n.id), c = centro[n.tipo] || { x: 0, y: 0 };
    n.x = c.x + (r() - 0.5) * 200; n.y = c.y + (r() - 0.5) * 200;
  });

  let alpha = 1;
  const cam = { x: 0, y: 0, k: 1 }, mira = { x: 0, y: 0, k: 1 };
  let auto = true, sel = null, hov = null, drag = null, livello = +(opz.livello || 0);
  const colori = {};
  const leggiColori = () => {
    const cs = getComputedStyle(host);
    const v = (n) => cs.getPropertyValue(n).trim();
    Object.assign(colori, {
      bg: v('--bg') || '#fff', testo: v('--text') || '#000', testo2: v('--text-2') || '#666',
      linea: v('--line-strong') || '#bbb', accento: v('--accent') || '#06f',
      feedback: v('--t-feedback') || '#e90', user: v('--t-user') || '#27e',
      reference: v('--t-reference') || '#2a5', project: v('--t-project') || '#a4d',
      font: cs.fontFamily,
    });
  };
  leggiColori();
  const colore = (t) => colori[t] || colori.testo2;

  const partecipa = (n) => n.visT > 0 || n.vis > 0.03;

  function passo() {
    const P = nodi.filter(partecipa);
    for (let i = 0; i < P.length; i++) {
      const a = P[i];
      for (let j = i + 1; j < P.length; j++) {
        const b = P[j];
        let dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy;
        if (d2 > 160000) continue;
        if (d2 < 0.01) { dx = (Math.random() - 0.5); dy = (Math.random() - 0.5); d2 = dx * dx + dy * dy + 0.01; }
        const d = Math.sqrt(d2);
        let f = (6400 * alpha) / d2;
        const min = a.r + b.r + 16;
        if (d < min) f += (min - d) * 0.06;
        const fx = (dx / d) * f, fy = (dy / d) * f;
        a.vx -= fx; a.vy -= fy; b.vx += fx; b.vy += fy;
      }
    }
    for (const e of archi) {
      if (!partecipa(e.a) || !partecipa(e.b)) continue;
      const dx = e.b.x - e.a.x, dy = e.b.y - e.a.y, d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = (d - (84 + e.a.r + e.b.r)) * 0.035 * (0.4 + alpha);
      const fx = (dx / d) * f, fy = (dy / d) * f;
      e.a.vx += fx; e.a.vy += fy; e.b.vx -= fx; e.b.vy -= fy;
    }
    for (const n of P) {
      const c = centro[n.tipo] || { x: 0, y: 0 };
      n.vx += (c.x - n.x) * 0.022 * (0.3 + alpha) - n.x * 0.0015;
      n.vy += (c.y - n.y) * 0.022 * (0.3 + alpha) - n.y * 0.0015;
      n.vx *= 0.8; n.vy *= 0.8;
      if (!n.fisso) { n.x += n.vx; n.y += n.vy; } else { n.vx = 0; n.vy = 0; }
    }
    alpha = Math.max(0.012, alpha * 0.985);
  }

  function ricalcolaVisibili() {
    const s = sel ? per.get(sel) : null;
    let dentro = null;
    if (livello > 0 && s) {
      dentro = new Set([s.id]);
      let fronte = [s.id];
      for (let l = 0; l < livello; l++) {
        const prox = [];
        fronte.forEach((id) => vicini.get(id).forEach((v) => { if (!dentro.has(v)) { dentro.add(v); prox.push(v); } }));
        fronte = prox;
      }
    }
    nodi.forEach((n) => { n.visT = (!dentro || dentro.has(n.id)) ? 1 : 0; });
    alpha = Math.max(alpha, 0.55);
    auto = true;
    sveglia();
  }

  function adatta(subito) {
    const V = nodi.filter((n) => n.visT > 0);
    if (!V.length || !W || !H) return;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    V.forEach((n) => { x0 = Math.min(x0, n.x - n.r); y0 = Math.min(y0, n.y - n.r); x1 = Math.max(x1, n.x + n.r); y1 = Math.max(y1, n.y + n.r); });
    const bw = Math.max(80, x1 - x0) + 110, bh = Math.max(80, y1 - y0) + 100;
    mira.k = Math.max(0.25, Math.min(2.2, Math.min(W / bw, H / bh)));
    mira.x = (x0 + x1) / 2; mira.y = (y0 + y1) / 2;
    if (subito) Object.assign(cam, mira);
  }

  const aSchermo = (x, y) => [(x - cam.x) * cam.k + W / 2, (y - cam.y) * cam.k + H / 2];
  const aMondo = (sx, sy) => [(sx - W / 2) / cam.k + cam.x, (sy - H / 2) / cam.k + cam.y];

  function disegna() {
    if (!W || !H) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const vicSel = sel ? vicini.get(sel) : null;
    const fuoco = hov;                       // si sfuma il resto solo sotto il puntatore
    const evidenza = hov || (sel && per.get(sel)); // i legami del nodo scelto si accendono sempre
    const vicFuoco = fuoco ? vicini.get(fuoco.id) : null;
    const fioco = (n) => fuoco ? (n === fuoco || vicFuoco.has(n.id) ? 1 : 0.3) : 1;

    ctx.save();
    ctx.translate(W / 2, H / 2); ctx.scale(cam.k, cam.k); ctx.translate(-cam.x, -cam.y);
    ctx.lineCap = 'round';
    for (const e of archi) {
      const v = Math.min(e.a.vis, e.b.vis);
      if (v < 0.03) continue;
      const evid = evidenza && (e.a === evidenza || e.b === evidenza);
      ctx.globalAlpha = v * (evid ? 0.95 : (fuoco ? 0.12 : 0.5));
      ctx.strokeStyle = evid ? colori.accento : colori.linea;
      ctx.lineWidth = (evid ? 2 : 1.2) / cam.k * Math.min(cam.k, 1.4);
      ctx.beginPath(); ctx.moveTo(e.a.x, e.a.y); ctx.lineTo(e.b.x, e.b.y); ctx.stroke();
    }
    for (const n of nodi) {
      if (n.vis < 0.03) continue;
      ctx.globalAlpha = n.vis * fioco(n) * (n.spento ? 0.2 : 1);
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      if (n.n.richiamabile) { ctx.fillStyle = colore(n.tipo); ctx.fill(); }
      else { ctx.fillStyle = colori.bg; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = colore(n.tipo); ctx.stroke(); }
      if (n.id === sel || n === hov) {
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 4, 0, Math.PI * 2);
        ctx.lineWidth = 2; ctx.strokeStyle = n.id === sel ? colori.accento : colori.testo2; ctx.stroke();
      }
    }
    ctx.restore();

    // le etichette in pixel di schermo, per restare nitide: prima chi conta
    // (scelto, sotto il puntatore, vicino), poi per numero di legami; un nome
    // che finirebbe sopra un altro non si scrive
    const candidati = nodi.filter((n) => n.vis > 0.5 && !n.spento).map((n) => {
      let prio = n.grado;
      if (n.id === sel) prio = 1000;
      else if (n === hov) prio = 900;
      else if ((vicSel && vicSel.has(n.id)) || (hov && vicini.get(hov.id).has(n.id))) prio = 500 + n.grado;
      return { n, prio };
    }).sort((p, q) => q.prio - p.prio);
    const presi = [];
    ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    ctx.font = `12px ${colori.font}`;
    let scritte = 0;
    for (const { n, prio } of candidati) {
      const importante = prio >= 500;
      // solo il nodo scelto o sotto il puntatore si scrive comunque: i suoi
      // vicini (a decine, in un grafo fitto) cedono il posto se si sovrapporrebbero
      const forte = prio >= 900;
      if (!importante && cam.k < 0.55 && n.grado < 3) continue;
      if (scritte > 80) break;
      const [sx, sy] = aSchermo(n.x, n.y);
      if (sx < -40 || sx > W + 40 || sy < -20 || sy > H + 20) continue;
      const nome = n.id.length > 26 ? n.id.slice(0, 25) + '…' : n.id;
      // il riquadro e' piu' largo e alto della scritta: due nomi non si toccano
      const w = ctx.measureText(nome).width + 14, y = sy + n.r * cam.k + 15;
      const box = [sx - w / 2, y - 14, sx + w / 2, y + 6];
      if (!forte && presi.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) continue;
      presi.push(box); scritte++;
      ctx.globalAlpha = n.vis * fioco(n);
      ctx.lineWidth = 4; ctx.strokeStyle = colori.bg; ctx.lineJoin = 'round';
      ctx.strokeText(nome, sx, y);
      ctx.fillStyle = importante ? colori.testo : colori.testo2;
      ctx.fillText(nome, sx, y);
    }
    // nomi dei tipi sopra ogni nube: dicono cosa raggruppa. Si scrivono per ultimi,
    // con l'alone del fondo, cosi' nessun nome di nodo li copre
    if (tipi.length > 1) {
      ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic'; ctx.lineJoin = 'round';
      ctx.font = `700 11px ${colori.font}`;
      tipi.forEach((t) => {
        const gr = nodi.filter((n) => n.tipo === t && n.vis > 0.5);
        if (!gr.length) return;
        let cx = 0, alto = Infinity;
        gr.forEach((n) => { cx += n.x; alto = Math.min(alto, n.y - n.r); });
        cx /= gr.length;
        const [sx, sy] = aSchermo(cx, alto);
        const et = cap(T((TIPI_MEM.find(([k]) => k === t) || [0, 'memoria'])[1])).toUpperCase().split('').join('\u200a');
        // se finirebbe sopra il nome di un nodo, sale finche' trova posto
        const largo = ctx.measureText(et).width + 6;
        let y = sy - 18;
        for (let prova = 0; prova < 6; prova++) {
          const box = [sx - largo / 2, y - 12, sx + largo / 2, y + 3];
          if (!presi.some((p) => box[0] < p[2] && box[2] > p[0] && box[1] < p[3] && box[3] > p[1])) break;
          y -= 14;
        }
        ctx.globalAlpha = 1; ctx.lineWidth = 5; ctx.strokeStyle = colori.bg; ctx.strokeText(et, sx, y);
        ctx.fillStyle = colore(t); ctx.fillText(et, sx, y);
      });
    }
    ctx.globalAlpha = 1;
  }

  function frame() {
    rAF = 0;
    if (!vivo) return;
    let mosso = false;
    if (alpha > 0.0125 || drag) { passo(); mosso = true; }
    for (const n of nodi) {
      const t = n.visT;
      if (Math.abs(n.vis - t) > 0.01) { n.vis += (t - n.vis) * 0.16; mosso = true; } else n.vis = t;
    }
    if (auto) adatta(false);
    const dk = mira.k - cam.k, dx = mira.x - cam.x, dy = mira.y - cam.y;
    if (Math.abs(dk) > 0.002 || Math.abs(dx) > 0.3 || Math.abs(dy) > 0.3) {
      cam.k += dk * 0.18; cam.x += dx * 0.18; cam.y += dy * 0.18; mosso = true;
    }
    disegna();
    if (mosso || drag) sveglia();
  }
  function sveglia() { if (!rAF && vivo) rAF = requestAnimationFrame(frame); }

  function dimensiona() {
    const r = host.getBoundingClientRect();
    W = Math.max(0, Math.floor(r.width)); H = Math.max(0, Math.floor(r.height));
    dpr = Math.min(2, window.devicePixelRatio || 1);
    cv.width = Math.max(1, Math.floor(W * dpr)); cv.height = Math.max(1, Math.floor(H * dpr));
    if (auto) { adatta(true); }
    disegna(); sveglia();
  }
  const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(dimensiona) : null;
  if (ro) ro.observe(host); else window.addEventListener('resize', dimensiona);
  const suTema = () => { leggiColori(); disegna(); };
  window.addEventListener('plancia-tema', suTema);

  // il primo disegno e' gia' assestato: si fa girare la fisica prima di mostrarla
  const giri = ridotto ? 500 : 340;
  for (let i = 0; i < giri; i++) passo();
  alpha = ridotto ? 0.012 : 0.05;

  // ------------------------------------------------ puntatore
  const punti = new Map();
  let pinch = null;
  const pos = (e) => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  function colpisci(sx, sy) {
    const [wx, wy] = aMondo(sx, sy);
    for (let i = nodi.length - 1; i >= 0; i--) {
      const n = nodi[i];
      if (n.vis < 0.4) continue;
      const r = n.r + 5 / cam.k;
      if ((wx - n.x) ** 2 + (wy - n.y) ** 2 <= r * r) return n;
    }
    return null;
  }
  cv.addEventListener('pointerdown', (e) => {
    try { cv.setPointerCapture(e.pointerId); } catch (err) { /* puntatore sintetico o gia' rilasciato */ }
    const [sx, sy] = pos(e);
    punti.set(e.pointerId, [sx, sy]);
    if (punti.size === 2) {
      const [p, q] = [...punti.values()];
      pinch = { d: Math.hypot(p[0] - q[0], p[1] - q[1]), k: cam.k };
      drag = null; auto = false; return;
    }
    const n = colpisci(sx, sy);
    if (n) { drag = { nodo: n, sx, sy, mosso: false }; n.fisso = true; }
    else drag = { pan: true, sx, sy, cx: cam.x, cy: cam.y, mosso: false };
    cv.classList.add('trascina'); sveglia();
  });
  cv.addEventListener('pointermove', (e) => {
    const [sx, sy] = pos(e);
    if (punti.has(e.pointerId)) punti.set(e.pointerId, [sx, sy]);
    if (pinch && punti.size === 2) {
      const [p, q] = [...punti.values()];
      const k = Math.max(0.15, Math.min(4, pinch.k * Math.hypot(p[0] - q[0], p[1] - q[1]) / pinch.d));
      cam.k = mira.k = k; disegna(); return;
    }
    if (drag) {
      if (Math.hypot(sx - drag.sx, sy - drag.sy) > 4) drag.mosso = true;
      if (drag.nodo && drag.mosso) {
        const [wx, wy] = aMondo(sx, sy);
        drag.nodo.x = wx; drag.nodo.y = wy; drag.nodo.vx = drag.nodo.vy = 0;
        alpha = Math.max(alpha, 0.4);
      } else if (drag.pan && drag.mosso) {
        auto = false;
        cam.x = mira.x = drag.cx - (sx - drag.sx) / cam.k;
        cam.y = mira.y = drag.cy - (sy - drag.sy) / cam.k;
      }
      sveglia(); return;
    }
    const n = colpisci(sx, sy);
    if (n !== hov) { hov = n; cv.classList.toggle('su-nodo', !!n); disegna(); }
  });
  const fine = (e) => {
    punti.delete(e.pointerId);
    if (punti.size < 2) pinch = null;
    if (drag) {
      if (drag.nodo) {
        drag.nodo.fisso = false;
        if (!drag.mosso) { if (opz.onSeleziona) opz.onSeleziona(drag.nodo.id); }
      }
      drag = null; cv.classList.remove('trascina'); sveglia();
    }
  };
  cv.addEventListener('pointerup', fine);
  cv.addEventListener('pointercancel', fine);
  cv.addEventListener('pointerleave', () => { if (hov && !drag) { hov = null; cv.classList.remove('su-nodo'); disegna(); } });
  cv.addEventListener('wheel', (e) => {
    e.preventDefault();
    const [sx, sy] = pos(e);
    const [wx, wy] = aMondo(sx, sy);
    const k = Math.max(0.15, Math.min(4, cam.k * Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0018))));
    cam.k = mira.k = k;
    cam.x = mira.x = wx - (sx - W / 2) / k;
    cam.y = mira.y = wy - (sy - H / 2) / k;
    auto = false; disegna();
  }, { passive: false });
  cv.addEventListener('dblclick', (e) => {
    const [sx, sy] = pos(e);
    if (!colpisci(sx, sy)) { auto = true; adatta(false); sveglia(); }
  });

  // ------------------------------------------------ comandi dall'esterno
  const api_ = {
    seleziona(id) {
      sel = per.has(id) ? id : null;
      if (livello > 0) ricalcolaVisibili(); else disegna();
    },
    setLivello(v) { livello = +v; opz.livello = livello; ricalcolaVisibili(); },
    zoom(dir) {
      auto = false;
      if (dir === 0) { auto = true; adatta(false); sveglia(); return; }
      const k = Math.max(0.15, Math.min(4, cam.k * (dir > 0 ? 1.3 : 1 / 1.3)));
      mira.k = k; mira.x = cam.x; mira.y = cam.y; sveglia();
    },
    // per le prove: dove sta un nodo sullo schermo, quanto e' ingrandito il disegno
    posizione(id) { const n = per.get(id); return n ? aSchermo(n.x, n.y) : null; },
    ingrandimento() { return cam.k; },
    lente(acceso) { nodi.forEach((n) => { n.spento = !!acceso && !acceso.has(n.id); }); disegna(); },
    distruggi() {
      vivo = false; if (rAF) cancelAnimationFrame(rAF);
      if (ro) ro.disconnect(); else window.removeEventListener('resize', dimensiona);
      window.removeEventListener('plancia-tema', suTema);
      cv.remove();
    },
    nodi,
  };
  sel = opz.sel && per.has(opz.sel) ? opz.sel : null;
  if (opz.acceso) api_.lente(opz.acceso);
  ricalcolaVisibili();
  nodi.forEach((n) => { n.vis = n.visT; });
  dimensiona();
  return api_;
}

function distruggiGrafo() {
  if (state.grafo) { state.grafo.distruggi(); state.grafo = null; }
}

/* Dopo che la vista e' nel documento: il canvas non sta nel markup. */
function dopoMemoria() {
  const f = state.filters.memoria;
  distruggiGrafo();
  if (!f || f.modo !== 'grafo' || !state.mappa) return;
  const host = $('#grafo-box');
  if (!host) return;
  state.grafo = montaGrafo(host, state.mappa, {
    livello: f.livello, sel: state.sel.memoria, acceso: accesiMem(state.mappa, f.lente),
    onSeleziona: (id) => seleziona('memoria', id),
  });
}

async function bloccoCapacita(soloCorpo) {
  const rows = await api('/api/capabilities');
  const groups = { skill: T('Skill'), plugin: T('Plugin'), routine: T('Routine programmate') };
  return `
  ${soloCorpo ? '' : `<div class="view-head"><h1>${T('Capacità')}</h1><p>${T('cosa sa fare il tuo Claude Code')}</p></div>`}
  ${Object.entries(groups).map(([kind, label]) => {
    const items = rows.filter((r) => r.kind === kind);
    if (!items.length) return '';
    return `<h3 style="margin:18px 0 10px;color:var(--faint);font-size:12px;text-transform:uppercase;letter-spacing:.05em">${label} · ${items.length}</h3>
    <div class="panel"><div class="panel-body tight">
      ${items.map((r) => `<div class="riga"><div class="main">
        <div class="title">${esc(r.name)}</div>
        <div class="sub clamp2">${esc(r.description || '')}</div>
      </div><div class="side"><span class="tag mono">${ago(r.updated_at)}</span></div></div>`).join('')}
    </div></div>`;
  }).join('')}`;
};

views.briefing = async () => {
  const text = await api('/api/briefing');
  return `<div class="view-head"><h1>${T('Briefing')}</h1><p>${T('quello che ogni nuova sessione di Claude riceve')}</p>
    <span class="spacer"></span><button class="ghost" data-act="copy-briefing">${T('Copia')}</button></div>
  <div class="panel"><div class="panel-body md" id="briefing-md">${md(text)}</div></div>
  <textarea id="briefing-raw" hidden>${esc(text)}</textarea>`;
};

/* ---------------------------------------------------------------- memoria */
/* LOTTO-L4-MEMORIA: "salvare in memoria gli ultimi aggiornamenti... fare in
   modo che non sia mai vuota" (Eugenio, 18/09/2026). Ogni disegno riuscito
   di una vista salva l'innerHTML di #view sotto una chiave versionata, così
   route() può ridipingerlo SUBITO alla riapertura invece di mostrare
   "carico…" o, peggio, "errore: …" quando il server non risponde più. La
   versione (MEMORIA_VERSIONE, nella chiave stessa) è la valvola: un domani
   che cambia il markup delle card cambia questa costante, e la memoria
   vecchia (chiave vecchia) resta per sempre ignorata invece di riaprire un
   html che il nuovo app.js non saprebbe più interpretare. Il tetto in byte
   evita che una vista anomala (un errore non filtrato che finisce nel testo,
   un elenco lunghissimo) riempia silenziosamente tutto il localStorage
   dell'origine: oltre non si salva, e lo si scrive in console una sola
   volta (memoriaAvvisato), non a ogni disegno. */
const MEMORIA_VERSIONE = 'plancia-memoria-v1';
const MEMORIA_TETTO = 400 * 1024; // byte, sulla voce intera (json compreso)
let memoriaAvvisato = false;
// Con i compartimenti attivi la memoria di una vista e' per compartimento: la
// vista di uno non deve comparire un istante nell'altro mentre il fetch arriva.
const memoriaChiave = (vista, lingua) => `${MEMORIA_VERSIONE}:${vista}:${lingua}`
  + (state.compartimenti && state.compartimenti.attivo
    ? ':c:' + (state.compartimento || state.compartimenti.predefinito) : '');

function memoriaSalva(vista, html) {
  // La vista 'cerca' con una query è un indirizzo (il testo cercato), non
  // uno stato della vista: riaprirla mostrerebbe i risultati di un'altra
  // ricerca al posto della casella vuota, più fuorviante che comodo.
  if (vista === 'cerca' && ((state.filters.cerca || {}).q || '').trim()) return;
  try {
    const voce = JSON.stringify({ quando: new Date().toISOString(), html });
    if (voce.length > MEMORIA_TETTO) {
      if (!memoriaAvvisato) {
        console.warn('plancia-memoria: voce oltre 400KB, non salvata (' + vista + ')');
        memoriaAvvisato = true;
      }
      return;
    }
    storageSet(memoriaChiave(vista, UILANG), voce);
  } catch (e) { /* JSON.stringify su qualcosa di strano: pazienza, come sopra */ }
}

function memoriaLeggi(vista, lingua) {
  const grezzo = storageGet(memoriaChiave(vista, lingua));
  if (!grezzo) return null;
  try {
    const v = JSON.parse(grezzo);
    return (v && typeof v.html === 'string') ? v : null;
  } catch (e) { return null; }
}

/* La riga di stato: "aggiornato alle 21:59" nel sottotitolo della testata, e
   da nessun'altra parte. Fresca, quella di prima mentre si aggiorna, oppure
   la memoria con il server che non risponde. `stato` e' 'aggiorno' (memoria in
   vista, fetch in corso), 'fresco' (fetch riuscito) o 'rotto' (fetch caduto,
   la memoria resta a schermo). Fuori da questi tre (prima apertura) resta vuota:
   non c'e' ancora niente di cui dare conto. */
const oraCorta = (ts) => (ts ? new Date(ts) : new Date())
  .toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' });

function spiaAggiorna(stato, quando) {
  const el = $('#tb-sub');
  if (!el) return;
  el.classList.toggle('avviso', stato === 'rotto');
  if (!stato) { el.textContent = ''; state.subTesto = ''; return; }
  if (stato === 'aggiorno') el.textContent = state.subTesto || T('spia_aggiorno');
  else if (stato === 'rotto') el.textContent = state.subTesto = fmt('spia_memoria', { ora: oraCorta(quando) });
  else el.textContent = state.subTesto = fmt('spia_aggiornato', { ora: oraCorta(quando) });
  el.style.color = stato === 'rotto' ? 'var(--warn)' : '';
}

/* ---------------------------------------------------------------- selezione */
/* Elenco e dettaglio stanno nella stessa pagina: scegliere una riga non
   ridisegna la vista, cambia solo il pannello a destra e l'indirizzo
   (replaceState, quindi niente hashchange e niente nuova richiesta). */
async function seleziona(lista, id, opz = {}) {
  state.sel[lista] = id;
  const cont = $(`[data-lista="${lista}"]`);
  if (!cont) return;
  $$('[data-sel]', cont).forEach((el) => {
    const on = el.dataset.sel === String(id);
    el.classList.toggle('sel', on);
    if (on && opz.scorri) el.scrollIntoView({ block: 'nearest' });
  });
  if (opz.apri !== false) cont.classList.add('aperto'); // sugli schermi stretti il dettaglio copre l'elenco
  const det = $('#dettaglio', cont);
  if (!det) return;
  const turno = (state.turnoSel = (state.turnoSel || 0) + 1);
  if (id == null) { det.innerHTML = ''; return; }
  let html;
  try { html = await DETTAGLI[lista](id); } catch (err) { html = `<div class="vuoto">${esc(err.message)}</div>`; }
  if (turno !== state.turnoSel) return; // nel frattempo ne e' stata scelta un'altra
  det.innerHTML = html;
  det.scrollTop = 0;
  if (opz.hash !== false) {
    try { history.replaceState(null, '', '#/' + lista + '/' + encodeURIComponent(id)); } catch (e) { /* pazienza */ }
  }
  if (lista === 'memoria' && state.grafo) state.grafo.seleziona(id);
}

/* ---------------------------------------------------------------- router */
const TITOLI = { oggi: 'Oggi', lavagna: 'Task', progetti: 'Progetti', social: 'Social', memoria: 'Memoria',
                 archivio: 'Archivio', briefing: 'Briefing', benvenuto: 'Guida di Plancia' };
const VISTE_MD = new Set(['lavagna', 'progetti', 'social', 'memoria']);
/* Le vecchie viste sono diventate altro: i vecchi indirizzi continuano a
   funzionare, portano dove il contenuto e' finito. */
const REDIREZIONI = { task: 'lavagna', riepilogo: 'oggi', sessioni: 'archivio', agenti: 'archivio',
                      conoscenza: 'memoria', capacita: 'archivio' };

async function route() {
  // con la ricerca aperta il contenuto e' quello dei risultati: un
  // aggiornamento di fondo non deve cancellarli
  if (ric.aperta) { disegnaRisultati(); return; }
  distruggiGrafo();
  const hash = location.hash.replace(/^#\//, '') || 'oggi';
  let [name, ...resto] = hash.split('/');
  let param = resto.length ? decodeURIComponent(resto.join('/')) : null;
  // `#/cerca?q=...`: una ricerca resta un indirizzo che si salva e si riapre.
  const dom = name.indexOf('?');
  let domanda = null;
  if (dom >= 0) {
    domanda = new URLSearchParams(name.slice(dom + 1)).get('q') || '';
    name = name.slice(0, dom);
  }
  if (name === 'cerca') {
    const inp = $('#cerca-q');
    if (inp) { inp.value = domanda || ''; if (domanda) cercaOra(domanda); else inp.focus(); }
    if (domanda) return;
    name = state.view || 'oggi';
  }
  if (REDIREZIONI[name]) {
    if (name === 'sessioni' || name === 'agenti' || name === 'capacita') {
      state.filters.archivio = { seg: name === 'agenti' ? 'agenti' : name === 'capacita' ? 'capacita' : 'sessioni' };
    }
    name = REDIREZIONI[name];
  }
  if (!views[name]) name = 'oggi';
  const fn = views[name];
  if (param != null && DETTAGLI[name]) state.sel[name] = param;
  state.view = name;
  $$('.rail nav a').forEach((a) => a.classList.toggle('on', a.dataset.view === name));
  const titolo = $('#tb-titolo');
  if (titolo) titolo.textContent = T(TITOLI[name] || 'Oggi');

  // Se c'e' memoria di questa vista (in questa lingua) va a schermo SUBITO e
  // resta interattiva per tutto il tempo che il fetch qui sotto ci mette a
  // finire, riuscito o no: la dashboard non e' mai vuota. Senza memoria (prima
  // apertura di questa vista) si mostra un "carico" e basta.
  const view = $('#view');
  view.dataset.layout = VISTE_MD.has(name) ? 'md' : '';
  const memoria = memoriaLeggi(name, UILANG);
  if (memoria) {
    view.innerHTML = memoria.html;
    view.dataset.memoria = '1';
    spiaAggiorna('aggiorno');
  } else {
    delete view.dataset.memoria;
    view.innerHTML = `<div class="vuoto">${T('carico…')}</div>`;
    spiaAggiorna(null);
  }
  const scorriVia = view.scrollTop;

  try {
    const chiamatePrima = apiChiamateOk;
    const html = await fn();
    if (ric.aperta) return; // mentre si aspettava e' stata aperta la ricerca
    if (state.view !== name) return; // ...o si e' cambiata vista
    if (!memoria || html !== memoria.html) view.innerHTML = html;
    delete view.dataset.memoria;
    if (memoria) view.scrollTop = scorriVia;
    memoriaSalva(name, html);
    if (VISTE_MD.has(name)) {
      if (name === 'memoria') dopoMemoria();
      seleziona(name, state.sel[name], { hash: param != null, apri: false, scorri: true });
    }
    // "aggiornato alle" dice QUANDO SONO STATI PRESI I DATI, non quando e'
    // finito questo giro di route(). fn() puo' arrivare qui senza aver
    // chiamato api() nemmeno una volta (views.progetti riusa state.overview se
    // c'e' gia'): in quel caso quello a schermo e' la stessa istantanea di
    // prima, e la riga deve dire l'ora di QUELLA (state.overviewQuando), non
    // "adesso". Se no, col server spento, mostrerebbe un orario falso.
    const fetchPartito = apiChiamateOk > chiamatePrima;
    spiaAggiorna('fresco', fetchPartito ? new Date() : (state.overviewQuando || new Date()));
    if (fetchPartito) state.ultimoOk = new Date();
  } catch (err) {
    if (state.view !== name) return;
    if (memoria) {
      // La memoria resta a schermo (niente "errore: ..." al suo posto): la
      // riga dice che il server non risponde e da quando sono i dati.
      spiaAggiorna('rotto', memoria.quando);
    } else {
      view.innerHTML = `<div class="vuoto">${T('errore: ')}${esc(err.message)}</div>`;
      spiaAggiorna(null);
    }
  }
  refreshBadges();
}

async function refreshBadges() {
  try {
    let d = state.overview;
    if (!d) { d = state.overview = await api('/api/overview?lang=' + UILANG); state.overviewQuando = new Date(); }
    const t = $('#badge-task');
    if (t) t.textContent = d.stats.lavagna_aperti || d.stats.task_aperti || '';
    const s = $('#badge-social');
    if (s) s.textContent = d.stats.post_in_coda || '';
    if (d.benvenuto && state.view !== 'benvenuto' && !state.benvenutoVisto) {
      state.benvenutoVisto = true;
      location.hash = '#/benvenuto';
    }
  } catch (e) { /* pazienza */ }
}

/* ---------------------------------------------------------------- azioni */
document.addEventListener('click', async (ev) => {
  const act = ev.target.closest('[data-act]');
  const proj = ev.target.closest('[data-project]');
  const mem = ev.target.closest('[data-memory]');

  if (act) {
    ev.preventDefault();
    const { act: name, id } = act.dataset;
    try {
      if (name === 'task-toggle') {
        const nuovo = act.dataset.status === 'fatto' ? 'aperto' : 'fatto';
        await api('/api/tasks/' + id, { method: 'PATCH', body: { status: nuovo } });
        if (nuovo === 'fatto') toast(T('task chiuso'));
        state.overview = null; ric.indiceP = null; await route();
      } else if (name === 'task-nuovo-apri') {
        const f = $('#task-form'); f.hidden = !f.hidden;
        if (!f.hidden) f.querySelector('input[name=title]').focus();
      } else if (name === 'indietro') {
        const c = act.closest('[data-lista]'); if (c) c.classList.remove('aperto');
      } else if (name === 'recap-espandi') {
        act.classList.toggle('aperto');
      } else if (name === 'ambito') {
        ric.ambito = act.dataset.v; disegnaRisultati();
      } else if (name === 'ordina') {
        const o = state.ordSess || (state.ordSess = { col: 'quando', dir: -1 });
        if (o.col === act.dataset.col) o.dir = -o.dir; else { o.col = act.dataset.col; o.dir = act.dataset.col === 'quando' ? -1 : 1; }
        await route();
      } else if (name === 'mem-prova-apri') {
        const b = $('#prova-mem'); b.hidden = !b.hidden;
        if (!b.hidden) $('#mfrase').focus();
      } else if (name === 'mem-lente') {
        const f = state.filters.memoria || (state.filters.memoria = { lente: '', modo: 'elenco', livello: 0 });
        f.lente = act.dataset.value; await route();
      } else if (name === 'mem-grafo') {
        const f = state.filters.memoria || (state.filters.memoria = { lente: '', modo: 'elenco', livello: 0 });
        f.modo = 'grafo'; f.livello = 1; f.lente = ''; state.sel.memoria = act.dataset.nome; await route();
      } else if (name === 'grafo-livello') {
        const f = state.filters.memoria; f.livello = +act.dataset.v;
        $$('[data-act="grafo-livello"]').forEach((b) => b.classList.toggle('on', +b.dataset.v === f.livello));
        if (state.grafo) state.grafo.setLivello(f.livello);
      } else if (name === 'grafo-zoom') {
        if (state.grafo) state.grafo.zoom(+act.dataset.v);
      } else if (name === 'task-cycle') {
        const next = { aperto: 'in corso', 'in corso': 'fatto', bloccato: 'in corso' }[act.dataset.status] || 'aperto';
        await api('/api/tasks/' + id, { method: 'PATCH', body: { status: next } });
        state.overview = null; await route();
      } else if (name === 'task-done') {
        await api('/api/tasks/' + id, { method: 'PATCH', body: { status: 'fatto' } });
        toast(T('task chiuso')); state.overview = null; await route();
      } else if (name === 'post-next') {
        await api('/api/posts/' + id, { method: 'PATCH', body: { status: act.dataset.next } });
        state.overview = null; await route();
      } else if (name === 'mprova') {
        // La prova del richiamo. Mostra anche chi ha perso e di quanto: senza
        // gli scartati non si capisce se una memoria non arriva perché è
        // scritta male o perché quella frase non la riguardava.
        const frase = ($('#mfrase') || {}).value || '';
        const esito = $('#mesito');
        esito.innerHTML = `<p class="sub">${T('carico…')}</p>`;
        const r = await api('/api/memoria/prova?q=' + encodeURIComponent(frase));
        const riga = (x, preso) => `<div class="mriga${preso ? ' preso' : ''}"
          data-memory="${esc(x.nome)}"><span class="num">${x.punteggio}</span>
          <span class="mnome">${esc(x.nome)}</span>
          <span class="sub clamp">${esc(x.descrizione || '')}</span></div>`;
        if (r.corta) {
          esito.innerHTML = `<p class="sub">${T('troppo corta per dire di cosa parla')}</p>`;
        } else if (!r.presi.length && !r.scartati.length) {
          esito.innerHTML = `<p class="sub">${T('niente sopra la soglia, e va bene così')}</p>`;
        } else {
          esito.innerHTML = (r.presi.length
            ? `<div class="label">${r.presi.length} ${T('va in contesto')}</div>`
              + r.presi.map((x) => riga(x, true)).join('')
            : `<p class="sub">${T('niente sopra la soglia, e va bene così')}</p>`)
            + (r.scartati.length
              ? `<div class="label" style="margin-top:10px">${T('scartate')} · ${
                T('soglia')} ${r.soglia}</div>`
                + r.scartati.map((x) => riga(x, false)).join('')
              : '');
        }
      } else if (name === 'post-new') {
        const box = $('#post-form'); box.hidden = !box.hidden; if (!box.hidden) box.querySelector('textarea').focus();
      } else if (name === 'post-edit') {
        const url = prompt('URL del post pubblicato (vuoto per annullare)');
        if (url) { await api('/api/posts/' + id, { method: 'PATCH', body: { url, status: 'pubblicato' } }); await route(); }
      } else if (name === 'copy-resume') {
        const cwd = act.dataset.cwd;
        const cmd = (cwd ? `cd ${JSON.stringify(cwd)} && ` : '') + `claude --resume ${act.dataset.id}`;
        await navigator.clipboard.writeText(cmd);
        toast(T('comando copiato'));
      } else if (name === 'passo') {
        state.passo = +act.dataset.n;
        state.vistaPrima = 'benvenuto';
        await route();
      } else if (name === 'prova-passo') {
        if (act.dataset.url) {
          location.href = act.dataset.url;
        } else if (act.dataset.azione === 'manda-nuovo') {
          if (!state.progetti) state.progetti = await api('/api/projects');
          await apriRiprendi({});
        } else if (act.dataset.vista === 'cerca') {
          const q = $('#cerca-q'); q.focus(); q.select();
        } else if (act.dataset.vista) {
          location.hash = '#/' + act.dataset.vista;
        }
      } else if (name === 'fine-benvenuto') {
        await api('/api/onboarding', { method: 'POST', body: { fatto: true } });
        state.overview = null; location.hash = '#/oggi';
        if (state.view === 'oggi') await route();
      } else if (name === 'manda' || name === 'manda-nuovo') {
        if (!state.progetti) state.progetti = await api('/api/projects');
        await apriRiprendi(act.dataset);
      } else if (name === 'riprendi-copia') {
        await navigator.clipboard.writeText(act.dataset.messaggio);
        toast(T('copiato: incollalo nella sessione'));
      } else if (name === 'riprendi') {
        const r = await api('/api/riprendi/' + act.dataset.id, { method: 'POST', body: { apri: true } });
        // LOTTO-L3-RITOCCO punto 11: `apri()` (plancia/riprendi.py) mette
        // `errore` nella risposta quando il lanciatore va in timeout - prima
        // il toast diceva "Avviato" comunque, come se fosse partito per davvero.
        if (r.errore) {
          toast(T('non sono riuscito a lanciarlo') + ': ' + Tmot(r.errore), true);
        } else {
          toast((r.riga ? T('riprendi_avviato') + ': ' + r.riga : r.messaggio) || T('riprendi_avviato'));
        }
      } else if (name === 'riprendi-background') {
        // Il modulo "In background" del pulsante Riprendi (LOTTO-L3-RIPRENDI-UI
        // punto 2): con un task (il form porta data-task, un id vero) va sul
        // suo endpoint; senza task (blank da "manda-nuovo", o una riga della
        // lavagna con la sua sessione) resta /api/cantiere, con un interruttore
        // booleano `scrive` al posto del vecchio menu proposta/esegui.
        //
        // Il lavoro riprende la sessione ORIGINALE quando e' chiusa (stesso id,
        // sua cartella); su una sessione aperta altrove il server NON lancia
        // niente (lanciato:false) e torna il messaggio da incollare li'; su una
        // persa parte una sessione nuova. Il piano si legge nel cassetto prima
        // di premere (mostraPiano) e la risposta dice cosa e' successo.
        const form = act.closest('form');
        const dati = Object.fromEntries(new FormData(form).entries());
        if (!form.dataset.task && !(dati.titolo || '').trim()) return;
        const scrive = !!dati.scrive, copia = !!dati.copia;
        const r = form.dataset.task
          ? await api('/api/riprendi/' + form.dataset.task, { method: 'POST', body: {
              background: true, scrive, copia, istruzioni: dati.istruzioni } })
          : await api('/api/cantiere', { method: 'POST', body: {
              titolo: dati.titolo, istruzioni: dati.istruzioni, progetto: dati.progetto || null,
              agente: dati.agente, scrive, copia, task_id: null,
              sessione: form.dataset.sessione || null } });
        if (r.lanciato === false) {
          // Non e' partito niente (sessione aperta altrove): il cassetto resta
          // aperto con il piano e il messaggio da incollare, che si copia se si puo'.
          mostraPiano(r.piano, r.messaggio);
          let copiato = false;
          if (r.messaggio) {
            try { await navigator.clipboard.writeText(r.messaggio); copiato = true; } catch (e) { /* appunti negati */ }
          }
          toast(`${T('non partito')}: ${copiato ? T('copiato: incollalo nella sessione') : T('copia il messaggio qui sotto')}`, !copiato);
          return;
        }
        $('#drawer').hidden = true;
        toast(`${T('avviato in background')} → ${r.agente} #${r.run} · ${T('continua_' + (r.continua || 'nuova'))}`);
        location.hash = '#/lavagna';
        await route();
      } else if (name === 'lancio') {
        await apriLancio(act.dataset.id);
      } else if (name === 'annulla-lancio') {
        await api('/api/runs/' + act.dataset.id + '/annulla', { method: 'POST', body: {} });
        $('#drawer').hidden = true; await route();
      } else if (name === 'proposta') {
        if (act.dataset.tipo === 'manda') {
          // Vedi il commento sopra la card delle proposte (views.oggi): una
          // proposta "manda" apre il drawer, non lancia niente da sola.
          if (!state.progetti) state.progetti = await api('/api/projects');
          await apriRiprendi({ task: act.dataset.task || '', titolo: act.dataset.titolo,
            progetto: act.dataset.progetto });
          return;
        }
        act.disabled = true; act.textContent = '…';
        const r = await api('/api/jarvis', { method: 'POST',
          body: { testo: act.dataset.frase || 'fallo', lang: state.recap?.lang || '', voce: false } });
        toast(r.risposta || T('riprendi_avviato'));
        // Consigliata dal critico (costa una riga): "vai" torna un'azione di
        // navigazione che finora restava ignorata - il bottone "Apri"
        // mostrava il toast e basta, senza andare da nessuna parte.
        // "rilancia" non porta questa azione (solo la risposta testuale): lì
        // non si naviga, si ricarica Oggi come sempre.
        if (r.azione && r.azione.tipo === 'vai') location.hash = '#/' + r.azione.vista;
        else { state.overview = null; await route(); }
      } else if (name === 'recap-gen') {
        state.recap.data = null; await generaRecap(true);
      } else if (name === 'recap-play') {
        suona(state.recap && state.recap.audio, state.recap && state.recap.notaVoce);
      } else if (name === 'recap-stop') {
        const p = $('#player'); p.pause(); p.currentTime = 0; aggiornaBottoneVoce(false);
      } else if (name === 'chiedi-veloce') {
        await chiedi(act.dataset.q);
      } else if (name === 'copy-briefing') {
        await navigator.clipboard.writeText($('#briefing-raw').value);
        toast(T('briefing copiato'));
      } else if (name === 'prossimi-altri') {
        // Le righe oltre il tetto sono gia' nel markup (panelloProssimi), solo
        // nascoste: si rivelano senza una seconda chiamata, e il pulsante sparisce.
        $$('.prossimi [data-extra]').forEach((el) => { el.hidden = false; });
        act.remove();
      } else if (name === 'albero-toggle') {
        const padre = act.closest('.albero-padre');
        const figli = padre.querySelector('.albero-figli');
        const chiusa = !padre.classList.contains('chiusa');
        padre.classList.toggle('chiusa', chiusa);
        figli.hidden = chiusa;
        if (chiusa) chiusiAlbero.add(padre.dataset.key); else chiusiAlbero.delete(padre.dataset.key);
      } else if (name === 'cassetto-dopo') {
        // Chiuso di default, carica al primo click (punto 3 del lotto): la
        // lista non si rifà una seconda volta se l'utente chiude e riapre.
        const lista = act.nextElementSibling;
        if (lista.hidden) {
          if (!lista.dataset.caricato) {
            const extra = await api('/api/tasks?project=' + encodeURIComponent(act.dataset.key) + '&dopo=1');
            lista.innerHTML = taskRows(extra);
            lista.dataset.caricato = '1';
          }
          lista.hidden = false;
        } else {
          lista.hidden = true;
        }
      }
    } catch (err) { toast(err.message, true); }
    return;
  }
  // Le righe scelte nell'elenco (task, progetti, post, memorie): cambia solo il
  // dettaglio a destra, la vista non si ridisegna.
  const riga = ev.target.closest('[data-lista] [data-sel]');
  if (riga && !ev.target.closest('a, select, input, textarea')) {
    const cont = riga.closest('[data-lista]');
    seleziona(cont.dataset.lista, riga.dataset.sel).catch((err) => toast(err.message, true));
    return;
  }
  // Un rinvio a una memoria o a un progetto da un altro posto (un legame, la
  // proposta di una riga di Prossimi): porta nella vista giusta con la voce
  // gia' scelta. Nella stessa vista si limita a cambiare il dettaglio.
  if (mem && mem.dataset.memory) {
    ev.preventDefault();
    if (state.view === 'memoria' && $('[data-lista="memoria"]')) {
      seleziona('memoria', mem.dataset.memory).catch((err) => toast(err.message, true));
    } else {
      location.hash = '#/memoria/' + encodeURIComponent(mem.dataset.memory);
    }
    return;
  }
  if (proj && proj.dataset.project) {
    ev.preventDefault();
    if (state.view === 'progetti' && $('[data-lista="progetti"]')) {
      seleziona('progetti', proj.dataset.project).catch((err) => toast(err.message, true));
    } else {
      location.hash = '#/progetti/' + encodeURIComponent(proj.dataset.project);
    }
    return;
  }
  const risultato = ev.target.closest('[data-vai]');
  if (risultato) { vaiA(risultato.dataset.vai); return; }

  const vai = ev.target.closest('[data-goto]');
  if (vai) { location.hash = '#/' + vai.dataset.goto; return; }

  const chip = ev.target.closest('[data-filter]');
  if (chip) {
    const [view, key] = chip.dataset.filter.split('.');
    state.filters[view][key] = chip.dataset.value;
    await route();
    return;
  }
});

document.addEventListener('change', async (ev) => {
  const sel = ev.target.closest('[data-filter-select]');
  if (sel) {
    const [view, key] = sel.dataset.filterSelect.split('.');
    state.filters[view][key] = sel.value;
    await route();
  }
});

document.addEventListener('input', (ev) => {
  const inp = ev.target.closest('[data-filter-input]');
  if (!inp) return;
  clearTimeout(inp._t);
  inp._t = setTimeout(async () => {
    const [view, key] = inp.dataset.filterInput.split('.');
    state.filters[view][key] = inp.value;
    const pos = inp.selectionStart;
    await route();
    const again = $(`[data-filter-input="${inp.dataset.filterInput}"]`);
    if (again) { again.focus(); again.setSelectionRange(pos, pos); }
  }, 320);
});

document.addEventListener('submit', async (ev) => {
  const form = ev.target.closest('[data-form]');
  if (!form) return;
  ev.preventDefault();
  const data = Object.fromEntries(new FormData(form).entries());
  try {
    if (form.dataset.form === 'task-quick') {
      if (!data.title.trim()) return;
      await api('/api/tasks', { method: 'POST', body: { ...data, priority: +(data.priority || 2) } });
      toast(T('task aggiunto'));
    } else if (form.dataset.form === 'post-new') {
      await api('/api/posts', { method: 'POST', body: data });
      toast(T('bozza salvata'));
    } else if (form.dataset.form === 'chiedi') {
      const q = (data.domanda || '').trim();
      if (!q) return;
      form.reset();
      await chiedi(q);
      return;
    } else if (form.dataset.form === 'project-edit') {
      await api('/api/projects/' + encodeURIComponent(form.dataset.key), {
        method: 'PATCH', body: { ...data, priority: +data.priority } });
      toast(T('progetto aggiornato'));
      $('#drawer').hidden = true;
    }
    state.overview = null;
    await route();
  } catch (err) { toast(err.message, true); }
});


/* ---------------------------------------------------------------- tastiera */
/* Lo slash e Cmd/Ctrl+K portano al campo di ricerca, come in mezzo mondo. Lo
   slash solo se non si sta gia' scrivendo da qualche parte, altrimenti chi
   scrive una data si ritrova altrove. */
const SCRIVE = (el) => el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'
                              || el.tagName === 'SELECT' || el.isContentEditable);

document.addEventListener('keydown', (ev) => {
  const inp = $('#cerca-q');
  if ((ev.key === '/' && !SCRIVE(document.activeElement) && !ev.metaKey && !ev.ctrlKey)
      || ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === 'k')) {
    ev.preventDefault();
    inp.focus(); inp.select();
    return;
  }
  // Da tastiera: Invio o Spazio aprono la riga a fuoco, le frecce passano alla vicina
  const riga = document.activeElement && document.activeElement.closest
    ? document.activeElement.closest('[data-sel],[data-project],[data-memory],[data-vai],[data-act][role="button"]') : null;
  if (riga && document.activeElement === riga && (ev.key === 'Enter' || ev.key === ' ')) {
    ev.preventDefault(); riga.click(); return;
  }
  if (riga && riga.matches('[data-sel]') && (ev.key === 'ArrowDown' || ev.key === 'ArrowUp')) {
    const lista = $$('[data-sel]', riga.closest('[data-lista]'));
    const vicina = lista[lista.indexOf(riga) + (ev.key === 'ArrowDown' ? 1 : -1)];
    if (vicina) { ev.preventDefault(); vicina.focus(); vicina.click(); }
    return;
  }
  if (ev.key === 'Escape') {
    if (!$('#menu-imp').hidden) { chiudiMenuImp(); return; }
    if (!$('#drawer').hidden) { $('#drawer').hidden = true; return; }
    if (ric.aperta) { chiudiRicerca(true); inp.blur(); }
  }
});

$('.rail nav').addEventListener('click', () => { if (ric.aperta) chiudiRicerca(true); });

$('#drawer').addEventListener('click', (ev) => { if (ev.target.id === 'drawer') $('#drawer').hidden = true; });
$('#drawer-close').addEventListener('click', () => { $('#drawer').hidden = true; });

/* ---------------------------------------------------------------- impostazioni */
/* Aspetto, lingua e dimensione del testo stanno in un menu, non in tre
   pulsanti della barra: sono cose che si scelgono una volta. */
const SCALE = [0.85, 1, 1.15, 1.3, 1.5];
function applicaScala(i) {
  i = Math.max(0, Math.min(SCALE.length - 1, i));
  storageSet('plancia-scala', String(i));
  document.documentElement.style.setProperty('--scala', SCALE[i]);
  const v = $('#scala-val'); if (v) v.textContent = Math.round(SCALE[i] * 100) + '%';
  state.scala = i;
  window.dispatchEvent(new Event('plancia-tema')); // il grafo ridisegna con la nuova dimensione
}
function statoMenuImp() {
  const modo = storageGet('plancia-theme') || 'auto';
  $$('#seg-tema button').forEach((b) => b.classList.toggle('on', b.dataset.tema === modo));
  $$('#seg-lingua button').forEach((b) => b.classList.toggle('on', b.dataset.lingua === UILANG));
}
function chiudiMenuImp() {
  $('#menu-imp').hidden = true;
  $('#btn-imp').setAttribute('aria-expanded', 'false');
}
$('#btn-imp').addEventListener('click', (ev) => {
  ev.stopPropagation();
  const m = $('#menu-imp');
  m.hidden = !m.hidden;
  $('#btn-imp').setAttribute('aria-expanded', String(!m.hidden));
  if (!m.hidden) statoMenuImp();
});
/* La casella "copia" del cassetto In background cambia cosa succede: il piano
   si richiede in anteprima (niente parte) e la frase si aggiorna. */
document.addEventListener('change', async (ev) => {
  const box = ev.target.closest && ev.target.closest('.riprendi-background input[name=copia]');
  if (!box) return;
  const form = box.closest('form');
  try {
    const r = form.dataset.task
      ? await api('/api/riprendi/' + form.dataset.task, { method: 'POST',
          body: { anteprima: true, copia: box.checked } })
      : await api('/api/cantiere', { method: 'POST', body: {
          titolo: '-', sessione: form.dataset.sessione || null, anteprima: true, copia: box.checked } });
    mostraPiano(r.piano);
  } catch (err) { toast(err.message, true); }
});
document.addEventListener('click', (ev) => {
  if (!ev.target.closest('#menu-imp') && !ev.target.closest('#btn-imp')) chiudiMenuImp();
  else if (ev.target.closest('#menu-imp a')) chiudiMenuImp();
});
$('#seg-tema').addEventListener('click', (ev) => {
  const b = ev.target.closest('[data-tema]');
  if (b) { applyTheme(b.dataset.tema); statoMenuImp(); }
});
$('#seg-lingua').addEventListener('click', async (ev) => {
  const b = ev.target.closest('[data-lingua]');
  if (!b || b.dataset.lingua === UILANG) return;
  UILANG = b.dataset.lingua;
  storageSet('plancia-ui', UILANG);
  traduciShell();
  statoMenuImp();
  disegnaSelettore();
  state.overview = null; state.recap = null; ric.indiceP = null;
  await route();
});
$('#seg-scala').addEventListener('click', (ev) => {
  const b = ev.target.closest('[data-scala]');
  if (!b) return;
  const passo = +b.dataset.scala;
  applicaScala(passo === 0 ? 1 : (state.scala ?? 1) + passo);
});
(function () {
  const g = parseInt(storageGet('plancia-scala'), 10);
  applicaScala(Number.isNaN(g) ? 1 : g);
})();

/* ---------------------------------------------------------------- tema e sync */
function applyTheme(mode) {
  const resolved = mode === 'auto'
    ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : mode;
  document.documentElement.dataset.theme = mode;
  document.documentElement.dataset.resolved = resolved;
  storageSet('plancia-theme', mode);
  window.dispatchEvent(new Event('plancia-tema'));
}
// `?tema=chiaro|scuro` nell'indirizzo forza l'aspetto senza toccare quello salvato:
// serve alle istantanee, che ripartono ogni volta da un profilo vuoto
const TEMAPARAM = new URLSearchParams(location.search).get('tema');
if (TEMAPARAM === 'scuro' || TEMAPARAM === 'dark') {
  document.documentElement.dataset.resolved = 'dark'; document.documentElement.dataset.theme = 'dark';
} else if (TEMAPARAM === 'chiaro' || TEMAPARAM === 'light') {
  document.documentElement.dataset.resolved = 'light'; document.documentElement.dataset.theme = 'light';
} else {
  applyTheme(storageGet('plancia-theme') || 'auto');
}
matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
  if ((storageGet('plancia-theme') || 'auto') === 'auto') applyTheme('auto');
});

$('#btn-sync').addEventListener('click', async () => {
  // /api/sync risponde {avviato:false} in DUE casi diversi, e solo uno dei due
  // porta anche "motivo":"--no-sync". Se un sync e' gia' in corso `avviato` e'
  // false ma non c'e' nessun motivo: il pulsante NON deve dire "disattivato
  // per --no-sync" (sarebbe falso), deve dire che un aggiornamento e' gia' in
  // corso e continuare a seguirlo con pollSync().
  ric.indiceP = null;
  try {
    const r = await api('/api/sync', { method: 'POST', body: {} });
    if (r.avviato) { toast(T('aggiornamento avviato')); pollSync(); }
    else if (r.motivo === '--no-sync') { toast(T('sync disattivato per questa sessione (--no-sync)')); state.overview = null; route(); }
    else { toast(T('aggiornamento già in corso')); pollSync(); }
  } catch (err) { toast(err.message, true); }
});

let syncWasRunning = false;
async function pollSync() {
  try {
    const st = await api('/api/status');
    const btn = $('#btn-sync');
    if (st.sync.running) {
      btn.classList.add('gira');
      syncWasRunning = true;
      setTimeout(pollSync, 1200);
    } else {
      btn.classList.remove('gira');
      if (syncWasRunning) { syncWasRunning = false; state.overview = null; ric.indiceP = null; route(); }
    }
  } catch (e) {
    // il server non risponde: la riga di stato lo dice con l'ora dei dati che si vedono
    spiaAggiorna('rotto', state.ultimoOk || state.overviewQuando || new Date());
  }
}

/* Il selettore di compartimento (E1-PLANCIA). Si disegna solo se il server dice
   che ci sono compartimenti nominati: senza, la barra e' quella di sempre. */
function disegnaSelettore() {
  const c = state.compartimenti;
  let sel = $('#sel-compartimento');
  if (!c || !c.attivo) { if (sel) sel.remove(); return; }
  if (!sel) {
    sel = document.createElement('select');
    sel.id = 'sel-compartimento';
    sel.addEventListener('change', async () => {
      state.compartimento = sel.value;
      // quello che la pagina teneva a mente e' del compartimento di prima
      state.overview = null; state.progetti = null; state.lav = null;
      state.recap = null; state.filters = {}; state.sel = {}; ric.indiceP = null;
      $('#drawer').hidden = true;
      await route();
    });
    $('.topbar-actions').prepend(sel);
  }
  sel.title = T('compartimento_etichetta');
  sel.setAttribute('aria-label', T('compartimento_etichetta'));
  sel.innerHTML = c.elenco.map((n) =>
    `<option value="${esc(n)}"${n === state.compartimento ? ' selected' : ''}>`
    + `${esc(n === c.predefinito ? T('compartimento_predefinito') : n)}</option>`).join('');
}

// `?compartimento=nome` nell'indirizzo apre la dashboard su quel compartimento
// (un nome che non c'e' e' il predefinito: lo decide il server).
const COMPARAM = new URLSearchParams(location.search).get('compartimento');

async function caricaCompartimenti() {
  try {
    const c = await api('/api/compartimenti'
      + (COMPARAM ? '?compartimento=' + encodeURIComponent(COMPARAM) : ''));
    state.compartimenti = c;
    state.compartimento = c.attivo ? (c.scelto || c.predefinito) : null;
  } catch (e) { state.compartimenti = null; }
  disegnaSelettore();
}

window.addEventListener('hashchange', () => { if (ric.aperta) chiudiRicerca(false); route(); });
traduciShell();
// prima di disegnare la prima vista si sa se ci sono compartimenti: una vista
// disegnata senza il parametro mostrerebbe il predefinito e poi cambierebbe
caricaCompartimenti().then(route);
pollSync();
setInterval(pollSync, 30000);


/* ------------------------------------------------------------ service worker */
/* LOTTO-U1-APPWEB: la dashboard si installa come app (Chrome, Edge, Safari
   con "Aggiungi al Dock") e si apre anche con il server spento, perche' la
   shell la tiene web/sw.js (vedi il commento in testa a quel file). Qui c'e'
   SOLO la registrazione, e le condizioni per farla:
   - il browser sa cosa e' un service worker;
   - la pagina e' servita da http(s) su localhost (un worker esiste solo in un
     contesto sicuro, e questa dashboard gira solo sulla macchina di chi la usa);
   - NON dentro l'app mac (data-app="mac", iniettato da main.swift a inizio
     documento, quindi gia' presente qui): la sua WKWebView non li supporta
     senza configurazione e non servono, l'app ha la sua pagina d'errore
     quando il server non risponde.
   Se registrare fallisce, per qualunque motivo (profilo privato, browser che
   li disattiva, sw.js non raggiungibile), la dashboard funziona lo stesso:
   una riga in console e via, niente toast, niente eccezione. La registrazione
   aspetta 'load' per non far concorrere il precaricamento della shell con il
   primo disegno. */
(function registraServiceWorker() {
  try {
    if (!('serviceWorker' in navigator)) return;
    if (document.documentElement.dataset.app === 'mac') return;
    if (!/^https?:$/.test(location.protocol)) return;
    if (!['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)) return;
    const registra = () => navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .catch((e) => console.warn('plancia: service worker non registrato:', e && e.message ? e.message : e));
    if (document.readyState === 'complete') registra();
    else window.addEventListener('load', registra, { once: true });
  } catch (e) {
    console.warn('plancia: service worker non registrato:', e && e.message ? e.message : e);
  }
})();

