Plancia reads what Claude Code and Codex already write on your disk and puts it
on one board. This is 1.0.

The 0.3 releases were about having the surfaces. This one is about the two things
that decide whether a tool like this gets used at all: what it costs you to keep
it plugged in, and whether it can find the thing you are looking for.

## Search, inside what was said

Until now the search index held, for each session, the opening prompt and nothing
else. Measured on a real archive that is 0.80 MB out of 979, 0.08% of the
material, and it is why the search tool had been called five times in its life:
it did not find things.

There is now a full text index over the prose of every turn, yours and the
agent's, from both agents. Tool results stay out on purpose: they are most of the
bytes and almost never the thing you remember. On the machine it was built for
that is 13,000 turns from 1,287 transcripts, 20 MB indexed, rebuilt from scratch
in 5 seconds and kept current incrementally at the cost of one `stat` per
unchanged file.

Every hit comes back verbatim with the file and the line it came from, so you
reopen the moment instead of reading a summary of it. Chips above the results
count the hits per project across the whole index, not just the page you are
looking at, so you can tell at a glance whether the thing is in one place or
scattered.

Three ways in: `/` from any view in the dashboard, `plancia cerca` in the
terminal, `plancia_search` inside Claude Code and Codex.

## It costs less to keep it plugged in

Tool schemas are paid for in every request of a session, not once. Twenty tools
meant twenty schemas in the context of every message. Now six stay exposed, the
six that actually get used, and the rest sit behind a single `plancia` tool you
call with `azione`. The old names still answer, for clients that are already
running.

Measured: 1195 tokens per Claude Code session, down from 2870. 1020 per Codex
session, down from 2196. Same binary for both, so the saving is the same saving.

## The cold pass got twenty times faster

It took forty seconds. Twenty of those were one folder. `git status` inside a
cloud-synced folder has to check every tracked file with the file provider:
measured cold on a 681 file repo, 2 minutes 51 seconds, against 10 ms for a repo
on disk.

Folders are now read eight at a time, a folder that does not answer within four
seconds is remembered and left alone for six hours, and a status that never
arrived is stored as unknown rather than as clean, because "I did not look" and
"nothing to commit" are different things and one of them feeds a proposal.

Hot pass ~40 ms, cold pass ~1.5 s.

## Tested enough to put a 1 on it

137 checks, about twenty seconds, run against a throwaway archive that never
touches yours. They cover the schema, the board, the proposals, the search index,
the recap, the MCP surface and a hard ceiling on its token cost, every read route
of the HTTP API, the session hook, the skills, and a full install and uninstall
into a fake home directory.

Two of those checks exist because a regression got past the suite during this
cycle and had to be found by hand.

## Installing

```bash
git clone https://github.com/nerln/plancia.git ~/dev/plancia
cd ~/dev/plancia
./bin/plancia install
./bin/plancia init
./mac/build.sh --install
```

Python 3.9+ and macOS 13 or later. No dependencies to install, no account, no
server. Everything lives in `~/.plancia/`.

Upgrading from 0.3: nothing to do beyond pulling and reinstalling. The turn index
builds itself on the first sync.

## About the .dmg attached here

**It is not signed or notarised.** macOS will refuse to open it on the first try
and offer only "Move to Trash" or "Done". To open it anyway you have to go to
System Settings, Privacy and Security, Security, and press "Open Anyway". Since
macOS Sequoia the old Control-click shortcut no longer works.

Building from source, with the commands above, avoids all of that and gives you
the same program.

A signed build that opens with a double click is what the paid version will be:
see the [website](https://nerln.github.io/plancia/#prezzo). The source stays free
and complete, always. What the price covers is the Apple certificate, the
notarisation, and the maintenance. It is the model Ardour and Krita have used for
years.

## Licence

GPL-3.0-or-later. Versions up to 0.2.0 were MIT and stay MIT. No licence keys and
no activation: under the GPL those would be a further restriction, which is not
allowed.

sha256 of the disk image is in the `.sha256` file next to it.
