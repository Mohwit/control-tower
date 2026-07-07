# Sessions: Error States, Rescheduling, and Terminated

Source: https://platform.claude.com/docs/en/managed-agents/events-and-streaming  
Source: https://platform.claude.com/docs/en/managed-agents/session-operations  
Source: https://platform.claude.com/docs/en/managed-agents/reference#event-types  
Fetched: 2026-06-30

---

## Error-Related Session Statuses

| Status | Description |
|--------|-------------|
| `rescheduling` | A transient error occurred; the session is retrying automatically. Surfaced as `session.status_rescheduled` event. |
| `terminated` | Session ended due to an unrecoverable error. Surfaced as `session.status_terminated` event. |

These are the only two error states in the session lifecycle. The distinction matters: `rescheduling` is automatic and temporary; `terminated` is final.

---

## Error Events

### `session.error`

Emitted when an error occurs during processing. This is an observability event that fires before or alongside the status transition events.

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

Fields on the `error` object:

| Field | Type | Description |
|-------|------|-------------|
| `message` | string | Human-readable error description |
| `retry_status` | string | Indicates whether the error is retryable. Distinguishes transient (rescheduling) from fatal (terminated) errors. |

The exact enum values for `retry_status` are not fully documented in the public docs, but they map to the session status: a retryable error leads to `rescheduling`; a non-retryable error leads to `terminated`.

### `session.status_rescheduled`

Emitted when a transient error occurred and the session is retrying automatically. No action required.

```json
{
  "type": "session.status_rescheduled",
  "id": "sevt_01...",
  "processed_at": "2026-03-25T14:01:00Z"
}
```

The session status becomes `rescheduling` after this event. The session will transition back to `running` or `idle` on recovery without any user intervention.

### `session.status_terminated`

Emitted when the session has ended due to an unrecoverable error.

```json
{
  "type": "session.status_terminated",
  "id": "sevt_01...",
  "processed_at": "2026-03-25T14:01:05Z"
}
```

The session status becomes `terminated` after this event. The session is permanently ended; no further events will be emitted for it. A new session must be created to continue.

### Multiagent thread equivalents

For multiagent sessions, threads have parallel error events:

| Thread event | Equivalent to |
|--------------|---------------|
| `session.thread_status_rescheduled` | `session.status_rescheduled` (for a thread) |
| `session.thread_status_terminated` | `session.thread_status_terminated` (archived or terminal error for a thread) |

---

## Error Detection in Streaming

When consuming the SSE stream, handle `session.error` to catch errors mid-execution:

```python
with client.beta.sessions.events.stream(session.id) as stream:
    for event in stream:
        match event.type:
            case "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(block.text, end="")
            case "session.status_idle":
                break
            case "session.error":
                error_message = event.error.message if event.error else "unknown"
                print(f"\n[Error: {error_message}]")
                break
```

```typescript
for await (const event of stream) {
  if (event.type === "agent.message") {
    for (const block of event.content) {
      if (block.type === "text") process.stdout.write(block.text);
    }
  } else if (event.type === "session.status_idle") {
    break;
  } else if (event.type === "session.error") {
    console.log(`\n[Error: ${event.error?.message ?? "unknown"}]`);
    break;
  }
}
```

In curl/bash:

```bash
case $(jq -r '.type' <<<"$event_json") in
  agent.message)
    jq -j '.content[] | select(.type == "text") | .text' <<<"$event_json"
    ;;
  session.status_idle)
    break
    ;;
  session.error)
    printf '\n[Error: %s]\n' "$(jq -r '.error.message // "unknown"' <<<"$event_json")"
    break
    ;;
esac
```

---

## Debugging Tips (from official docs)

- **Check session events**: Session errors are conveyed through the `session.error` event
- **Review tool results**: Tool execution failures often explain unexpected agent behavior
- **Track token usage**: Monitor token consumption to optimize prompts and reduce costs
- **Use system prompts**: Add logging instructions to the system prompt to make the agent explain its reasoning

---

## Operations on Error/Terminated Sessions

### Archiving a session

- Cannot archive a `running` session. Send `user.interrupt` first.
- Archiving prevents new events from being sent while preserving history.
- A `terminated` session can be archived (no interrupt needed since it is not running).

### Deleting a session

- Cannot delete a `running` session. Send `user.interrupt` first.
- A `terminated` session can be deleted.
- Deletion permanently removes the session record, events, and associated sandbox.
- Independent resources (files, memory stores, vaults, skills, environments, agents) are NOT affected by deletion.

---

## Outcome Evaluation Errors

The `span.outcome_evaluation_end` event includes a `result` field that can indicate failure modes:

```json
{
  "type": "span.outcome_evaluation_end",
  "result": "failed",
  "explanation": "The rubric criteria fundamentally contradict the task description.",
  "iteration": 0,
  ...
}
```

| Result | Meaning |
|--------|---------|
| `satisfied` | Success; session transitions to `idle`. |
| `needs_revision` | Not yet done; agent starts a new iteration. |
| `max_iterations_reached` | Ran out of iterations; agent may do a final revision then goes `idle`. |
| `failed` | Rubric/description mismatch (e.g., contradictory criteria); session goes `idle`. Not a system error — the task definition is the problem. |
| `interrupted` | A `user.interrupt` was sent after `span.outcome_evaluation_start` already fired. |

`failed` and `max_iterations_reached` are soft failures: the session becomes `idle` and you can continue conversationally or define a new outcome.

---

## Validation Errors

Some event-send operations can return validation errors synchronously (before any session state change):

- `model_does_not_support_mid_conversation_system`: returned when sending a `system.message` event to a session whose model is not Claude Opus 4.8.

These appear as HTTP error responses, not as `session.error` events on the stream.

---

## HTTP Rate Limit Errors

Rate limits apply per organization:

| Operation | Limit |
|-----------|-------|
| Create endpoints (agents, sessions, environments) | 300 requests/minute |
| Read endpoints (retrieve, list, stream) | 1,200 requests/minute |

Organization-level spend limits and usage-tier rate limits also apply (standard Anthropic API rate limiting).

When a rate limit is exceeded, you receive a standard HTTP 429 response.

---

## State Transition Summary

```
CREATE SESSION
      |
      v
   [idle] <----- user.message / user.tool_confirmation / user.custom_tool_result
      |
      v
  [running] -----> session.status_running
      |
      +---(transient error)---> [rescheduling] ---(auto retry)---> [running]
      |
      +---(requires action)---> [idle] with stop_reason: requires_action
      |                              |
      |                              +--- user.tool_confirmation ---> [running]
      |                              +--- user.custom_tool_result ---> [running]
      |
      +---(end_turn)---> [idle] with stop_reason: end_turn
      |
      +---(fatal error)---> [terminated] (final)
      |
      +---(user.interrupt)---> [idle] with stop_reason: interrupted (resumes on next user.message)

[idle] --(archive)--> [archived] (history preserved, no new events)
[idle/terminated/archived] --(delete)--> [deleted] (permanent, all data removed)
```
