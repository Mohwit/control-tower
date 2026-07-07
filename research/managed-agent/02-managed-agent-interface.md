# Claude Managed Agents — Full API Interface

Source: https://platform.claude.com/docs/en/managed-agents/sessions  
Source: https://platform.claude.com/docs/en/managed-agents/events-and-streaming  
Source: https://platform.claude.com/docs/en/managed-agents/reference  
Source: https://platform.claude.com/docs/en/managed-agents/multi-agent  
Retrieved: 2026-06-30

---

## SDK Client Setup

```python
from anthropic import Anthropic
client = Anthropic()  # reads ANTHROPIC_API_KEY from env
```

```typescript
import Anthropic from "@anthropic-ai/sdk";
const client = new Anthropic();
```

All SDK calls go through `client.beta.*`. The SDK sets `anthropic-beta: managed-agents-2026-04-01` automatically.

---

## Agent API

### `client.beta.agents.create(...)` — Create an agent

Parameters:

| Param | Type | Required | Notes |
|---|---|---|---|
| `name` | string | Yes | Human-readable label |
| `model` | string \| `{id, speed}` | Yes | Model ID or object |
| `system` | string \| null | No | System prompt |
| `tools` | array | No | Tool definitions |
| `mcp_servers` | array | No | MCP server declarations |
| `skills` | array | No | Skills |
| `multiagent` | `{type, agents}` | No | Coordinator config for multi-agent |
| `description` | string \| null | No | Description |
| `metadata` | object | No | Arbitrary k/v |

Returns: Agent object with `id`, `type`, `version`, `created_at`, `updated_at`, `archived_at`, and all input fields echoed back.

### `client.beta.agents.update(agent_id, ...)` — Update an agent

Parameters: same as create, plus:

| Param | Type | Required | Notes |
|---|---|---|---|
| `version` | int | Yes | Must match current version (optimistic concurrency; 409 on mismatch) |

### `client.beta.agents.archive(agent_id)` — Archive an agent

No additional parameters. Returns agent object with `archived_at` set. Irreversible.

### `client.beta.agents.versions.list(agent_id)` — List versions

Paginated. SDK auto-pages.

---

## Environment API

### `client.beta.environments.create(...)`

| Param | Type | Notes |
|---|---|---|
| `name` | string | Label |
| `config` | object | `{type: "cloud", networking: {type: "unrestricted"}}` or self-hosted config |

Returns: `{id, ...}`. Save the `id`.

---

## Session API

### `client.beta.sessions.create(...)` — Create a session

| Param | Type | Required | Notes |
|---|---|---|---|
| `agent` | string \| `{type, id, version}` | Yes | Agent ID string = latest version; object = pinned version |
| `environment_id` | string | Yes | |
| `title` | string | No | |
| `vault_ids` | string[] | No | OAuth credential vaults for MCP tools |

Returns: Session object with `id`, `status`, `usage`, and more.

```python
session = client.beta.sessions.create(
    agent=agent.id,
    environment_id=environment.id,
)
# Pinned version:
pinned = client.beta.sessions.create(
    agent={"type": "agent", "id": agent.id, "version": 1},
    environment_id=environment.id,
)
```

Creating a session provisions the sandbox but does NOT start any work. Work begins when you send a `user.message` event.

---

## Events API

### `client.beta.sessions.events.send(session_id, events=[...])` — Send events

Sends one or more events into the session. Events are processed in order.

```python
client.beta.sessions.events.send(
    session.id,
    events=[
        {
            "type": "user.message",
            "content": [{"type": "text", "text": "List the files in the working directory."}],
        },
    ],
)
```

### `client.beta.sessions.events.stream(session_id)` — Open SSE stream (context manager)

Returns a stream that yields event objects as they arrive. **Open the stream BEFORE sending events** to avoid missing events.

```python
with client.beta.sessions.events.stream(session.id) as stream:
    client.beta.sessions.events.send(session.id, events=[...])
    for event in stream:
        if event.type == "session.status_idle":
            break
```

TypeScript (async iterator):
```typescript
const stream = await client.beta.sessions.events.stream(session.id);
await client.beta.sessions.events.send(session.id, { events: [...] });
for await (const event of stream) {
  if (event.type === "session.status_idle") break;
}
```

