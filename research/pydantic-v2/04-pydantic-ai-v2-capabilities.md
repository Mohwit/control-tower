# Q5 — pydantic-ai v2 Capabilities Module

Research target: GitHub `pydantic/pydantic-ai` main branch + https://pydantic.dev/docs/ai
Date: 2026-06-30

> **Important framing note.** The package under research has no separate "v2" PyPI distribution name — it is still `pydantic-ai` / `pydantic_ai_slim`. The `main` branch HAS substantially evolved its public architecture around a new `capabilities` subpackage (the "capabilities + hooks" middleware model). All findings below are from the live `main` branch source.

---

## 1. Does `pydantic_ai.capabilities` exist? — YES (with proof)

**YES.** It exists as a full subpackage, not a single module.

Proof (GitHub tree `https://api.github.com/repos/pydantic/pydantic-ai/git/trees/main?recursive=1`), files under `pydantic_ai_slim/pydantic_ai/capabilities/`:

```
capabilities/AGENTS.md
capabilities/__init__.py
capabilities/_deferred_capability_loader.py
capabilities/_dynamic.py
capabilities/_ordering.py
capabilities/_pending_messages.py
capabilities/_tool_search.py
capabilities/abstract.py
capabilities/capability.py
capabilities/combined.py
capabilities/deferred_tool_handler.py
capabilities/hooks.py
capabilities/image_generation.py
capabilities/include_return_schemas.py
capabilities/instrumentation.py
capabilities/mcp.py
capabilities/native_or_local.py
capabilities/native_tool.py
capabilities/prefix_tools.py
capabilities/prepare_tools.py
capabilities/process_event_stream.py
capabilities/process_history.py
capabilities/reinject_system_prompt.py
capabilities/set_tool_metadata.py
capabilities/thinking.py
capabilities/thread_executor.py
capabilities/toolset.py
capabilities/web_fetch.py
capabilities/web_search.py
capabilities/wrapper.py
capabilities/x_search.py
```

> Note: the original research prompt suggested checking `pydantic_ai_slim/pydantic_ai/capabilities.py` (a flat module). That path does **not** exist; it is a **package** (`capabilities/`) instead. There is also a private `_deferred_capabilities.py` at top level (distinct file).

---

## 2. Full contents of the capabilities package

### 2.1 Public exports (`capabilities/__init__.py`, `__all__`)

Source: `pydantic_ai_slim/pydantic_ai/capabilities/__init__.py` (145 lines).

Concrete built-in capability classes exported:

| Class | Module | Purpose |
|---|---|---|
| `NativeTool` | `native_tool.py` | Wrap a provider-native tool |
| `NativeOrLocalTool` | `native_or_local.py` | Native tool with local fallback |
| `ImageGeneration` | `image_generation.py` | Image-generation capability |
| `Instrumentation` | `instrumentation.py` | OTel / logfire instrumentation |
| `IncludeToolReturnSchemas` | `include_return_schemas.py` | Add tool return schemas |
| `MCP` | `mcp.py` | Model Context Protocol server integration |
| `PrefixTools` | `prefix_tools.py` | Prefix all tool names |
| `PrepareTools` / `PrepareOutputTools` | `prepare_tools.py` | Per-run tool-definition mutation |
| `ProcessEventStream` | `process_event_stream.py` | Transform the streamed event stream |
| `ProcessHistory` | `process_history.py` | Transform message history before requests |
| `ReinjectSystemPrompt` | `reinject_system_prompt.py` | Re-inject system prompt |
| `SetToolMetadata` | `set_tool_metadata.py` | Attach metadata to tools |
| `Thinking` | `thinking.py` | Enable/configure reasoning/thinking |
| `ThreadExecutor` | `thread_executor.py` | Sync-tool thread pool execution |
| `ToolSearch` | `_tool_search.py` | On-demand tool discovery (re-exported) |
| `Toolset` | `toolset.py` | Register a toolset as a capability |
| `WebFetch` | `web_fetch.py` | Web-fetch native/local capability |
| `WebSearch` | `web_search.py` | Web-search native/local capability |
| `XSearch` | `x_search.py` | X/Twitter search capability |
| `Capability` | `capability.py` | Convenience bundle (no subclassing) |
| `CombinedCapability` | `combined.py` | Compose multiple capabilities |
| `WrapperCapability` | `wrapper.py` | Wrap another capability |
| `DynamicCapability` | `_dynamic.py` | Wraps a `CapabilityFunc` (run-context → capability) |
| `HandleDeferredToolCalls` | `deferred_tool_handler.py` | Handle deferred tool calls |
| `Hooks` | `hooks.py` | Decorator-based lifecycle hooks (no subclassing) |

Abstract base + supporting types exported: `AbstractCapability`, `AgentCapability` (TypeAlias), `AgentNode`, `CapabilityDescription`, `CapabilityFunc`, `CapabilityOrdering`, `CapabilityPosition`, `CapabilityRef`, `NodeResult`, `RawOutput`, `RawToolArgs`, `ValidatedToolArgs`, all the `Wrap*Handler` type aliases, `HookTimeoutError`, `OutputContext`, `CAPABILITY_TYPES` (registry dict), plus tool-search types `ToolSearchFunc`, `ToolSearchLocalStrategy`, `ToolSearchNativeStrategy`, `ToolSearchStrategy`.

