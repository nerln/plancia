# Skills for Claude Code

Two skills that tell Claude Code when to read from Plancia and when to write
back to it. They are plain text files: a `SKILL.md` each, nothing to build.

| Skill | What it does |
|---|---|
| [plancia](plancia/SKILL.md) | Reads the briefing when you open a project, searches past sessions, records tasks, decisions and the next step, and saves social post drafts with the work they come from. |
| [riepilogo](riepilogo/SKILL.md) | Tells you how the day went from Plancia's data, optionally out loud, and ends with one proposal that comes from a signal in the data. |

Both are written in English and trigger on English and Italian phrases, so
"what did I get done" and "cosa ho fatto" call the same skill.

## They need Plancia

The skills call Plancia's MCP tools (`plancia_search`, `plancia_task_add`,
`plancia_task_update`, `plancia_log`, `plancia_project_update`,
`plancia_post_add`, and `plancia` with an `azione`) and its `plancia` command.
Without Plancia installed they have nothing to talk to. Install Plancia first,
as described in the [main README](../README.md#install).

`plancia install` also writes these two skills into `~/.claude/skills/` for
you. The versions in this folder are for reading, for copying by hand, and for
anyone who wants to change them.

## Install by hand

Copy the folders you want into your Claude Code skills directory:

```bash
cp -R skills/plancia skills/riepilogo ~/.claude/skills/
```

Start a new Claude Code session and ask for a recap. If Plancia's MCP server is
not connected, run `plancia install` and `plancia doctor`.

## Licence

The skills in this folder are MIT licensed, see [LICENSE](LICENSE). The rest of
the Plancia repository is GPL-3.0-or-later, see the [LICENSE](../LICENSE) at
the root.
