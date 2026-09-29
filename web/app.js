/* Plancia, interfaccia. Nessun framework: fetch, template literal, delega eventi. */

const TOKEN = document.querySelector('meta[name=plancia-token]').content;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = { overview: null, view: null, filters: {}, paletteIndex: 0, paletteHits: [],
                compartimenti: null, compartimento: null };


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
  'prossimi': 'Next up', 'prossimi_altri': '{n} more',
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
  'spia_memoria': 'from memory, {ora}, server unreachable',
  'spia_aggiorno': 'updating…',
  // E1-PLANCIA: il selettore di compartimento in alto.
  'compartimento_etichetta': 'Compartment',
  'compartimento_predefinito': 'Default',
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
  'prossimi': 'Prossimi', 'prossimi_altri': 'altri {n}',
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
  'progetti_n': '{n} progetti',
  'modo_proposta': 'solo lettura', 'modo_esegui': 'può modificare i file',
  'progetti_1': '1 progetto',

  // LOTTO-L4-MEMORIA punto 4: vedi il commento in EN, poco più sopra.
  'spia_titolo': 'stato dei dati',
  'spia_aggiornato': 'aggiornato alle {ora}',
  'spia_memoria': 'memoria delle {ora}, server non raggiungibile',
  'spia_aggiorno': 'aggiorno…',

  // E1-PLANCIA: il selettore di compartimento in alto (vedi conCompartimento).
  'compartimento_etichetta': 'Compartimento',
  'compartimento_predefinito': 'Predefinito',
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
  (s, [k, v]) => s.replace('{' + k + '}', v), T(chiave));
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
    else el.childNodes[0].nodeValue = T(chiave);
  });
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

views.oggi = async () => {
  const d = state.overview = await api('/api/overview?lang=' + UILANG);
  state.overviewQuando = new Date(); // vedi spiaAggiorna in route(): l'ora dei DATI, non del disegno
  const riepilogo = await bloccoRiepilogo(true);
  // Il pannello Prossimi (LOTTO-L2-VISTA punto 2, ex "Task aperti"): si
  // aspetta qui, prima di restituire la vista, non dentro il pannello
  // stesso: altrimenti la vista tornerebbe con un segnaposto "carico…" per
  // il solo pannello, che il punto 7 del lotto vieta esplicitamente (il
  // collaudo a video lo vedrebbe come rosso). Se l'API non risponde (server
  // giù, o vuota) `prossimi` resta null e panelloProssimi mostra
  // 'prossimi_vuoto' invece di rompere il resto della vista.
  let prossimi = null;
  try { prossimi = await api('/api/prossimi'); } catch (e) { /* prossimi_vuoto sotto */ }
  const s = d.stats;
  const attivi = d.progetti.filter((p) => p.status === 'attivo');
  const oggi = d.attivita[d.attivita.length - 1] || { claude: 0, codex: 0, commit: 0 };
  const agenti = Object.fromEntries((d.agenti || []).map((a) => [a.agente, a]));
  const coda = d.post.filter((p) => p.status !== 'pubblicato' && p.status !== 'scartato');

  return `
  <div class="view-head">
    <h1>${T('Oggi')}</h1>
    <p>${new Date().toLocaleDateString(LOC(), { weekday: 'long', day: 'numeric', month: 'long' })}</p>
    <span class="spacer"></span>
    <p>${T('aggiornato ')}${ago(d.ultimo_sync)}</p>
  </div>

  <div data-in="1" style="margin-bottom:var(--s3)">${riepilogo}</div>

  <div class="bento" data-in="2">
    <div class="cell tall wide" style="justify-content:flex-start">
      <div class="k">${T('Ritmo · 30 giorni')}</div>
      ${nastro(d.attivita)}
    </div>
    ${cella(oggi.claude + oggi.codex, T('sessioni oggi'), '', oggi.commit ? `${oggi.commit} ${T('commit oggi')}` : '')}
    ${cella(s.task_aperti, T('task aperti'), s.task_scaduti ? 'alarm' : '',
       s.task_scaduti ? `${s.task_scaduti} ${T('in ritardo')}` : '')}
    ${cella(s.progetti_attivi, T('progetti attivi'))}
    ${cella(kilo(s.token_out_mese), T('token 30 giorni'), s.fuga ? 'warn' : 'quiet',
       s.fuga ? `${T('oggi')} ${String(s.fuga).replace('.', ',')}× ${T('la media')}` : '')}
  </div>

  <div class="bento" data-in="3" style="grid-template-columns:repeat(4,1fr)">
    ${agenteCella('claude', agenti.claude)}
    ${agenteCella('codex', agenti.codex)}
    ${cella(s.scambi || 0, T('sessioni con scambi'), s.scambi ? 'nominal' : 'quiet',
       s.scambi ? T('Codex e Claude si sono parlati') : '')}
    ${cella(s.post_in_coda, T('post in coda'), 'quiet',
       s.post_pubblicati ? `${s.post_pubblicati} ${T('pubblicati')}` : '')}
  </div>

  ${(d.proposte || []).length ? `
  <div class="panel" data-in="3" style="margin-bottom:var(--s3)">
    <header><h3>${T('Cosa converrebbe fare')}</h3><span class="spacer"></span>
      <span class="tag mono">${d.proposte.length}</span></header>
    <div class="panel-body tight">
      ${d.proposte.map((p, i) => {
        // L3-RIPRENDI-UI-4 (obbligatoria del critico): un click su "Riprendi"
        // qui mandava SUBITO /api/jarvis {testo:'fallo'}, che sul server
        // esegue la proposta scelta senza nessuna conferma - su una proposta
        // "manda" quello vuol dire un claude/codex headless partito senza
        // drawer, senza pulsante di stato, senza che l'utente lo vedesse
        // arrivare. Ora "manda" apre lo stesso drawer del pulsante Riprendi
        // di riga (con o senza task, come apriRiprendi già sa fare): il
        // lancio parte solo dal click su "In background" dentro il drawer.
        // Le altre proposte NON passano da lì: il click va dritto a
        // /api/jarvis (vedi il gestore di data-act="proposta" più sotto), ma
        // "vai" e "rilancia" non fanno la stessa cosa una volta arrivate
        // laggiù (L4-MEMORIA, obbligatoria del critico: questo commento
        // diceva "chiama cantiere e lancia davvero" per ENTRAMBE, ed era
        // falso per "vai"). "rilancia" chiama davvero cantiere.avvia
        // (plancia/jarvis.py:_esegui_proposta) - voluto, non un residuo: è
        // la risposta a "Il lancio è fallito. Lo riprovo?", e per questo
        // l'etichetta dice "Rilancia", non "Riprendi", che qui promette una
        // ripresa (un drawer, una scelta) che non fa. "vai" invece non
        // tocca cantiere per niente: jarvis risponde solo con un'azione di
        // navigazione ({tipo:'vai', vista}, senza lancio), che il gestore
        // più sotto ora segue (location.hash = '#/' + vista) - prima di
        // L4-MEMORIA non la seguiva affatto, e il bottone "Apri" mostrava
        // solo il toast senza aprire niente.
        // (Dal tester di L3-RIPRENDI-UI: questo commento diceva il
        // contrario, che "vai"/"rilancia" restassero pura navigazione - non
        // era vero già prima di questo lotto per "rilancia".)
        const az = p.azione || {};
        const frase = i === 0 ? 'fallo' : ['', 'la seconda', 'la terza', 'la quarta'][i] || 'fallo';
        const etichetta = az.tipo === 'manda' ? T('Riprendi') : az.tipo === 'rilancia' ? T('Rilancia') : T('Apri');
        return `
        <div class="row">
          <div class="prio p${p.urgenza < 2 ? 1 : p.urgenza < 4 ? 2 : 3}"></div>
          <div class="main"><div class="title">${esc(p.testo)}</div></div>
          <div class="side">
            <button class="mini go riprendi" data-act="proposta" data-frase="${frase}"
              data-testo="${esc(p.testo)}" data-tipo="${esc(az.tipo || '')}"
              data-task="${az.task_id || ''}" data-titolo="${esc(az.titolo || '')}"
              data-progetto="${esc(az.progetto || '')}">${etichetta}</button>
          </div>
        </div>`;
      }).join('')}
    </div>
  </div>` : ''}

  <div class="grid cols-2" data-in="4">
    <div style="display:flex;flex-direction:column;gap:var(--s3)">
      <div class="panel">
        <header><h3>${T('prossimi')}</h3></header>
        <form class="inline-form" data-form="task-quick">
          <input type="text" name="title" placeholder="${T('Aggiungi un task e premi invio')}" autocomplete="off">
          <select name="project" style="width:150px">
            <option value="">${T('nessun progetto')}</option>
            ${d.progetti.map((p) => `<option value="${esc(p.key)}">${esc(p.name)}</option>`).join('')}
          </select>
        </form>
        <div class="panel-body tight">${panelloProssimi(prossimi)}</div>
      </div>

      <div class="panel">
        <header><h3>${T('Progetti attivi')}</h3><span class="spacer"></span>
          <a class="mini" href="#/progetti">${T('tutti')}</a></header>
        <div class="panel-body tight">
          ${attivi.slice(0, 7).map((p) => `
            <div class="row" data-project="${esc(p.key)}" style="cursor:pointer">
              <div class="prio p${p.priority}"></div>
              <div class="main">
                <div class="title">${esc(p.name)}</div>
                <div class="sub truncate">${esc(p.next_action || p.summary) || '—'}</div>
              </div>
              <div class="side">
                ${p.task_aperti ? `<span class="tag">${p.task_aperti}</span>` : ''}
                <span class="tag mono">${ago(p.last_activity)}</span>
              </div>
            </div>`).join('') || `<div class="empty">${T('nessun progetto attivo')}</div>`}
        </div>
      </div>
    </div>

    <div style="display:flex;flex-direction:column;gap:var(--s3)">
      <div class="panel">
        <header><h3>${T('Attività recente')}</h3><span class="spacer"></span>
          <a class="mini" href="#/archivio">${T('sessioni')}</a></header>
        <div class="panel-body"><div class="tl">${timeline(d.eventi.slice(0, 20))}</div></div>
      </div>
      ${coda.length ? `
      <div class="panel">
        <header><h3>${T('Social in coda')}</h3><span class="spacer"></span>
          <a class="mini" href="#/social">${T('pipeline')}</a></header>
        <div class="panel-body tight">
          ${coda.slice(0, 4).map((p) => `
            <div class="row"><div class="main">
              <div class="title clamp2">${esc(p.text)}</div>
              <div class="sub">${esc(p.platform)} · ${esc(p.project) || T('nessun progetto')}</div>
            </div><div class="side"><span class="tag ${statusClass[p.status] || ''}">${T(p.status)}</span></div></div>`).join('')}
        </div>
      </div>` : ''}
    </div>
  </div>`;
};

const cella = (v, etichetta, cls = '', nota = '') => `
  <div class="cell ${cls}">
    <div class="k">${etichetta}</div>
    <div class="v">${typeof v === 'number' ? num(v) : v}</div>
    ${nota ? `<div class="n">${nota}</div>` : ''}
  </div>`;

const agenteCella = (nome, a) => {
  const colore = nome === 'codex' ? 'var(--codex)' : 'var(--claude)';
  if (!a) return `<div class="cell quiet"><div class="k">${nome}</div>
    <div class="v" style="font-size:15px">${T('Codex non è collegato')}</div></div>`;
  return `
  <div class="cell" style="cursor:pointer" data-goto="agenti">
    <div class="k"><span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${colore};margin-right:6px;vertical-align:1px"></span>${nome}</div>
    <div class="v">${num(a.sessioni)}<small>${T('sessioni')}</small></div>
    <div class="n">${kilo(a.token)} ${T('token generati')} · ${num(a.tool)} tool</div>
  </div>`;
};

/* Il nastro: una linea d'orizzonte, le sessioni sopra e i commit sotto.
   Si legge di sbieco, che è il punto di uno strumento. */
