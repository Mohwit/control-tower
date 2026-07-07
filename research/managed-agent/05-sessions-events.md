# Sessions Events: SSE Event Shapes and Streaming Protocol

Source: https://platform.claude.com/docs/en/managed-agents/events-and-streaming  
Source: https://platform.claude.com/docs/en/managed-agents/reference#event-types  
Fetched: 2026-06-30

---

## Event Architecture

Communication with Claude Managed Agents is **event-based**. Two directions:

- **Inbound (you send)**: `user.*` events and `system.*` events
- **Outbound (you receive)**: `agent.*` events, `session.*` events, `span.*` events

Event type strings follow the `{domain}.{action}` naming convention.

Every event includes a `processed_at` timestamp (ISO 8601) indicating when the event was recorded server-side. If `processed_at` is `null`, the event has been queued and will be handled after preceding events finish processing.

Every event has a stable `id` field usable for deduplication when reconnecting.

---

## Complete Event Type Catalog

### User Events (you send)

| Type | Description |
|------|-------------|
| `user.message` | A user message with text content. Starts or continues agent work. |
| `user.interrupt` | Stop the agent mid-execution. |
| `user.custom_tool_result` | Response to a custom tool call from the agent. |
| `user.tool_confirmation` | Approve or deny an agent or MCP tool call when a permission policy requires confirmation. |
| `user.define_outcome` | Define an outcome (target + rubric) for the agent to work toward. |
| `user.tool_result` | For `self_hosted` environments only: provide `agent_toolset` results. (SDK/CLI do this automatically.) |

### Agent Events (you receive)

| Type | Description |
|------|-------------|
| `agent.message` | Agent response containing text content blocks. |
| `agent.thinking` | Agent thinking content, emitted separately from messages. |
| `agent.tool_use` | Agent invokes a pre-built agent tool (bash, file operations, etc.). |
| `agent.tool_result` | Result of a pre-built agent tool execution. |
| `agent.mcp_tool_use` | Agent invokes an MCP server tool. |
| `agent.mcp_tool_result` | Result of an MCP tool execution. |
| `agent.custom_tool_use` | Agent invokes one of your custom tools. Must respond with `user.custom_tool_result`. |
| `agent.thread_context_compacted` | Conversation history was compacted to fit the context window. |
| `agent.thread_message_received` | In a multiagent session, an agent delivered its result to the coordinator. |
| `agent.thread_message_sent` | In a multiagent session, the coordinator sent a follow-up to another agent. |

### Session Events (you receive)

| Type | Description |
|------|-------------|
| `session.status_running` | Agent is actively processing. |
| `session.status_idle` | Agent finished its current task and is waiting for input. Includes `stop_reason`. |
| `session.status_rescheduled` | A transient error occurred; session is retrying automatically. |
| `session.status_terminated` | Session ended due to an unrecoverable error. |
| `session.deleted` | Session was deleted. Terminates any active event stream; no further events are emitted. |
| `session.updated` | A session update changed at least one field. Includes only the changed fields. Updates apply on the next turn. |
| `session.error` | An error occurred during processing. Includes a typed `error` object with a `retry_status`. |
| `session.thread_created` | A multiagent thread was created. |
| `session.thread_status_running` | A multiagent thread started activity. |
| `session.thread_status_idle` | A multiagent thread finished its turn and is awaiting input. Includes `stop_reason`. |
| `session.thread_status_rescheduled` | A multiagent thread hit a transient error and is retrying automatically. |
| `session.thread_status_terminated` | A multiagent thread was archived or reached a terminal error. |

### Span Events (you receive — observability)

Span events wrap activity for timing and usage tracking.

| Type | Description |
|------|-------------|
| `span.model_request_start` | A model inference call has started. |
| `span.model_request_end` | A model inference call has completed. Includes `model_usage` with token counts. |
| `span.outcome_evaluation_start` | Outcome evaluation has started. Only emitted for outcome-oriented sessions. |
| `span.outcome_evaluation_ongoing` | Heartbeat during an ongoing outcome evaluation. |
| `span.outcome_evaluation_end` | Outcome evaluation has completed. |

