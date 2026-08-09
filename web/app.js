/* Plancia, interfaccia. Nessun framework: fetch, template literal, delega eventi. */

const TOKEN = document.querySelector('meta[name=plancia-token]').content;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = { overview: null, view: null, filters: {}, paletteIndex: 0, paletteHits: [] };


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
  'Task aperti': 'Open tasks', 'Progetti attivi': 'Active projects',
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
  'conversazioni con Claude Code': 'conversations with Claude Code',
  'cerca nel primo messaggio…': 'search the opening message…',
  'tutti i progetti': 'all projects', 'quando': 'when', 'di cosa': 'about',
  'progetto': 'project', 'tool': 'tools', 'riprendi': 'resume',
  'nessuna sessione': 'no sessions', 'senza titolo': 'untitled',
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
  'Lavagna': 'Board', 'Guida': 'Guide', 'tutti': 'all', 'tutte': 'all', 'dettaglio': 'detail', 'esito': 'outcome', 'tutti i task aperti, di tutti gli agenti': 'every open task, every agent',
  'fonte': 'source', 'manda': 'dispatch', 'Manda a un agente': 'Dispatch to an agent',
  'Come lo voglio fatto': 'How I want it done', 'proposta': 'plan only', 'esegui': 'do it',
  'guarda e propone, non tocca niente': 'reads and plans, touches nothing',
  'può modificare i file del progetto': 'can modify the project files',
  'In lavorazione': 'Running', 'Lanci recenti': 'Recent runs',
  'riuscito': 'done', 'fallito': 'failed', bloccato: 'blocked', 'in coda': 'queued', 'annullato': 'cancelled',
  'Cosa converrebbe fare': 'What is worth doing', 'fallo': 'do it',
  'niente in sospeso': 'nothing pending', 'nessun task aperto da nessuna parte': 'no open task anywhere',
  'Il lavoro': 'The work', 'annulla': 'cancel', 'apri il registro': 'open the log',
  'lanci': 'runs', 'mandato': 'dispatched', "tutto quello che è già successo": 'everything that already happened',
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
const UIPARAM = new URLSearchParams(location.search).get('ui');
let UILANG = UIPARAM || localStorage.getItem('plancia-ui') ||
  (navigator.language.startsWith('it') ? 'it' : 'en');
if (UIPARAM) localStorage.setItem('plancia-ui', UIPARAM);
const T = (s) => (UILANG === 'en' && EN[s] !== undefined) ? EN[s] : s;
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

