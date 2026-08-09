# Come si rilascia Plancia

Questo documento è per una persona sola: quella che taglia la release. Dice cosa
si fa, in che ordine, e perché le scelte sono queste e non altre.

## Il modello in una riga

Sorgente completo e gratuito sotto GPL, build firmata a pagamento.

Non è una versione mutilata contro una completa: è lo stesso programma. Chi se lo
compila ha tutto. Chi paga compra la parte che costa soldi veri a chi la
pubblica, cioè il certificato Apple e la notarizzazione, più il fatto che
qualcuno continui a sistemarlo.

È il modello di [Ardour](https://ardour.org) (GPLv2+, 5.715 abbonati per 14.130
dollari al mese) e di Krita (GPLv3): sorgente libero, binari compilati a
pagamento. La GPL lo permette esplicitamente. Quello che la GPL non
impedisce è che qualcun altro ridistribuisca gratis il binario che ha comprato:
va messo in conto, non è un buco da tappare. In pratica non è mai stato il
problema di nessuno di questi progetti.

## Perché GPL e non MIT

Fino alla 0.2.0 Plancia era MIT. Quei commit restano MIT: una licenza data non si
ritira.

Dalla 0.3.0 è GPL-3.0-or-later, per una ragione sola: sotto MIT chiunque può
prendere il codice, chiuderlo, metterci sopra un nome nuovo e venderlo senza
restituire niente. Sotto GPL può ancora venderlo, ma deve pubblicare il sorgente
di quello che ha cambiato. Il lavoro resta pubblico.

Per l'utente non cambia niente: legge, usa, modifica, ridistribuisce.

Se un giorno vuoi tornare a MIT, è un file solo (`LICENSE`) più la nota in
`COPYRIGHT` e le due righe nei README. Sei l'unico titolare del copyright, quindi
puoi.

## Il prezzo

Quanto vuoi, da 5 euro, suggerito 15. Un pagamento solo, niente abbonamento,
niente account, e **niente chiavi di licenza**: sotto GPL sarebbero una
restrizione ulteriore, vietata dal paragrafo 10. Lo dice anche Ardour, che per
questo non le usa.

Il minimo esiste per una ragione pratica: sotto i pochi euro le commissioni si
mangiano tutto. Il suggerito sta dove sta perché per un'utilità di nicchia
quindici euro sono la cifra che non richiede di pensarci.

Il prezzo sta scritto in due punti, e vanno cambiati insieme:
- `site/index.html`, sezione `#prezzo`
- il link di pagamento, attributo `data-pagamento` sullo stesso bottone

## Chi incassa

Il venditore è una persona fisica in Spagna che vende software in tutto il mondo.
Il problema non è incassare, è l'IVA: venduto a un consumatore europeo, il
software si tassa nel paese del compratore. Farlo da soli vuol dire registrarsi
al regime OSS e presentare dichiarazioni trimestrali.

Per questo la scelta è una piattaforma che faccia da **merchant of record**: è lei
il venditore verso il cliente, si prende la responsabilità di IVA e imposte, e a
te gira il netto. Costa qualche punto percentuale in più di un semplice
processore di pagamenti, e vale ogni punto.

La scelta è **Polar**: 5% più 50 centesimi, ed è l'unica delle quattro che mette
per iscritto che una persona fisica può vendere, nominando Spagna e Italia. Il
confronto completo, con i numeri verificati e le trappole, sta in
[MONETIZZAZIONE.md](MONETIZZAZIONE.md).

GitHub Sponsors resta acceso in parallelo per chi vuole solo lasciare qualcosa
senza scaricare niente.

## La firma di Apple

Per far aprire l'app con un doppio clic serve:

1. iscrizione all'Apple Developer Program (99 dollari l'anno, verificato)
2. un certificato **Developer ID Application** nel portachiavi
3. la notarizzazione di ogni build

Senza, macOS non blocca l'app per sempre, ma la nasconde dietro un percorso che
la maggior parte delle persone non trova. Da Sequoia in poi **il clic destro >
Apri non esiste più**: la prima finestra offre solo "Sposta nel cestino" o
"Fine", e per aprirla davvero bisogna andare in Impostazioni di Sistema, Privacy
e sicurezza, Sicurezza, "Apri comunque", e confermare con la password. Chi paga non deve passare di lì.
Chi si compila il sorgente da sé ci passa una volta, e nel README c'è scritto.