function nastro(giorni) {
  const maxSu = Math.max(1, ...giorni.map((g) => (g.claude || 0) + (g.codex || 0)));
  const maxGiu = Math.max(1, ...giorni.map((g) => g.commit || 0));
  const H = 42;
  const totC = giorni.reduce((a, g) => a + (g.claude || 0), 0);
  const totX = giorni.reduce((a, g) => a + (g.codex || 0), 0);
  const totK = giorni.reduce((a, g) => a + (g.commit || 0), 0);
  return `
  <div class="ribbon">
    ${giorni.map((g, i) => {
      const c = g.claude || 0, x = g.codex || 0, k = g.commit || 0;
      const su = ((c + x) / maxSu) * H, giu = (k / maxGiu) * H;
      const hc = (c + x) ? (c / (c + x)) * su : 0;
      const ultimo = i === giorni.length - 1;
      return `<div class="day ${ultimo ? 'oggi' : ''}" title="${g.giorno} · ${c} claude, ${x} codex, ${k} commit">
        ${x ? `<div class="up codex" style="height:${su}px"></div>` : ''}
        ${c ? `<div class="up" style="height:${hc}px"></div>` : ''}
        ${k ? `<div class="down" style="height:${giu}px"></div>` : ''}
        ${(!c && !x && !k) ? '<div class="tick"></div>' : ''}
      </div>`;
    }).join('')}
  </div>
  <div class="ribbon-legend">
    <span><i style="background:var(--claude)"></i>claude ${totC}</span>
    <span><i style="background:var(--codex)"></i>codex ${totX}</span>
    <span><i style="background:var(--text-3);opacity:.6"></i>commit ${totK}</span>
    <span class="spacer">${T('sopra la linea le sessioni, sotto i commit')}</span>
  </div>`;
}

function timeline(events) {
  if (!events.length) return `<div class="empty">${T('niente da mostrare')}</div>`;
  return events.map((e) => `
    <div class="ev" data-k="${esc(e.kind)}">
      <div class="when">${ago(e.ts)} · ${T(e.kind)}${e.progetto ? ' · ' + esc(e.progetto) : ''}</div>
      <div class="what truncate">${esc(Tev(e.title))}</div>
    </div>`).join('');
}

function taskRows(tasks) {
  if (!tasks.length) return `<div class="empty">${T('nessun task aperto')}</div>`;
  return tasks.map((t) => `
    <div class="row" data-task="${t.id}">
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

/* Il pannello "Prossimi" di Oggi (LOTTO-L2-VISTA punto 2): una riga per
   progetto, raggruppata per area come /api/prossimi la manda già (vedi
   plancia/api.py:prossimi_raggruppati). Il tetto di 7 righe VISIBILI in
   totale si applica qui, non sul server: ogni riga oltre il tetto è
   comunque nel markup (per non fare una seconda chiamata quando si preme
   "altri N"), solo nascosta con [hidden] e rivelata dal click
   (data-act="prossimi-altri" nel listener). Il tetto è per gruppo di
   comparsa: un gruppo incontrato dopo che le 7 sono già finite mostra 0
   righe e va comunque dietro il proprio "altri N" (mai un gruppo silenzioso
   senza modo di aprirlo). */
const PROSSIMI_TETTO = 7;

function panelloProssimi(dati) {
  if (!dati) return `<div class="prossimi-vuoto">${T('prossimi_vuoto')}</div>`;
  const gruppi = [
    // Come in alberoPadre: il nome dell'area 'cartelle-viste' passa da T(),
    // non dal nome vero del progetto (sempre in italiano lì), cosi' l'inglese
    // mostra un nome tradotto anche qui.
    ...dati.aree.map((a) => ({
      key: a.key, name: a.key === 'cartelle-viste' ? T('cartelle_viste') : a.name, righe: a.righe,
    })),
    ...(dati.senza_area.length ? [{ key: '', name: T('area_senza'), righe: dati.senza_area }] : []),
  ].filter((g) => g.righe.length);
  if (!gruppi.length) return `<div class="prossimi-vuoto">${T('prossimi_vuoto')}</div>`;

  let mostrate = 0;
  return `<div class="prossimi">${gruppi.map((g) => {
    const visibili = Math.min(g.righe.length, Math.max(0, PROSSIMI_TETTO - mostrate));
    mostrate += visibili;
    return `
    <div class="prossimi-area">
      <span class="prossimi-area-nome">${esc(g.name)}</span>
      <span class="prossimi-area-conta">${g.righe.length}</span>
    </div>
    ${g.righe.map((r, i) => rigaProssimo(r, g.key, i >= visibili)).join('')}
    ${g.righe.length > visibili ? `<button class="mini prossimi-altri" type="button"
        data-act="prossimi-altri" data-area="${esc(g.key)}">${conN('prossimi_altri', g.righe.length - visibili)}</button>` : ''}`;
  }).join('')}</div>`;
}

const FONTE_CHIAVE = { task: 'task', next_action: 'next_action', vuoto: 'vuoto' };
// Nomi CSS concordati con L2-GLASS (LOTTO-L2-VISTA): 'next_action' diventa
// 'fonte-next', non 'fonte-next_action'.
const FONTE_CLASSE = { task: 'fonte-task', next_action: 'fonte-next', vuoto: 'fonte-vuoto' };

function rigaProssimo(r, areaKey, nascosta) {
  // Quando la fonte è 'vuoto' non c'è niente da attribuire: la piccola
  // etichetta di fonte si salta (altrimenti sarebbe "vuoto vuoto", la
  // stessa parola due volte per due cose diverse nella stessa riga).
  const fonte = r.fonte !== 'vuoto'
    ? `<span class="prossimi-fonte ${FONTE_CLASSE[r.fonte] || 'fonte-vuoto'}">${T(FONTE_CHIAVE[r.fonte])}</span>` : '';
  return `
  <div class="prossimi-riga" data-project="${esc(r.key)}" data-area="${esc(areaKey)}"
       data-chiave="${esc(areaKey)}:${esc(r.key)}"${nascosta ? ' hidden' : ''}>
    <div class="prossimi-progetto">${esc(r.name)}</div>
    <div class="prossimi-cosa">${r.cosa ? esc(r.cosa) : T('niente in coda')} ${fonte}</div>
    ${r.scadenza ? `<div class="prossimi-scadenza">${dateIt(r.scadenza)}</div>` : ''}
    <div class="prossimi-quando">${ago(r.ultima_attivita)}</div>
  </div>`;
}


/* ---------------------------------------------------------------- riepilogo */
const SUGGERIMENTI = {
  it: ['Cosa dovrei riprendere adesso?', 'Cosa ho fatto ieri?', 'Su cosa sono fermo da troppo?', 'Quanto ho lavorato questa settimana?'],
  en: ['What should I pick up now?', 'What did I do yesterday?', 'What has been idle too long?', 'How much did I work this week?'],
  es: ['¿Qué debería retomar ahora?', '¿Qué hice ayer?', '¿Qué lleva parado demasiado?', '¿Cuánto he trabajado esta semana?'],
};

async function bloccoRiepilogo(soloCorpo) {
  const r = state.recap || (state.recap = { lang: '', data: null, qa: [], voce: null });
  // Una lingua sola per superficie: quella scelta col selettore. La lingua
  // della configurazione resta per il riepilogo che parte da solo la mattina,
  // quando nessuno sta guardando l'interfaccia.
  r.lang = UILANG;
  const lingue = ['it', 'en', 'es', 'fr', 'de', 'pt'];
  const attiva = r.lang || 'it';

  // Se c'è in cache si dipinge subito; altrimenti si genera in sottofondo.
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
  ${soloCorpo ? '' : `<div class="view-head">
    <h1>${T('Riepilogo')}</h1><p>${T('la tua giornata, raccontata come la diresti a voce')}</p>
  </div>`}

  <div class="recap">
    <div class="panel">
      <header><h3>${T('Riepilogo')}</h3><span class="spacer"></span>
        ${d ? `<span class="tag ${d.fonte === 'claude' ? 'accent' : ''}">${esc(T(d.fonte))}</span>` : ''}
      </header>
      <div class="panel-body">
        <div class="recap-testo ${d ? '' : 'attesa'}" id="recap-testo">${
          d ? esc(d.testo) : T('preparo il riepilogo, ci vogliono pochi secondi…')}</div>
        <div class="recap-bar" style="margin-top:16px">
          <button class="speak" data-act="recap-play" ${d ? '' : 'disabled'}>
            <span id="speak-icona">▶</span><span id="speak-testo">${T('Ascolta')}</span></button>
          <button class="ghost" data-act="recap-stop">${T('Ferma')}</button>
          <span style="color:var(--faint);font-size:12px" id="recap-voce">${
            r.voce ? T('voce') + ': ' + esc(r.voce) : ''}</span>
        </div>
      </div>
    </div>

    <div class="panel">
      <header><h3>${T('Chiedi')}</h3><span class="spacer"></span>
        <span class="tag mono">claude</span></header>
      <div class="panel-body qa">
        <div class="suggerimenti">${(SUGGERIMENTI[attiva] || SUGGERIMENTI.en).map((q) =>
          `<span class="chip" data-act="chiedi-veloce" data-q="${esc(q)}">${esc(q)}</span>`).join('')}</div>
        <form data-form="chiedi" style="display:flex;gap:8px">
          <input type="text" name="domanda" placeholder="${T('Chiedi qualcosa sul tuo lavoro')}" autocomplete="off">
          <button class="primary" type="submit">${T('Chiedi')}</button>
        </form>
        <div id="qa-bolle">${r.qa.map((b) =>
          `<div class="bolla ${b.mia ? 'mia' : 'sua'}">${esc(b.testo)}</div>`).join('')}</div>
      </div>
    </div>
  </div>`;
};

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
  testo.textContent = attivo ? T('in ascolto') : T('Ascolta');
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
        }).join('') || `<div class="empty">${T('niente da mostrare')}</div>`}
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
            <div class="row"><div class="main">
              <div class="title truncate">${esc(e.title)}</div>
              <div class="sub">${ago(e.ts)} · ${e.n > 1 ? e.n + ' ' + T('riprese') + ' · ' : ''}${esc(e.detail || '')}${e.progetto ? ' · ' + esc(e.progetto) : ''}</div>
            </div></div>`).join('') || `<div class="empty">${T('nessuno scambio registrato')}</div>`}
        </div>
      </div>
    </div>
  </div>`;
};


/* ---------------------------------------------------------------- archivio */
const SEGMENTI = [['sessioni', 'Sessioni'], ['agenti', 'Agenti'],
                  ['memoria', 'Conoscenza'], ['capacita', 'Capacità']];

views.archivio = async () => {
  const f = state.filters.archivio || (state.filters.archivio = { seg: 'sessioni' });
  const corpo = f.seg === 'agenti' ? await bloccoAgenti(true)
    : f.seg === 'memoria' ? await bloccoConoscenza(true)
    : f.seg === 'capacita' ? await bloccoCapacita(true)
    : await bloccoSessioni(true);
  return `
  <div class="view-head">
    <h1>${T('Archivio')}</h1><p>${T('tutto quello che è già successo')}</p>
    <span class="spacer"></span>
    <div class="filters" style="margin:0">
      ${SEGMENTI.map(([k, etichetta]) =>
        `<span class="chip ${f.seg === k ? 'on' : ''}" data-filter="archivio.seg" data-value="${k}">${T(etichetta)}</span>`).join('')}
    </div>
  </div>
  <div data-in="1">${corpo}</div>`;
};



/* ------------------------------------------------------------------- cerca */
/* La ragione per aprire quest'app, che prima non c'era. Fino al 9 agosto 2026 la
   ricerca vedeva il solo primo prompt di ogni sessione, lo 0,08% del materiale,
   e infatti non trovava niente. Adesso guarda dentro dodicimila turni: quello
   che è stato detto davvero, con la riga esatta da cui viene. */

/* Il frammento arriva con i termini fra « » perché SQLite non sa niente di HTML.
   Si scappa prima e si marca dopo, o un turno che parla di uno script diventa
   uno script. */
