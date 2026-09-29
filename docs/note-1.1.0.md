Plancia reads what Claude Code and Codex already write on your disk and puts it
on one board. 1.0 made it find things. 1.1 is about the question you open it
with: what do I do now, and where was I.

## One line per project

The board used to list open tasks. With a hundred projects that is a wall, and a
wall does not tell you what to do.

Today's view now shows **Next up**: one line per project, the first open task or
the next step you wrote down, grouped by area and ordered by deadline and then by
last activity. Seven lines, then "3 more". Everything else stays folded in the
project's **After** drawer, one click away.

## Areas

Projects can now have a parent, one level deep. An area adds up what is under
it: sessions, events, open tasks. New folders the ingest discovers land under
the right area when a rule can tell (same path, same repository, same prefix),
and under **Folders seen** when it cannot.

Reorganising a hundred projects by hand does not happen, and a reorganisation you
cannot undo does not get applied. So `plancia riordina` proposes a map in a file
(`--proponi`), shows it (`--mostra`), applies it in one batch (`--applica`) and
puts everything back exactly as it was (`--annulla`).

## Resume the conversation, not a copy of it

Every task created from Claude Code or Codex now remembers the session, the
folder, the agent and the machine it came from. The button on a task says what
state that session is in:

- **live**: it is still open, so the message to paste into it goes to your
  clipboard. There is nothing to launch.
- **closed**: the transcript is there, so a visible Terminal opens on
  `claude --resume <id>` or `codex resume <id>`, in the task's folder, with the
  task as the first message.
- **lost**: no session, or it was on another machine. It says so, and starts
  fresh with the context written out.

Running an agent headless with nobody watching is still there, once, as
**In the background**, with a switch for whether it may edit files. Same
behaviour from `plancia riprendi <id>` in the terminal, from the `plancia` tool
in Claude Code and Codex, and by voice.

## Glass, and type that is not the default

Every surface is glass now: panels, cards, columns, drawers. In the Mac app the
whole window sits on the native material, Liquid Glass on macOS 26 and later,
a translucent window material before that, and follows the theme you pick in the page. A
light smoked layer inside the app keeps text readable over a busy desktop:
contrast was measured on real pixels over coloured backgrounds, lowest value
4.78:1.

Titles are set in Fraunces, text in IBM Plex Sans, numbers in IBM Plex Mono. All
three are OFL and ship inside the repository. Nothing is fetched from anyone at
runtime, in the app or on the website.

## Never an empty screen

Each view now appears at once with the last state it had, saved locally, and
stays usable while fresh data arrives. When it arrives, cards that moved slide
to their new place with a small turn instead of vanishing and reappearing. A pill
at the top says "updated at 08:39", or "from memory, 08:39, server unreachable"
when the server does not answer. A real reload with the server down works too:
the dashboard keeps its own shell in the browser, so the page opens from there
and shows what it last saw. Data calls never go through that cache, so nothing
stale is ever passed off as fresh.

## A new icon, from the bridge

Plancia is Italian for a ship's bridge, so the icon is a piece of one: a brass
engine order telegraph on mahogany deck boards, with the lever on the one amber
sector. It is an Icon Composer document made of layers, so macOS 26 and later
put their own glass and light on the brass and on the dial. On a Mac without the
new tools the build uses a ready rendering of the same icon, so the two cannot
drift apart. The favicon, the mark in the dashboard and the website use it too.

## Windows and Linux

macOS comes first, and the native app stays macOS only. Everything else in
Plancia is Python and a local web server, and it now installs and runs on
Windows and Linux as well: `python bin/plancia install` sets up the command, the
MCP server, the hooks, the skills and the start at login with what each system
has (Task Scheduler or the Startup folder, systemd `--user` or autostart).
Resume opens Windows Terminal or the first terminal Linux has, the recap speaks
with the system voice when there is one, and when a piece is missing Plancia
says what to install instead of failing. The README has the exact commands.

In Chrome or Edge, open the dashboard and choose **Install Plancia**: it gets
its own window and icon, like an app. Safari on macOS does the same with Add to
Dock.

## Compartments

Some work on a machine is shared with other people and must not mix with the
rest. `compartimenti` in `~/.plancia/config.json` names those groups by their
folders and sessions; everything else is the default compartment. With it, each
session, task, project, memory note and run gets a compartment from the data it
already has, and every surface shows only its own: the session briefing, the
recall of notes from other folders, the MCP tools, the `plancia` command run
from a session, the voice assistant. Writes on another compartment's project or
task are refused with a plain message. The dashboard is your view, so it shows
everything, separated by a selector at the top. Without the key, Plancia does
what it always did.

Next to it there is an optional guard for Claude Code, `bin/plancia-guardiano`:
a PreToolUse hook that looks at what a tool call says it will touch and stops a
session from reading the other group's files, from searching its way into them,
or from switching the guard off. It starts in log-only mode (`solo-registro`), so
you can read what it would have denied before letting it deny anything. It is a
guard against incidents, not a security boundary: the README says plainly what
it does not see, and a real boundary is a separate user or a container.

## Private folders and sessions

Two new keys in `config.json`, `cartelle_escluse` and `sessioni_escluse`, keep
folders and sessions out of Plancia entirely: no transcripts, no memory, no
search index, no hook queue, no Codex sessions from there. `plancia esclusi`
lists what the rules match, and cleans out what had already come in before you
wrote them (`--prova` counts without touching anything).

## Tested

4001 checks for the program and 442 for the dashboard, green on Python
3.9 and 3.12, plus a pass that opens every view in a headless browser and fails
on an empty view or a script error. The continuous integration now runs them on
macOS, Windows and Linux. Every check added in this cycle was seen failing
without its fix first.

The website no longer publishes on every push to main: only by hand or when a
version tag is pushed.

## Installing

```bash
git clone https://github.com/nerln/plancia.git ~/dev/plancia
cd ~/dev/plancia
./bin/plancia install
./bin/plancia init
./mac/build.sh --install
```

Python 3.9+ and macOS 13 or later. No dependencies, no account, no server.
Everything lives in `~/.plancia/`. On Windows and Linux, clone the same way and
run `python bin/plancia install`, `python bin/plancia init` and `python
bin/plancia serve --open`; the README has the details for each system.

Upgrading from 1.0: pull, then `./bin/plancia install` again, so the skills,
the hooks and the Codex registration learn about resuming and compartments. The new columns are added to your
archive on the first start. Tasks created before this version have no session
attached; `plancia riprendi --backfill --secco` shows which ones it can match to
a session by time and project, and without `--secco` it writes them, in a batch
you can undo.

## About the .dmg attached here

**It is not signed or notarised.** macOS will refuse to open it on the first try.
To open it anyway, go to System Settings, Privacy and Security, and press "Open
Anyway". Building from source, with the commands above, gives you the same
program without that step.

## Licence

GPL-3.0-or-later. No licence keys and no activation.

sha256 of the disk image is in the `.sha256` file next to it.
