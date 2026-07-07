# Claude Managed Agents — Overview, Agent Definition, Key Concepts

Source: https://platform.claude.com/docs/en/managed-agents/overview  
Source: https://platform.claude.com/docs/en/managed-agents/quickstart  
Source: https://platform.claude.com/docs/en/managed-agents/agent-setup  
Retrieved: 2026-06-30  
Beta header required: `anthropic-beta: managed-agents-2026-04-01`

---

## What is Claude Managed Agents?

Claude Managed Agents is a **pre-built, configurable agent harness** that runs in managed (or self-hosted) infrastructure. It handles the agent loop, tool execution, sandbox provisioning, and conversation history so you do not need to build those yourself.

Contrast with the Messages API:

| | Messages API | Claude Managed Agents |
|---|---|---|
| What it is | Direct model prompting access | Pre-built configurable agent harness |
| Best for | Custom agent loops, fine-grained control | Long-running tasks, async work |

Best-fit workloads: long-running execution (minutes or hours), secure cloud sandboxes, self-hosted execution for compliance, stateful sessions with persistent filesystem and history.

---

## Four Core Concepts

| Concept | Description |
|---|---|
| **Agent** | The model, system prompt, tools, MCP servers, and skills |
| **Environment** | Where sessions run: Anthropic-managed cloud sandbox or self-hosted |
| **Session** | A running agent instance within an environment; performs a task; generates outputs |
| **Events** | Messages exchanged between your app and the agent (user turns, tool results, status updates) |

---

## How It Works (End-to-End Flow)

1. **Create an agent** — define model, system prompt, tools, MCP servers, skills once; get back a persistent `agent.id`.
2. **Create an environment** — configure cloud or self-hosted sandbox.
3. **Start a session** — provide `agent_id` + `environment_id`; get a `session.id`.
4. **Send events and stream responses** — send `user.message` events; Claude autonomously executes tools; receive SSE stream of events.
5. **Steer or interrupt** — send additional `user.message` or `user.interrupt` events mid-execution.

---

## Agent Definition

Agents are **config-based** (not class-based or decorator-based). You call `client.beta.agents.create(...)` with a dict/object of parameters. The agent is a versioned, persistent resource identified by `agent.id`.

### Agent Configuration Fields

| Field | Required | Type | Description |
|---|---|---|---|
| `name` | Yes | string | Human-readable name |
| `model` | Yes | string or `{id, speed}` object | Claude model ID. Accepts `"claude-opus-4-8"` or `{"id": "claude-opus-4-8", "speed": "fast"}`. All Claude 4.5+ models supported. |
| `system` | No | string or null | System prompt. Distinct from user messages. Can be cleared with `null`. |
| `tools` | No | array | Combines pre-built toolset, MCP tools, custom tools. See doc 03. |
| `mcp_servers` | No | array | MCP servers providing standardized third-party capabilities. |
| `skills` | No | array | Domain-specific context with progressive disclosure. |
| `multiagent` | No | object | Coordinator declaration listing agents this agent can delegate to. |
| `description` | No | string or null | Description of what the agent does. |
| `metadata` | No | object | Arbitrary key-value pairs for tracking. |

### Agent Response Shape

```json
{
  "id": "agent_01HqR2k7vXbZ9mNpL3wYcT8f",
  "type": "agent",
  "name": "Coding Assistant",
  "model": {
    "id": "claude-opus-4-8",
    "speed": "standard"
  },
  "system": "You are a helpful coding agent.",
  "description": null,
  "tools": [
    {
      "type": "agent_toolset_20260401",
      "default_config": {
        "permission_policy": { "type": "always_allow" }
      }
    }
  ],
  "skills": [],
  "mcp_servers": [],
  "metadata": {},
  "version": 1,
  "created_at": "2026-04-03T18:24:10.412Z",
  "updated_at": "2026-04-03T18:24:10.412Z",
  "archived_at": null
}
```

---

## Creating an Agent (Python example)

```python
from anthropic import Anthropic

client = Anthropic()

agent = client.beta.agents.create(
    name="Coding Assistant",
    model="claude-opus-4-8",
    system="You are a helpful coding assistant. Write clean, well-documented code.",
    tools=[
        {"type": "agent_toolset_20260401"},
    ],
)

print(f"Agent ID: {agent.id}, version: {agent.version}")
```

TypeScript:
```typescript
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();

const agent = await client.beta.agents.create({
  name: "Coding Assistant",
  model: "claude-opus-4-8",
  system: "You are a helpful coding assistant. Write clean, well-documented code.",
  tools: [
    { type: "agent_toolset_20260401" },
  ],
});

console.log(`Agent ID: ${agent.id}, version: ${agent.version}`);
```

---

## Updating an Agent

Updating generates a new version when configuration changes. The `version` field is **required** and must match current version (optimistic concurrency). A version mismatch returns 409.

```python
updated_agent = client.beta.agents.update(
    agent.id,
    version=agent.version,
    system="You are a helpful coding agent. Always write tests.",
)
print(f"New version: {updated_agent.version}")
```

### Update semantics