const marca = (frammento) => esc(frammento || '')
  .split('«').join('<mark>').split('»').join('</mark>');

const RUOLO = { assistant: 'Claude', user: 'tu' };

function rigaTurno(t) {
  const file = (t.percorso || '').split('/').pop();
  return `
  <article class="trovato">
    <div class="trovato-testa">
      <span class="tag${t.ruolo === 'user' ? ' tu' : ''}">${T(RUOLO[t.ruolo] || t.ruolo)}</span>
      <span class="mono muted">${esc((t.progetto || '').split('/').pop())}</span>
      <span class="spacer"></span>
      <span class="mono faint">${ago(t.ts)}</span>
    </div>
    <p class="trovato-testo">${marca(t.frammento)}</p>
    <div class="trovato-piede mono faint">${esc(file)} · ${T('riga')} ${t.riga}</div>
  </article>`;
}

/* I progetti da cui vengono i risultati, con quanti per uno. Il conto è su tutto
   l'indice e non sulla pagina, quindi dice davvero se la cosa cercata sta in un
   posto solo. Cliccare stringe, ricliccare allarga. */
function chipProgetti(gruppi, attivo) {
  if (!gruppi || gruppi.length < 2) return '';
  const uno = (g) => `<button class="chip${g.progetto === attivo ? ' on' : ''}"
      data-progetto="${esc(g.progetto)}">${esc(g.progetto)} <em>${g.turni}</em></button>`;
  return `<div class="chips">${gruppi.map(uno).join('')}</div>`;
}

