# Daytona MCP server

The Daytona [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
server lets an AI agent (Copilot) create and drive Daytona sandboxes
programmatically — sandbox management, file-system operations, git, process/code
execution, and preview. This is how the SAShiny demo is hosted and driven
(issue #12).

The workspace-root [`.mcp.json`](../.mcp.json) configures the server for any
Copilot session in this repo. It is portable and team-shareable.

## Prerequisites

1. **Daytona CLI** (macOS):
   ```sh
   brew install daytonaio/cli/daytona
   ```
   (Windows: use the installer from <https://www.daytona.io/docs/en/tools/cli>.)
2. **Authenticate** the CLI (uses the same account/API key as the SDK):
   ```sh
   daytona login
   ```
3. Confirm the server starts:
   ```sh
   daytona mcp start
   ```

## Configuration

The `.mcp.json` uses the portable Copilot format (top-level `mcpServers`):

```json
{
  "mcpServers": {
    "daytona": {
      "command": "daytona",
      "args": ["mcp", "start"]
    }
  }
}
```

No credentials are stored here — the MCP server uses the CLI's stored auth from
`daytona login`. To see the exact command/args Daytona would emit, run
`daytona mcp config`.

## Tool groups

| Group | What it does |
|---|---|
| Sandbox management | create, start, stop, delete, list sandboxes |
| File system | read/write/list files inside a sandbox |
| Git | clone, commit, push inside a sandbox |
| Process / code execution | run commands and code inside a sandbox |
| Preview | expose a running service (e.g. the demo app) on a URL |

## Relationship to the demo (#12)

- `deploy/daytona/verify_sandbox.py` is a **one-shot tier check** (does the
  sandbox reach `*.oda.sas.com:8591`?).
- The MCP server gives **interactive sandbox control** for future work: create a
  sandbox from the demo image, run the app, and preview it — all from within a
  Copilot session.

## Notes

- The server is a **stdio** server launched by the `daytona` CLI; it must be on
  the `PATH` of the machine running the agent.
- For remote/dev-container sessions, install the CLI inside the container and
  authenticate there.
- The `.mcp.json` is read automatically by Copilot harness sessions; no manual
  step is needed once the CLI is installed and logged in.