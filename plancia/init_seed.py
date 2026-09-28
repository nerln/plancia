"""Primo avvio: costruisce la mappa dei progetti dai dati che ci sono già.

Guarda i repo su GitHub, le cartelle con un .git, i file di memoria di Claude e
le cartelle di lavoro, e ne ricava un `~/.plancia/seed.json` da correggere a
mano. Meglio partire da qualcosa di sbagliato ma reale che da un file vuoto.
"""

import json
import os
import re

from . import config, esclusi, ingest, store

STOP = {"the", "and", "for", "with", "una", "che", "per", "con", "del", "della",
        "app", "test", "main", "code", "tool", "repo", "project", "progetto"}


def parole(*testi) -> list:
    """Parole che vale la pena usare come indizio per attribuire una sessione."""
    fuori = []
    for t in testi:
        for w in re.findall(r"[a-zA-Zà-ùÀ-Ù0-9]{4,}", (t or "").lower()):
            if w not in STOP and w not in fuori:
                fuori.append(w)
    return fuori[:8]


def titolo(slug: str) -> str:
    return re.sub(r"[-_]+", " ", slug).strip().capitalize()


def raccogli() -> dict:
    progetti = {}
    escl = esclusi.carica()

    def voce(key):
        key = store.slugify(key)
        return progetti.setdefault(key, {
            "key": key, "name": titolo(key), "kind": "progetto", "priority": 2,
            "pinned": 0, "keywords": [], "links": {}})

    # 1. repo su GitHub
    out = ingest.run(["gh", "repo", "list", "--limit", "60", "--json",
                      "name,description,visibility,pushedAt"], timeout=40)
    if out:
        try:
            for repo in json.loads(out):
                v = voce(repo["name"])
                v["links"].setdefault("repo", []).append(repo["name"])
                v["keywords"] = parole(repo["name"], repo.get("description"))
                if (repo.get("pushedAt") or "") > "2026-01-01":
                    v["priority"] = 1
        except Exception:
            pass

    # 2. cartelle con un .git
    radici = [ingest.expand(r) for r in config.load_config().get("code_roots", [])]
    drive = ingest.drive_root()
    if drive:
        radici.append(drive)
    for radice in radici:
        if not radice or not os.path.isdir(radice):
            continue
        try:
            entries = sorted(os.scandir(radice), key=lambda e: e.name)
        except OSError:
            continue
        for e in entries:
            if not e.is_dir() or e.name.startswith("."):
                continue
            if not os.path.isdir(os.path.join(e.path, ".git")):
                continue
            # Cartella privata: niente scheda in seed.json. `plancia init`
            # scrive un file che l'utente poi corregge a mano e guarda; non
            # è una scrittura nel database (quella la fa sync_seed, che ha
            # il suo stesso controllo), ma un nome e delle parole chiave
            # scritti lì sono comunque testo che non deve uscire da questa
            # cartella.
            if esclusi.percorso_escluso(e.path, escl):
                continue
            v = voce(e.name)
            v["links"].setdefault("path", []).append(
                e.path.replace(drive, "DRIVE") if drive and e.path.startswith(drive) else
                e.path.replace(str(config.HOME), "~"))
            if not v["keywords"]:
                v["keywords"] = parole(e.name)

    # 3. memoria di Claude, tipo progetto
    for md in sorted(config.CLAUDE_PROJECTS.glob("*/memory/*.md")):
        if md.name == "MEMORY.md":
            continue
        if esclusi.trascrizione_esclusa(md, escl):
            continue
        try:
            meta, _ = ingest.read_frontmatter(md.read_text("utf-8", errors="replace")[:2500])
        except OSError:
            continue
        tipo = (meta.get("metadata") or {}).get("type") if isinstance(meta.get("metadata"), dict) else None
        nome = meta.get("name") or md.stem
        if tipo != "project":
            continue
        v = voce(nome)
        v["links"].setdefault("memory", []).append(nome)
        if not v["keywords"]:
            v["keywords"] = parole(nome, meta.get("description"))

    for v in progetti.values():
        for kind, valori in v["links"].items():
            v["links"][kind] = sorted(set(valori))
    return progetti


def scrivi(progetti: dict, forza=False) -> str:
    if config.USER_SEED.exists() and not forza:
        return f"{config.USER_SEED} esiste già. Usa --force per riscriverlo."
    seed = {
        "_note": ("Mappa dei progetti generata da `plancia init`. Correggila a mano: "
                  "unisci quelli che sono lo stesso progetto, cambia i nomi, aggiungi "
                  "le parole chiave che usi quando ne parli."),
        "projects": sorted(progetti.values(), key=lambda p: p["key"]),
        "method_memories": [],
    }
    config.ensure_dirs()
    config.USER_SEED.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n", "utf-8")
    return f"{len(seed['projects'])} progetti scritti in {config.USER_SEED}"