function toast(msg, bad) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast' + (bad ? ' bad' : '');
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, 2600);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', 'X-Plancia-Token': TOKEN, ...(opts.headers || {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const ctype = res.headers.get('content-type') || '';
  const data = ctype.includes('json') ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.errore) || res.statusText);
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
  const riepilogo = await bloccoRiepilogo(true);
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
      ${d.proposte.map((p, i) => `
        <div class="row">
          <div class="prio p${p.urgenza < 2 ? 1 : p.urgenza < 4 ? 2 : 3}"></div>
          <div class="main"><div class="title">${esc(p.testo)}</div></div>
          <div class="side">
            <button class="mini go" data-act="proposta" data-frase="${i === 0 ? 'fallo' : ['', 'la seconda', 'la terza', 'la quarta'][i] || 'fallo'}"
              data-testo="${esc(p.testo)}">${T('fallo')}</button>
          </div>
        </div>`).join('')}
    </div>
  </div>` : ''}

  <div class="grid cols-2" data-in="4">
    <div style="display:flex;flex-direction:column;gap:var(--s3)">
      <div class="panel">
        <header><h3>${T('Task aperti')}</h3><span class="spacer"></span>
          <button class="mini" data-act="task-tutti">${T('tutti')}</button></header>
        <form class="inline-form" data-form="task-quick">
          <input type="text" name="title" placeholder="${T('Aggiungi un task e premi invio')}" autocomplete="off">
          <select name="project" style="width:150px">
            <option value="">${T('nessun progetto')}</option>
            ${d.progetti.map((p) => `<option value="${esc(p.key)}">${esc(p.name)}</option>`).join('')}
          </select>
        </form>
        <div class="panel-body tight">${taskRows(d.task.slice(0, 8))}</div>
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
        ${d ? `<span class="tag ${d.fonte === 'claude' ? 'accent' : ''}">${esc(d.fonte)}</span>` : ''}
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
    r.inCorso = false;
    if (state.view === 'oggi') await route();
    if (rigenera) toast(T('riepilogo aggiornato'));
  } catch (err) {
    r.inCorso = false;
    if (box) box.textContent = T('errore: ') + err.message;
  }
}

function suona(url) {
  const p = $('#player');
  if (!url) return toast(T('audio non pronto'), true);
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

views.cerca = async () => {
  const f = state.filters.cerca || (state.filters.cerca = { q: '' });
  let corpo;
  if ((f.q || '').trim()) {
    const d = await api('/api/search?q=' + encodeURIComponent(f.q));
    const trovati = d.turni || [];
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
      it: "Da ogni riga della lavagna puoi scrivere come vuoi che sia fatta e mandarla a Claude o a Codex. Il modo predefinito è proposta: l'agente legge e ti dice cosa farebbe, senza toccare niente. Esegui lo lascia modificare i file, e va scelto ogni volta.",
      en: "From any row on the board you can write how you want it done and dispatch it to Claude or Codex. The default mode is plan only: the agent reads and tells you what it would do, touching nothing. Do it lets it modify files, and you choose that every single time.",
    },
    prova: { etichetta: { it: "Prova il compositore", en: "Try the composer" }, azione: "manda-nuovo" },
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
  if (!state.overview) state.overview = await api('/api/overview?lang=' + UILANG);
  if (!state.lav) { try { state.lav = await api('/api/lavagna'); } catch (e) { state.lav = { conteggi: {} }; } }
  const c = (state.lav && state.lav.conteggi) || {};
  const o = state.overview.stats || {};
  // ogni passo mostra i tuoi numeri: cosi' l'onboarding e' anche la prova che legge davvero
  const CIFRE = [
    [[o.progetti_attivi, L === 'en' ? 'projects read' : 'progetti letti'],
     [(state.overview.agenti || []).length || 2, L === 'en' ? 'agents' : 'agenti'],
     [0, L === 'en' ? 'bytes sent out' : 'byte usciti']],
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
    <h1>${T('Lavagna')}</h1><p>${T('tutti i task aperti, di tutti gli agenti')}</p>
    <span class="spacer"></span>
    <button class="ghost" data-act="manda-nuovo">${T('Manda a un agente')}</button>
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
            <button class="mini go" data-act="manda" data-titolo="${esc(v.titolo)}"
              data-dettaglio="${esc((v.dettaglio || '').slice(0, 600))}"
              data-progetto="${esc(v.progetto_chiave || '')}"
              data-task="${v.fonte === 'plancia' ? v.task_id || '' : ''}">${T('manda')}</button>
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
      <div class="sub" title="${esc(r.cwd || '')}">${T(r.modo)} · ${esc(cartellaCorta(r.cwd))}${r.token ? ' · ' + kilo(r.token) + ' token' : ''}</div>
    </div>
    <div class="side">
      <span class="tag ${STATO_LANCIO[r.stato] || ''}">${T(r.stato)}</span>
    </div>
  </div>`;