Le credenziali per la notarizzazione si mettono nel portachiavi una volta sola:

```bash
xcrun notarytool store-credentials plancia-notarizzazione \
  --apple-id TUA@MAIL --team-id ILTUOTEAMID --password xxxx-xxxx-xxxx-xxxx
```

La password è una "app specific password" generata su appleid.apple.com, non la
password del tuo account.

## Tagliare una release

```bash
python3 tools/prova.py          # 138 controlli, una ventina di secondi
./tools/rilascia.sh 1.0.0       # versione, build, firma, DMG, notarizzazione
```

Se il collaudo non passa, lo script si ferma: una release che esce con i
controlli rossi è il modo più veloce per pubblicare una cosa rotta.

Lo script fa, in ordine:

1. scrive la versione in `mac/build.sh` e `plancia/__init__.py`
2. i controlli: compilazione Python, `node --check` su `app.js`, il collaudo
3. compila `Plancia.app`
4. firma con il primo certificato Developer ID che trova (o `FIRMA=...`)
5. impacchetta un DMG con il collegamento ad Applications
6. lo manda a notarizzare e ci grappa sopra l'esito
7. stampa lo SHA-256 da pubblicare accanto al file

Senza certificato salta i punti 4 e 6 e te lo dice: il DMG esce buono per
provarlo, non per venderlo.

Poi:

```bash
git tag v1.0.0 && git push origin v1.0.0
gh release create v1.0.0 dist/Plancia-1.0.0.dmg dist/Plancia-1.0.0.dmg.sha256 \
  --notes-file docs/note-1.0.0.md
```

## La lista prima di pubblicare

- [ ] `python3 tools/prova.py` verde (lo script lo fa da sé e si ferma se non lo è)
- [ ] gli screenshot sono rigenerati: `./tools/scatti.sh` rifà l'archivio finto,
      apre il server, scatta le quattro immagini in inglese a 2400x1830 e chiude
      tutto. Fino alla 1.0 si facevano a mano, e si vedeva: tagli diversi a ogni
      giro, e uno mostrava ancora una barra laterale senza la voce Cerca.
- [ ] i README dicono le funzioni che ci sono davvero
- [ ] niente em dash nei testi pubblici (lo controlla il collaudo)
- [ ] `~/.plancia/seed.json` non è finito nel repo
- [ ] il DMG si apre su un Mac dove non hai mai compilato niente
- [ ] il link di pagamento porta dove deve

## Il gancio prima del push

```bash
git config core.hooksPath .githooks
```

Una volta sola, e da lì in poi `git push` fa girare il collaudo e non parte se
non passa. Esiste perché è già successo di spedire una riga rotta avendo letto
l'esito in fondo a una catena di comandi che usciva sempre con zero.

Con `git push --no-verify` si salta, quando serve davvero.

## Il sito

Sta in `site/`, è HTML e CSS scritti a mano, nessuna dipendenza e nessun passo di
build. Si pubblica da solo a ogni push su `main` che tocchi quella cartella, con
`.github/workflows/pages.yml`.

Da fare una volta sola nel repo: **Settings > Pages > Source: GitHub Actions**.

Le due lingue stanno nella stessa pagina, marcate con `data-lingua`, e si accende
quella giusta con l'attributo `lang` sull'elemento radice. La lingua si sceglie
da quella salvata, se no da quella del browser, se no inglese.

Gli screenshot del sito sono gli stessi del README, ridotti a 1600 px.

```bash
./tools/scatti.sh
```

Rifà l'archivio dimostrativo, apre il server su una porta sua, scatta le quattro
immagini con Chrome a schermo spento e chiude tutto. Non tocca la tua
configurazione: prima bisognava cambiare la porta in `config.json`, riavviare
l'app e ricordarsi di rimetterla a posto dopo.

La lingua è forzata a inglese (`PLANCIA_DEMO_LANG` per cambiarla): senza,
l'interfaccia segue quella del sistema e gli scatti cambiano da macchina a
macchina.
