# Sessions: Tool Confirmations and Human-in-the-Loop

Source: https://platform.claude.com/docs/en/managed-agents/events-and-streaming  
Source: https://platform.claude.com/docs/en/managed-agents/reference#event-types  
Fetched: 2026-06-30

---

## Overview

Two distinct mechanisms require human-in-the-loop intervention and cause the session to pause with `stop_reason: requires_action`:

1. **Tool confirmations** — a permission policy requires your approval before a built-in agent tool or MCP tool executes
2. **Custom tool results** — the agent called a custom tool you defined, and you must execute it and provide the result

Both are signaled by the same `session.status_idle` event with `stop_reason.type == "requires_action"`.

---

## The `requires_action` Pause Mechanism

When any action requires your intervention:

1. The session emits the tool use event (`agent.tool_use`, `agent.mcp_tool_use`, or `agent.custom_tool_use`)
2. The session emits `session.status_idle` with:
   ```json
   {
     "type": "session.status_idle",
     "stop_reason": {
       "type": "requires_action",
       "event_ids": ["aevt_01abc...", "aevt_01def..."]
     }
   }
   ```
3. You respond to each event ID in `stop_reason.event_ids`
4. Once all blocking events are resolved, the session transitions back to `running`

Multiple tool calls can be blocked simultaneously; `event_ids` is an array. You can resolve them in any order; the session resumes only after all are resolved.

---

## Tool Confirmations

### When it applies

A **permission policy** on the agent's tools or MCP tools can require confirmation before execution. This is configured on the agent definition, not at session time.

### Flow

1. Agent decides to use a tool
2. `agent.tool_use` or `agent.mcp_tool_use` event is emitted
3. `session.status_idle` with `stop_reason: requires_action` and the tool use event ID(s)
4. You send `user.tool_confirmation` for each blocked event ID

### `user.tool_confirmation` event shape

```json
{
  "type": "user.tool_confirmation",
  "tool_use_id": "aevt_01abc...",
  "result": "allow"
}
```

Fields:

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `type` | string | `"user.tool_confirmation"` | Event type |
| `tool_use_id` | string | event ID from `stop_reason.event_ids` | References the blocked tool use event |
| `result` | enum | `"allow"` or `"deny"` | Whether to permit or block the tool execution |
| `deny_message` | string | optional | Explanation provided to the agent when denying |

### Allow example

```json
{
  "events": [
    {
      "type": "user.tool_confirmation",
      "tool_use_id": "aevt_01abc...",
      "result": "allow"
    }
  ]
}
```

### Deny example

```json
{
  "events": [
    {
      "type": "user.tool_confirmation",
      "tool_use_id": "aevt_01abc...",
      "result": "deny",
      "deny_message": "This file is outside the allowed working directory."
    }
  ]
}
```

### Full streaming confirmation pattern (Python)

```python
with client.beta.sessions.events.stream(session.id) as stream:
    for event in stream:
        if event.type == "session.status_idle" and (stop_reason := event.stop_reason):
            match stop_reason.type:
                case "requires_action":
                    for event_id in stop_reason.event_ids:
                        # Approve the pending tool call
                        client.beta.sessions.events.send(
                            session.id,
                            events=[
                                {
                                    "type": "user.tool_confirmation",
                                    "tool_use_id": event_id,
                                    "result": "allow",
                                },
                            ],
                        )
                case "end_turn":
                    break
```

### Full streaming confirmation pattern (TypeScript)

```typescript
const stream = await client.beta.sessions.events.stream(session.id);

for await (const event of stream) {
  if (event.type !== "session.status_idle") continue;
  if (event.stop_reason.type === "end_turn") break;
  if (event.stop_reason.type !== "requires_action") continue;

  for (const eventId of event.stop_reason.event_ids) {
    await client.beta.sessions.events.send(session.id, {
      events: [
        {
          type: "user.tool_confirmation",
          tool_use_id: eventId,
          result: "allow",
        },
      ],
    });
  }
}
```

### Full streaming confirmation pattern (curl)

```bash
exec {stream_fd}< <(curl --fail-with-body -sS -N \
  "https://api.anthropic.com/v1/sessions/$SESSION_ID/events/stream?beta=true" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: managed-agents-2026-04-01" \
  -H "content-type: application/json" \
  -H "accept: text/event-stream")

while IFS= read -r -u "$stream_fd" line; do
  [[ $line == data:* ]] || continue
  event_json="${line#data: }"
  stop_reason=$(jq -r 'select(.type == "session.status_idle") | .stop_reason.type // empty' <<<"$event_json")
  case "$stop_reason" in
    requires_action)
      while IFS= read -r event_id; do
        jq -n --arg id "$event_id" \
          '{events: [{type: "user.tool_confirmation", tool_use_id: $id, result: "allow"}]}' |
          curl --fail-with-body -sS \
            "https://api.anthropic.com/v1/sessions/$SESSION_ID/events?beta=true" \
            -H "x-api-key: $ANTHROPIC_API_KEY" \
            -H "anthropic-version: 2023-06-01" \
            -H "anthropic-beta: managed-agents-2026-04-01" \
            -H "content-type: application/json" \
            -d @-
      done < <(jq -r '.stop_reason.event_ids[]' <<<"$event_json")
      ;;
    end_turn)
      break
      ;;
  esac
done
exec {stream_fd}<&-
```

---

