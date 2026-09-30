Plancia reads what Claude Code and Codex already write on your disk and puts it
on one board. 2.0 is the Mac app rebuilt from scratch as a native app, a
search that no longer makes you wait, a Jarvis you can trust, work that resumes in
the session that saved it, and a redrawn web dashboard.

## Who this is for

**On a Mac with macOS 26 or later:** the app is new. Update, rebuild, open it.
Your data, your server and your tasks are exactly where they were.

**On macOS 13 to 15:** the 2.0 app does not run there. Stay on 1.1.0, or use the
dashboard in the browser, which installs as a web app and is redrawn in 2.0.

**On Windows and Linux:** you get the redrawn dashboard, the faster search and the
resume-in-the-same-session behaviour below. The Mac app, its Wood style and the
new Jarvis panel are macOS only.

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
  comes from and its links, in three modes. **List** is the default.
  **Neighbourhood** shows one note in the centre with its links on two rings, at
  most about fifteen nodes, laid out once. **Map** is the whole memory as a graph
  with real physics (see below). "Try recall" asks what Plancia would tell an
  agent for a sentence you type.
- **Archive** has the sessions in a sortable table, and the event log as a
  second view.
- **Settings** (⌘,) hold language (Italian or English) and appearance (system,
  light, dark). There is no Theme or language button in the window. Refresh is
  ⌘R, and the sections are ⌘1 to ⌘6.
- **Freshness** lives in the window subtitle: "updated at 21:59", or "server
  unreachable" with the data it had. When the server is down every view keeps
  showing what it last saw.

- **Text size** follows ⌘+, ⌘- and ⌘0 (⌘= works too), in seven steps from 85% to
  125%, also in Settings, and is remembered between launches. The whole window
  scales, sidebar, tables, inspector and graph together, except the system
  toolbar. Past 125% the views run out of room at the normal window width, so that
  is the ceiling.

What stays from 1.x: the app starts and supervises the server, the voice panel,
the menu bar item, the `plancia://` actions, notifications, and the log in
`~/.plancia/app.log`. "Open in browser" is now a menu item; the web dashboard is
not shown inside the app any more.

The app only talks to `127.0.0.1`. It reads the token from `~/.plancia/token`
and sends it with writes only.

## A Wood style

Settings has a Style: **System** (the look above) or **Wood**, a modern take on
the skeuomorphic dashboard of the app icon. The sidebar and the strip under the
toolbar sit on mahogany boards taken from the icon's own layers; the selection and
the counts are solid brass; the content stays on warm paper, light or dark
following Appearance. Controls and glass are still the system's, and the font is
still the system font. Contrast was measured from the sources (ink on paper 14.6
and 13.8, brass text on paper 5.1 and 9.0, cream on the wood 9.9 and 11.8) and
checked by a script. With System selected nothing changes: the twelve light
snapshots match the previous build pixel for pixel.

## A memory map with physics

**Map**, the third mode in Memory, draws every note as a node coloured by kind,
sized by how many links it has, with the busiest labelled first and labels
appearing as you zoom. Drag a node and its neighbours follow; drag the background
to pan; pinch, the scroll wheel or ⌘+ ⌘- ⌘0 over the map to zoom in steps with a
spring camera. **1**, **2** and **All** pick how much is in view around the selected
note: nodes that enter are born on a neighbour already there, nodes that leave are
pulled back onto one and fade. Click selects and opens the inspector; double click
goes to level 2. With Reduce Motion the transitions are instant.

The simulation (repulsion, springs on links, gravity, soft collisions, damping and
a cooling heat) runs at a fixed 1/60 s step in an actor off the main thread and
stops by itself when the scene is still, so a still map costs nothing. Measured
with the real view in a real window on 246 nodes and 575 links: about 118 frames
per second settling, 116 dragging, 112 zooming, no frame drawn in more than 16.7 ms;
the physics costs 0.1 to 0.14 ms per step, and 0.5 to 0.8 ms at 600 nodes.

## The app lags less

