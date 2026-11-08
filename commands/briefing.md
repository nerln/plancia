---
description: Plancia briefing for the project you are in, and link this session to it
argument-hint: "[project key or name]"
---

Bring this session into Plancia. Requested project, if any: "$ARGUMENTS".

1. Link the folder you are working in to its project. Call the Plancia MCP tool
   `plancia` with `azione: "collega"` and `cartella` set to the absolute path of
   the directory you are working in now (it can differ from the one the session
   was opened in). If a project was requested above, pass it as `progetto`.
   - The answer says the folder is a container (like `~/dev`): ask which project
     folder this session is about, or move there first, then call again.
   - No project has that name: show the similar ones it returns and ask which.
     Pass `crea: true` only if the user says to create a new project.
   - The folder is not linked and no project was requested: the answer lists
     `candidati`, best first, each with the reason (the git remote, a word of the
     path). If the first one is clearly right (its git remote matches, or it is
     the only candidate), call `collega` again with it as `progetto`; otherwise
     ask, naming the candidates.
2. Call `plancia` with `azione: "briefing"` and `project` set to the linked key.
3. Answer in the user's language, briefly: which project the session is linked to
   and whether this changed anything, then where the project stands (next action,
   open tasks, last activity). Prose and short lists, no raw JSON.

If the Plancia tools are missing from this session, say so in one line and
suggest `/plancia:doctor`.