views.cerca = async () => {
  const f = state.filters.cerca || (state.filters.cerca = { q: '', progetto: '' });
  let corpo = '', chips = '';
  if ((f.q || '').trim()) {
    const d = await api('/api/search?q=' + encodeURIComponent(f.q)
      + (f.progetto ? '&progetto=' + encodeURIComponent(f.progetto) : ''));
    const trovati = d.turni || [];
    chips = chipProgetti(d.progetti, f.progetto);
    corpo = trovati.length
      ? `<div class="trovati">${trovati.map(rigaTurno).join('')}</div>`
      : `<div class="empty">${T('nessun turno contiene quelle parole')}</div>`;
  } else {
    corpo = `<div class="empty">${T('Scrivi qualcosa che ricordi di aver detto, o letto.')}</div>`;
  }
  return `
  <div class="view-head">
    <h1>${T('Cerca')}</h1><p>${T('dentro quello che è stato detto, non solo nei titoli')}</p>
  </div>
  <input class="cercabox" type="search" autocomplete="off" data-filter-input="cerca.q"
         placeholder="${T('una frase, un nome di file, un numero…')}"
         value="${esc(f.q || '')}">
  ${chips}
  <div data-in="1">${corpo}</div>`;
};


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
  <div style="max-width:660px;margin:6vh auto 0" data-in="1">
    <div class="label" style="margin-bottom:var(--s4)">
      ${i + 1} / ${PASSI.length}
      <span style="display:inline-flex;gap:4px;margin-left:var(--s3);vertical-align:middle">
        ${PASSI.map((_, k) => `<i style="width:${k === i ? 18 : 6}px;height:3px;border-radius:2px;background:${k <= i ? 'var(--amber)' : 'var(--border)'};display:block"></i>`).join('')}
      </span>
    </div>
    <h1 class="serif" style="font-size:32px;letter-spacing:-.03em;line-height:1.15">${p.t[L]}</h1>
    <p style="font-size:16px;line-height:1.7;color:var(--muted);margin-top:var(--s4)">${p.c[L]}</p>
    ${CIFRE ? `<div class="grid cols-3" style="margin-top:var(--s5)">
      ${CIFRE.map(([n, e]) => `<div class="kpi"><div class="num mono">${n}</div><div class="label">${e}</div></div>`).join('')}
    </div>` : ''}
    <div style="display:flex;gap:var(--s2);margin-top:var(--s6);align-items:center">
      ${i > 0 ? `<button class="ghost" data-act="passo" data-n="${i - 1}">${L === 'en' ? 'Back' : 'Indietro'}</button>` : ''}
      ${p.prova ? `<button class="ghost" data-act="prova-passo"
        data-vista="${p.prova.vista || ''}" data-azione="${p.prova.azione || ''}"
        data-url="${p.prova.url || ''}">${p.prova.etichetta[L]}</button>` : ''}
      <span class="spacer" style="margin-left:auto"></span>
      ${i < PASSI.length - 1
        ? `<button class="primary" data-act="passo" data-n="${i + 1}">${L === 'en' ? 'Next' : 'Avanti'}</button>`
        : `<button class="primary" data-act="fine-benvenuto">${L === 'en' ? 'Start using it' : 'Comincia'}</button>`}
      <button class="mini" data-act="fine-benvenuto">${L === 'en' ? 'skip' : 'salta'}</button>
    </div>
  </div>`;
};

/* ---------------------------------------------------------------- lavagna */
const FONTI = [['', 'tutti'], ['plancia', 'plancia'], ['claude', 'claude'], ['codex', 'codex']];

views.lavagna = async (soloCorpo) => {
  const f = state.filters.lavagna || (state.filters.lavagna = { fonte: '', stato: 'aperti' });
  const [d, lanci, progetti] = await Promise.all([
    api(`/api/lavagna?stato=${f.stato}${f.fonte ? '&fonte=' + f.fonte : ''}`),
    api('/api/runs?limite=6'),
    api('/api/projects'),
  ]);
  state.progetti = progetti;
  const attivi = lanci.filter((r) => r.stato === 'in coda' || r.stato === 'in corso');

  return `
  ${soloCorpo ? '' : `<div class="view-head">
    <h1>${T('tutti_i_task')}</h1><p>${T('tutti_i_task_nota')}</p>
    <span class="spacer"></span>
    <button class="ghost" data-act="manda-nuovo">${T('in_background')}</button>
  </div>`}

  <div class="filters" data-in="1">
    ${FONTI.map(([k, etichetta]) => `<span class="chip ${f.fonte === k ? 'on' : ''}"
      data-filter="lavagna.fonte" data-value="${k}">${k ? etichetta : T(etichetta)}${
        k && d.conteggi[k] ? ` <b style="opacity:.6">${d.conteggi[k].aperti || 0}</b>` : ''}</span>`).join('')}
    <span style="margin-left:auto"></span>
    ${['aperti', 'fatto', 'tutti'].map((k) => `<span class="chip ${f.stato === k ? 'on' : ''}"
      data-filter="lavagna.stato" data-value="${k}">${T(k)}</span>`).join('')}
  </div>

  ${attivi.length ? `<div class="panel" data-in="2" style="margin-bottom:var(--s3)">
    <header><h3>${T('In lavorazione')}</h3><span class="spacer"></span>
      <span class="dot busy"></span></header>
    <div class="panel-body tight">${attivi.map(rigaLancio).join('')}</div>
  </div>` : ''}

  <div class="panel" data-in="3">
    <div class="panel-body tight">
      ${d.voci.map((v) => `
        <div class="row">
          <span class="tag agente ${v.fonte === 'codex' ? 'codex' : v.fonte === 'plancia' ? 'plancia' : ''}"
            style="flex:none">${esc(v.fonte)}</span>
          <div class="main">
            <div class="title">${esc(v.titolo)}</div>
            <div class="sub">${T(v.stato)}${v.progetto ? ' · ' + esc(v.progetto) : ''}${
              v.aggiornato_at ? ' · ' + ago(v.aggiornato_at) : ''}</div>
          </div>
          <div class="side">
            <button class="mini go riprendi" data-act="manda" data-titolo="${esc(v.titolo)}"
              data-dettaglio="${esc((v.dettaglio || '').slice(0, 600))}"
              data-progetto="${esc(v.progetto_chiave || '')}"
              data-task="${v.fonte === 'plancia' ? v.task_id || '' : ''}"
              data-sessione="${esc(v.sessione || '')}" data-agente="${esc(v.agente || '')}"
              >${T('Riprendi')}</button>
          </div>
        </div>`).join('') || `<div class="empty">${T('nessun task aperto da nessuna parte')}</div>`}
    </div>
  </div>

  ${lanci.length ? `<div class="panel" data-in="4" style="margin-top:var(--s3)">
    <header><h3>${T('Lanci recenti')}</h3></header>
    <div class="panel-body tight">${lanci.slice(0, 6).map(rigaLancio).join('')}</div>
  </div>` : ''}`;
};

const STATO_LANCIO = { riuscito: 'ok', fallito: 'danger', bloccato: 'warn',
                       'in corso': 'accent', 'in coda': '', annullato: '' };

const rigaLancio = (r) => `
  <div class="row" data-act="lancio" data-id="${r.id}" style="cursor:pointer">
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
        <button class="primary" type="button" data-act="riprendi-background">${T('in_background')}</button>
      </form>
    </section>
    ${dati.dettaglio ? `<section><h3>${T('dettaglio')}</h3>
      <div style="font-size:12.5px;color:var(--muted);white-space:pre-wrap">${esc(dati.dettaglio)}</div></section>` : ''}`;
  $('#drawer').hidden = false;
  if (!dati.task) return;
  // Ora la GET, con il cassetto già aperto: il segnaposto sopra si sostituisce
  // da solo quando arriva (o si toglie, nel catch, se il task non c'è più).
  try {
    const r = await api('/api/riprendi/' + dati.task);
    const slot = $('#riprendi-stato-slot');
    if (slot) slot.innerHTML = bottoneRiprendi({ ...r.riprendi, id: dati.task, messaggio: r.messaggio },
      r.sessione_data);
  } catch (err) {
    // Un task che GET /api/riprendi non trova (cancellato nel frattempo), o
    // l'interrogazione delle sessioni aperte fallita: il segnaposto lascia
    // il posto al modulo "In background", niente pulsante di stato.
    const slot = $('#riprendi-stato-slot');
    if (slot) slot.innerHTML = '';
  }
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

views.progetti = async () => {
  // LOTTO-L4-MEMORIA (correzione del critico, punto "la spia"): quando non
  // c'è niente in cassa il fetch va salvato in state.overview (prima si
  // buttava via tutto tranne .progetti), altrimenti la prossima vista che
  // legge state.overview lo trova ancora vuoto e rifà la stessa richiesta -
  // e senza state.overviewQuando la spia non saprebbe mai l'ora di QUESTI
  // dati quando un'altra vista li riuserà dalla cassa.
  if (!state.overview) { state.overview = await api('/api/overview?lang=' + UILANG); state.overviewQuando = new Date(); }
  const list = state.overview.progetti;
  const groups = [['attivo', T('attivo')], ['idea', T('idea')], ['in pausa', T('in pausa')], ['concluso', T('concluso')]];
  // Annidamento (LOTTO-L2-VISTA punto 4): /api/overview porta già
  // parent_id su ogni progetto (colonna di projects, letta con "p.*" in
  // plancia/api.py:overview), quindi il nido si costruisce qui dai dati che
  // la vista scarica comunque, senza una seconda chiamata a
  // /api/projects?albero=1; quell'endpoint resta per chi vuole solo
  // l'albero (stessa slot.albero(), stessi totali, vedi plancia/api.py), ma
  // qui servirebbe solo a duplicare un calcolo già fatto da /api/overview
  // (che in più porta repos e token_30g, che slot.albero() non calcola).
  // Un figlio non compare mai come card a sé nel proprio gruppo di stato:
  // resta sempre dentro il padre, qualunque sia lo stato del figlio.
  const figliDiId = {};
  list.forEach((p) => { if (p.parent_id) (figliDiId[p.parent_id] = figliDiId[p.parent_id] || []).push(p); });
  const eFiglio = new Set(list.filter((p) => p.parent_id).map((p) => p.id));

  return `
  <div class="view-head"><h1>${T('Progetti')}</h1><p>${list.length} ${T('tracciati')}</p></div>
  ${groups.map(([st, label]) => {
    const items = list.filter((p) => p.status === st && !eFiglio.has(p.id));
    if (!items.length) return '';
    return `<h3 style="margin:18px 0 10px;color:var(--faint);font-size:12px;text-transform:uppercase;letter-spacing:.05em">${label} · ${items.length}</h3>
    <div class="albero cards">${items.map((p) =>
      figliDiId[p.id] ? alberoPadre(p, figliDiId[p.id]) : projectCard(p)).join('')}</div>`;
  }).join('')}`;
};

/* Un padre con figli (LOTTO-L2-VISTA punto 4): nasce APERTO, figli visibili
   sotto (.albero-figli senza [hidden]) - solo `cartelle-viste` (il
   contenitore delle cartelle senza un manuale, kind infra, creato da
   plancia/ingest.py e plancia/riordina.py) nasce chiuso
   (.albero-padre.chiusa, [hidden] su .albero-figli): non è "un'idea di
   cartelle raggruppate" in generale, è quell'area specifica, e il verdetto
   (docs/CONSIGLIO-2026-09-16-verdetto.md) la vuole chiusa di default in
   quanto tale, non come regola per ogni padre. Il toggle è sul bottone
   .albero-toggle (data-act="albero-toggle" nel listener), i totali sommati
   padre+figli vanno su .albero-totali. Il click che apre il drawer resta
   sul nome/descrizione, non sull'intera card: altrimenti coprirebbe anche
   il bottone del toggle (il listener dei click controlla prima [data-act],
   quindi non ci sarebbe un conflitto reale, ma un'area di click più piccola
   e precisa per "apri il progetto" evita comunque l'ambiguità visiva di una
   card che fa due cose diverse a seconda di dove la tocchi). */
function alberoPadre(padre, figli) {
  const task = (padre.task_aperti || 0) + figli.reduce((n, f) => n + (f.task_aperti || 0), 0);
  const sessioni = (padre.sessioni || 0) + figli.reduce((n, f) => n + (f.sessioni || 0), 0);
  // Residuo dei tester dell'ondata 2 (16/09/2026), punto 5: la card del
  // padre aveva solo priorità e i due totali, non le altre informazioni che
  // una projectCard normale porta già (kind, token, repo, pinned) né i
  // totali veri del sottoalbero per token e ultima attività.
  const token30 = (padre.token_30g || 0) + figli.reduce((n, f) => n + (f.token_30g || 0), 0);
  const ultimaAttivita = figli.reduce(
    (max, f) => (f.last_activity && f.last_activity > (max || '')) ? f.last_activity : max,
    padre.last_activity);
  const chiusa = padre.key === 'cartelle-viste';
  // Il nome di 'cartelle-viste' passa da T() (chiave 'cartelle_viste') così
  // l'inglese non mostra il nome italiano del progetto: per ogni altro
  // padre il nome resta quello vero, che non è una chiave da tradurre.
  const nome = chiusa ? T('cartelle_viste') : padre.name;
  return `
  <div class="albero-padre card${chiusa ? ' chiusa' : ''}${padre.pinned ? ' pinned' : ''}" data-chiave="${esc(padre.key)}">
    <div style="display:flex;align-items:baseline;gap:8px" data-project="${esc(padre.key)}">
      <h4>${esc(nome)}</h4>
      <span class="spacer" style="margin-left:auto"></span>
      <span class="tag ${padre.priority === 1 ? 'danger' : ''}">${prioTag(padre.priority)}</span>
    </div>
    <div class="desc clamp2" data-project="${esc(padre.key)}">${
      esc(padre.summary || padre.next_action) || T('nessuna descrizione')}</div>
    <div class="meta albero-totali">
      <span class="tag">${T(padre.kind)}</span>
      ${task ? `<span class="tag warn">${task} ${task === 1 ? T('task aperto') : T('task aperti')}</span>` : ''}
      ${sessioni ? `<span class="tag">${sessioni} ${T('sessioni')}</span>` : ''}
      ${token30 ? `<span class="tag mono" title="${T('token generati negli ultimi 30 giorni')}">${kilo(token30)}</span>` : ''}
      ${padre.repos ? `<span class="tag info mono">${esc(String(padre.repos).split(',')[0])}</span>` : ''}
      <span style="margin-left:auto">${ago(ultimaAttivita)}</span>
    </div>
    <button class="mini albero-toggle" type="button" data-act="albero-toggle">${progettiN(figli.length)}</button>
    <div class="albero-figli"${chiusa ? ' hidden' : ''}>${figli.map((f) => projectCard(f, 'albero-figlio')).join('')}</div>
  </div>`;
}

const projectCard = (p, extra = '') => `
  <div class="card ${extra} ${p.pinned ? 'pinned' : ''} ${p.status === 'concluso' ? 'dim' : ''}"
       data-project="${esc(p.key)}" data-chiave="${esc(p.key)}">
    <div style="display:flex;align-items:baseline;gap:8px">
      <h4>${esc(p.name)}</h4>
      <span class="spacer" style="margin-left:auto"></span>
      <span class="tag ${p.priority === 1 ? 'danger' : ''}">${prioTag(p.priority)}</span>
    </div>
    <div class="desc clamp2">${esc(p.summary || p.next_action) || T('nessuna descrizione')}</div>
    <div class="meta">
      <span class="tag">${T(p.kind)}</span>
      ${p.task_aperti ? `<span class="tag warn">${p.task_aperti} ${p.task_aperti === 1 ? T('task aperto') : T('task aperti')}</span>` : ''}
      ${p.sessioni ? `<span class="tag">${p.sessioni} ${T('sessioni')}</span>` : ''}
      ${p.token_30g ? `<span class="tag mono" title="${T('token generati negli ultimi 30 giorni')}">${kilo(p.token_30g)}</span>` : ''}
      ${p.repos ? `<span class="tag info mono">${esc(String(p.repos).split(',')[0])}</span>` : ''}
      <span style="margin-left:auto">${ago(p.last_activity)}</span>
    </div>
  </div>`;

async function bloccoTask(soloCorpo) {
  const f = state.filters.task || (state.filters.task = { status: 'aperti', project: '' });
  const [tasks, projects] = await Promise.all([
    api(`/api/tasks?status=${encodeURIComponent(f.status)}${f.project ? '&project=' + encodeURIComponent(f.project) : ''}`),
    api('/api/projects'),
  ]);
  return `
  ${soloCorpo ? '' : `<div class="view-head"><h1>${T('Task')}</h1><p>${tasks.length} ${T('in elenco')}</p></div>`}
  <div class="filters">
    ${['aperti', 'in corso', 'bloccato', 'fatto', 'tutti'].map((s) =>
      `<span class="chip ${f.status === s ? 'on' : ''}" data-filter="task.status" data-value="${s}">${T(s)}</span>`).join('')}
    <select data-filter-select="task.project" style="margin-left:auto">
      <option value="">${T('tutti i progetti')}</option>
      ${projects.map((p) => `<option value="${esc(p.key)}" ${f.project === p.key ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}
    </select>
  </div>
  <div class="panel">
    <form class="inline-form" data-form="task-quick">
      <input type="text" name="title" placeholder="${T('Nuovo task')}" autocomplete="off">
      <select name="project" style="width:170px">
        <option value="${esc(f.project)}">${esc(projects.find((p) => p.key === f.project)?.name || 'nessun progetto')}</option>
        ${projects.filter((p) => p.key !== f.project).map((p) => `<option value="${esc(p.key)}">${esc(p.name)}</option>`).join('')}
      </select>
      <select name="priority" style="width:110px">
        <option value="2">${T('media')}</option><option value="1">${T('alta')}</option><option value="3">${T('bassa')}</option>
      </select>
      <button class="primary" type="submit">${T('Aggiungi')}</button>
    </form>
    <div class="panel-body tight">${taskRows(tasks)}</div>
  </div>`;
};

const LANES = [['idea', 'Idee'], ['bozza', 'Bozze'], ['approvato', 'Approvati'],
  ['programmato', 'Programmati'], ['pubblicato', 'Pubblicati']];  // etichette tradotte in vista
const NEXT = { idea: 'bozza', bozza: 'approvato', approvato: 'programmato', programmato: 'pubblicato' };

views.social = async () => {
  const [posts, projects] = await Promise.all([api('/api/posts'), api('/api/projects')]);
  return `
  <div class="view-head">
    <h1>${T('Social')}</h1><p>${T('ogni post è legato al lavoro che lo ha prodotto')}</p>
    <span class="spacer"></span>
    <button class="ghost" data-act="post-new">${T('Nuova bozza')}</button>
  </div>
  <div class="kanban">
    ${LANES.map(([st, label]) => {
      const items = posts.filter((p) => p.status === st);
      return `<div class="klane"><h4>${T(label)}<span>${items.length}</span></h4>
        <div class="kbody">${items.map((p) => `
          <div class="kcard" data-chiave="${p.id}">
            <div class="txt">${esc(p.text.length > 260 ? p.text.slice(0, 260) + '…' : p.text)}</div>
            ${p.source_ref ? `<div class="foot mono truncate">${T('fonte')}: ${esc(p.source_ref)}</div>` : ''}
            <div class="foot">
              <span class="tag">${esc(p.platform)}</span>
              ${p.project ? `<span class="tag info">${esc(p.project)}</span>` : ''}
              <span class="spacer"></span>
              ${p.url ? `<a class="mini" href="${esc(p.url)}" target="_blank" rel="noopener">${T('apri')}</a>` : ''}
              ${NEXT[p.status] ? `<button class="mini go" data-act="post-next" data-id="${p.id}" data-next="${NEXT[p.status]}">→ ${T(NEXT[p.status])}</button>` : ''}
              ${p.status !== 'pubblicato' ? `<button class="mini" data-act="post-edit" data-id="${p.id}">url</button>` : ''}
            </div>
          </div>`).join('') || `<div class="empty" style="padding:14px;font-size:12px">${T('vuoto')}</div>`}
        </div></div>`;
    }).join('')}
  </div>
  <div class="panel" style="margin-top:16px" id="post-form" hidden>
    <header><h3>${T('Nuova bozza')}</h3></header>
    <div class="panel-body">
      <form data-form="post-new" style="display:flex;flex-direction:column;gap:10px">
        <textarea name="text" placeholder="${T('Il testo del post')}" required></textarea>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <select name="platform" style="width:130px"><option value="x">x</option><option value="linkedin">linkedin</option><option value="bluesky">bluesky</option><option value="mastodon">mastodon</option><option value="hn">hn</option><option value="reddit">reddit</option></select>
          <select name="project" style="width:190px"><option value="">nessun progetto</option>
            ${projects.map((p) => `<option value="${esc(p.key)}">${esc(p.name)}</option>`).join('')}</select>
          <input type="text" name="source_ref" placeholder="${T('fonte: commit, repo, sessione')}" style="flex:1;min-width:200px">
          <button class="primary" type="submit">${T('Salva bozza')}</button>
        </div>
      </form>
    </div>
  </div>`;
};

async function bloccoSessioni(soloCorpo) {
  const f = state.filters.sessioni || (state.filters.sessioni = { q: '', project: '', agent: '' });
  const [rows, projects] = await Promise.all([
    api(`/api/sessions?limit=150${f.q ? '&q=' + encodeURIComponent(f.q) : ''}${f.project ? '&project=' + encodeURIComponent(f.project) : ''}${f.agent ? '&agent=' + f.agent : ''}`),
    api('/api/projects'),
  ]);
  return `
  ${soloCorpo ? '' : `<div class="view-head"><h1>${T('Sessioni')}</h1><p>${rows.length} ${T('conversazioni con Claude Code')}</p></div>`}
  <div class="filters">
    <input type="search" data-filter-input="sessioni.q" value="${esc(f.q)}" placeholder="${T('cerca nel primo messaggio…')}" style="min-width:280px">
    ${['', 'claude', 'codex'].map((a) =>
      `<span class="chip ${f.agent === a ? 'on' : ''}" data-filter="sessioni.agent" data-value="${a}">${a || T('tutti')}</span>`).join('')}
    <select data-filter-select="sessioni.project">
      <option value="">${T('tutti i progetti')}</option>
      ${projects.map((p) => `<option value="${esc(p.key)}" ${f.project === p.key ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}
    </select>
  </div>
  <div class="panel"><table>
    <thead><tr><th>${T('quando')}</th><th>${T('di cosa')}</th><th>${T('agente')}</th><th>${T('progetto')}</th><th style="text-align:right">${T('turni')}</th><th style="text-align:right">${T('tool')}</th><th></th></tr></thead>
    <tbody>${rows.map((s) => `
      <tr>
        <td class="num" style="white-space:nowrap;color:var(--faint)">${dateIt(s.started_at)}<br><small>${ago(s.started_at)}</small></td>
        <td><div style="max-width:520px">
          <div>${esc(s.title || (s.prompt || s.first_prompt || '').slice(0, 90)) || T('senza titolo')}</div>
          <div class="sub clamp2" style="color:var(--faint);font-size:11.5px">${esc((s.first_prompt || '').slice(0, 190))}</div>
        </div></td>
        <td><span class="tag agente ${s.agent === 'codex' ? 'codex' : ''}">${esc(s.agent || 'claude')}</span></td>
        <td>${s.progetto ? `<span class="tag">${esc(s.progetto)}</span>` : '<span style="color:var(--faint)">—</span>'}
          ${s.dedotto_da === 'percorsi' ? `<div class="sub" style="color:var(--faint);font-size:10.5px"
            title="${esc(s.dir_dedotta || '')}">${T('dedotta dai percorsi')}</div>` : ''}</td>
        <td class="num" style="text-align:right">${num(s.n_user)}</td>
        <td class="num" style="text-align:right">${num(s.n_tools)}</td>
        <td style="text-align:right;white-space:nowrap">
          <button class="mini" data-act="copy-resume" data-id="${esc(s.session_id)}" data-cwd="${esc(s.cwd || '')}">${T('riprendi')}</button>
        </td>
      </tr>`).join('') || `<tr><td colspan="7" class="empty">${T('nessuna sessione')}</td></tr>`}
    </tbody>
  </table></div>`;
};

async function bloccoConoscenza(soloCorpo) {
  const rows = await api('/api/knowledge');
  const byType = {};
  rows.forEach((r) => (byType[r.type || 'altro'] = byType[r.type || 'altro'] || []).push(r));
  const label = { project: T('Progetti'), feedback: T('Come lavorare'), user: T('Chi sei'), reference: T('Riferimenti'), altro: T('Altro') };
  return `
  ${soloCorpo ? '' : `<div class="view-head"><h1>${T('Conoscenza')}</h1><p>${rows.length} ${T('memorie indicizzate da Claude')}</p></div>`}
  ${Object.entries(byType).map(([type, items]) => `
    <h3 style="margin:18px 0 10px;color:var(--faint);font-size:12px;text-transform:uppercase;letter-spacing:.05em">${label[type] || type} · ${items.length}</h3>
    <div class="panel"><div class="panel-body tight">
      ${items.map((k) => `
        <div class="row" data-memory="${esc(k.name)}" style="cursor:pointer">
          <div class="main">
            <div class="title">${esc(k.name)}</div>
            <div class="sub clamp2">${esc(k.description || '')}</div>
          </div>
          <div class="side">${k.progetto ? `<span class="tag">${esc(k.progetto)}</span>` : ''}<span class="tag mono">${ago(k.updated_at)}</span></div>
        </div>`).join('')}
    </div></div>`).join('')}`;
};

/* ------------------------------------------------------------------ memoria */
/* L'elenco delle memorie stava già in Archivio, e diceva cosa c'è. Qui si vede
   com'è messo: chi tira le fila, cosa non è legato a niente, e soprattutto cosa
   il richiamo potrà davvero andare a prendere quando serve, che da quando il
   richiamo esiste è la domanda vera. Le posizioni dei nodi le calcola il server
   e non cambiano mai: una mappa che si ridispone a ogni apertura non si impara. */

const TIPI_MEM = [['feedback', 'preferenze'], ['user', 'chi sei'],
                  ['reference', 'riferimenti'], ['project', 'progetti']];

const LENTI = [['', 'tutte'], ['doppie', 'in due cartelle'], ['orfane', 'senza legami'],
               ['rotti', 'link rotti'], ['vuote', 'quasi vuote']];

/* Chi finisce sotto la lente. Fuori da lì i nodi restano, ma spenti: togliere
   il resto della mappa farebbe perdere il punto di riferimento. */
function accesiMem(m, lente) {
  const d = m.diagnosi;
  if (lente === 'doppie') return new Set(d.doppie.map((x) => x.nome));
  if (lente === 'orfane') return new Set(d.orfane);
  if (lente === 'vuote') return new Set(d.vuote);
  if (lente === 'rotti') return new Set(d.rotti.map((x) => x.da));
  return null;
}

function mappaMem(m, lente) {
  const W = 1000, H = 520;
  const acceso = accesiMem(m, lente);
  const dove = {};
  m.nodi.forEach((n) => { dove[n.nome] = [n.x * W, n.y * H]; });
  const archi = m.archi.map((a) => {
    const p = dove[a.da], q = dove[a.a];
    if (!p || !q) return '';
    const vivo = !acceso || acceso.has(a.da) || acceso.has(a.a);
    return `<line x1="${p[0].toFixed(1)}" y1="${p[1].toFixed(1)}" x2="${q[0].toFixed(1)}"
      y2="${q[1].toFixed(1)}" class="marco${vivo ? '' : ' spento'}"/>`;
  }).join('');
  // Le etichette si contendono lo spazio con le altre etichette e con i nodi:
  // un nome scritto sopra due pallini non si legge più di due nomi sovrapposti.
  // I cerchi prenotano il posto per primi, poi i nomi, in ordine di grado, così
  // chi tira le fila lo dice e chi non ne ha tace.
  // Sotto la lente prenotano il posto solo i nodi accesi: gli altri sono
  // sbiaditi al diciotto per cento, e un nome che ci passa sopra si legge
  // lo stesso. Senza questo, accendere otto memorie ne mostrava quattro.
  const presi = m.nodi.filter((n) => !acceso || acceso.has(n.nome)).map((n) => {
    const r = 5 + Math.min(n.grado, 18) * 1.05;
    return [n.x * W - r, n.y * H - r, n.x * W + r, n.y * H + r];
  });
  const cape = (x, y, testo, ancora) => {
    const largo = testo.length * 5.6, alto = 13;
    const sx = ancora === 'start' ? x : ancora === 'end' ? x - largo : x - largo / 2;
    const box = [sx, y - alto, sx + largo, y];
    if (presi.some((p) => box[0] < p[2] && box[2] > p[0] && box[1] < p[3] && box[3] > p[1])) {
      return false;
    }
    presi.push(box);
    return true;
  };
  const nodi = m.nodi.map((n) => {
    const [x, y] = dove[n.nome];
    const r = 5 + Math.min(n.grado, 18) * 1.05;
    const vivo = !acceso || acceso.has(n.nome);
    // L'etichetta solo a chi tira le fila, o a chi la lente ha appena acceso:
    // scriverle tutte e quarantasette vuol dire non leggerne nessuna.
    const merita = vivo && (n.grado >= 4 || (acceso && acceso.has(n.nome)));
    const nome = merita ? esc(n.nome) : '';
    // Vicino ai bordi il nome si aggancia dal lato che lo tiene dentro il
    // riquadro, invece di uscire e farsi tagliare.
    const ancora = n.x < 0.14 ? 'start' : n.x > 0.86 ? 'end' : 'middle';
    // Sopra il nodo, tranne quando il nodo sta troppo in alto: lì l'etichetta
    // uscirebbe dal riquadro, quindi passa sotto.
    const ty = y - r - 5 > 12 ? y - r - 5 : y + r + 12;
    const scritta = nome && cape(x, ty, n.nome, ancora);
    // Il nome per esteso al passaggio del mouse: le etichette scritte sono
    // poche per forza, ma nessun pallino deve restare senza nome.
    const dove2 = (n.dove || []).join(', ');
    return `<g data-memory="${esc(n.nome)}" class="mnodo ${esc(n.tipo)}${vivo ? '' : ' spento'}${
      n.richiamabile ? ' preso' : ''}">
      <title>${esc(n.nome)} · ${esc(n.tipo)}${dove2 ? ' · ' + esc(dove2) : ''}</title>
      <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(1)}"/>
      ${scritta ? `<text x="${x.toFixed(1)}" y="${ty.toFixed(1)}"
        text-anchor="${ancora}">${nome}</text>` : ''}
    </g>`;
  }).join('');
  return `<svg class="mmappa" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
    <g class="archi">${archi}</g>${nodi}</svg>`;
}

/* Le poche cose contabili, e niente di più. Un pannello che elenca nove difetti
   ogni volta che lo apri diventa un rimprovero fisso, e al terzo giorno non lo
   apri più: quando non c'è niente, resta quasi bianco, ed è il premio. */
function guaiMem(d) {
  const voci = [];
  if (d.doppie.length) voci.push([d.doppie.length, 'in due cartelle',
    d.doppie.map((x) => x.nome).join(', ')]);
  if (d.orfane.length) voci.push([d.orfane.length, 'senza legami', d.orfane.join(', ')]);
  if (d.rotti.length) voci.push([d.rotti.length, 'link rotti',
    d.rotti.map((x) => x.da + ' → ' + x.verso).join(', ')]);
  if (d.vuote.length) voci.push([d.vuote.length, 'quasi vuote', d.vuote.join(', ')]);
  const righe = voci.map(([quante, etichetta, chi]) => `<div class="row">
    <div class="main"><div class="title">${quante} ${T(etichetta)}</div>
    <div class="sub clamp2">${esc(chi)}</div></div></div>`).join('');
  // Un rinvio a una memoria che non c'è, ma verso un progetto che esiste, non
  // è un guasto: è una memoria che varrebbe la pena scrivere. Va detto con
  // un'altra voce, se no un invito si legge come un errore.
  const invito = (d.da_scrivere || []).length ? `<div class="row">
    <div class="main"><div class="title">${d.da_scrivere.length} ${
      T('da scrivere')}</div>
    <div class="sub clamp2">${esc(d.da_scrivere.join(', '))} · ${
      T('le citi in altre memorie ma non le hai mai scritte')}</div></div></div>` : '';
  if (!righe && !invito) return `<p class="sub">${T('niente da sistemare')}</p>`;
  return righe + invito;
}

views.memoria = async () => {
  const f = state.filters.memoria || (state.filters.memoria = { lente: '' });
  const m = await api('/api/memoria/mappa');
  const d = m.diagnosi;
  if (!d.totale) {
    return `<div class="view-head"><h1>${T('Memoria')}</h1></div>
      <div class="empty">${T('nessuna memoria')}</div>`;
  }
  const conta = {};
  m.nodi.forEach((n) => { conta[n.tipo] = (conta[n.tipo] || 0) + 1; });
  return `
  <div class="view-head">
    <h1>${T('Memoria')}</h1>
    <p>${T('che forma ha quello che Claude si ricorda di te')}</p>
  </div>

  <div class="panel"><div class="panel-body">
    <div class="mtesta">
      <div><b class="num">${d.totale}</b> <span class="label">${T('fatti')}</span></div>
      <div><b class="num">${d.richiamabili}</b> <span class="label">${
        T("che il richiamo può andare a prendere da un'altra cartella")}</span></div>
      <span class="spacer"></span>
      <div class="filters" style="margin:0">${LENTI.map(([k, etichetta]) =>
        `<span class="chip ${f.lente === k ? 'on' : ''}" data-filter="memoria.lente"
          data-value="${k}">${T(etichetta)}</span>`).join('')}</div>
    </div>
    ${mappaMem(m, f.lente)}
    <div class="mlegenda">${TIPI_MEM.map(([k, etichetta]) =>
      `<span class="mvoce ${k}"><i></i>${T(etichetta)} <em>${conta[k] || 0}</em></span>`).join('')}
      <span class="spacer"></span>
      <span class="sub">${T('pieno vuol dire che il richiamo può portarla in contesto')}</span>
    </div>
    <p class="sub" style="margin:6px 0 0">${
      T('i legami sono i doppi quadri che hai scritto a mano: due memorie sullo stesso argomento senza un legame, qui sembrano estranee')}</p>
  </div></div>

  <div class="grid cols-2">
    <div class="panel"><header><b>${T('Cosa ti direbbe')}</b>
      <span class="sub">${T('scrivi una frase e guarda cosa ti richiamerebbe')}</span></header>
      <div class="panel-body">
        <div class="inline-form">
          <input id="mfrase" autocomplete="off"
            placeholder="${T('una frase qualsiasi, come la scriveresti a Claude')}">
          <button class="mini go" data-act="mprova">${T('Prova')}</button>
        </div>
        <div id="mesito"></div>
      </div>
    </div>
    <div class="panel"><header><b>${T('Da sistemare')}</b></header>
      <div class="panel-body tight">${guaiMem(d)}</div>
    </div>
  </div>`;
};

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
      ${items.map((r) => `<div class="row"><div class="main">
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