The data layer was reworked so that refreshing and the background cycle cost almost
nothing on the main thread: identical requests are merged into one, an answer with
the same bytes as the last one is not decoded or assigned again, the subtitle and
the badge change once a minute instead of at every cycle, the memory map is not
re-fetched unless notes change, the cycle slows in the background, and a search
that only deletes a character reuses its cache. Measured as CPU time of the main
thread on a large demo archive (6000 tasks, 4000 sessions): reload from 84.6 ms
to 8.1 ms over 18 reloads, and the background cycle from 121 ms to 24 ms over 16
cycles. **Switching section did not get faster**: it costs 100 to 190 ms and that
cost is in SwiftUI and AppKit layout (per-view toolbars, inspectors and automatic
row heights), not in the data. That is the next thing to fix.

## Jarvis, rebuilt

Jarvis is a new panel in system glass, still on ⌥Space. A waveform follows the
microphone while it listens, breathes while it thinks and follows the voice while
it speaks (a bar with Reduce Motion). The text arrives word by word, and the voice
starts with the first sentence: a local neural voice (Pocket, then Voicebox) is
asked one sentence at a time, and the next one is synthesised while the first
plays. If the neural voice does not answer in time it falls back to the enhanced or
premium system voices and says so at the bottom of the panel; the basic robotic
voice is never used unless you allow it in the panel menu. Listening runs on the
Mac and never falls back to Apple's servers.

It is also safe to start. The microphone turns on only from the button or the
shortcut, is visibly on, and turns off after each sentence unless you enable
Continuous conversation. The model behind it is read-only, with the writing tools
denied by name. Tasks, closes, archives, agents and "resume task N" never start
from a sentence, only from a card the server builds with the real data (what,
which agent, read-only or may edit files, folder, session) and a Confirm button
that Return does not press. A card is valid for five minutes, once; Esc, Cancel
and closing the panel throw it away.

## Work resumes in the session that saved it

"In background" on a task, the Retry and Resume proposals and Jarvis now continue
in the session that saved the task, with the same id and in its folder, instead of
a new or forked one. One function decides, and the dashboard, MCP, the command line
and Jarvis all use it. A closed session is resumed (`claude -p --resume <id>`, or
`codex exec resume <id>`). An open one is not touched: you get the message to paste,
and a copy starts only if you ask for it. A lost session, or one without a known
folder, starts a new one, and the plan says so before anything runs, in the Mac app
too. A Codex thread held open by the desktop app is recognised and reported as
blocked instead of failing.

## Project states and mergers

`plancia riordina` now also sets a project's state (active, archived, done) and
records mergers ("merged into X"), from the same file that assigns parents, with a
reason required on every state or merger row. One batch per file, all or nothing
per row, and `--annulla` puts parent, state and note back field by field, only
where the field is still what the batch left. Manual projects are touched only by
a row that names them.

## A redrawn web dashboard

The web dashboard follows the Mac app: system fonts, six sections in a sidebar,
Today as a reading column, Tasks as a table with a detail panel, Projects and
Social as list plus detail, Memory with a physics graph on canvas (drag, levels 1,
2 and All, zoom), search in the top field with five scopes and text size in five
steps in Settings. Contrast meets AA in light and dark. Windows and Linux use
this.

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

- The interface was checked in System and Wood, light and dark, in Italian and
  English, and with the server off, from window snapshots. The glass as you see it
  on your screen, VoiceOver, Reduce Transparency and Increase Contrast were not
  checked.
- Some paths were written and read but not clicked: writes from the views
  (mark done, new task, post state, next action), the Neighbourhood interactions,
  the recall popover, and the Map gestures on a real mouse and trackpad.
- Jarvis was never run with the real microphone, speakers, Voicebox, Pocket or a
  real `claude`; the panel and its safety rules were tested against fakes. This Mac
  has no enhanced or premium system voice installed, so without a neural voice
  Jarvis stays text-only until you download one.
- Row selection in tables and lists follows the system accent (blue or grey), not
  the brass, in Wood. At 125% text the inspector overlaps the last table column a
  little.
- Switching section is still 100 to 190 ms of main-thread time.
- The web export page still uses the old style.
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
