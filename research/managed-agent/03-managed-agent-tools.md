# Claude Managed Agents — Tool Definition, Registration, Execution

Source: https://platform.claude.com/docs/en/managed-agents/tools  
Retrieved: 2026-06-30

---

## Overview

Tools are declared on the **agent definition**, not on the session. The agent's `tools` array is a list of tool descriptor objects. Three kinds exist:

1. **`agent_toolset_20260401`** — pre-built toolset (all built-in tools bundled)
2. **`custom`** — user-defined tools that your application executes
3. **`mcp_toolset`** — tools from a declared MCP server

---

## Pre-Built Agent Toolset

Enable all built-in tools in one declaration:

```python
agent = client.beta.agents.create(
    name="Coding Assistant",
    model="claude-opus-4-8",
    tools=[
        {"type": "agent_toolset_20260401"},
    ],
)
```

### Available Built-In Tools

| Tool | Name key | Description |
|---|---|---|
| Bash | `bash` | Execute bash commands in a shell session |
| Read | `read` | Read a file from the sandbox filesystem |
| Write | `write` | Write a file to the sandbox filesystem |
| Edit | `edit` | Perform string replacement in a file |
| Glob | `glob` | Fast file pattern matching using glob patterns |
| Grep | `grep` | Text search using regex patterns |
| Web fetch | `web_fetch` | Fetch content from a URL |
| Web search | `web_search` | Search the web for information |

All 8 tools are enabled by default when you include the toolset. Large tool outputs (>100,000 tokens) are automatically written to a file in the sandbox; the model receives a truncated preview with the path.

---

## Toolset Configuration Object

```json
{
  "type": "agent_toolset_20260401",
  "default_config": { ... },
  "configs": [ ... ]
}
```

| Field | Type | Description |
|---|---|---|
| `type` | `"agent_toolset_20260401"` | Required. Identifies the pre-built toolset. |
| `default_config` | object | Sets baseline for every tool in the set. |
| `configs` | array of `{name, enabled, permission_policy}` | Per-tool overrides. Name values are the Name keys from the table above. |

### Disabling Specific Tools

```json
{
  "type": "agent_toolset_20260401",
  "configs": [
    { "name": "web_fetch", "enabled": false },
    { "name": "web_search", "enabled": false }
  ]
}
```

Python:
```python
tools=[
    {
        "type": "agent_toolset_20260401",
        "configs": [
            {"name": "web_fetch", "enabled": False},
        ],
    },
]
```

### Enabling Only Specific Tools (allowlist approach)

Set `default_config.enabled: false` to disable all, then re-enable specific tools:

```json
{
  "type": "agent_toolset_20260401",
  "default_config": { "enabled": false },
  "configs": [
    { "name": "bash", "enabled": true },
    { "name": "read", "enabled": true },
    { "name": "write", "enabled": true }
  ]
}
```

---

## Permission Policies

Each tool config entry can have a `permission_policy` that controls whether calls are auto-approved or require confirmation:

```json
{
  "type": "agent_toolset_20260401",
  "configs": [
    {
      "name": "bash",
      "permission_policy": { "type": "always_ask" }
    }
  ]
}
```

When `always_ask`, the session pauses at `session.status_idle` with `stop_reason: requires_action`. Your app must send a `user.tool_confirmation` event with `tool_use_id` and `result: "allow"` or `"deny"` to resume.

The default policy (shown in the agent response `default_config`) is `always_allow`.

---

## Custom Tools

Custom tools are analogous to user-defined client tools in the Messages API. The model emits a structured request (`agent.custom_tool_use`); your code executes it and returns the result.

### Definition

```python
agent = client.beta.agents.create(
    name="Weather Agent",
    model="claude-opus-4-8",
    tools=[
        {"type": "agent_toolset_20260401"},
        {
            "type": "custom",
            "name": "get_weather",
            "description": "Get current weather for a location",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                },
                "required": ["location"],
            },
        },
    ],
)
```