/* Il compositore: da una riga della lavagna a un prompt vero. */
function apriCompositore(dati = {}) {
  const progetti = state.progetti || [];
  $('#drawer-body').innerHTML = `
    <h2>${T('Manda a un agente')}</h2>
    <p style="color:var(--muted);font-size:12.5px">${T('Il lavoro')}</p>
    <form data-form="manda" style="display:flex;flex-direction:column;gap:var(--s3);margin-top:var(--s3)">
      <input type="text" name="titolo" value="${esc(dati.titolo || '')}" placeholder="${T('Il lavoro')}" required>
      <textarea name="istruzioni" placeholder="${T('Come lo voglio fatto')}" style="min-height:110px">${esc(dati.istruzioni || '')}</textarea>
      <div style="display:flex;gap:var(--s2);flex-wrap:wrap">
        <select name="progetto" style="width:190px">
          <option value="">${T('nessun progetto')}</option>
          ${progetti.map((p) => `<option value="${esc(p.key)}" ${p.key === dati.progetto ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}
        </select>
        <select name="agente" style="width:130px">
          <option value="claude">claude</option><option value="codex">codex</option>
        </select>
        <select name="modo" style="width:160px">
          <option value="proposta">${T('proposta')}</option>
          <option value="esegui">${T('esegui')}</option>
        </select>
        <input type="hidden" name="task_id" value="${dati.task || ''}">
        <button class="primary" type="submit">${T('manda')}</button>
      </div>
      <p id="manda-nota" style="color:var(--faint);font-size:11.5px;margin:0">
        ${T('guarda e propone, non tocca niente')}</p>
    </form>
    ${dati.dettaglio ? `<section><h3>${T('dettaglio')}</h3>
      <div style="font-size:12.5px;color:var(--muted);white-space:pre-wrap">${esc(dati.dettaglio)}</div></section>` : ''}`;
  $('#drawer').hidden = false;
  const sel = $('#drawer-body select[name=modo]');
  sel.addEventListener('change', () => {
    $('#manda-nota').textContent = sel.value === 'esegui'
      ? T('può modificare i file del progetto') : T('guarda e propone, non tocca niente');
    $('#manda-nota').style.color = sel.value === 'esegui' ? 'var(--alarm)' : 'var(--faint)';
  });
}

async function apriLancio(id) {
  const d = await api('/api/runs/' + id);
  $('#drawer-body').innerHTML = `
    <h2>${T('lanci')} #${d.id}</h2>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:var(--s3)">
      <span class="tag agente ${d.agente === 'codex' ? 'codex' : ''}">${esc(d.agente)}</span>
      <span class="tag">${T(d.modo)}</span>
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
  const list = state.overview ? state.overview.progetti : (await api('/api/overview?lang=' + UILANG)).progetti;
  const groups = [['attivo', T('attivo')], ['idea', T('idea')], ['in pausa', T('in pausa')], ['concluso', T('concluso')]];
  return `
  <div class="view-head"><h1>${T('Progetti')}</h1><p>${list.length} ${T('tracciati')}</p></div>
  ${groups.map(([st, label]) => {
    const items = list.filter((p) => p.status === st);
    if (!items.length) return '';
    return `<h3 style="margin:18px 0 10px;color:var(--faint);font-size:12px;text-transform:uppercase;letter-spacing:.05em">${label} · ${items.length}</h3>
    <div class="cards">${items.map(projectCard).join('')}</div>`;
  }).join('')}`;
};