`AgentCapability` type alias (the item type accepted by `Agent(capabilities=[...])` and `agent.run(capabilities=[...])`):
```python
AgentCapability: TypeAlias = AbstractCapability[AgentDepsT] | CapabilityFunc[AgentDepsT]
```
(A plain function returning a capability is auto-wrapped in `DynamicCapability`.)

### 2.2 `CAPABILITY_TYPES` registry

A `dict[str, type[AbstractCapability[Any]]]` mapping serialization name → class, built from every capability whose `get_serialization_name()` is non-None. Used for YAML/JSON agent-spec construction (`Agent.from_spec`). Note in source: `OpenAICompaction` and `AnthropicCompaction` have serialization names but are excluded here due to circular imports — register via `custom_capability_types` in `AgentSpec`.

### 2.3 `AbstractCapability` — the base class

Source: `pydantic_ai_slim/pydantic_ai/capabilities/abstract.py` (914 lines).

```python
@dataclass(init=False)
class AbstractCapability(ABC, Generic[AgentDepsT]):
    id: str | None = None              # unique-within-run identifier; required if defer_loading
    description: str | None = None
    defer_loading: bool = False        # hide tools/instructions until model loads via `load_capability` tool
```

**Lifecycle / static-config methods (called at construction or run setup):**

| Method | Signature (return) | Role |
|---|---|---|
| `apply(visitor)` | `-> None` | visit all leaf capabilities |
| `get_serialization_name()` (classmethod) | `-> str \| None` | spec name; `None` opts out |
| `from_spec(*args, **kwargs)` (classmethod) | `-> AbstractCapability[Any]` | spec construction |
| `get_ordering()` | `-> CapabilityOrdering \| None` | declare position / wraps / requires |
| `for_run(ctx)` (async) | `-> AbstractCapability[AgentDepsT]` | per-run instance (state isolation) |
| `get_instructions()` | `-> AgentInstructions \| None` | contribute instructions |
| `get_description()` | `-> CapabilityDescription \| None` | catalog description for deferred load |
| `get_model_settings()` | `-> AgentModelSettings \| None` | contribute/merge model settings |
| `get_toolset()` | `-> AgentToolset \| None` | contribute a toolset |
| `get_native_tools()` | `-> Sequence[AgentNativeTool]` | contribute native tools |
| `get_wrapper_toolset(toolset)` | `-> AbstractToolset \| None` | wrap the assembled toolset (per-run) |
| `prepare_tools(...)` (async) | mutate tool defs | |
| `prepare_output_tools(...)` (async) | mutate output tool defs | |
| `prefix_tools(prefix)` | `-> PrefixTools` | helper |

**Middleware/hook methods (fire during a run)** — a full onion of `before_*`, `after_*`, `wrap_*`, and `on_*_error` hooks across five lifecycle scopes:

- **Run**: `before_run`, `after_run`, `wrap_run`, `on_run_error`
- **Node (graph step)**: `before_node_run`, `after_node_run`, `wrap_node_run`, `on_node_run_error`
- **Run event stream**: `wrap_run_event_stream`
- **Model request**: `before_model_request`, `after_model_request`, `wrap_model_request`, `on_model_request_error`
- **Tool validate**: `before_tool_validate`, `after_tool_validate`, `wrap_tool_validate`, `on_tool_validate_error`
- **Tool execute**: `before_tool_execute`, `after_tool_execute`, `wrap_tool_execute`, `on_tool_execute_error`
- **Output validate**: `before_output_validate`, `after_output_validate`, `wrap_output_validate`, `on_output_validate_error`
- **Output process**: `before_output_process`, `after_output_process`, `wrap_output_process`, `on_output_process_error`
- **Deferred tools**: `handle_deferred_tool_calls`

All hooks are `async`. The `wrap_*` handler types (`WrapRunHandler`, `WrapModelRequestHandler`, `WrapToolExecuteHandler`, `WrapOutputValidateHandler`, etc.) are exported type aliases — a capability calls `await handler(...)` to continue the chain (classic middleware "next()" pattern).

**Ordering — `CapabilityOrdering` dataclass:**
```python
@dataclass
class CapabilityOrdering:
    position: CapabilityPosition | None = None      # 'outermost' | 'innermost' | None
    wraps: Sequence[CapabilityRef] = ()             # this is OUTSIDE these (by type or instance)
    wrapped_by: Sequence[CapabilityRef] = ()        # this is INSIDE these
    requires: Sequence[type[AbstractCapability[Any]]] = ()  # must be present, no ordering
```
First capability in the list = outermost layer. `CombinedCapability` topologically sorts children to satisfy constraints, with user list order as tiebreaker.

### 2.4 `Capability` convenience class

Source: `capabilities/capability.py` (325 lines). Bundles instructions + tools + toolsets + description **without subclassing** `AbstractCapability`.