/* ---------------------------------------------------------------- drawer */
async function openProject(key) {
  const d = await api('/api/projects/' + encodeURIComponent(key));
  const p = d.progetto;
  $('#drawer-body').innerHTML = `
    <h2>${esc(p.name)}</h2>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px">
      <span class="tag ${statusClass[p.status] || ''}">${T(p.status)}</span>
      <span class="tag">${T(p.kind)}</span>
      <span class="tag">${T('priorità')} ${prioTag(p.priority)}</span>
      <span class="tag mono">${esc(p.key)}</span>
      <span class="tag">attivo ${ago(p.last_activity)}</span>
    </div>
    <p style="color:var(--muted)">${esc(p.summary || '')}</p>

    <section>
      <h3>${T('Governo')}</h3>
      <form data-form="project-edit" data-key="${esc(p.key)}" style="display:flex;flex-direction:column;gap:8px">
        <input type="text" name="next_action" value="${esc(p.next_action || '')}" placeholder="${T('prossimo passo concreto')}">
        <div style="display:flex;gap:8px">
          <select name="status" style="width:150px">${['attivo', 'in pausa', 'idea', 'concluso']
            .map((s) => `<option value="${s}" ${p.status === s ? 'selected' : ''}>${T(s)}</option>`).join('')}</select>
          <select name="priority" style="width:130px">${[[1, 'alta'], [2, 'media'], [3, 'bassa']]
            .map(([v, l]) => `<option value="${v}" ${p.priority === v ? 'selected' : ''}>${T(l)}</option>`).join('')}</select>
          <button class="primary" type="submit">${T('Salva')}</button>
        </div>
      </form>
    </section>

    ${section(T('Task'), sezioneTaskDrawer(d.task))}

    ${cassettoDopo(p, d.task)}

    ${d.memoria.length ? section(T('Memoria'), d.memoria.map((k) =>
      `<div class="row" data-memory="${esc(k.name)}" style="cursor:pointer;border:1px solid var(--border);border-radius:8px;margin-bottom:6px">
        <div class="main"><div class="title">${esc(k.name)}</div><div class="sub clamp2">${esc(k.description || '')}</div></div>
      </div>`).join('')) : ''}

    ${d.repo.length ? section(T('Repository'), d.repo.map((r) =>
      `<div class="row" style="border:1px solid var(--border);border-radius:8px;margin-bottom:6px">
        <div class="main"><div class="title mono">${esc(r.name)}</div>
        <div class="sub">${esc(r.description || r.local_path || '')}</div></div>
        <div class="side">${r.visibility ? `<span class="tag">${esc(r.visibility)}</span>` : ''}
        ${r.dirty ? `<span class="tag warn">${r.dirty} ${T('modifiche')}</span>` : ''}
        ${r.url ? `<a class="mini" href="${esc(r.url)}" target="_blank" rel="noopener">github</a>` : ''}</div>
      </div>`).join('')) : ''}

    ${d.commit.length ? section(T('Commit recenti'), `<div class="panel"><div class="panel-body tight">${
      d.commit.slice(0, 12).map((c) => `<div class="row"><div class="main">
        <div class="title truncate">${esc(c.message)}</div>
        <div class="sub mono">${esc(c.repo)} · ${esc((c.sha || '').slice(0, 7))} · ${ago(c.date)}${
          c.sessione_titolo ? ` · <span style="opacity:.75">${T('da')} ${esc(c.sessione_titolo.slice(0, 46))}</span>` : ''}</div>
      </div></div>`).join('')}</div></div>`) : ''}

    ${d.sessioni.length ? section(T('Sessioni'), `<div class="panel"><div class="panel-body tight">${
      d.sessioni.slice(0, 12).map((s) => `<div class="row"><div class="main">
        <div class="title truncate">${esc(s.title || (s.prompt || '').slice(0, 80)) || T('senza titolo')}</div>
        <div class="sub">${dateIt(s.started_at)} · ${s.n_user} scambi · ${s.n_tools} tool${
          s.dedotto_da === 'percorsi' ? ' · ' + T('dedotta dai percorsi') : ''}</div>
      </div><div class="side"><button class="mini" data-act="copy-resume" data-id="${esc(s.session_id)}" data-cwd="">riprendi</button></div></div>`).join('')}</div></div>`) : ''}

    ${d.post.length ? section(T('Post'), d.post.map((o) =>
      `<div class="kcard" style="margin-bottom:8px"><div class="txt">${esc(o.text)}</div>
      <div class="foot"><span class="tag ${statusClass[o.status] || ''}">${T(o.status)}</span>
      <span class="tag">${esc(o.platform)}</span></div></div>`).join('')) : ''}

    ${section(T('Cronologia'), `<div class="tl">${timeline(d.eventi.slice(0, 30))}</div>`)}
  `;
  $('#drawer').hidden = false;
}

