---
description: Check the connection to Plancia (database, MCP server, dashboard) and repair what can be repaired
argument-hint: "[--migra]"
allowed-tools: Bash(python3:*)
---

!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/plancia-plugin" salute --ripara`

Report the result above to the user in their language, one line per check, and
say plainly what is wrong and what was repaired.

- If it lists registrations from before the plugin (an MCP server `plancia` in
  `~/.claude.json`, Plancia hooks in `settings.json`), the session runs two
  servers and prints the briefing twice. If the user passed `--migra`, or says
  yes when you ask, run
  `python3 "${CLAUDE_PLUGIN_ROOT}/bin/plancia-plugin" migra` and report what it
  moved. It keeps a dated copy of every file it changes. The change applies to
  sessions started after it.
- If the MCP server check failed, quote the last error line and suggest the
  fix it points to. The sentinel restarts the server on the next call by itself;
  a session whose Plancia tools disappeared entirely needs `/mcp` to reconnect.