Constructor:
```python
Capability(
    *, instructions=None, toolsets=None, tools=(),
    id=None, description=None, defer_loading=False,
)
```
Provides `@cap.tool`, `@cap.tool_plain`, and `@cap.instructions` decorators mirroring `Agent.tool` / `Agent.tool_plain` / `Agent.instructions`. `get_serialization_name()` returns `None` (not spec-serializable, since it holds functions/callables).

---

## 3. Harness-layer abstractions ABOVE `Agent`

The capabilities package IS the primary harness/middleware layer. Beyond it, the package ships several harness-grade layers:

| Layer | Path | What it provides |
|---|---|---|
| **Capabilities** | `capabilities/` | Composable middleware (instructions, tools, settings, lifecycle hooks). The recommended extension point per `capabilities/AGENTS.md`: "Prefer a capability over a new `Agent` constructor kwarg when behavior contributes instructions, settings, tools, native tools, wrappers, lifecycle hooks, or event/history processing." |
| **Toolsets** | `toolsets/` | `AbstractToolset` + combinators: `CombinedToolset`, `FilteredToolset`, `PrefixedToolset`, `RenamedToolset`, `PreparedToolset`, `ApprovalRequiredToolset`, `ExternalToolset`, `FunctionToolset`, dynamic + deferred-loading toolsets. |
| **UI / harness adapters** | `ui/` | `ui/ag_ui/` (AG-UI protocol) and `ui/vercel_ai/` (Vercel AI SDK) adapters with `_adapter.py`, `_event_stream.py`, request/response types — i.e. front-end harness integration. Also `ui/_web/` (a built-in web app/API). |
| **Durable execution** | `durable_exec/` | Orchestration wrappers: `durable_exec/temporal/`, `durable_exec/dbos/`, `durable_exec/prefect/` — each wraps `Agent` for durable workflow engines (`_agent.py`, `_model.py`, `_mcp.py`, etc.). |
| **Direct API** | `direct.py` | Lower-level direct model-request helpers (below the Agent). |
| **Agent abstraction** | `agent/` | `agent/abstract.py` (`AbstractAgent`), `agent/wrapper.py` (`WrapperAgent`), `agent/spec.py` (declarative `AgentSpec` + `Agent.from_spec` / `Agent.to_spec`). |
| **Common tools** | `common_tools/` | DuckDuckGo, Tavily, Exa, web-fetch, image-gen, X-search prebuilt tools. |

So: there is a rich harness layer. The intended "compose behavior on top of Agent" mechanism is **capabilities** (middleware), with **toolsets** for tool composition, **ui adapters** for front-end harnesses, and **durable_exec** for workflow orchestration.

---

## 4. `ext` / `contrib` namespaces

- **`pydantic_ai.ext` — EXISTS.** Contains only `ext/__init__.py` and `ext/langchain.py` (LangChain tool interop). Proof: tree shows `pydantic_ai_slim/pydantic_ai/ext/__init__.py` and `.../ext/langchain.py`.
- **`pydantic_ai.contrib` — DOES NOT EXIST.** No path matching `pydantic_ai/contrib*` in the tree.

(Third-party LLM/provider integrations live in `providers/` and `profiles/`, not in a `contrib` namespace.)

---

## 5. What SDK authors must build themselves

Given the capabilities + hooks middleware system, most cross-cutting concerns now have a built-in seam. SDK authors typically build:

- **Custom capabilities** by subclassing `AbstractCapability` (or using `Hooks` for decorator-based hooks, or `Capability` to bundle tools/instructions) for memory, guardrails, cost budgeting, approval workflows, retry policy, logging — anything that wraps run/model/tool/output lifecycle. The docs explicitly frame capabilities as the home for "memory systems, guardrails, cost tracking, approval workflows."
- **Custom toolsets** by subclassing `AbstractToolset` for dynamic/remote/filtered tool sourcing.
- **Custom output processors / output validators** (see Q8) for domain validation beyond Pydantic.
- **Custom `Model` implementations** for unsupported providers.
- **Spec serialization hooks** (`get_serialization_name` / `from_spec`) only if their capability must round-trip through YAML/JSON `AgentSpec`.

What they do NOT need to build (already provided): the middleware chain itself, ordering/topological sort, deferred (on-demand) capability/tool loading via the `load_capability` and tool-search tools, instrumentation/OTel, MCP integration, thinking, web search/fetch, image generation, message-history processing, event-stream processing, durable execution wrappers, and UI/front-end adapters.

---

## Sources
- GitHub tree: `https://api.github.com/repos/pydantic/pydantic-ai/git/trees/main?recursive=1`
- `pydantic_ai_slim/pydantic_ai/capabilities/__init__.py`
- `pydantic_ai_slim/pydantic_ai/capabilities/abstract.py`
- `pydantic_ai_slim/pydantic_ai/capabilities/capability.py`
- `pydantic_ai_slim/pydantic_ai/capabilities/AGENTS.md`
- Docs: https://pydantic.dev/docs/ai/core-concepts/capabilities/
