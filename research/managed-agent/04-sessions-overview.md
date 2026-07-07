# Sessions Overview: Lifecycle, States, and Creation

Source: https://platform.claude.com/docs/en/managed-agents/sessions  
Source: https://platform.claude.com/docs/en/managed-agents/session-operations  
Fetched: 2026-06-30

---

## What a Session Is

A session is an agent instance within an environment. It:

- References an **agent** (defines behavior: model, system prompt, tools, MCP servers)
- References an **environment** (provides the sandbox)
- Maintains **conversation history** across multiple interactions
- Maintains **sandbox state** (filesystem, installed packages, created files) via checkpointing

Sessions follow a two-step lifecycle:
1. **Create the session** — provisions the environment sandbox
2. **Send a user event** — starts actual work

---

## Session Statuses

| Status | Description |
|--------|-------------|
| `idle` | Agent is waiting for input, including user messages or tool confirmations. Sessions start in `idle`. |
| `running` | Agent is actively executing. |
| `rescheduling` | A transient error occurred; retrying automatically. |
| `terminated` | Session has ended due to an unrecoverable error. |

Additional states visible in session resource:
- **archived**: Session is archived (no new events allowed; history preserved). Not listed in the statuses table but accessible via the `archive` operation.

---

## API Endpoints

All requests require:
- Header: `anthropic-version: 2023-06-01`
- Header: `anthropic-beta: managed-agents-2026-04-01`
- Header: `x-api-key: $ANTHROPIC_API_KEY`

| Operation | Method | Path |
|-----------|--------|------|
| Create session | `POST` | `/v1/sessions` |
| Retrieve session | `GET` | `/v1/sessions/:id` |
| List sessions | `GET` | `/v1/sessions?agent_id=...` |
| Update session | `POST` | `/v1/sessions/:id` |
| Archive session | `POST` | `/v1/sessions/:id/archive` |
| Delete session | `DELETE` | `/v1/sessions/:id` |
| Send events | `POST` | `/v1/sessions/:id/events` |
| Stream events | `GET` | `/v1/sessions/:id/events/stream` |
| List past events | `GET` | `/v1/sessions/:id/events` |

Rate limits:
- Create endpoints: 300 requests/minute per organization
- Read endpoints: 1,200 requests/minute per organization

---

## Creating a Session

### Minimum required fields

```json
POST /v1/sessions
{
  "agent": "$AGENT_ID",
  "environment_id": "$ENVIRONMENT_ID"
}
```

`agent` as a string uses the **latest agent version**.

### Pinning to a specific agent version

```json
{
  "agent": {
    "type": "agent",
    "id": "$AGENT_ID",
    "version": 1
  },
  "environment_id": "$ENVIRONMENT_ID"
}
```

### With MCP vault authentication

```json
{
  "agent": "$AGENT_ID",
  "environment_id": "$ENVIRONMENT_ID",
  "vault_ids": ["$VAULT_ID"]
}
```

`vault_ids` references vaults containing stored OAuth credentials. Anthropic manages token refresh.

### With a title (used for outcome sessions)

```json
{
  "agent": "$AGENT_ID",
  "environment_id": "$ENVIRONMENT_ID",
  "title": "Financial analysis on Costco"
}
```

### Session creation response (example shape)

```json
{
  "id": "sesn_01...",
  "status": "idle",
  "agent": { "type": "agent", "id": "...", "version": 1 },
  "environment_id": "env_01...",
  "vault_ids": [],
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0
  },
  "outcome_evaluations": []
}
```

---

## Starting Work

Creating a session provisions the sandbox but starts no work. Send a `user.message` event:

```json
POST /v1/sessions/$SESSION_ID/events
{
  "events": [
    {
      "type": "user.message",
      "content": [{"type": "text", "text": "List the files in the working directory."}]
    }
  ]
}
```

---

## Session Operations

### Retrieving a session

```
GET /v1/sessions/$SESSION_ID
```

Returns the full session object including current `status` and cumulative `usage`.

### Listing sessions

```
GET /v1/sessions?agent_id=$AGENT_ID
```

Paginated. Each item has at minimum `id` and `status`.

### Updating a session

Sessions can have `agent.tools` and `agent.mcp_servers` (including permission policies) updated mid-session without creating a new agent version. Semantics are **full replacement**: the provided array replaces the existing value.

- Session must be `idle` to update. Interrupt first if running.
- Updates are session-local and do not propagate to the underlying agent.

```json
POST /v1/sessions/$SESSION_ID
{
  "agent": {
    "tools": [
      {"type": "agent_toolset_20260401"},
      {"type": "mcp_toolset", "mcp_server_name": "linear"}
    ],
    "mcp_servers": [
      {"type": "url", "name": "linear", "url": "https://mcp.linear.app/sse"}
    ]
  }
}
```

### Archiving a session

Prevents new events from being sent while preserving history. A `running` session cannot be archived — send an interrupt event first.

```
POST /v1/sessions/$SESSION_ID/archive
```

### Deleting a session

Permanently removes the session record, its events, and associated sandbox. A `running` session cannot be deleted — interrupt first.

Files, memory stores, vaults, skills, environments, and agents are **independent resources** and are not affected by session deletion.

```
DELETE /v1/sessions/$SESSION_ID
```

---

## Session Persistence and Sandbox State

- **Conversation history** is persisted until the session is explicitly deleted.
- **Sandbox checkpoints** (filesystem, installed packages, created files) are preserved for **30 days** after the session's last activity.
- To reset the inactivity timer and keep the checkpoint alive beyond 30 days, send periodic `user.message` events.
- Resuming a session is simply sending a new `user.message` event to the existing session ID.

---

## Usage Tracking

The session object includes a `usage` field with cumulative token statistics:

```json
{
  "id": "sesn_01...",
  "status": "idle",
  "usage": {
    "input_tokens": 5000,
    "output_tokens": 3200,
    "cache_creation_input_tokens": 2000,
    "cache_read_input_tokens": 20000
  }
}
```

- `input_tokens`: uncached input tokens across all model calls in the session
- `output_tokens`: total output tokens across all model calls
- `cache_creation_input_tokens`: tokens written to prompt cache
- `cache_read_input_tokens`: tokens read from prompt cache (cheaper per-token)
- Cache TTL: 5 minutes. Back-to-back turns within 5 minutes benefit from cache reads.

---

## Outcome-Oriented Sessions

Sessions can be given an "outcome" — a target state with a grading rubric. The agent iterates toward the outcome automatically.

See `06-sessions-tools-confirmations.md` and `define-outcomes` documentation for full details. The `user.define_outcome` event kicks off outcome mode; no additional `user.message` is needed.

The session object includes `outcome_evaluations[]` which can be polled for status without streaming.

```json
{
  "outcome_evaluations": [
    {
      "outcome_id": "outc_01a...",
      "result": "satisfied"
    }
  ]
}
```

Outcome evaluation results: `satisfied`, `needs_revision`, `max_iterations_reached`, `failed`, `interrupted`.
