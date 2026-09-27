"""Il cervello in un file solo, da portare sul telefono.

Un file HTML che contiene l'archivio dentro di sé e sa cercarselo. Nessuna
richiesta di rete, nessun server, nessun account: si apre e funziona, anche in
aereo, anche col Mac spento, anche fra due anni.

Serve a rispondere a una domanda precisa: come porto il mio secondo cervello sul
telefono senza farlo passare da nessuno. La risposta è che non lo mandi da
nessuna parte, glielo consegni a mano. AirDrop fra Mac e telefono è un
collegamento diretto fra i due dispositivi, e il Wi-Fi di casa non esce di casa:
in tutt'e due i casi il file non tocca internet e non tocca un servizio di
terzi. Una VPN servirebbe solo per raggiungere il Mac da lontano, e per
aggiornare una copia basta essergli vicino una volta ogni tanto.

Tutto è inline apposta. Un solo `<link>` o un solo font remoto vorrebbe dire che
aprire l'archivio racconta a qualcuno che l'hai aperto, e sarebbe esattamente la
fuga di dati che questo file esiste per evitare.
"""

import base64
import json
import sqlite3
from datetime import datetime, timezone

from . import config, richiamo

# I quattro volti che il file porta con sé, in base64: solo il sottoinsieme
# latin (non latin-ext). La posta di questo file è restare abbastanza
# piccolo da passare per AirDrop, e l'italiano e lo spagnolo di casa stanno
# già dentro il subset latin da soli (à, è, ñ, ¿, ¡ sono tutti sotto U+00FF).
_VOLTI = (
    ("Fraunces", "300 700", "fraunces.woff2"),
    ("IBM Plex Sans", "400 600", "plex-sans.woff2"),
    ("IBM Plex Mono", "400", "plex-mono-400.woff2"),
    ("IBM Plex Mono", "500", "plex-mono-500.woff2"),
)


def _font_data_uri(nome: str) -> str:
    """Il woff2 incorporato: l'export non deve chiedere niente alla rete,
    quindi il file va portato dentro l'HTML, non collegato con un percorso."""
    grezzo = (config.WEB_DIR / nome).read_bytes()
    return "data:font/woff2;base64," + base64.b64encode(grezzo).decode("ascii")


def _moto_css() -> str:
    """LOTTO-L4-MEMORIA punto 6: incorporata come i font (un <style> in più,
    mai un <link> esterno - vedi il docstring del modulo su "un solo link o
    un solo font remoto"). Non per il vortice: questa pagina non è
    web/index.html con web/app.js, è un mini-visualizzatore scritto a mano
    (vedi PAGINA più sotto), senza router, senza card con data-chiave, senza
    localStorage - app.js non ci gira, quindi web/style.css e web/app.js
    stessi NON sono incorporati qui (solo i font, vedi _fonts_css), e le
    regole di moto.css restano di fatto inerti in questa pagina. Restano
    incorporate comunque perché il lotto lo chiede esplicitamente e perché
    costa zero byte di rete in più (a differenza dei font, il testo del CSS
    è già minuscolo): se un domani questa pagina guadagnasse le sue card,
    le classi ci sono già pronte, senza un secondo giro su questo modulo."""
    return (config.WEB_DIR / "moto.css").read_text(encoding="utf-8")


def _fonts_css() -> str:
    """Le stesse tre famiglie della dashboard, embedded. Un solo @font-face
    per famiglia/peso: qui non serve lo split latin/latin-ext del sito, un
    file solo con lo unicode-range di default copre già quello che serve."""
    blocchi = []
    for famiglia, peso, nome in _VOLTI:
        blocchi.append(
            "@font-face{{font-family:'{f}';font-style:normal;"
            "font-weight:{p};font-display:swap;"
            "src:url({u}) format('woff2');}}".format(
                f=famiglia, p=peso, u=_font_data_uri(nome)))
    return "".join(blocchi)


TIPI = {"feedback": "preferenze", "user": "chi sei", "reference": "riferimenti",
        "project": "progetti", "altro": "altro"}