const section = (title, html) => `<section><h3>${title}</h3>${html}</section>`;

/* Residuo dei tester dell'ondata 2 (16/09/2026), punto 4: la sezione "Task"
   del drawer mostrava OGNI task non archiviato, compresi tutti quelli
   aperti - non solo il primo (quello che slot.prossimi() chiama "cosa") - e
   il cassetto "Dopo" qui sotto li ripeteva daccapo (aperti.slice(1)), righe
   duplicate fra le due sezioni. Qui resta solo il primo task aperto (se
   c'è) più quelli chiusi/fatti: il resto sta solo nel cassetto. */
function sezioneTaskDrawer(task) {
  const aperti = task.filter((t) => ['aperto', 'in corso', 'bloccato'].includes(t.status));
  const resto = task.filter((t) => !['aperto', 'in corso', 'bloccato', 'archiviato'].includes(t.status));
  const mostrati = (aperti.length ? [aperti[0]] : []).concat(resto);
  return mostrati.length
    ? `<div class="panel"><div class="panel-body tight">${taskRows(mostrati)}</div></div>`
    : `<p style="color:var(--faint)">${T('nessuno')}</p>`;
}

/* Il cassetto "Dopo" del drawer (LOTTO-L2-VISTA punto 3): il conteggio è
   calcolato qui, dai task che il drawer ha già (d.task, stesso ordine di
   actions.tasks_list di /api/tasks?project=&dopo=1: "il primo" è sempre lo
   stesso in entrambi i posti); il contenuto invece si carica al click, da
   quell'endpoint, per non portare a video una lista che nessuno apre mai. */
function cassettoDopo(p, task) {
  const aperti = task.filter((t) => ['aperto', 'in corso', 'bloccato'].includes(t.status));
  const conta = Math.max(0, aperti.length - 1);
  if (!conta) return '';
  return `
  <section class="cassetto-dopo">
    <h3 data-act="cassetto-dopo" data-key="${esc(p.key)}">${conN('dopo_conta', conta)}</h3>
    <div class="cassetto-dopo-lista" hidden></div>
  </section>`;
}

async function openMemory(name) {
  const k = await api('/api/knowledge?name=' + encodeURIComponent(name));
  $('#drawer-body').innerHTML = `
    <h2>${esc(k.name)}</h2>
    <div style="display:flex;gap:6px;margin-bottom:10px">
      <span class="tag">${T(k.type || 'memoria')}</span>
      <span class="tag mono">${ago(k.updated_at)}</span>
    </div>
    <p style="color:var(--muted)">${esc(k.description || '')}</p>
    <div class="md" style="margin-top:16px">${md(k.body)}</div>
    <p style="color:var(--faint);font-size:11px;margin-top:22px" class="mono">${esc(k.path)}</p>`;
  $('#drawer').hidden = false;
}

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

/* La spia (punto 4): una pillola in topbar che dice se quello che si vede è
   fresco o è la memoria di prima. `stato` è 'aggiorno' (memoria in vista,
   fetch in corso), 'fresco' (fetch riuscito) o 'rotto' (fetch caduto, la
   memoria resta a schermo). Fuori da questi tre casi (prima apertura, prima
   che il primo fetch sia mai partito) la pillola resta nascosta: non c'è
   ancora niente di cui dare conto. */
const oraCorta = (ts) => (ts ? new Date(ts) : new Date())
  .toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' });

function spiaAggiorna(stato, quando) {
  const el = $('#spia-memoria');
  if (!el) return;
  if (!stato) { el.hidden = true; return; }
  el.hidden = false;
  el.title = T('spia_titolo');
  el.classList.toggle('avviso', stato === 'rotto');
  if (stato === 'aggiorno') el.textContent = T('spia_aggiorno');
  else if (stato === 'rotto') el.textContent = fmt('spia_memoria', { ora: oraCorta(quando) });
  else el.textContent = fmt('spia_aggiornato', { ora: oraCorta(quando) });
}

/* Il vortice (punto 3): FLIP sugli elementi con [data-chiave] (le card dei
   progetti nell'albero e nella griglia, le righe di Prossimi, le card del
   kanban - vedi projectCard, alberoPadre, rigaProssimo, views.social più
   sopra). Si misurano le posizioni PRIMA di toccare il DOM (mentre è ancora
   quello vecchio, quello di memoria), si sostituisce l'html, poi si misurano
   le posizioni DOPO sugli elementi nuovi con la stessa chiave: chi
   sopravvive (stessa chiave nei due momenti) anima dalla vecchia posizione
   alla nuova con `transform` - mai `opacity` (vedi il commento in
   web/moto.css: una finestra coperta sospende le animazioni css, e un
   elemento fermo a opacity:0 resterebbe invisibile per sempre, il contrario
   di "mai vuota"). Chi è nuovo (chiave non vista un momento fa) non ha da
   dove animare uno spostamento: entra con .vortice-entra, il ritardo dato da
   --i (impostato qui, letto da moto.css), fermo a un tetto cosicché tredici
   card o tremila non superino mai i 320ms totali che il lotto chiede. Gli
   elementi spariti non ricevono nessun trattamento: sono già scomparsi con
   la sostituzione dell'html, un elemento che non c'è più non si anima.

   Correzione del critico (il vortice non animava affatto, misurato
   sull'app vera): web/style.css:.card ha GIÀ una `transition` su `transform`
   (240ms, per l'hover), sempre attiva - non solo mentre corre .vortice-muove.
   Se si legge un rect (getBoundingClientRect forza un ricalcolo di stile) fra
   la scrittura del transform inverso di un elemento e quella del prossimo,
   quella lettura fa scattare la transizione di .card SUL transform appena
   scritto: l'elemento comincia a scivolare verso lo zero mentre il codice
   crede ancora di essere nella fase "posiziona senza animare", e la classe
   .vortice-muove (che dovrebbe SEGNARE l'inizio dell'animazione) arriva a
   metà di una transizione già partita per conto suo. Il rimedio è
   l'ordine classico del FLIP, in tre passate separate, mai intrecciate:
   (1) SOLE LETTURE - tutti i rect "dopo" di tutti gli elementi sopravvissuti,
   prima di scrivere qualunque cosa; (2) SOLE SCRITTURE - per ogni elemento
   che si muove, transition:'none' (spegne la transizione di .card mentre si
   scrive la posizione di partenza) e transform = l'inverso; (3) UN SOLO
   reflow forzato (`view.offsetHeight`, letto e buttato via) che fa
   applicare (2) per davvero prima di procedere - senza, il motore potrebbe
   fondere (2) e la scrittura del rAF qui sotto nello stesso giro di stile e
   non animare niente. Solo nel rAF che segue si toglie transition:'none' (si
   assegna una transizione inline che vince su quella di .card qualunque sia
   l'ordine in cui i due foglietti sono linkati), si aggiunge .vortice-muove
   per chi la legge da fuori, e si azzera il transform: È QUESTO il momento
   in cui l'animazione comincia, non un secondo giro di rAF (che qui non
   serve più: il reflow forzato al passo (3) fa già da spartiacque fra "stato
   vecchio applicato" e "stato nuovo in transizione").

   Annidati (correzione del critico): un .albero-padre con [data-chiave] può
   contenere .albero-figlio con [data-chiave] loro (vedi alberoPadre più
   sopra). Se il padre si muove e il figlio riceve ANCHE lui un transform
   proprio, il figlio finisce per somministrare due spostamenti (il suo più
   quello, ereditato via CSS, del padre) e ruota attorno al centro del padre
   invece che al proprio. Si anima solo lo spostato più esterno: un elemento
   con un antenato [data-chiave] già in movimento non riceve trasformazioni
   proprie, ci arriva già portato dal padre.

   Rect nulli (correzione del critico): una riga di Prossimi oltre
   PROSSIMI_TETTO porta [hidden] finché non si preme "altri" - il suo rect è
   {0,0,0,0}. Un rect nullo PRIMA o DOPO non è una posizione da cui o verso
   cui animare un transform: trattato come se l'elemento non ci fosse (va a
   vortice-entra se ora è visibile, altrimenti ignorato del tutto) - non un
   volo dall'angolo in alto a sinistra dello schermo. */
