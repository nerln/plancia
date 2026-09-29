/* Plancia: il service worker della dashboard (LOTTO U1-APPWEB).

   Due cose sole, e nessuna delle due tocca i dati:

   1. la dashboard si installa come app (Chrome, Edge, Safari con "Aggiungi al
      Dock") e ha bisogno di un worker perche' il browser la consideri tale;
   2. la SHELL (la pagina, il js, i css, i font, le icone) sta in cache, cosi'
      con il server spento una ricarica vera della pagina apre comunque la
      dashboard: prima anche index.html arrivava dal server, e un F5 a server
      spento mostrava la pagina d'errore del browser. Le card le mette la
      memoria locale di L4-MEMORIA (localStorage), con la pillola "server non
      raggiungibile": qui si garantisce solo che la pagina che le disegna si
      apra.

   Cosa NON fa, di proposito:
   - Le chiamate /api/ non passano mai da qui, ne' in lettura ne' in
     scrittura: il fetch non viene nemmeno intercettato (niente respondWith).
     I dati freschi, o il loro fallimento, li gestisce gia' app.js. Nessuna
     risposta di /api/ finisce mai nella cache, e nessuna richiesta con il
     token (X-Plancia-Token, cioe' ogni scrittura) e' toccata dal worker.
     Stessa regola per /audio/ (le voci: file pesanti e a perdere).
   - Non intercetta altro che GET dello stesso sito.

   Come si aggiorna. Il server scrive qui sotto la versione e l'elenco dei file
   (plancia/api.py, _sw_js): se un file della shell cambia, la versione sale,
   i byte di questo script cambiano e il browser, che li ricontrolla a ogni
   navigazione, installa il worker nuovo. Il nuovo NON chiama skipWaiting()
   ne' clients.claim(): resta in attesa e prende il posto del vecchio al
   caricamento dopo, quando nessuna pagina e' piu' sotto il vecchio. Un
   skipWaiting aggressivo cambierebbe la cache sotto le dita di chi ha la
   dashboard aperta (un font, una risorsa caricata dopo, che arrivano dalla
   versione nuova mentre la pagina e' ancora la vecchia). Non serve nemmeno
   per essere sicuri di non vedere la shell vecchia: la navigazione va prima
   in rete, quindi con il server acceso la pagina e' sempre quella nuova, e
   css e js hanno `?v=` con la stessa versione, quindi il worker vecchio non
   li ha in cache e li prende dalla rete. Quando il nuovo si attiva cancella
   le cache delle versioni vecchie (activate, sotto).

   Tutto senza librerie: solo l'API del browser. */
'use strict';

/* Scritti dal server a ogni richiesta di /sw.js. Nel file su disco restano
   segnaposto: JSON.parse su un segnaposto non riscritto fallisce a voce alta
   (l'installazione va in errore e il worker non parte) invece di mettere in
   cache un elenco vuoto senza dire niente. */
const VERSIONE = '__PLANCIA_V__';
const SHELL = JSON.parse('__PLANCIA_SHELL__');

const PREFISSO = 'plancia-shell-';
const CACHE = PREFISSO + VERSIONE;
const PAGINA = '/';

/* I file statici del sito, per nome: quelli che il server serve da web/ (piatti,
   piu' le PNG di /icone/). Fuori da qui il worker non risponde, lascia fare
   alla rete. */
const STATICO = /^\/(?:[\w.-]+\.(?:css|js|woff2|png|webmanifest)|icone\/[\w.-]+\.png)$/;

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    /* cache:'reload' salta la cache http del browser: la shell messa da parte
       e' quella che il server serve adesso, non una copia vecchia. Se anche
       un solo file manca l'installazione fallisce e il worker vecchio resta
       al suo posto: meglio la shell di prima che una a meta'. */
    await Promise.all(SHELL.map(async (url) => {
      const risposta = await fetch(new Request(url, { cache: 'reload' }));
      if (!risposta.ok) throw new Error('shell: ' + url + ' ' + risposta.status);
      await cache.put(url, risposta);
    }));
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const nomi = await caches.keys();
    await Promise.all(nomi
      .filter((n) => n.startsWith(PREFISSO) && n !== CACHE)
      .map((n) => caches.delete(n)));
  })());
});

/* La pagina: prima la rete (cosi' un aggiornamento si vede subito e il token
   dentro index.html e' quello vero), e a ogni risposta buona se ne tiene una
   copia. Solo se la rete non risponde (server spento: fetch che fallisce, non
   un 500 del server, che e' una risposta) si serve l'ultima copia. */
async function paginaReteAllaPrima(event) {
  try {
    const risposta = await fetch(event.request);
    if (risposta.ok) {
      const copia = risposta.clone();
      event.waitUntil(caches.open(CACHE).then((c) => c.put(PAGINA, copia)));
    }
    return risposta;
  } catch (errore) {
    const propria = await caches.open(CACHE).then((c) => c.match(PAGINA));
    /* Se il worker attivo e' uno vecchio e la sua cache non ha la pagina
       (non dovrebbe: l'installazione la mette), si cerca in tutte. */
    const salvata = propria || await caches.match(PAGINA);
    if (salvata) return salvata;
    throw errore;
  }
}

/* Le risorse statiche: prima la cache, poi la rete. I css e il js portano
   `?v=` con la versione, quindi un file nuovo ha un indirizzo nuovo e non
   trova mai la copia vecchia. Quello che manca (un font caricato dopo) si
   prende dalla rete e si tiene per la volta dopo. */
async function staticoCacheAllaPrima(event) {
  const cache = await caches.open(CACHE);
  const trovato = await cache.match(event.request);
  if (trovato) return trovato;
  const risposta = await fetch(event.request);
  if (risposta.ok && risposta.type === 'basic') {
    const copia = risposta.clone();
    event.waitUntil(cache.put(event.request, copia));
  }
  return risposta;
}

self.addEventListener('fetch', (event) => {
  const richiesta = event.request;
  /* Niente respondWith = il browser fa da se', come se il worker non ci fosse. */
  if (richiesta.method !== 'GET') return;
  if (richiesta.headers.has('X-Plancia-Token') || richiesta.headers.has('Range')) return;
  const url = new URL(richiesta.url);
  if (url.origin !== self.location.origin) return;
  const percorso = url.pathname;
  if (percorso.startsWith('/api/') || percorso.startsWith('/audio/')) return;
  if (richiesta.mode === 'navigate') {
    if (percorso === '/' || percorso === '/index.html') event.respondWith(paginaReteAllaPrima(event));
    return;
  }
  if (STATICO.test(percorso)) event.respondWith(staticoCacheAllaPrima(event));
});