### System Events (you send)

| Type | Description |
|------|-------------|
| `system.message` | Update the agent's system prompt between turns. Only supported on Claude Opus 4.8. |

---

## HTTP Endpoints and Transport

### Sending events

```
POST /v1/sessions/$SESSION_ID/events
Content-Type: application/json

{
  "events": [
    {
      "type": "user.message",
      "content": [{"type": "text", "text": "..."}]
    }
  ]
}
```

Multiple events can be sent in a single request (e.g., `user.interrupt` + `user.message` together).

### Streaming events (SSE)

```
GET /v1/sessions/$SESSION_ID/events/stream
Accept: text/event-stream
```

Returns a text/event-stream (SSE) stream. Each SSE data line is a JSON event object:

```
data: {"type": "session.status_running", "id": "...", "processed_at": "..."}

data: {"type": "agent.message", "id": "...", "content": [...], "processed_at": "..."}

data: {"type": "session.status_idle", "id": "...", "stop_reason": {"type": "end_turn"}, "processed_at": "..."}
```

**Critical ordering rule**: Open the stream BEFORE sending events to avoid a race condition. Only events emitted after the stream is opened are delivered on the live stream.

### Listing past events (history)

```
GET /v1/sessions/$SESSION_ID/events
```

Returns paginated event history. Filter by type:

```
GET /v1/sessions/$SESSION_ID/events?types[]=agent.tool_use&types[]=agent.tool_result
```

---

## Key Event Shapes

### `user.message` (send)

```json
{
  "type": "user.message",
  "content": [
    {"type": "text", "text": "Analyze the performance of the sort function in utils.py"}
  ]
}
```

### `user.interrupt` (send)

```json
{"type": "user.interrupt"}
```

Can be combined with `user.message` in the same request to redirect mid-execution.

### `system.message` (send)

```json
{
  "type": "system.message",
  "content": [
    {"type": "text", "text": "The user's current timezone is America/New_York."}
  ]
}
```

- `content` accepts 1–1000 text items.
- Cannot be sent while the session is idle with `stop_reason: requires_action`.
- Only supported on Claude Opus 4.8. Sending to a non-supporting model returns a `model_does_not_support_mid_conversation_system` validation error.

### `agent.message` (receive)

```json
{
  "type": "agent.message",
  "id": "aevt_01...",
  "content": [
    {"type": "text", "text": "Here are the files in the working directory: ..."}
  ],
  "processed_at": "2026-03-25T14:00:30Z"
}
```

### `session.status_idle` (receive)

The `stop_reason` field indicates why the agent stopped:

```json
{
  "type": "session.status_idle",
  "id": "sevt_01...",
  "stop_reason": {
    "type": "end_turn"
  },
  "processed_at": "2026-03-25T14:01:00Z"
}
```

Stop reason types:
- `end_turn` — agent finished naturally
- `requires_action` — session paused, waiting for your response (tool confirmation or custom tool result). Includes `event_ids` array:

```json
{
  "type": "session.status_idle",
  "id": "sevt_01...",
  "stop_reason": {
    "type": "requires_action",
    "event_ids": ["aevt_01abc...", "aevt_01def..."]
  },
  "processed_at": "2026-03-25T14:00:50Z"
}
```

### `session.error` (receive)

```json
{
  "type": "session.error",
  "id": "sevt_01...",
  "error": {
    "message": "...",
    "retry_status": "..."
  },
  "processed_at": "2026-03-25T14:00:55Z"
}
```

The `error` object has a `retry_status` field (exact enum values not fully documented, but distinguishes retryable from fatal errors).

### `span.model_request_end` (receive)

```json
{
  "type": "span.model_request_end",
  "id": "sevt_01...",
  "model_usage": {
    "input_tokens": 1200,
    "output_tokens": 450,
    "cache_creation_input_tokens": 600,
    "cache_read_input_tokens": 4000
  },
  "processed_at": "2026-03-25T14:00:40Z"
}
```