- **Omitted fields are preserved.**
- **Scalar fields** (`model`, `system`, `name`, `description`) — replaced with new value. `system` and `description` can be cleared with `null`. `model` and `name` cannot be cleared.
- **Array fields** (`tools`, `mcp_servers`, `skills`) — fully replaced. Pass `null` or `[]` to clear.
- **`multiagent`** — replaced as a whole. Pass `null` to clear.
- **Metadata** — merged at key level. Set key to `null` to delete it.
- **No-op detection** — if update produces no change, no new version is created; existing version is returned.
- **Coordinator rosters** — not auto-updated when a referenced sub-agent changes; must update coordinator explicitly.

---

## Agent Lifecycle

| Operation | Behavior |
|---|---|
| Update | Generates new version when config changes |
| List versions | Returns full version history (paginated) |
| Archive | Makes agent read-only; cannot be undone; existing sessions continue; new sessions cannot reference it |

### List agent versions (Python)

```python
for version in client.beta.agents.versions.list(agent.id):
    print(f"Version {version.version}: {version.updated_at.isoformat()}")
```

### Archive an agent (Python)

```python
archived = client.beta.agents.archive(agent.id)
print(f"Archived at: {archived.archived_at.isoformat()}")
```

---

## Creating an Environment

```python
environment = client.beta.environments.create(
    name="quickstart-env",
    config={
        "type": "cloud",
        "networking": {"type": "unrestricted"},
    },
)
print(f"Environment ID: {environment.id}")
```

Environment types:
- `cloud` — Anthropic-managed sandbox
- `self_hosted` — your own infrastructure

---

## Creating a Session

```python
session = client.beta.sessions.create(
    agent=agent.id,
    environment_id=environment.id,
    title="Quickstart session",
)
print(f"Session ID: {session.id}")
```

### Session create parameters

| Parameter | Type | Description |
|---|---|---|
| `agent` | string or `{type, id, version}` object | Agent ID string (latest version) or pinned version object |
| `environment_id` | string | Environment to run in |
| `title` | string (optional) | Human label for the session |
| `vault_ids` | string[] (optional) | Vault IDs for MCP OAuth credentials |

### Pinning a specific agent version

```python
pinned_session = client.beta.sessions.create(
    agent={"type": "agent", "id": agent.id, "version": 1},
    environment_id=environment.id,
)
```

---

## Full Quickstart Flow

```python
from anthropic import Anthropic

client = Anthropic()

# Step 1: Create agent
agent = client.beta.agents.create(
    name="Coding Assistant",
    model="claude-opus-4-8",
    system="You are a helpful coding assistant. Write clean, well-documented code.",
    tools=[{"type": "agent_toolset_20260401"}],
)

# Step 2: Create environment
environment = client.beta.environments.create(
    name="quickstart-env",
    config={"type": "cloud", "networking": {"type": "unrestricted"}},
)

# Step 3: Create session
session = client.beta.sessions.create(
    agent=agent.id,
    environment_id=environment.id,
    title="Quickstart session",
)

# Step 4: Open stream, send message, process events
with client.beta.sessions.events.stream(session.id) as stream:
    client.beta.sessions.events.send(
        session.id,
        events=[
            {
                "type": "user.message",
                "content": [
                    {
                        "type": "text",
                        "text": "Create a Python script that generates the first 20 Fibonacci numbers and saves them to fibonacci.txt",
                    },
                ],
            },
        ],
    )

    for event in stream:
        match event.type:
            case "agent.message":
                for block in event.content:
                    print(block.text, end="")
            case "agent.tool_use":
                print(f"\n[Using tool: {event.name}]")
            case "session.status_idle":
                print("\n\nAgent finished.")
                break
```

---

## What Happens When You Send a Message

1. Sandbox is provisioned (per environment config)
2. Claude runs the agent loop; determines which tools to use
3. Tools execute inside the sandbox (file writes, bash, web fetch, etc.)
4. Events stream in real-time as the agent works
5. Agent emits `session.status_idle` when finished

---

## Beta Status and Constraints

- Beta header `managed-agents-2026-04-01` required on all requests (SDKs set it automatically).
- Not eligible for Zero Data Retention (ZDR) or HIPAA BAA — sessions are stateful.
- Checkpoints (sandbox state) preserved for 30 days after last activity.
- You can delete sessions and files via API at any time.
- MCP tunnels and dreaming features require separate access request.

---

## CLI (`ant`) Commands

```bash
# Install
brew install anthropics/tap/ant

# Agents
ant beta:agents create --name "..." --model '{id: claude-opus-4-8}' --tool '{type: agent_toolset_20260401}'
ant beta:agents update --agent-id "$AGENT_ID" --version "$VERSION" --system "..."
ant beta:agents archive --agent-id "$AGENT_ID"
ant beta:agents:versions list --agent-id "$AGENT_ID"

# Environments
ant beta:environments create --name "..." --config '{type: cloud, networking: {type: unrestricted}}'

# Sessions
ant beta:sessions create --agent "$AGENT_ID" --environment-id "$ENV_ID"
ant beta:sessions:events send --session-id "$SESSION_ID"
ant beta:sessions:events list --session-id "$SESSION_ID"
```

---

## Supported Models

All Claude 4.5-family and later models. Examples seen in docs:
- `claude-opus-4-8`
- `claude-opus-4-7`
- `claude-haiku-4-5`

Fast mode: pass model as object `{"id": "claude-opus-4-8", "speed": "fast"}`.