const VORTICE_TETTO_I = 13; // 13 * 24ms = 312ms, sotto il tetto di 320ms
const rectNullo = (r) => !r.width && !r.height;

function vortice(view, html) {
  // Passata di sole letture (PRIMA).
  const prima = new Map();
  $$('[data-chiave]', view).forEach((el) => {
    const r = el.getBoundingClientRect();
    if (!rectNullo(r)) prima.set(el.dataset.chiave, r);
  });

  view.innerHTML = html;
  if (!prima.size) return; // niente da confrontare: nessuna card prima, nessun FLIP possibile

  // Passata di sole letture (DOPO): TUTTI i rect nuovi, prima di scrivere
  // qualunque transform - vedi il commento sopra sul perché intrecciare
  // letture e scritture, qui, fa saltare l'animazione.
  const dopo = new Map();
  $$('[data-chiave]', view).forEach((el) => {
    const r = el.getBoundingClientRect();
    if (!rectNullo(r)) dopo.set(el.dataset.chiave, { el, r });
  });

  // Passata di sole scritture: decide chi si muove (e chi è nuovo) e scrive
  // SOLO il transform inverso, senza leggere nient'altro nel frattempo.
  const mossi = [];
  const mossiSet = new Set();
  let i = 0;
  dopo.forEach(({ el, r: rDopo }, chiave) => {
    const rPrima = prima.get(chiave);
    if (!rPrima) {
      el.classList.add('vortice-entra');
      el.style.setProperty('--i', Math.min(i, VORTICE_TETTO_I));
      i++;
      // Consigliata dal critico (costa una riga): .vortice-entra ha
      // animation-fill-mode 'both' (vedi moto.css), quindi il fotogramma
      // finale (transform:none) resterebbe applicato per sempre e
      // annullerebbe il .card:hover translateY(-1px) di style.css su ogni
      // card entrata col vortice. Tolta la classe a animazione finita,
      // l'hover torna a funzionare come su una card mai animata.
      el.addEventListener('animationend', () => el.classList.remove('vortice-entra'), { once: true });
      return;
    }
    const antenato = el.parentElement && el.parentElement.closest('[data-chiave]');
    if (antenato && mossiSet.has(antenato)) return; // il padre lo porta già con sé (vedi sopra)
    const dx = rPrima.left - rDopo.left, dy = rPrima.top - rDopo.top;
    if (!dx && !dy) return; // stessa posizione: niente da animare
    const rot = Math.max(-8, Math.min(8, (Math.abs(dx) >= Math.abs(dy) ? dx : dy) / 15));
    el.style.transition = 'none';
    el.style.transform = `translate(${dx}px, ${dy}px) rotate(${rot}deg)`;
    mossi.push(el);
    mossiSet.add(el);
  });
  if (!mossi.length) return;

  // Un solo reflow forzato: applica per davvero la posizione di partenza
  // scritta qui sopra (con transition:none) prima che il rAF che segue
  // cambi lo stato - vedi il commento sopra la funzione.
  void view.offsetHeight;

  requestAnimationFrame(() => {
    mossi.forEach((el) => {
      el.classList.add('vortice-muove');
      el.style.transition = 'transform 420ms var(--ease-out)'; // inline: vince su .card, qualunque sia l'ordine dei foglietti
      el.style.transform = '';
    });
    setTimeout(() => mossi.forEach((el) => {
      el.classList.remove('vortice-muove');
      el.style.transition = '';
      el.style.transform = '';
    }), 460);
  });
}

/* ---------------------------------------------------------------- router */
/* Le vecchie viste sono diventate blocchi: i vecchi indirizzi continuano a
   funzionare, portano dove il contenuto è finito. */
const REDIREZIONI = { riepilogo: 'oggi', task: 'oggi', sessioni: 'archivio',
                      agenti: 'archivio', conoscenza: 'archivio', capacita: 'archivio' };