### `user.define_outcome` (send) — echoed back on receipt

```json
{
  "type": "user.define_outcome",
  "description": "Build a DCF model for Costco in .xlsx",
  "rubric": {"type": "file", "file_id": "file_01..."},
  "max_iterations": 5
}
```

or inline rubric:

```json
{
  "type": "user.define_outcome",
  "description": "Build a DCF model for Costco in .xlsx",
  "rubric": {"type": "text", "content": "# DCF Model Rubric\n..."},
  "max_iterations": 5
}
```

`max_iterations`: optional, default 3, max 20.

Echoed back with `processed_at` and `outcome_id` fields added.

### `span.outcome_evaluation_start` (receive)

```json
{
  "type": "span.outcome_evaluation_start",
  "id": "sevt_01def...",
  "outcome_id": "outc_01a...",
  "iteration": 0,
  "processed_at": "2026-03-25T14:01:45Z"
}
```

`iteration` is 0-indexed: `0` = first evaluation.

### `span.outcome_evaluation_ongoing` (receive)

```json
{
  "type": "span.outcome_evaluation_ongoing",
  "id": "sevt_01ghi...",
  "outcome_id": "outc_01a...",
  "processed_at": "2026-03-25T14:02:10Z"
}
```

Heartbeat while grader runs. Grader's internal reasoning is opaque.

### `span.outcome_evaluation_end` (receive)

```json
{
  "type": "span.outcome_evaluation_end",
  "id": "sevt_01jkl...",
  "outcome_evaluation_start_id": "sevt_01def...",
  "outcome_id": "outc_01a...",
  "result": "satisfied",
  "explanation": "All 12 criteria met: revenue projections use 5 years of historical data...",
  "iteration": 0,
  "usage": {
    "input_tokens": 2400,
    "output_tokens": 350,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 1800
  },
  "processed_at": "2026-03-25T14:03:00Z"
}
```

`result` values:

| Value | Next action |
|-------|-------------|
| `satisfied` | Session transitions to `idle`. |
| `needs_revision` | Agent starts a new iteration cycle. |
| `max_iterations_reached` | No further cycles. Agent may run one final revision before transitioning to `idle`. |
| `failed` | Session transitions to `idle`. Returned when rubric fundamentally doesn't match task (e.g., description and rubric contradict). |
| `interrupted` | Only emitted if `outcome_evaluation_start` already fired before the interrupt. |

---

## Streaming Workflow

### Basic pattern

```python
# 1. Open stream FIRST
with client.beta.sessions.events.stream(session.id) as stream:
    # 2. Send the work
    client.beta.sessions.events.send(
        session.id,
        events=[{"type": "user.message", "content": [{"type": "text", "text": "..."}]}]
    )
    # 3. Consume events
    for event in stream:
        match event.type:
            case "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(block.text, end="")
            case "session.status_idle":
                break
            case "session.error":
                print(f"[Error: {event.error.message}]")
                break
```

### Reconnection pattern

When reconnecting to a session without missing events:

1. Open a new stream (starts buffering immediately)
2. List the full event history to seed a set of seen event IDs
3. Tail the live stream, skipping events already in the history set

```python
with client.beta.sessions.events.stream(session.id) as stream:
    # Stream is open and buffering
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

### Interrupt and redirect pattern

```json
POST /v1/sessions/$SESSION_ID/events
{
  "events": [
    {"type": "user.interrupt"},
    {
      "type": "user.message",
      "content": [{"type": "text", "text": "Instead, focus on fixing the bug in line 42."}]
    }
  ]
}
```

Both events can be sent atomically in a single request.

---

## Console Observability

The Anthropic Console provides:

- **Session list**: All sessions with status, creation time, and model
- **Tracing view**: Chronological view of events (content, timestamps, token usage) within a session. Accessible only to Developers and Admins.
- **Tool execution**: Details of each tool call and its result