### `client.beta.sessions.events.list(session_id, types=[...])` — List past events

Paginated history of all events. Optional `types` filter:

```python
events = client.beta.sessions.events.list(
    session.id,
    types=["agent.tool_use", "agent.tool_result"],
)
for event in events.data:
    print(f"[{event.type}] {event.processed_at}")
```

Every event has a `processed_at` timestamp (null = queued, not yet processed) and an `id`.

---

## Complete Event Type Catalog

### User events (what you send)

| Type | Description |
|---|---|
| `user.message` | A user message with text content. Starts or continues agent work. |
| `user.interrupt` | Stop the agent mid-execution. Optionally target a specific thread via `session_thread_id`. |
| `user.custom_tool_result` | Response to a custom tool call. Fields: `custom_tool_use_id`, `content`. |
| `user.tool_confirmation` | Approve/deny an agent or MCP tool call. Fields: `tool_use_id`, `result` ("allow"/"deny"), optional `deny_message`. |
| `user.define_outcome` | Define an outcome for the agent to work toward. |
| `user.tool_result` | For self-hosted environments only — provide agent_toolset results. |

### System events (what you send)

| Type | Description |
|---|---|
| `system.message` | Update the agent's system prompt between turns. Only supported on Claude Opus 4.8. Content: 1–1000 text items. Cannot be sent when session is idle with `requires_action`. |

### Agent events (what you receive)

| Type | Description |
|---|---|
| `agent.message` | Agent response with text content blocks. `.content` is a list of `{type, text}`. |
| `agent.thinking` | Agent thinking content, emitted separately from messages. |
| `agent.tool_use` | Agent invokes a pre-built agent tool (bash, file ops, etc.). Has `.name`. |
| `agent.tool_result` | Result of a pre-built agent tool execution. |
| `agent.mcp_tool_use` | Agent invokes an MCP server tool. |
| `agent.mcp_tool_result` | Result of an MCP tool execution. |
| `agent.custom_tool_use` | Agent invokes one of your custom tools. Contains `.name` and `.input`. Respond with `user.custom_tool_result`. |
| `agent.thread_context_compacted` | Conversation history was compacted to fit the context window. |
| `agent.thread_message_received` | Multiagent: agent delivered result to coordinator. Has `from_session_thread_id`, `from_agent_name`, `content`. |
| `agent.thread_message_sent` | Multiagent: coordinator sent follow-up to another agent. Has `to_session_thread_id`, `to_agent_name`, `content`. |

### Session events (what you receive)

| Type | Description |
|---|---|
| `session.status_running` | Agent is actively processing. |
| `session.status_idle` | Agent finished; waiting for input. Has `stop_reason`. |
| `session.status_rescheduled` | Transient error; session retrying automatically. |
| `session.status_terminated` | Session ended due to unrecoverable error. |
| `session.deleted` | Session deleted. Terminates active stream; no further events. |
| `session.updated` | Session update changed at least one field. Includes only changed fields. |
| `session.error` | Error during processing. Has typed `error` object with `retry_status`. |
| `session.thread_created` | Multiagent thread created. Has `session_thread_id`, `agent_name`. |
| `session.thread_status_running` | Multiagent thread started activity. |
| `session.thread_status_idle` | Multiagent thread finished; awaiting input. Has `stop_reason`. |
| `session.thread_status_rescheduled` | Multiagent thread hit transient error; retrying. |
| `session.thread_status_terminated` | Multiagent thread archived or reached terminal error. |

### Span events (observability)

| Type | Description |
|---|---|
| `span.model_request_start` | Model inference call started. |
| `span.model_request_end` | Model inference call completed. Has `model_usage` with token counts. |
| `span.outcome_evaluation_start` | Outcome evaluation started. |
| `span.outcome_evaluation_ongoing` | Heartbeat during ongoing outcome evaluation. |
| `span.outcome_evaluation_end` | Outcome evaluation completed. |

---

## `session.status_idle` — Stop Reasons

When the session emits `session.status_idle`, it includes a `stop_reason` object:

| `stop_reason.type` | Meaning |
|---|---|
| `end_turn` | Agent finished naturally. |
| `requires_action` | Agent is waiting for you. `stop_reason.event_ids` lists blocking event IDs. Triggers for: custom tool calls, tool confirmation requests (permission policy). |

---

## Handling Custom Tool Calls

When `agent.custom_tool_use` fires followed by `session.status_idle` with `requires_action`:

```python
with client.beta.sessions.events.stream(session.id) as stream:
    for event in stream:
        if event.type == "session.status_idle" and (stop_reason := event.stop_reason):
            match stop_reason.type:
                case "requires_action":
                    for event_id in stop_reason.event_ids:
                        tool_event = events_by_id[event_id]
                        result = call_tool(tool_event.name, tool_event.input)
                        client.beta.sessions.events.send(
                            session.id,
                            events=[
                                {
                                    "type": "user.custom_tool_result",
                                    "custom_tool_use_id": event_id,
                                    "content": [{"type": "text", "text": result}],
                                },
                            ],
                        )
                case "end_turn":
                    break
```

---

## Handling Tool Confirmations (Permission Policy)

When a permission policy requires confirmation before a tool executes:

```python
with client.beta.sessions.events.stream(session.id) as stream:
    for event in stream:
        if event.type == "session.status_idle" and (stop_reason := event.stop_reason):
            match stop_reason.type:
                case "requires_action":
                    for event_id in stop_reason.event_ids:
                        client.beta.sessions.events.send(
                            session.id,
                            events=[
                                {
                                    "type": "user.tool_confirmation",
                                    "tool_use_id": event_id,
                                    "result": "allow",  # or "deny"
                                },
                            ],
                        )
                case "end_turn":
                    break
```

---

## Interrupting the Agent

```python
client.beta.sessions.events.send(
    session.id,
    events=[
        {"type": "user.interrupt"},
        {
            "type": "user.message",
            "content": [{"type": "text", "text": "Instead, focus on fixing the bug in line 42."}],
        },
    ],
)
```

---

## Updating System Prompt Mid-Session

```python
client.beta.sessions.events.send(
    session.id,
    events=[
        {
            "type": "system.message",
            "content": [
                {"type": "text", "text": "The user's current timezone is America/New_York."},
            ],
        },
    ],
)
```

Note: only supported on Claude Opus 4.8. Cannot be sent when `stop_reason: requires_action`.

---

## Resuming an Idle Session

Sessions are persistent. Conversation history preserved until explicitly deleted. Sandbox checkpointed (preserves filesystem, packages, files) for 30 days after last activity.

```python
# Resume by sending any new user.message event to the existing session.id
client.beta.sessions.events.send(
    session.id,
    events=[
        {
            "type": "user.message",
            "content": [{"type": "text", "text": "Now run the tests against the changes you made earlier."}],
        },
    ],
)
```

---

## Reconnecting to an Existing Session (avoiding missed events)

Open the stream first, list history to get seen IDs, then tail the live stream deduplicating by event ID:

```python
with client.beta.sessions.events.stream(session.id) as stream:
    history = client.beta.sessions.events.list(session.id)
    seen_event_ids = {past_event.id for past_event in history}

    for event in stream:
        if event.id in seen_event_ids:
            continue
        seen_event_ids.add(event.id)
        match event.type:
            case "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(block.text, end="")
            case "session.status_idle":
                break
```

---

## Token Usage Tracking

The session object has a `usage` field with cumulative statistics. Fetch after session goes idle:

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

- `input_tokens`: uncached input tokens across all model calls
- `output_tokens`: total output tokens across all model calls
- `cache_creation_input_tokens`: prompt cache writes
- `cache_read_input_tokens`: prompt cache reads (5-minute TTL)

---

## Multi-Agent: Coordinator Configuration

Set `multiagent` on an agent definition to make it a coordinator:

```python
coordinator = client.beta.agents.create(
    name="Engineering Lead",
    model="claude-opus-4-8",
    system="You coordinate engineering work. Delegate code review to the reviewer agent and test writing to the test agent.",
    tools=[{"type": "agent_toolset_20260401"}],
    multiagent={
        "type": "coordinator",
        "agents": [
            {"type": "agent", "id": reviewer_agent.id},
            {"type": "agent", "id": test_writer_agent.id},
        ],
    },
)
```