async function route() {
  const hash = location.hash.replace(/^#\//, '') || 'oggi';
  let [name] = hash.split('/');
  // `#/cerca?q=...&progetto=...`: una ricerca diventa un indirizzo che si salva
  // e si riapre, invece di una cosa da riscrivere ogni volta.
  const dom = name.indexOf('?');
  if (dom >= 0) {
    const p = new URLSearchParams(name.slice(dom + 1));
    name = name.slice(0, dom);
    if (name === 'cerca') {
      state.filters.cerca = { q: p.get('q') || '', progetto: p.get('progetto') || '' };
    }
  }
  if (REDIREZIONI[name]) {
    if (name !== 'riepilogo' && name !== 'task') {
      state.filters.archivio = { seg: name === 'agenti' ? 'agenti'
        : name === 'conoscenza' ? 'memoria' : name === 'capacita' ? 'capacita' : 'sessioni' };
    }
    name = REDIREZIONI[name];
  }
  const fn = views[name] || views.oggi;
  state.view = name;
  $$('.rail nav a').forEach((a) => a.classList.toggle('on', a.dataset.view === name));

  // LOTTO-L4-MEMORIA, punto 2 ("mai vuota"): se c'è memoria di questa vista
  // (in questa lingua) va a schermo SUBITO, con data-memoria="1" e senza
  // "carico…" - e resta interattiva (link e data-act funzionano) per tutto
  // il tempo che il fetch qui sotto ci mette a finire, riuscito o no. Senza
  // memoria (prima apertura di questa vista) il percorso è quello di sempre.
  const view = $('#view');
  const memoria = memoriaLeggi(name, UILANG);
  if (memoria) {
    view.innerHTML = memoria.html;
    view.dataset.memoria = '1';
    spiaAggiorna('aggiorno');
  } else {
    delete view.dataset.memoria;
    view.innerHTML = `<div class="empty">${T('carico…')}</div>`;
    spiaAggiorna(null);
  }

  try {
    const chiamatePrima = apiChiamateOk;
    const html = await fn();
    // Il fetch è riuscito: da qui la vista è di nuovo fresca, la memoria
    // (se c'era) ha fatto il suo lavoro e l'attributo sparisce. Html
    // identico a quello di memoria -> niente animazione (punto 3, ultima
    // riga); diverso -> il vortice fa il resto: FLIP su chi sopravvive,
    // .vortice-entra su chi è nuovo, e sostituisce l'html lui stesso.
    if (memoria && html !== memoria.html) vortice(view, html);
    else if (!memoria) view.innerHTML = html;
    delete view.dataset.memoria;
    memoriaSalva(name, html);
    // Correzione del critico: "aggiornato alle" deve dire QUANDO SONO STATI
    // PRESI I DATI, non quando è finito questo giro di route(). fn() può
    // arrivare qui senza aver chiamato api() nemmeno una volta (views.progetti
    // e views.benvenuto riusano state.overview se c'è già): in quel caso
    // apiChiamateOk non è cambiato, quello a schermo è la stessa istantanea
    // di prima, e la pillola deve dire l'ora di QUELLA istantanea
    // (state.overviewQuando), non "adesso" - altrimenti, navigando dal menu
    // (Oggi -> Progetti, cassa calda) col server spento, la pillola direbbe
    // un orario falso di "adesso" e non parlerebbe più di server
    // irraggiungibile, pur non avendo controllato niente.
    const fetchPartito = apiChiamateOk > chiamatePrima;
    spiaAggiorna('fresco', fetchPartito ? new Date() : (state.overviewQuando || new Date()));
  } catch (err) {
    if (memoria) {
      // La memoria resta a schermo (niente "errore: …" al suo posto): la
      // spia dice che il server non risponde, data-memoria resta per dire
      // che quello che si vede non è fresco.
      spiaAggiorna('rotto', memoria.quando);
    } else {
      view.innerHTML = `<div class="empty">${T('errore: ')}${esc(err.message)}</div>`;
      spiaAggiorna(null);
    }
  }
  refreshBadges();
}

async function refreshBadges() {
  try {
    let d = state.overview;
    if (!d) { d = state.overview = await api('/api/overview?lang=' + UILANG); state.overviewQuando = new Date(); }
    const lav = $('#badge-lavagna');
    if (lav) lav.textContent = d.stats.lavagna_aperti || d.stats.task_aperti || '';
    $('#badge-social').textContent = d.stats.post_in_coda || '';
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
      if (name === 'task-cycle') {
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
        // suo endpoint, che fa il fork della sessione quando c'è; senza task
        // (blank da "manda-nuovo", o una proposta di Claude/Codex senza riga
        // propria in Plancia) resta /api/cantiere di sempre, solo senza più
        // il menu proposta/esegui (un interruttore booleano al suo posto).
        const form = act.closest('form');
        const dati = Object.fromEntries(new FormData(form).entries());
        if (!form.dataset.task && !(dati.titolo || '').trim()) return;
        const scrive = !!dati.scrive;
        const r = form.dataset.task
          ? await api('/api/riprendi/' + form.dataset.task, { method: 'POST', body: {
              background: true, scrive, istruzioni: dati.istruzioni } })
          // LOTTO-L3-RITOCCO punto 13: `scrive` (bool) invece di `modo`
          // ("proposta"/"esegui") - /api/cantiere lo passa a
          // cantiere.avvia() com'è, senza più tradurlo da una stringa.
          // L3-RIPRENDI-UI-4 (obbligatoria del critico): la voce della
          // lavagna (Claude/Codex, non un task Plancia con data-task) ha già
          // una sua sessione (v.sessione, plancia/lavagna.py) - prima non
          // passava mai da qui, e /api/cantiere partiva sempre da zero
          // (task_id: null, nessuna sessione), anche quando "Riprendi"
          // prometteva il contrario. form.dataset.sessione (impostato da
          // apriRiprendi con quello che il bottone di riga porta) fa il
          // fork quando c'è una sessione da riprendere, esattamente come il
          // ramo con data-task qui sopra.
          : await api('/api/cantiere', { method: 'POST', body: {
              titolo: dati.titolo, istruzioni: dati.istruzioni, progetto: dati.progetto || null,
              agente: dati.agente, scrive, task_id: null,
              sessione: form.dataset.sessione || null } });
        $('#drawer').hidden = true;
        toast(`${T('avviato in background')} → ${r.agente} #${r.run}`);
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
        // Le righe oltre il tetto sono già nel markup (panelloProssimi),
        // solo nascoste con [hidden]: si rivelano senza una seconda
        // chiamata, e il bottone stesso sparisce (non c'è più "altro" da
        // aprire per quest'area).
        $$(`.prossimi-riga[data-area="${CSS.escape(act.dataset.area)}"][hidden]`).forEach((el) => { el.hidden = false; });
        act.remove();
      } else if (name === 'albero-toggle') {
        const padre = act.closest('.albero-padre');
        const figli = padre.querySelector('.albero-figli');
        const chiusa = !padre.classList.contains('chiusa');
        padre.classList.toggle('chiusa', chiusa);
        figli.hidden = chiusa;
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
  // LOTTO-L4-MEMORIA (obbligatoria del critico, punto 2 "mai vuota"): queste
  // due chiamate non passano dal try/catch qui sopra (quello è solo per
  // [data-act]) e sono async senza await - senza .catch, un click su una
  // card/wikilink a server spento non faceva NIENTE (nessun toast, nessun
  // errore in console: la promessa rifiutata restava inosservata). La vista
  // di memoria deve restare interattiva e dire quando un'azione fallisce,
  // non restare muta.
  if (mem && mem.dataset.memory) {
    ev.preventDefault();
    openMemory(mem.dataset.memory).catch((err) => toast(err.message, true));
    return;
  }
  if (proj && proj.dataset.project) {
    ev.preventDefault();
    openProject(proj.dataset.project).catch((err) => toast(err.message, true));
    return;
  }

  const vai = ev.target.closest('[data-goto]');
  if (vai) { location.hash = '#/' + vai.dataset.goto; return; }

  const chip = ev.target.closest('[data-filter]');
  if (chip) {
    const [view, key] = chip.dataset.filter.split('.');
    state.filters[view][key] = chip.dataset.value;
    await route();
    return;
  }

  // I chip della ricerca fanno interruttore: lo stesso progetto due volte
  // riallarga, altrimenti per tornare a vedere tutto bisognerebbe ricancellare
  // la domanda.
  const prog = ev.target.closest('[data-progetto]');
  if (prog) {
    const f = state.filters.cerca || (state.filters.cerca = { q: '', progetto: '' });
    f.progetto = f.progetto === prog.dataset.progetto ? '' : prog.dataset.progetto;
    await route();
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

/* ---------------------------------------------------------------- palette */
const palette = $('#palette'), pinput = $('#palette-input'), presults = $('#palette-results');

function openPalette() {
  palette.hidden = false; pinput.value = ''; presults.innerHTML = ''; pinput.focus();
}
function closePalette() { palette.hidden = true; }

let ptimer;
pinput.addEventListener('input', () => {
  clearTimeout(ptimer);
  ptimer = setTimeout(async () => {
    const q = pinput.value.trim();
    if (q.length < 2) { presults.innerHTML = ''; return; }
    try {
      /* Dal 9 agosto /api/search torna un oggetto e non piu' un array: qui c'era
         un `hits.length` su un oggetto, quindi la palette diceva sempre niente
         senza sbagliare rumorosamente. I turni entrano come prima riga, perche'
         e' li' che sta quello che si cerca; le schede restano sotto. */
      const d = await api('/api/search?q=' + encodeURIComponent(q));
      const dai_turni = (d.turni || []).slice(0, 5).map((t) => ({
        kind: 'turno', title: (t.frammento || '').split('«').join('').split('»').join(''),
        snip: '', project: t.progetto, turno: t,
      }));
      const hits = dai_turni.concat(d.schede || []);
      state.paletteHits = hits; state.paletteIndex = 0;
      presults.innerHTML = hits.length ? hits.map((h, i) => `
        <div class="pres ${i === 0 ? 'sel' : ''}" data-i="${i}">
          <div class="k">${esc(h.kind)}</div>
          <div class="t"><div class="truncate">${esc(h.title) || T('senza titolo')}</div>
          <small>${(h.snip || '').replace(/[<>]/g, '').replace(/«/g, '<b class="hl">').replace(/»/g, '</b>')}${h.project ? ' · ' + esc(h.project) : ''}</small></div>
        </div>`).join('') : `<div class="empty">${T('niente')}</div>`;
    } catch (err) { presults.innerHTML = `<div class="empty">${esc(err.message)}</div>`; }
  }, 190);
});

presults.addEventListener('click', (ev) => {
  const row = ev.target.closest('.pres');
  if (row) choosePalette(state.paletteHits[+row.dataset.i]);
});

function choosePalette(hit) {
  if (!hit) return;
  closePalette();
  // Scegliere un turno porta nella vista Cerca con la stessa domanda: li' c'e'
  // il testo intero e il file da cui viene, che nella palette non ci starebbero.
  if (hit.kind === 'turno') {
    state.filters.cerca = { q: pinput.value.trim(), progetto: '' };
    // Se ci si e' gia' dentro l'hash non cambia e hashchange non scatta: senza
    // questo, cercare dalla palette stando in Cerca non faceva niente.
    if (location.hash === '#/cerca') route(); else location.hash = '#/cerca';
  }
  else if (hit.kind === 'memoria') openMemory(hit.title).catch((err) => toast(err.message, true));
  else if (hit.kind === 'sessione') { state.filters.sessioni = { q: hit.title || '', project: '' }; location.hash = '#/sessioni'; }
  else if (hit.kind === 'task') location.hash = '#/task';
  else if (hit.kind === 'post') location.hash = '#/social';
  else toast(hit.title || '');
}

/* Lo slash apre la ricerca, come in mezzo mondo. Solo se non stai gia' scrivendo
   da qualche parte, altrimenti chi scrive una data si ritrova altrove. */
const SCRIVE = (el) => el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'
                              || el.isContentEditable);

document.addEventListener('keydown', (ev) => {
  if (ev.key === '/' && !SCRIVE(document.activeElement) && palette.hidden) {
    ev.preventDefault();
    if (state.view === 'cerca') { const c = $('.cercabox'); if (c) c.focus(); }
    else location.hash = '#/cerca';
    return;
  }
  if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === 'k') { ev.preventDefault(); openPalette(); return; }
  if (palette.hidden) return;
  if (ev.key === 'Escape') closePalette();
  if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
    ev.preventDefault();
    const rows = $$('.pres', presults);
    if (!rows.length) return;
    state.paletteIndex = (state.paletteIndex + (ev.key === 'ArrowDown' ? 1 : rows.length - 1)) % rows.length;
    rows.forEach((r, i) => r.classList.toggle('sel', i === state.paletteIndex));
    rows[state.paletteIndex].scrollIntoView({ block: 'nearest' });
  }
  if (ev.key === 'Enter') choosePalette(state.paletteHits[state.paletteIndex]);
});

palette.addEventListener('click', (ev) => { if (ev.target === palette) closePalette(); });
$('#btn-search').addEventListener('click', openPalette);
// La scorciatoia di ricerca e' Cmd+K sul Mac e Ctrl+K altrove (il gestore accetta
// tutte e due): il suggerimento nella barra dice quella giusta.
(function suggerimentoScorciatoia() {
  const fuoriMac = !/mac|iphone|ipad/i.test(
    (navigator.userAgentData && navigator.userAgentData.platform)
    || navigator.platform || navigator.userAgent || '');
  const kbd = $('#btn-search kbd');
  if (kbd && fuoriMac) kbd.textContent = 'Ctrl+K';
})();
$('#btn-lang').addEventListener('click', async () => {
  UILANG = UILANG === 'it' ? 'en' : 'it';
  storageSet('plancia-ui', UILANG);
  $('#btn-lang').textContent = UILANG.toUpperCase();
  traduciShell();
  disegnaSelettore();
  state.overview = null;
  await route();
});
$('#btn-lang').textContent = UILANG.toUpperCase();
$('#drawer').addEventListener('click', (ev) => { if (ev.target.id === 'drawer') $('#drawer').hidden = true; });
$('#drawer-close').addEventListener('click', () => { $('#drawer').hidden = true; });

/* ---------------------------------------------------------------- tema e sync */
function applyTheme(mode) {
  const resolved = mode === 'auto'
    ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : mode;
  document.documentElement.dataset.theme = mode;
  document.documentElement.dataset.resolved = resolved;
  storageSet('plancia-theme', mode);
  // Addendum del coordinatore (26/09): contratto con L4-VETRO-2
  // (mac/Sources/main.swift, che registra il gestore 'tema'). Fuori
  // dall'app nativa `window.webkit` non esiste e la `?.` si ferma lì senza
  // fare niente; dentro l'app il materiale dietro la finestra prende lo
  // stesso chiaro/scuro della pagina, anche al primo giro e ogni volta che
  // l'automatico segue un cambio di `prefers-color-scheme`.
  window.webkit?.messageHandlers?.tema?.postMessage(resolved);
}
$('#btn-theme').addEventListener('click', () => {
  const order = ['auto', 'light', 'dark'];
  const next = order[(order.indexOf(storageGet('plancia-theme') || 'auto') + 1) % 3];
  applyTheme(next);
  toast(T('tema: ') + next);
});
applyTheme(storageGet('plancia-theme') || 'auto');
matchMedia('(prefers-color-scheme: light)').addEventListener('change', () =>
  applyTheme(storageGet('plancia-theme') || 'auto'));

$('#btn-sync').addEventListener('click', async () => {
  // LOTTO-L3-RITOCCO punto 4 + L3-RIPRENDI-UI-4 (regressione trovata dal
  // critico): /api/sync risponde {avviato:false} in DUE casi diversi, e solo
  // uno dei due porta anche "motivo":"--no-sync". Se un sync è già in corso
  // (quello d'avvio, o un giro del ticker) `avviato` è false ma non c'è
  // nessun motivo: il bottone NON deve dire "disattivato per --no-sync"
  // (sarebbe falso), deve dire che un aggiornamento è già in corso e
  // continuare a seguirlo con pollSync(), come faceva prima di questo lotto.
  try {
    const r = await api('/api/sync', { method: 'POST', body: {} });
    if (r.avviato) { toast(T('aggiornamento avviato')); pollSync(); }
    else if (r.motivo === '--no-sync') toast(T('sync disattivato per questa sessione (--no-sync)'));
    else { toast(T('aggiornamento già in corso')); pollSync(); }
  } catch (err) { toast(err.message, true); }
});

let syncWasRunning = false;
async function pollSync() {
  try {
    const st = await api('/api/status');
    const dot = $('#sync-dot'), text = $('#sync-text');
    if (st.sync.running) {
      dot.className = 'dot busy';
      text.textContent = (st.sync.message || T('aggiorno')).slice(0, 34);
      syncWasRunning = true;
      setTimeout(pollSync, 1200);
    } else {
      dot.className = 'dot' + (st.sessione_viva ? ' live' : '');
      text.textContent = T('aggiornato ') + ago(st.ultimo_sync);
      if (syncWasRunning) { syncWasRunning = false; state.overview = null; route(); }
    }
  } catch (e) { $('#sync-text').textContent = T('server non raggiungibile'); }
}

/* Il selettore di compartimento (E1-PLANCIA). Si disegna solo se il server dice
   che ci sono compartimenti nominati: senza, la topbar e' quella di sempre. */
function disegnaSelettore() {
  const c = state.compartimenti;
  let sel = $('#sel-compartimento');
  if (!c || !c.attivo) { if (sel) sel.remove(); return; }
  if (!sel) {
    sel = document.createElement('select');
    sel.id = 'sel-compartimento';
    sel.style.width = 'auto';
    sel.style.minWidth = '150px';
    sel.addEventListener('change', async () => {
      state.compartimento = sel.value;
      // quello che la pagina teneva a mente e' del compartimento di prima
      state.overview = null; state.progetti = null; state.lav = null;
      state.recap = null; state.filters = {};
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

window.addEventListener('hashchange', route);
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