def raccogli(conn) -> dict:
    """Quello che vale la pena avere in tasca: la memoria, e dove sei rimasto."""
    memorie, viste = [], set()
    for r in conn.execute(
            "SELECT name, type, scope, description, body, updated_at, "
            "LENGTH(COALESCE(description,'')) + LENGTH(COALESCE(body,'')) AS peso "
            "FROM knowledge ORDER BY name, updated_at DESC"):
        if r["name"] in viste:
            continue
        viste.add(r["name"])
        memorie.append({
            "n": r["name"],
            "t": r["type"] or "altro",
            "d": (r["description"] or "").strip(),
            "c": (r["body"] or "").strip(),
            "q": richiamo._dove(r["scope"] or ""),
            "a": (r["updated_at"] or "")[:10],
            # La stessa distinzione della mappa: se il richiamo non può
            # raggiungerla, il telefono non deve far finta di sì.
            "r": bool(r["type"] in richiamo.TIPI_TRASVERSALI
                      and (r["peso"] or 0) >= richiamo.SOSTANZA_MINIMA),
        })

    progetti = [{"n": r["name"], "s": r["status"], "p": (r["next_action"] or "").strip()}
                for r in conn.execute(
                    "SELECT name, status, next_action FROM projects "
                    "WHERE status='attivo' AND COALESCE(hidden,0)=0 "
                    "ORDER BY COALESCE(pinned,0) DESC, priority, name")]

    task = [{"n": r["title"], "s": r["status"], "p": r["pname"] or ""}
            for r in conn.execute(
                "SELECT t.title, t.status, p.name AS pname FROM tasks t "
                "LEFT JOIN projects p ON p.id=t.project_id "
                "WHERE t.status != 'fatto' ORDER BY t.status, t.id DESC")]

    return {"memorie": memorie, "progetti": progetti, "task": task,
            "quando": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")}


PAGINA = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Memoria">
<meta name="referrer" content="no-referrer">
<title>Memoria</title>
<style>
__FONTS__
__MOTO__
:root {
  --bg:#0e1219; --panel:#141922; --line:#1e2530; --text:#e7ebf2;
  --muted:#9aa4b4; --faint:#626d7e; --amber:#e8934e; --info:#8fb8d9;
  --nominal:#5bb89b;
  --serif:"Fraunces",ui-serif,"New York","Iowan Old Style",Palatino,Georgia,serif;
  --sans:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme: light) {
  :root { --bg:#f4f5f7; --panel:#fff; --line:#e2e5ec; --text:#121620;
          --muted:#5b6474; --faint:#8b93a2; --amber:#a95c14; --info:#3f6f9c;
          --nominal:#1c7f62; }
}
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
/* IBM Plex Mono qui dentro ha solo i pesi 400 e 500 (vedi _VOLTI sopra):
   senza questa guardia un futuro font-weight:600 su .mono verrebbe
   sintetizzato invece di restare sul 500 vero, stessa regola di web/style.css
   e site/style.css. */
html { font-synthesis:none; }
body { margin:0; background:var(--bg); color:var(--text); font-family:var(--sans);
  font-size:16px; line-height:1.55; padding:env(safe-area-inset-top) 0 40px; }
header { position:sticky; top:0; background:var(--bg); padding:14px 16px 10px;
  border-bottom:1px solid var(--line); z-index:5; }
h1 { margin:0 0 2px; font-family:var(--serif); font-size:19px; font-weight:400; letter-spacing:-.01em; }
.sotto { color:var(--faint); font-size:12px; margin:0 0 10px; }
input { width:100%; padding:12px 14px; font-size:16px; font-family:inherit;
  background:var(--panel); color:var(--text); border:1px solid var(--line);
  border-radius:10px; outline:none; }
input:focus { border-color:var(--amber); }
.chips { display:flex; gap:6px; margin-top:9px; overflow-x:auto; padding-bottom:2px;
  scrollbar-width:none; }
.chips::-webkit-scrollbar { display:none; }
.chip { flex:none; padding:5px 11px; border:1px solid var(--line); border-radius:999px;
  font-size:12.5px; color:var(--muted); background:var(--panel); cursor:pointer; }
.chip.on { color:var(--amber); border-color:var(--amber); }
main { padding:12px 16px; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:12px;
  padding:13px 15px; margin-bottom:9px; cursor:pointer; }
.tit { font-size:15px; font-weight:600; display:flex; align-items:center; gap:7px; }
.pallino { width:9px; height:9px; border-radius:50%; flex:none; border:1.5px solid currentColor; }
.pallino.pieno { background:currentColor; }
.feedback { color:var(--amber); } .user { color:var(--info); }
.reference { color:var(--nominal); } .project, .altro { color:var(--faint); }
.desc { color:var(--muted); font-size:13.5px; margin-top:3px; }
.meta { color:var(--faint); font-size:11px; font-family:var(--mono); margin-top:6px; }
.corpo { display:none; margin-top:11px; padding-top:11px; border-top:1px solid var(--line);
  font-size:14px; white-space:pre-wrap; word-break:break-word; color:var(--text); }
.card.aperta .corpo { display:block; }
.corpo code { font-family:var(--mono); font-size:12.5px; background:var(--bg);
  padding:1px 4px; border-radius:4px; }
mark { background:rgba(217,164,65,.28); color:inherit; border-radius:3px; padding:0 2px; }
.vuoto { color:var(--faint); text-align:center; padding:34px 10px; font-size:14px; }
.sez { color:var(--faint); font-size:11px; text-transform:uppercase; letter-spacing:.06em;
  margin:20px 0 8px; }
footer { color:var(--faint); font-size:11px; text-align:center; margin-top:26px;
  padding:0 16px; line-height:1.6; }
</style>
</head>
<body>
<header>
  <h1>Memoria</h1>
  <p class="sotto" id="sotto"></p>
  <input id="q" type="search" placeholder="cerca" autocomplete="off"
         autocapitalize="off" autocorrect="off" enterkeyhint="search">
  <div class="chips" id="chips"></div>
</header>
<main id="out"></main>
<footer id="pie"></footer>
<script>
const DATI = __DATI__;
const TIPI = __TIPI__;
const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
let filtro = '', domanda = '';

/* Ordine dei risultati: prima chi ha la parola nel nome, poi nella descrizione,
   poi nel corpo. Con quarantaquattro voci non serve altro, e qualunque cosa piu'
   furba renderebbe imprevedibile una ricerca che deve solo ritrovare. */
function cerca(voci, q) {
  if (!q) return voci.map((m) => ({ m, dove: 0 }));
  const t = q.toLowerCase().split(/\\s+/).filter(Boolean);
  const fuori = [];
  for (const m of voci) {
    const nome = m.n.toLowerCase(), desc = (m.d || '').toLowerCase(),
          corpo = (m.c || '').toLowerCase();
    if (!t.every((x) => nome.includes(x) || desc.includes(x) || corpo.includes(x))) continue;
    const dove = t.every((x) => nome.includes(x)) ? 0
      : t.every((x) => nome.includes(x) || desc.includes(x)) ? 1 : 2;
    fuori.push({ m, dove });
  }
  return fuori.sort((a, b) => a.dove - b.dove || a.m.n.localeCompare(b.m.n));
}

/* Il minimo indispensabile di markdown: grassetto, codice e i rinvii fra doppie
   quadre. Il resto resta com'e' scritto, che e' anche come lo leggi nel file. */
function md(testo) {
  return esc(testo)
    .replace(/\\*\\*([^*]+)\\*\\*/g, '<b>$1</b>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\\[\\[([^\\]]+)\\]\\]/g, '<i>$1</i>');
}

/* L'evidenziazione entra solo nel testo, mai dentro un tag: cercare «b» o
   «code» altrimenti spezzerebbe il markup appena costruito. */
function marca(testo, q, conMd) {
  const html = conMd ? md(testo) : esc(testo);
  if (!q) return html;
  const t = q.toLowerCase().split(/\\s+/).filter(Boolean);
  return html.split(/(<[^>]*>)/).map((pezzo) => {
    if (pezzo.startsWith('<')) return pezzo;
    return t.reduce((acc, x) => {
      const re = new RegExp('(' + x.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&') + ')', 'gi');
      return acc.replace(re, '<mark>$1</mark>');
    }, pezzo);
  }).join('');
}

function scheda(m, q) {
  const corpo = m.c ? marca(m.c.length > 4000 ? m.c.slice(0, 4000) + '\\n…' : m.c, q, true) : '';
  return '<article class="card" data-n="' + esc(m.n) + '">'
    + '<div class="tit ' + esc(m.t) + '"><span class="pallino' + (m.r ? ' pieno' : '') + '"></span>'
    + '<span>' + marca(m.n, q) + '</span></div>'
    + (m.d ? '<div class="desc">' + marca(m.d, q) + '</div>' : '')
    + '<div class="meta">' + esc(TIPI[m.t] || m.t) + ' · ' + esc(m.q) + ' · ' + esc(m.a)
    + (m.r ? '' : ' · non richiamabile') + '</div>'
    + (corpo ? '<div class="corpo">' + corpo + '</div>' : '') + '</article>';
}

function disegna() {
  const q = domanda.trim();
  let voci = DATI.memorie;
  if (filtro) voci = voci.filter((m) => (filtro === 'richiamabili' ? m.r : m.t === filtro));
  const trovate = cerca(voci, q);
  let html = trovate.map((x) => scheda(x.m, q)).join('');

  /* Progetti e task solo quando cerchi: in cima devono esserci le memorie, che
     sono la ragione per cui apri questo file. */
  if (q) {
    const p = DATI.progetti.filter((x) => (x.n + ' ' + x.p).toLowerCase().includes(q.toLowerCase()));
    const t = DATI.task.filter((x) => (x.n + ' ' + x.p).toLowerCase().includes(q.toLowerCase()));
    if (p.length) html += '<div class="sez">progetti</div>' + p.map((x) =>
      '<article class="card"><div class="tit">' + marca(x.n, q) + '</div>'
      + (x.p ? '<div class="desc">' + marca(x.p, q) + '</div>' : '') + '</article>').join('');
    if (t.length) html += '<div class="sez">task aperti</div>' + t.map((x) =>
      '<article class="card"><div class="tit">' + marca(x.n, q) + '</div>'
      + '<div class="meta">' + esc(x.s) + (x.p ? ' · ' + esc(x.p) : '') + '</div></article>').join('');
  }
  document.getElementById('out').innerHTML = html
    || '<p class="vuoto">niente che corrisponda</p>';
}

document.getElementById('chips').innerHTML =
  [['', 'tutte'], ['richiamabili', 'richiamabili'], ['feedback', 'preferenze'],
   ['reference', 'riferimenti'], ['user', 'chi sei'], ['project', 'progetti']]
    .map(([k, e]) => '<span class="chip' + (k ? '' : ' on') + '" data-f="' + k + '">'
      + e + '</span>').join('');

document.getElementById('q').addEventListener('input', (e) => {
  domanda = e.target.value; disegna();
});
document.addEventListener('click', (e) => {
  const chip = e.target.closest('.chip');
  if (chip) {
    filtro = chip.dataset.f;
    document.querySelectorAll('.chip').forEach((c) => c.classList.toggle('on', c === chip));
    disegna(); return;
  }
  const card = e.target.closest('.card');
  if (card) card.classList.toggle('aperta');
});

const quante = DATI.memorie.length, prese = DATI.memorie.filter((m) => m.r).length;
document.getElementById('sotto').textContent =
  quante + ' memorie · ' + prese + ' che il richiamo può raggiungere';
document.getElementById('pie').textContent =
  'copia del ' + DATI.quando + ' UTC · vive solo su questo dispositivo, '
  + 'non chiede niente alla rete';
disegna();
</script>
</body>
</html>
"""


def costruisci(dati: dict) -> str:
    """Il file finito. Il `</` scappato perché una memoria che contiene un tag
    di chiusura chiuderebbe lo script e romperebbe la pagina. I font entrano
    qui, non nel testo di PAGINA: sono letti da disco e incorporati in
    base64 a ogni chiamata, così il modulo non tiene in memoria 150 KB di
    dati che il grosso delle chiamate (i test) non guarda nemmeno."""
    crudo = json.dumps(dati, ensure_ascii=False).replace("</", "<\\/")
    return (PAGINA
            .replace("__FONTS__", _fonts_css())
            .replace("__MOTO__", _moto_css())
            .replace("__DATI__", crudo)
            .replace("__TIPI__", json.dumps(TIPI, ensure_ascii=False)))


def esporta(destinazione) -> tuple:
    conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        dati = raccogli(conn)
    finally:
        conn.close()
    pagina = costruisci(dati)
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    destinazione.write_text(pagina, "utf-8")
    return destinazione, len(pagina.encode("utf-8")), len(dati["memorie"])

