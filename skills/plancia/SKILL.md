---
name: plancia
description: >-
  Reads and updates Plancia, the control centre for the user's work with AI:
  projects, tasks, social posts, past sessions, memory. Use it when the user
  asks "where was I", "what I had left open", "what should I do today", "where
  did we do this", when they open one of their projects, when a piece of work
  is finished and needs recording, and before writing social posts. Also for
  "update plancia", "mark this", "open the dashboard". Italian triggers:
  "a che punto sono", "cosa avevo lasciato", "cosa devo fare oggi", "dove
  l'avevamo fatto", "aggiorna plancia", "segna questo", "apri la dashboard".
---

# Plancia

Plancia is the single archive of the user's work with AI. The code lives in
the folder where Plancia was cloned, the data in `~/.plancia/plancia.db`, the
dashboard at http://127.0.0.1:7773. The MCP server exposes six direct tools
(`plancia_search`, `plancia_task_add`, `plancia_task_update`, `plancia_log`,
`plancia_project_update`, `plancia_post_add`) and a seventh, `plancia`, behind
which everything else sits: call it with `azione="<name>"` (`azione="aiuto"`
for the arguments of an action you do not know). If you see none of these
tools, the server is not connected, and it is registered with `plancia install`.

## At the start

If the conversation is about one of the user's projects, call `plancia` with
`azione="briefing"` before answering. It returns active projects, open tasks,
queued posts and the latest activity. It costs little and saves asking the
user things that are already written down.

If the user says "we already talked about this", or you are looking for past
work, use `plancia_search`: it indexes Claude Code sessions, memory, tasks,
posts and commits. `plancia` with `azione="sessions"` gives the list, with
the command to resume the conversation.

## During the work

- Work found but not done: `plancia_task_add`, which also remembers where it
  came from. A recorded task survives the end of the conversation, a promise
  in chat does not.
- A decision made, a path abandoned, a milestone reached: `plancia_log`.
- A project changes state, or the next step becomes clear:
  `plancia_project_update` with `next_action`. It is the first thing the next
  session will read.

## At the end

Before closing a substantial piece of work: update the project's `next_action`
and close the finished tasks with `plancia_task_update`. There is no need to
ask permission to write to Plancia: it is the user's own archive, not an
action toward the outside world.

## The board

`plancia` with `azione="lavagna"` ("lavagna" is Italian for whiteboard) is the
single list of everything that is open right now, across all three: Claude
Code's task lists, Codex's goals, Plancia's own tasks. Use it when the user
asks "what's open", "what are we stuck on", "what is Codex doing". States are
mapped to the same five: open, in progress, blocked, done, gone (the tool
reports them as `aperto`, `in corso`, `bloccato`, `fatto`, `sparito`).

`azione="lanci"` says how a run that already started went: outcome, tokens,
cost. `azione="eventi"` reads the append-only log, useful to anyone who has to
react to a piece of work that just finished.

## Resuming a task

Every task created with `plancia_task_add` remembers where it came from: the
session, the folder, the agent and the machine. Closing the terminal does not
lose it.

If the user asks "resume task N", call `plancia` with `azione="riprendi"` and
`id` (task N): it answers with the state, the session, the folder and the
command to reopen it. Then, depending on the state:

- **viva** (alive): the session is still open somewhere. Deliver the message
  "riprendi il task N di Plancia: <titolo>" to the session indicated, with the
  desktop app's `send_message` tool if you see it among your tools. If it is
  not there, tell the user the folder and the session, give them the same
  message, "riprendi il task N di Plancia: <titolo>", to paste, and let them
  reopen it themselves.
- **chiusa** (closed): tell the user the command to open in the terminal. Call
  `plancia` again with `azione="riprendi", apri=true` only if the user asks
  for it, because it opens a terminal on their machine, an action toward the
  outside world.
- **persa** (lost): explain the reason (folder gone, different machine, session
  too old) and propose starting over instead of chasing it.

Resuming means going back to the earlier conversation, not starting a new one
that writes on its own: nothing is launched autonomously here. Running in the
background stays a secondary option that the user picks from the dashboard,
not an action you decide.

## The proposals

The recap ends with the things that would be worth doing, computed from the
signals in the data and never invented. If the user asks "what should I do
now", `plancia` with `azione="recap"` already contains them: do not add any of
your own on top, at most explain why one of them comes first.

## Social

`plancia_post_add` saves a draft, it does not publish anything. The
`source_ref` field must point to the real work behind the post: a commit sha,
a repository name, a session id. The rule of the account is that every post
comes from something that really happened.

**Every post is born with its image.** The `media` field is the path of the
file that goes out together with the text, and it is filled in when the draft
is written, not at publishing time: afterwards the work it came from is no
longer at hand. A post without an image is the exception and needs a reason.

When you close a piece of work that deserves a post, you usually already have
the image: a screenshot already in the repository (`docs/img/...`), the
Plancia dashboard, the site that was just published. If a new one is needed,
make it before saving the draft. Two rules learned by publishing: keep it
under 400 KB, and look at it before attaching it, because a screenshot carries
out everything that was on the screen.

Writing the post and publishing it are not Plancia's job. If you have skills
for those, use them, and make sure publishing asks for explicit approval.
Plancia keeps the count: `plancia` with `azione="posts"` for the state of the
pipeline, `azione="post_update"` with the url when a post is really online.

## Voice

`plancia` with `azione="recap"` returns the day's recap, written to be
listened to. With `speak=true` it reads it aloud on the user's computer.
`azione="speak"` reads any text: use it only if the user asks, and write for
the ear, not for the eye.

The languages are it, en, es, fr, de, pt. If the user does not specify one, the
one in `~/.plancia/config.json` applies.

## Jarvis

In the Mac app, `plancia://jarvis` opens the hands-free voice panel, or press
Option+Space from any app. It listens continuously, understands from the
silence when the user has finished speaking, acts and answers by voice. The
commands it recognises on its own (open a view, mark a task, close it, reread
the sources, the recap) start immediately; everything else reaches Claude Code
with the `plancia_*` tools open, so it can really act.

The user can interrupt it while it speaks: they just start talking again, the
microphone stays open even while it answers. "Cancel" stops a run that has
started, "stop" closes the panel, "repeat" says the last thing again, "slower"
and "faster" change the speed of the voice. When a run finishes it says so
aloud even if the user was doing something else in the meantime.

`plancia jarvis "sentence"` does the same thing from the terminal, without a
microphone.

Three paths, in order: commands and questions about the data are resolved in a
tenth of a second without calling any model; everything else goes to a Claude
process kept warm, about three seconds. The recap is precomputed, so it is
immediate.

## The two agents

Plancia also reads Codex's sessions from `~/.codex/sessions` and registers its
own MCP server inside `~/.codex/config.toml`: Codex and Claude see the same
archive and the same tools. The Agents view shows who worked on what and when
the two handed work to each other.

## Commands

```bash
plancia lavagna          # everything open, across all agents
plancia lanci            # how the runs went
plancia eventi --dopo <id>
plancia recap --speak    # recap read aloud
plancia jarvis "..."     # a voice command, typed
plancia ask "..." --speak
plancia daily on 08:45   # automatic recap every morning
plancia flusso           # where the data comes from and how fresh it is
plancia sync --modo caldo   # only sessions and hooks, a hundredth of a second
plancia serve --open     # dashboard
plancia sync             # rereads sessions, memory, repositories
plancia briefing         # the briefing on stdout
plancia doctor           # checks the connections
```