## Custom Tool Results

### When it applies

When you define **custom tools** on an agent, the agent can call them. Since these tools run in your system (not inside the sandbox), you must execute the tool and provide the result.

### Flow

1. Agent decides to call your custom tool
2. `agent.custom_tool_use` event emitted with tool `name` and `input`
3. `session.status_idle` with `stop_reason: requires_action` and the custom tool use event ID(s)
4. You execute the tool in your system
5. You send `user.custom_tool_result` for each blocked event ID

### `agent.custom_tool_use` event shape

```json
{
  "type": "agent.custom_tool_use",
  "id": "aevt_01abc...",
  "name": "my_custom_tool",
  "input": {
    "param1": "value1",
    "param2": "value2"
  },
  "processed_at": "2026-03-25T14:00:45Z"
}
```

### `user.custom_tool_result` event shape

```json
{
  "type": "user.custom_tool_result",
  "custom_tool_use_id": "aevt_01abc...",
  "content": [
    {"type": "text", "text": "result of tool execution"}
  ]
}
```

Fields:

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | `"user.custom_tool_result"` |
| `custom_tool_use_id` | string | Event ID from `stop_reason.event_ids` (the `agent.custom_tool_use` event) |
| `content` | array | Result content. Array of content blocks (e.g., `{"type": "text", "text": "..."}`) |

### Full pattern (Python)

```python
# events_by_id is a dict you build while consuming the stream
events_by_id = {}

with client.beta.sessions.events.stream(session.id) as stream:
    for event in stream:
        # Track events by ID for later lookup
        if hasattr(event, 'id'):
            events_by_id[event.id] = event

        if event.type == "session.status_idle" and (stop_reason := event.stop_reason):
            match stop_reason.type:
                case "requires_action":
                    for event_id in stop_reason.event_ids:
                        # Look up the custom tool use event and execute it
                        tool_event = events_by_id[event_id]
                        result = call_tool(tool_event.name, tool_event.input)

                        # Send the result back
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

### Full pattern (curl)

```bash
exec {stream_fd}< <(curl --fail-with-body -sS -N \
  "https://api.anthropic.com/v1/sessions/$SESSION_ID/events/stream?beta=true" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: managed-agents-2026-04-01" \
  -H "content-type: application/json" \
  -H "accept: text/event-stream")

while IFS= read -r -u "$stream_fd" line; do
  [[ $line == data:* ]] || continue
  event_json="${line#data: }"
  stop_reason=$(jq -r 'select(.type == "session.status_idle") | .stop_reason.type // empty' <<<"$event_json")
  case "$stop_reason" in
    requires_action)
      while IFS= read -r event_id; do
        # Execute the tool and send the result back
        result=$(call_tool "$event_id")
        jq -n --arg id "$event_id" --arg result "$result" \
          '{events: [{type: "user.custom_tool_result", custom_tool_use_id: $id, content: [{type: "text", text: $result}]}]}' |
          curl --fail-with-body -sS \
            "https://api.anthropic.com/v1/sessions/$SESSION_ID/events?beta=true" \
            -H "x-api-key: $ANTHROPIC_API_KEY" \
            -H "anthropic-version: 2023-06-01" \
            -H "anthropic-beta: managed-agents-2026-04-01" \
            -H "content-type: application/json" \
            -d @-
      done < <(jq -r '.stop_reason.event_ids[]' <<<"$event_json")
      ;;
    end_turn)
      break
      ;;
  esac
done
exec {stream_fd}<&-
```

---

## Outcome-Driven HITL: `user.define_outcome`

For outcome-oriented sessions, you define what "done" looks like and the agent iterates automatically. This is not a blocking HITL pause — the agent iterates without your intervention — but you can intervene:

- Send `user.message` events to an in-progress outcome session to direct the agent
- Send `user.interrupt` to pause the current outcome (marks `span.outcome_evaluation_end.result` as `interrupted`)
- After interruption, send a new `user.define_outcome` to start a new outcome chain

### `user.define_outcome` shape

```json
{
  "type": "user.define_outcome",
  "description": "Build a DCF model for Costco in .xlsx",
  "rubric": {
    "type": "text",
    "content": "# DCF Model Rubric\n## Revenue Projections\n- Uses historical data..."
  },
  "max_iterations": 5
}
```

Or with an uploaded file rubric:

```json
{
  "type": "user.define_outcome",
  "description": "Build a DCF model for Costco in .xlsx",
  "rubric": {
    "type": "file",
    "file_id": "file_01..."
  },
  "max_iterations": 5
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"user.define_outcome"` |
| `description` | string | yes | What the agent should produce |
| `rubric` | object | yes | Scoring criteria. Either `{type: "text", content: "..."}` or `{type: "file", file_id: "..."}` |
| `max_iterations` | int | no | Default 3, max 20. Number of evaluation cycles before stopping. |

Only one active outcome at a time. Chain outcomes by sending a new `user.define_outcome` after the terminal event of the previous outcome.

---

## Updating Session Tools Mid-Session

To change the permission policies (which control when confirmations are required) without creating a new agent version:

1. Session must be `idle` (interrupt if running)
2. Send a `POST /v1/sessions/$SESSION_ID` with updated `agent.tools` and/or `agent.mcp_servers`
3. The full replacement semantics apply: GET first, modify, then POST the full array

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

Updates are session-local and do not propagate to the underlying agent definition.