Roster entry forms:
- `{"type": "agent", "id": agent.id}` — latest version at coordinator creation time
- `{"type": "agent", "id": agent.id, "version": N}` — specific pinned version
- `{"type": "self"}` — coordinator can spawn copies of itself

Limits:
- Max 20 unique agents in `multiagent.agents`
- Max 25 concurrent threads per session
- Coordinator can only delegate one level deep (depth > 1 ignored)
- Coordinator can call multiple copies of a single agent (creating multiple threads)
- Roster is snapshotted at coordinator create/update time; does not auto-update when sub-agents change

### Session threads (multi-agent)

In multi-agent sessions, the **primary thread** (`/v1/sessions/:id/events/stream`) shows a condensed view of all activity. Sub-agent threads are separate event streams.

```python
# List all threads
for thread in client.beta.sessions.threads.list(session.id):
    print(f"[{thread.agent.name}] {thread.status}")

# Stream a specific thread
with client.beta.sessions.threads.events.stream(
    thread.id,
    session_id=session.id,
) as stream:
    for event in stream:
        if event.type == "agent.message":
            for block in event.content:
                if block.type == "text":
                    print(block.text, end="")
        elif event.type == "session.thread_status_idle":
            break

# Interrupt a specific thread
client.beta.sessions.events.send(
    session.id,
    events=[{"type": "user.interrupt", "session_thread_id": thread.id}],
)

# Archive a completed thread (frees up against 25-thread limit)
archived = client.beta.sessions.threads.archive(thread.id, session_id=session.id)
```

Multi-agent primary thread events:

| Type | Description |
|---|---|
| `session.thread_created` | Thread created. Has `session_thread_id`, `agent_name`. |
| `session.thread_status_running` | Thread started activity. |
| `session.thread_status_idle` | Thread awaiting input. Has `stop_reason`. |
| `session.thread_status_terminated` | Thread archived or terminal error. |
| `agent.thread_message_received` | Agent delivered result to coordinator. Has `from_session_thread_id`, `from_agent_name`, `content`. |
| `agent.thread_message_sent` | Coordinator sent follow-up to agent. Has `to_session_thread_id`, `to_agent_name`, `content`. |

---

## Rate Limits

| Operation | Limit |
|---|---|
| Create endpoints (agents, sessions, environments) | 300 requests/minute per org |
| Read endpoints (retrieve, list, stream) | 1,200 requests/minute per org |

Organization-level spend and usage-tier limits also apply.

---

## HTTP Endpoints (for reference)

| Operation | Method | Endpoint |
|---|---|---|
| Create agent | POST | `/v1/agents` |
| Update agent | PATCH | `/v1/agents/:id` |
| Archive agent | POST | `/v1/agents/:id/archive` |
| List agent versions | GET | `/v1/agents/:id/versions` |
| Create environment | POST | `/v1/environments` |
| Create session | POST | `/v1/sessions` |
| Send events | POST | `/v1/sessions/:id/events` |
| Stream events (SSE) | GET | `/v1/sessions/:id/events/stream` |
| List past events | GET | `/v1/sessions/:id/events` |
| List threads | GET | `/v1/sessions/:id/threads` |
| Archive thread | POST | `/v1/sessions/:id/threads/:tid/archive` |
| Stream thread events | GET | `/v1/sessions/:id/threads/:tid/stream` |
| List thread events | GET | `/v1/sessions/:id/threads/:tid/events` |

All endpoints require headers:
```
x-api-key: $ANTHROPIC_API_KEY
anthropic-version: 2023-06-01
anthropic-beta: managed-agents-2026-04-01
content-type: application/json
```

---

## Lifecycle Hooks / Middleware

**There are no lifecycle hooks or middleware in the Managed Agents API.** The model is event-driven:

- You can intercept before tool execution via `permission_policy: "always_ask"` on a tool config, which causes the session to pause at `requires_action` and wait for a `user.tool_confirmation` event.
- You can update the system prompt mid-session via `system.message` (Opus 4.8 only).
- You can interrupt the agent at any time via `user.interrupt`.
- You can define outcomes via `user.define_outcome`.

There is no pre/post-tool hook, no middleware chain, and no overridable agent loop.
