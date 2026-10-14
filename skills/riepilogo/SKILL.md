---
name: riepilogo
description: >-
  Tells the user how their day of work with AI went, using Plancia's real
  data, and reads it aloud in their language if they ask. Use it for "how did
  today go", "recap", "what did I get done", "read me the recap", "briefing",
  "resumen". Italian triggers: "com'è andata oggi", "riepilogo", "cosa ho
  fatto", "leggimi il riepilogo".
---

# The day's recap

The recap is not invented and not rebuilt by hand: Plancia produces it from
the real data, with `plancia` and `azione="recap"`.

## How to do it

1. Call `plancia` with `azione="recap"`. With no other arguments it is today,
   in the user's language. `day` takes YYYY-MM-DD for a past day, `lang`
   changes the language.
2. Report the text as it is. It is already written to be listened to: short
   sentences, no lists, no markdown. Do not reformat it into bullet points.
3. If the user asks to hear it ("read it to me", "tell me", "out loud"), call
   `plancia` again with `azione="recap", speak=true`, or `azione="speak"` if
   you want to read out an answer of your own.

Inside `dati` is the whole detail: sessions, commits, closed and open tasks,
posts, stalled projects. Use it to answer the questions the user asks next,
without regenerating the recap.

## The recap ends with a proposal

After the facts comes the thing that would be worth doing, and it is not
generic advice: it comes from a signal in the data. A failed run, a Codex
goal without quota, files uncommitted since yesterday, an approved post that
never went out, the next step of a stalled project.

If the user answers "do it", "the second one", "run it" to a proposal that
resumes a Plancia task, call `plancia` with `azione="riprendi"` and the `id` of
that task (see the `plancia` skill, section "Resuming a task": the three
states viva/chiusa/persa, meaning alive, closed, lost), or tell the user out
loud that you do not know which id it is. **Do not launch anything on your
own**: the default mode looks and reports, and "In background" stays at most a
secondary option that the user chooses, not you.

If the signal is not there, the proposal is not there, and that is intended.
Do not add one of your own to fill the ending.

## What not to do

Do not add results that are not in the data. If the day was empty, the recap
says so in one line and that is fine: filling it with encouraging phrases
makes it useless the next time.

Do not read it aloud unless the user asked. The audio comes out of the
computer's speakers and they might not be alone.

Do not rewrite the text for the voice: Plancia takes care of that, removing
addresses, paths and shas before saying it, because read aloud they sound like
nonsense.

## Every morning

`plancia daily on 08:45` sets up a scheduled job (launchd on macOS) that
prepares the recap and sends the notification. With `--voce` it reads it
aloud too. `plancia daily off` removes it. The Plancia Mac app has the same
thing in the menu bar, and `plancia://recap` launches it from a system
shortcut.