const projectCard = (p) => `
  <div class="card ${p.pinned ? 'pinned' : ''} ${p.status === 'concluso' ? 'dim' : ''}" data-project="${esc(p.key)}">
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
          <div class="kcard">
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
        <td>${s.progetto ? `<span class="tag">${esc(s.progetto)}</span>` : '<span style="color:var(--faint)">—</span>'}</td>
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

    ${section(T('Task'), d.task.length ? `<div class="panel"><div class="panel-body tight">${taskRows(d.task.filter((t) => t.status !== 'archiviato'))}</div></div>` : `<p style="color:var(--faint)">${T('nessuno')}</p>`)}

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
        <div class="sub">${dateIt(s.started_at)} · ${s.n_user} scambi · ${s.n_tools} tool</div>
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

/* ---------------------------------------------------------------- router */
/* Le vecchie viste sono diventate blocchi: i vecchi indirizzi continuano a
   funzionare, portano dove il contenuto è finito. */
const REDIREZIONI = { riepilogo: 'oggi', task: 'oggi', sessioni: 'archivio',
                      agenti: 'archivio', conoscenza: 'archivio', capacita: 'archivio' };

async function route() {
  const hash = location.hash.replace(/^#\//, '') || 'oggi';
  let [name] = hash.split('/');
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
  $('#view').innerHTML = `<div class="empty">${T('carico…')}</div>`;
  try {
    $('#view').innerHTML = await fn();
  } catch (err) {
    $('#view').innerHTML = `<div class="empty">${T('errore: ')}${esc(err.message)}</div>`;
  }
  refreshBadges();
}

async function refreshBadges() {
  try {
    const d = state.overview || (state.overview = await api('/api/overview?lang=' + UILANG));
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
      } else if (name === 'task-tutti') {
        state.filters.task = { status: 'tutti', project: '' };
        const box = act.closest('.panel').querySelector('.panel-body');
        box.innerHTML = taskRows(await api('/api/tasks?status=tutti&limit=200'));
      } else if (name === 'passo') {
        state.passo = +act.dataset.n;
        state.vistaPrima = 'benvenuto';
        await route();
      } else if (name === 'prova-passo') {
        if (act.dataset.url) {
          location.href = act.dataset.url;
        } else if (act.dataset.azione === 'manda-nuovo') {
          if (!state.progetti) state.progetti = await api('/api/projects');
          apriCompositore({});
        } else if (act.dataset.vista) {
          location.hash = '#/' + act.dataset.vista;
        }
      } else if (name === 'fine-benvenuto') {
        await api('/api/onboarding', { method: 'POST', body: { fatto: true } });
        state.overview = null; location.hash = '#/oggi';
        if (state.view === 'oggi') await route();
      } else if (name === 'manda' || name === 'manda-nuovo') {
        if (!state.progetti) state.progetti = await api('/api/projects');
        apriCompositore(act.dataset);
      } else if (name === 'lancio') {
        await apriLancio(act.dataset.id);
      } else if (name === 'annulla-lancio') {
        await api('/api/runs/' + act.dataset.id + '/annulla', { method: 'POST', body: {} });
        $('#drawer').hidden = true; await route();
      } else if (name === 'proposta') {
        const testo = act.dataset.testo;
        act.disabled = true; act.textContent = '…';
        const r = await api('/api/jarvis', { method: 'POST',
          body: { testo: act.dataset.frase || 'fallo', lang: state.recap?.lang || '', voce: false } });
        toast(r.risposta || T('fallo'));
        state.overview = null; await route();
      } else if (name === 'recap-gen') {
        state.recap.data = null; await generaRecap(true);
      } else if (name === 'recap-play') {
        suona(state.recap && state.recap.audio);
      } else if (name === 'recap-stop') {
        const p = $('#player'); p.pause(); p.currentTime = 0; aggiornaBottoneVoce(false);
      } else if (name === 'chiedi-veloce') {
        await chiedi(act.dataset.q);
      } else if (name === 'copy-briefing') {
        await navigator.clipboard.writeText($('#briefing-raw').value);
        toast(T('briefing copiato'));
      }
    } catch (err) { toast(err.message, true); }
    return;
  }
  if (mem && mem.dataset.memory) { ev.preventDefault(); openMemory(mem.dataset.memory); return; }
  if (proj && proj.dataset.project) { ev.preventDefault(); openProject(proj.dataset.project); return; }

  const vai = ev.target.closest('[data-goto]');
  if (vai) { location.hash = '#/' + vai.dataset.goto; return; }

  const chip = ev.target.closest('[data-filter]');
  if (chip) {
    const [view, key] = chip.dataset.filter.split('.');
    state.filters[view][key] = chip.dataset.value;
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
    } else if (form.dataset.form === 'manda') {
      const r = await api('/api/cantiere', { method: 'POST', body: {
        titolo: data.titolo, istruzioni: data.istruzioni, progetto: data.progetto || null,
        agente: data.agente, modo: data.modo,
        task_id: data.task_id ? +data.task_id : null } });
      $('#drawer').hidden = true;
      toast(`${T('mandato')} → ${data.agente} #${r.run}`);
      location.hash = '#/lavagna';
      await route();
      return;
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
      const hits = await api('/api/search?q=' + encodeURIComponent(q));
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
  if (hit.kind === 'memoria') openMemory(hit.title);
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
$('#btn-lang').addEventListener('click', async () => {
  UILANG = UILANG === 'it' ? 'en' : 'it';
  localStorage.setItem('plancia-ui', UILANG);
  $('#btn-lang').textContent = UILANG.toUpperCase();
  traduciShell();
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
  localStorage.setItem('plancia-theme', mode);
}
$('#btn-theme').addEventListener('click', () => {
  const order = ['auto', 'light', 'dark'];
  const next = order[(order.indexOf(localStorage.getItem('plancia-theme') || 'auto') + 1) % 3];
  applyTheme(next);
  toast(T('tema: ') + next);
});
applyTheme(localStorage.getItem('plancia-theme') || 'auto');
matchMedia('(prefers-color-scheme: light)').addEventListener('change', () =>
  applyTheme(localStorage.getItem('plancia-theme') || 'auto'));

$('#btn-sync').addEventListener('click', async () => {
  try { await api('/api/sync', { method: 'POST', body: {} }); toast(T('aggiornamento avviato')); pollSync(); }
  catch (err) { toast(err.message, true); }
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

window.addEventListener('hashchange', route);
traduciShell();
route();
pollSync();
setInterval(pollSync, 30000);