TypeScript:
```typescript
const agent = await client.beta.agents.create({
  name: "Weather Agent",
  model: "claude-opus-4-8",
  tools: [
    { type: "agent_toolset_20260401" },
    {
      type: "custom",
      name: "get_weather",
      description: "Get current weather for a location",
      input_schema: {
        type: "object",
        properties: { location: { type: "string", description: "City name" } },
        required: ["location"]
      }
    }
  ]
});
```

curl:
```json
{
  "name": "Weather Agent",
  "model": "claude-opus-4-8",
  "tools": [
    { "type": "agent_toolset_20260401" },
    {
      "type": "custom",
      "name": "get_weather",
      "description": "Get current weather for a location",
      "input_schema": {
        "type": "object",
        "properties": {
          "location": {"type": "string", "description": "City name"}
        },
        "required": ["location"]
      }
    }
  ]
}
```

### Custom Tool Object Fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | `"custom"` | Yes | |
| `name` | string | Yes | Tool identifier the model uses |
| `description` | string | Yes | Tells the model what the tool does and when to use it |
| `input_schema` | JSON Schema object | Yes | Schema for the tool's input parameters |

### Custom Tool Execution Flow

1. Agent emits `agent.custom_tool_use` event with `.name` and `.input`.
2. Session pauses with `session.status_idle`, `stop_reason: requires_action`. `stop_reason.event_ids` contains blocking event IDs.
3. Your code executes the tool.
4. Send `user.custom_tool_result` for each event ID.
5. Session resumes to `running`.

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

### `user.custom_tool_result` Fields

| Field | Type | Notes |
|---|---|---|
| `type` | `"user.custom_tool_result"` | |
| `custom_tool_use_id` | string | The event ID from `stop_reason.event_ids` |
| `content` | array | Content blocks: `[{"type": "text", "text": "..."}]` |

---

## MCP Tools

MCP servers are declared in `mcp_servers` on the agent, then exposed via `mcp_toolset` in `tools`.

```python
agent = client.beta.agents.create(
    name="researcher",
    model="claude-haiku-4-5",
    mcp_servers=[
        {"type": "url", "name": "github", "url": "https://api.githubcopilot.com/mcp/"},
    ],
    tools=[{"type": "mcp_toolset", "mcp_server_name": "github"}],
)
```

The `mcp_toolset` tool type:

| Field | Type | Notes |
|---|---|---|
| `type` | `"mcp_toolset"` | |
| `mcp_server_name` | string | Must match a name in `mcp_servers` |

MCP server types supported: remote HTTP MCP servers (streamable HTTP transport) and private servers via MCP tunnels (limited research preview, requires access request).

MCP credentials (OAuth) are managed via Vaults — pass `vault_ids` at session creation:
```python
session = client.beta.sessions.create(
    agent=agent.id,
    environment_id=environment.id,
    vault_ids=[vault.id],
)
```

---

## Best Practices for Custom Tool Definitions

From the official docs:

1. **Write extremely detailed descriptions.** The most important factor in tool performance. Explain what the tool does, when to use it (and when not to), what each parameter means, and any caveats or limitations. Aim for 3–4 sentences per tool; more for complex tools.

2. **Consolidate related operations into fewer tools.** Instead of `create_pr`, `review_pr`, `merge_pr` — use a single `pr` tool with an `action` parameter. Fewer, more capable tools reduce selection ambiguity.

3. **Use meaningful namespacing in tool names.** Prefix with the resource: `db_query`, `storage_read`. This makes tool selection unambiguous as the library grows.

4. **Design tool responses to return only high-signal information.** Return semantic, stable identifiers (slugs, UUIDs) rather than opaque internal references. Include only fields Claude needs to determine its next step.

---

## Tool Execution Model Summary

| Tool kind | Who executes | How result flows back |
|---|---|---|
| Pre-built (`agent_toolset_20260401`) | Anthropic's sandbox (cloud) or your worker (self-hosted) | Automatic; agent receives `agent.tool_result` event |
| Custom | **Your application** | You send `user.custom_tool_result` event |
| MCP | MCP server (remote HTTP) | Automatic via MCP protocol; agent receives `agent.mcp_tool_result` event |

The model never executes anything on its own. For custom tools, it emits a structured request and waits. For pre-built and MCP tools with `always_allow` policy, execution happens automatically inside the sandbox.
