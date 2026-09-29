Plancia reads what Claude Code and Codex already write on your disk and puts it
on one board. 2.0 is the Mac app rebuilt from scratch as a native app, and a
search that no longer makes you wait.

## Who this is for

**On a Mac with macOS 26 or later:** the app is new. Update, rebuild, open it.
Your data, your server and your tasks are exactly where they were.

**On macOS 13 to 15:** the 2.0 app does not run there. Stay on 1.1.0, or use the
dashboard in the browser, which installs as a web app and is unchanged.

**On Windows and Linux:** nothing changes in the dashboard. You still get the
faster search below.

## A native Mac app

The 1.x app was a window around the web dashboard. 2.0 is written in SwiftUI
with the standard macOS controls, so it looks and behaves like Finder, Mail and
Safari, including the Liquid Glass materials of macOS 26 in the sidebar, the
toolbar and the inspector.

- **Sidebar** with six sections: Today, Tasks, Projects, Social, Memory,
  Archive. No logo, no wordmark. Open tasks show as a count on Tasks.
- **Search** is the system search field in the toolbar (⌘F). Type and the
  Results view replaces the content until the field is empty. Matches in what
  is already loaded appear at once; the server adds the deeper ones a moment
  later, without moving the rows you are looking at. Scopes: everything, tasks,
  projects, sessions, memory.
- **Inspector** on the right for whatever you select, with its actions: resume,
  mark done, open the project, copy the text of a post, change a post's state.
- **Today** is one reading column: the recap in a single line with a button to
  hear it, Next up (one row per project, grouped by area, seven and then "Show
  more"), and the proposals with one button per row.
- **Tasks** is a sortable table with filters for state and source, and ⌘N for a
  new task.
- **Projects** are grouped by area on the left, with the selected project on the
  right: next action (editable), tasks, recent sessions, commits, links.
- **Social** is the post queue with the image next to the text.
- **Memory** is a list grouped by kind, with the full text of a note, where it
  comes from and its links. The graph is no longer the main view: **Neighbourhood**
  shows one note in the centre with its links on two rings, at most about
  fifteen nodes, laid out once. "Try recall" asks what Plancia would tell an
  agent for a sentence you type.
- **Archive** has the sessions in a sortable table, and the event log as a
  second view.
- **Settings** (⌘,) hold language (Italian or English) and appearance (system,
  light, dark). There is no Theme or language button in the window. Refresh is
  ⌘R, and the sections are ⌘1 to ⌘6.
- **Freshness** lives in the window subtitle: "updated at 21:59", or "server
  unreachable" with the data it had. When the server is down every view keeps
  showing what it last saw.

What stays from 1.x: the app starts and supervises the server, the voice panel,
the menu bar item, the `plancia://` actions, notifications, and the log in
`~/.plancia/app.log`. "Open in browser" is now a menu item; the web dashboard is
not shown inside the app any more.

The app only talks to `127.0.0.1`. It reads the token from `~/.plancia/token`
and sends it with writes only.

## Search, faster for everyone

Full-text search over past conversations could take several seconds on a large
archive, twice per request. Two causes, both fixed in the server, so the web
dashboard, the `plancia` command and the MCP tools get it too:

- With compartments on, the search joined the hits against temporary views and
  SQLite repeated the visibility check for every hit.
- On a cold cache, each hit was read from disk only to learn which session it
  belonged to.

Search now reads only ranks from the index and finds the file of each hit from a
small map (one range of row ids per file), computes visibility once per file, and
reads the real text only for the rows it shows. The map is built while indexing
and rebuilt on its own if it does not cover the index; without it the search
falls back to the same query as before. Results and their order are the same as
before, checked on 66 queries.

Measured in-process on a large archive (tens of thousands of indexed turns, many
sessions, compartments on), 53 words, phrases and operators: the median went from
0.25 s to 0.11 s, and the worst case from 12.6 s to 0.58 s. Those are warm-cache
timings of the function behind the route, not end to end over HTTP.

## Known limits

- The interface was checked in light and dark, in Italian and English, and with
  the server off, from window snapshots. The glass as you see it on your screen,
  VoiceOver, Reduce Transparency and Increase Contrast were not checked.
- Some paths were written and read but not clicked: writes from the views
  (mark done, new task, post state, next action), the Neighbourhood interactions
  and the recall popover.
- The first sync after the update builds the search map, which takes a few
  seconds on a large archive.

## Tested

4061 checks for the program, 450 for the dashboard, and 55 for the Mac
side: the app's data layer decodes the server's answers (saved from the demo
archive, so no real data) and talks to a fake server, checking that the token
goes only with writes and that a chosen compartment goes with every request.
The new search-speed check was seen failing on the old code first (6 to 7 s on
one word) and passes now, including that the fast path returns exactly what the
slow one does. The app was built and photographed in light and dark against a
demo archive; nobody has clicked through it on a real screen yet.

## Installing

```bash
git clone https://github.com/nerln/plancia.git ~/dev/plancia
cd ~/dev/plancia
./bin/plancia install
./bin/plancia init
./mac/build.sh --install
```

Python 3.9+. The Mac app needs macOS 26 or later. Everything lives in
`~/.plancia/`. On Windows and Linux, clone the same way and run
`python bin/plancia install`, `python bin/plancia init` and
`python bin/plancia serve --open`.

Upgrading from 1.1: pull, run `./bin/plancia install` again, then
`./mac/build.sh --install`. Nothing in your archive needs converting.

## Licence

GPL-3.0-or-later. No licence keys and no activation.
