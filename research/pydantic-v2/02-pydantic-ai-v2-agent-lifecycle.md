# Pydantic AI v2 — Agent Class & Run Lifecycle (Q3)

> Research scope: Q3 — the `Agent` class, its run methods, and the internal run lifecycle.
> Sources: pydantic-ai `main` branch (the v2 line; the distributed package is `pydantic-ai-slim`)
> and the official docs.
> All citations reference exact file paths / line numbers in the source fetched on 2026-06-30
> and the live documentation.

## Source map (important structural note)

In v2 the old single `pydantic_ai/agent.py` has been replaced by an **`agent/` package**:

| Symbol | Location |
| --- | --- |
| `Agent` (concrete class) | `pydantic_ai_slim/pydantic_ai/agent/__init__.py` |
| `AbstractAgent` (base with the run methods) | `pydantic_ai_slim/pydantic_ai/agent/abstract.py` |
| `WrapperAgent` | `pydantic_ai_slim/pydantic_ai/agent/wrapper.py` |
| `AgentRun`, `AgentRunResult`, `AgentRunResultEvent` | `pydantic_ai_slim/pydantic_ai/run.py` |
| Graph nodes (`UserPromptNode`, `ModelRequestNode`, `CallToolsNode`), `GraphAgentState`, `GraphAgentDeps`, `EndStrategy` | `pydantic_ai_slim/pydantic_ai/_agent_graph.py` |
| `StreamedRunResult`, `AgentStream`, `StreamedRunResultSync`, `FinalResult` | `pydantic_ai_slim/pydantic_ai/result.py` |
| All exception classes | `pydantic_ai_slim/pydantic_ai/exceptions.py` |
| `RunContext` | `pydantic_ai_slim/pydantic_ai/_run_context.py` |

> NOTE: the request mentioned `pydantic-ai-slim/pydantic_ai/agent.py` and `_run.py`. Neither exists on
> current `main` — `agent.py` → `agent/` package (HTTP 404 on the flat file), and there is no `_run.py`
> (the file is `run.py`). The `run`/`run_sync`/`run_stream`/`iter` methods live in `agent/abstract.py`,
> not in the concrete `Agent` class (which only overrides `iter`).
> Docs URL `https://ai.pydantic.dev/agents/` now 301-redirects to
> `https://pydantic.dev/docs/ai/core-concepts/agent/`.

---

## 1. `Agent.__init__` — full signature

Source: `agent/__init__.py` lines 322–343.

```python
def __init__(
    self,
    model: models.Model | models.KnownModelName | str | None = None,
    *,
    output_type: OutputSpec[OutputDataT] = str,
    instructions: AgentInstructions[AgentDepsT] = None,
    system_prompt: str | Sequence[str] = (),
    deps_type: type[AgentDepsT] = object,
    name: str | None = None,
    description: TemplateStr[AgentDepsT] | str | None = None,
    model_settings: AgentModelSettings[AgentDepsT] | None = None,
    retries: int | AgentRetries | None = None,
    validation_context: Any | Callable[[RunContext[AgentDepsT]], Any] = None,
    tools: Sequence[Tool[AgentDepsT] | ToolFuncEither[AgentDepsT, ...]] = (),
    toolsets: Sequence[AgentToolset[AgentDepsT]] | None = None,
    defer_model_check: bool = False,
    end_strategy: EndStrategy = 'graceful',
    metadata: AgentMetadata[AgentDepsT] | None = None,
    tool_timeout: float | None = None,
    max_concurrency: _concurrency.AnyConcurrencyLimit = None,
    capabilities: Sequence[AgentCapability[AgentDepsT]] | None = None,
) -> None:
```

Parameter reference (from the docstring, lines 344–410):

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `model` | `Model \| KnownModelName \| str \| None` | `None` | Default model; if `None` must be passed at run time. |
| `output_type` | `OutputSpec[OutputDataT]` | `str` | Output type used to validate model output. |
| `instructions` | `AgentInstructions[AgentDepsT]` | `None` | Static instructions (str/`TemplateStr`/callable/sequence). |
| `system_prompt` | `str \| Sequence[str]` | `()` | Static system prompt(s). |
| `deps_type` | `type[AgentDepsT]` | `object` | Type for dependency injection (typing only). |
| `name` | `str \| None` | `None` | Agent name (inferred from call frame on first run if `None`). |
| `description` | `TemplateStr \| str \| None` | `None` | Human-readable description, attached to run span as `gen_ai.agent.description`. |
| `model_settings` | `AgentModelSettings \| None` | `None` | Static `ModelSettings` dict **or** a callable `RunContext -> ModelSettings` (called before each request). |
| `retries` | `int \| AgentRetries \| None` | `None` | Per-category retry budgets (`{'tools': int, 'output': int}`); int sets both. Defaults to 1 for both. |
| `validation_context` | `Any \| Callable[[RunContext], Any]` | `None` | Pydantic validation context for tool args & outputs. |
| `tools` | `Sequence[Tool \| ToolFuncEither]` | `()` | Tools to register. |
| `toolsets` | `Sequence[AgentToolset] \| None` | `None` | Toolsets / MCP servers / toolset functions. |
| `defer_model_check` | `bool` | `False` | If `True`, defer resolving a named model until first run. |
| `end_strategy` | `EndStrategy` | `'graceful'` | How to handle tool calls requested alongside a final output. **Default changed from `'early'`→`'graceful'` in v2.** |
| `metadata` | `AgentMetadata \| None` | `None` | dict or `RunContext`-callable; resolved at run start and recomputed after success. |
| `tool_timeout` | `float \| None` | `None` | Default per-tool execution timeout (sec); exceeding → retry prompt counting toward the retry limit. |
| `max_concurrency` | `AnyConcurrencyLimit` | `None` | int / `ConcurrencyLimit` / `ConcurrencyLimiter` / `None`; caps concurrent `run()`/`iter()` calls (waits when full). |
| `capabilities` | `Sequence[AgentCapability] \| None` | `None` | v2 capability plugins (see §5). Custom ones subclass `AbstractCapability`. |

**Not constructor parameters (assigned afterward):**
- `instrument` — exposed as a **property + setter** (`agent/__init__.py:811-817`), set via `agent.instrument = ...`, the classmethod `Agent.instrument_all(...)` (line 806), or by adding an `Instrumentation` capability. There is **no** `instrument=` kwarg on `__init__` in this version.
- `end_strategy` is also a public mutable attribute (`self.end_strategy`, line 418).

`AgentRetries` (a `TypedDict(total=False)` with `tools` and `output` keys) is defined in `agent/abstract.py:93`.

---

## 2. Run methods — full signatures

All defined in `agent/abstract.py` (the base `AbstractAgent`). The shared per-run keyword set is
nearly identical across `run` / `run_sync` / `run_stream` / `iter`.

### 2.1 `run` (async) — `agent/abstract.py:289`

```python
async def run(
    self,
    user_prompt: str | Sequence[_messages.UserContent] | None = None,
    *,
    output_type: OutputSpec[RunOutputDataT] | None = None,
    message_history: Sequence[_messages.ModelMessage] | None = None,
    deferred_tool_results: DeferredToolResults | None = None,
    conversation_id: str | None = None,
    model: models.Model | models.KnownModelName | str | None = None,
    instructions: _instructions.AgentInstructions[AgentDepsT] = None,
    deps: AgentDepsT = None,
    model_settings: AgentModelSettings[AgentDepsT] | None = None,
    usage_limits: _usage.UsageLimits | None = None,
    usage: _usage.RunUsage | None = None,
    metadata: AgentMetadata[AgentDepsT] | None = None,
    retries: int | AgentRetries | None = None,
    infer_name: bool = True,
    toolsets: Sequence[AbstractToolset[AgentDepsT]] | None = None,
    event_stream_handler: EventStreamHandler[AgentDepsT] | None = None,
    capabilities: Sequence[AgentCapability[AgentDepsT]] | None = None,
    spec: dict[str, Any] | AgentSpec | None = None,
) -> AgentRunResult[Any]:
```
Implementation (lines 359–429): builds the graph via `self.iter(...)`, then drives it node-by-node
(`agent_run.next(node)` / `_run_node_with_hooks`) until an `End` node, returning `agent_run.result`.

### 2.2 `run_sync` — `agent/abstract.py:479`

Same parameter list and return type (`AgentRunResult[Any]`) as `run`. It is a convenience wrapper around
`self.run` via `loop.run_until_complete(...)` (docstring line 503) — cannot be used inside async code
or with an active event loop.

### 2.3 `run_stream` (async context manager) — `agent/abstract.py:623`

```python
async def run_stream(
    self,
    user_prompt: str | Sequence[_messages.UserContent] | None = None,
    *,
    output_type: OutputSpec[RunOutputDataT] | None = None,
    message_history: Sequence[_messages.ModelMessage] | None = None,
    deferred_tool_results: DeferredToolResults | None = None,
    conversation_id: str | None = None,
    model: models.Model | models.KnownModelName | str | None = None,
    instructions: _instructions.AgentInstructions[AgentDepsT] = None,
    deps: AgentDepsT = None,
    model_settings: AgentModelSettings[AgentDepsT] | None = None,
    usage_limits: _usage.UsageLimits | None = None,
    usage: _usage.RunUsage | None = None,
    metadata: AgentMetadata[AgentDepsT] | None = None,
    retries: int | AgentRetries | None = None,
    infer_name: bool = True,
    toolsets: Sequence[AbstractToolset[AgentDepsT]] | None = None,
    event_stream_handler: EventStreamHandler[AgentDepsT] | None = None,
    capabilities: Sequence[AgentCapability[AgentDepsT]] | None = None,
    spec: dict[str, Any] | AgentSpec | None = None,
) -> AsyncGenerator[result.StreamedRunResult[AgentDepsT, Any]]:
```
Used as `async with agent.run_stream(...) as response:`. **Semantics (docstring lines 645–655):** it
runs the graph only until the model produces output matching `output_type`, yields a
`StreamedRunResult`, and **stops there — it does NOT execute tool calls the model made after that
"final" output**. To always run to completion while streaming, use `run()` with an
`event_stream_handler`, or `iter()`.

### 2.4 `run_stream_sync` — `agent/abstract.py:875`

Synchronous wrapper around `run_stream` (`loop.run_until_complete`), returning `StreamedRunResultSync`
(defined in `result.py:723`). Same per-run kwargs.

### 2.5 `run_stream_events` — `agent/abstract.py:1029`

```python
def run_stream_events(
    self, ...same per-run kwargs...
) -> AbstractAsyncContextManager[
        AsyncIterator[_messages.AgentStreamEvent | AgentRunResultEvent[Any]]
     ]:
```
Async context manager yielding a stream of `AgentStreamEvent` items, terminated by a single
`AgentRunResultEvent` that carries the final `AgentRunResult` (docstring lines 1107–1164). Unlike
`run_stream`, it processes the **complete** graph execution.

### 2.6 `iter` (async context manager) — abstract at `agent/abstract.py:1278`, concrete impl at `agent/__init__.py:935`

```python
async def iter(
    self,
    user_prompt: str | Sequence[_messages.UserContent] | None = None,
    *,
    output_type: OutputSpec[RunOutputDataT] | None = None,
    message_history: Sequence[_messages.ModelMessage] | None = None,
    deferred_tool_results: DeferredToolResults | None = None,
    conversation_id: str | None = None,
    model: models.Model | models.KnownModelName | str | None = None,
    instructions: _instructions.AgentInstructions[AgentDepsT] = None,
    deps: AgentDepsT = None,
    model_settings: AgentModelSettings[AgentDepsT] | None = None,
    usage_limits: _usage.UsageLimits | None = None,
    usage: _usage.RunUsage | None = None,
    metadata: AgentMetadata[AgentDepsT] | None = None,
    retries: int | AgentRetries | None = None,
    infer_name: bool = True,
    toolsets: Sequence[AbstractToolset[AgentDepsT]] | None = None,
    capabilities: Sequence[AgentCapability[AgentDepsT]] | None = None,
    spec: dict[str, Any] | AgentSpec | None = None,
) -> AsyncGenerator[AgentRun[AgentDepsT, Any]]:
```
Note: `iter` has **no `event_stream_handler` parameter** (that is `run`/`run_sync`/`run_stream` only).
It yields an `AgentRun` you can `async for node in agent_run`.

### 2.7 Common per-run parameter notes (from `run` docstring, lines 328–355)

- `output_type` — per-run override; only valid if the agent has no output validators.
- `conversation_id` — pass `'new'` to start fresh; otherwise falls back to the latest
  `conversation_id` on `message_history` or a generated UUID7.
- `deferred_tool_results` — results for deferred tool calls in the history.
- `usage` — seed usage (resume a conversation / agent-as-tool).
- `retries` (per run) — overrides only the **output** budget; **tool retries cannot be overridden per
  run**.
- `spec` — optional `AgentSpec`/dict applied additively for the run.

---

## 3. Internal run lifecycle (graph phases, in order)

The run is a `pydantic_graph` state machine. Nodes (`_agent_graph.py`):

```
UserPromptNode  →  ModelRequestNode  →  CallToolsNode  →  End(FinalResult)
(_agent_graph.py:264)  (:597)             (:1077)            (loop or finish)
                          ▲                   │
                          └───────────────────┘  (loop back when more tool calls / retries)
```

Ordered phases:

1. **`UserPromptNode.run`** (`_agent_graph.py:286`) — builds the initial `ModelRequest` from the user
   prompt, system prompts, and instructions; resolves dependencies; sets `run_id`/`conversation_id`.
   Returns a `ModelRequestNode` (or `CallToolsNode` on the resume-without-prompt path).
2. **`ModelRequestNode.run`** (`_agent_graph.py:609`) → `_make_request` (`:809`) /
   `_prepare_request` (`:872`):
   - Appends the request to `message_history`; **increments `ctx.state.run_step += 1`** (`:887`).
   - Resolves toolsets/tools for the step (`tool_manager.for_run_step`, `:903`) and instructions.
   - **`usage_limits.check_before_request(usage)`** (`:991`); optionally counts tokens first when
     `count_tokens_before_request` (`:984`).
   - Calls the model through the capability chain
     `root_capability.wrap_model_request(...)` (`:847`), with `before_model_request` /
     `after_model_request` / `on_model_request_error` hooks (see §5).
   - Accumulates usage (`ctx.state.usage.incr(response.usage)`, `:1053`) and
     **`usage_limits.check_tokens(usage)`** (`:1055`).
   - Returns a `CallToolsNode` wrapping the `ModelResponse`.
3. **`CallToolsNode.run`** (`_agent_graph.py:1098`) → `_run_stream` (`:1124`):
   - Inspects the `ModelResponse` parts. Handles empty / thinking-only responses, content-filter,
     and `finish_reason == 'length'` (→ `UnexpectedModelBehavior` / `IncompleteToolCall`).
   - Processes tool calls and output tools per the **`end_strategy`** (see §4); emits
     `HandleResponseEvent`s during execution.
   - If a final output is produced → `_handle_final_result(...)` returns `End(FinalResult(...))`
     (`:1409`). Otherwise builds a new `ModelRequestNode` (e.g. for tool returns / retries) and
     loops back to phase 2.
4. **`End(FinalResult[...])`** — terminal. `FinalResult` carries the validated output.
   `AgentRunResult` (`run.py:474`) wraps it; `result.output` is the validated output.

Per-run state lives in **`GraphAgentState`** (`_agent_graph.py:138`): `message_history`,
`usage: RunUsage`, `output_retries_used`, **`run_step`**, `run_id`, `conversation_id`, `metadata`,
`pending_messages`, etc.
Per-run config lives in **`GraphAgentDeps`** (`:199`): `model`, `usage_limits`, `max_output_retries`,
`end_strategy`, `output_schema`, `output_validators`, `root_capability`, `tool_manager`, `tracer`,
`instrumentation_settings`, etc.

---

## 4. Tool execution loop — iteration limits & retry behavior

### Iteration / step limits
- **`run_step`** (`GraphAgentState.run_step`) increments once per model request (`_agent_graph.py:887`).
- There is **no `max_steps` / `max_iterations` parameter**. The loop is bounded by **`UsageLimits`**
  passed via `usage_limits=`:
  - `request_limit` — caps number of model requests (the primary loop guard against infinite
    tool loops). Enforced by `usage_limits.check_before_request` (`:991`).
  - token limits (e.g. `output_tokens_limit`, total token caps) — `check_tokens` (`:1055`).
  - `tool_calls_limit` — caps successful tool invocations (per docs).
  - Exceeding any → **`UsageLimitExceeded`**.

### Retry behavior
- Agent-level `retries: int | AgentRetries` → `_max_tool_retries`, `_max_output_retries`
  (`agent/__init__.py:453-454`). Default **1** for each (`_normalize_agent_retries`, default=1).
- **Output-validation retries**: tracked by `GraphAgentState.output_retries_used`; each `ModelRetry`
  from an output validator / `ToolRetryError` calls `consume_output_retry(max_output_retries)`
  (`_agent_graph.py:178`). Exceeding the budget → **`UnexpectedModelBehavior("Exceeded maximum output
  retries (...)")`** (`:194`). This `output` budget is overridable per run via `run(retries=...)`.
- **Per-tool retries**: enforced separately by `ToolManager._check_max_retries`; default per-tool
  `max_retries` comes from the `tools` budget (not per-run overridable). `ToolOutput(max_retries=...)`
  overrides per output tool.
- **`ModelRetry`** (raised in a tool / output validator / capability hook) sends a retry prompt back to
  the model rather than failing the run.
- **`tool_timeout`**: a tool exceeding its timeout is treated as a failure → retry prompt that counts
  toward the retry limit.

### `end_strategy` (`EndStrategy = Literal['early','graceful','exhaustive']`, `_agent_graph.py:70`)
Governs tool calls requested *alongside* an output tool:
- **`'early'`** — output tools run in emitted order; run ends at the first success; function tools are
  skipped. If all output tools fail, function tools run so the model can correct.
- **`'graceful'` (default in v2)** — tools run in emitted order; function tools preceding an output
  tool complete first; first successful output wins (later output tools skipped). A function tool's
  `ModelRetry` **suppresses** the output result and surfaces the retry instead.
- **`'exhaustive'`** — every tool runs (parallel by default); first valid output by emission order
  wins. `sequential=True` on a tool makes it a non-overlapping barrier.

---

## 5. Hooks and callbacks

### 5.1 `event_stream_handler` (per-run callback)
Type alias (`agent/abstract.py:67`):
```python
EventStreamHandler: TypeAlias = Callable[
    [RunContext[AgentDepsT], AsyncIterable[_messages.AgentStreamEvent]], Awaitable[None]
]
```
- Accepted as a kwarg on `run`, `run_sync`, `run_stream` (NOT on `iter`), or set agent-wide via the
  `event_stream_handler` property (durable-execution subclasses).
- Receives `(ctx, async-iterable-of-AgentStreamEvent)`. When set, `run()` streams each model-request /
  call-tools node and forwards events to the handler (`agent/abstract.py:394-416`).
- Related alias `EventStreamProcessor` (`:72`) is used by the `ProcessEventStream` capability to
  modify/drop/add events.

### 5.2 Instrumentation (observability hook)
- `Agent.instrument` property + setter (`agent/__init__.py:811-817`); `Agent.instrument_all(...)`
  classmethod (`:806`) sets a global default.
- Value type: `InstrumentationSettings | bool | None`. Resolved per run into
  `GraphAgentDeps.instrumentation_settings` and an OTel `tracer`.
- Recommended setup (docs): `logfire.configure(); logfire.instrument_pydantic_ai()`. Emits OpenTelemetry
  spans/events (messages, tool calls, token usage, latency, errors). The run span carries
  `gen_ai.agent.description` when a `description` is set.

### 5.3 Capability hook system (the v2 extensibility surface)
The richest hook mechanism is **`AbstractCapability`** (`capabilities/abstract.py:144`), passed via the
`capabilities=` constructor arg / per-run `capabilities=`. Built-ins live in
`pydantic_ai/capabilities/` (e.g. `instrumentation.py`, `mcp.py`, `process_event_stream.py`,
`process_history.py`, `web_search.py`, `prepare_tools.py`, `thinking.py`, etc.).

Full lifecycle hook set (`capabilities/abstract.py`), every phase has `before_/after_/wrap_/on_*_error`:

| Phase | Hooks (line) |
| --- | --- |
| Run | `before_run` (363), `after_run` (369), `wrap_run` (378), `on_run_error` (399) |
| Node | `before_node_run` (423), `after_node_run` (432), `wrap_node_run` (442), `on_node_run_error` (473) |
| Event stream | `wrap_run_event_stream` (496) |
| Model request | `before_model_request` (514), `after_model_request` (522), `wrap_model_request` (537), `on_model_request_error` (552) |
| Tool validate | `before_tool_validate` (577), `after_tool_validate` (592), `wrap_tool_validate` (607), `on_tool_validate_error` (619) |
| Tool execute | `before_tool_execute` (644), `after_tool_execute` (659), `wrap_tool_execute` (675), `on_tool_execute_error` (687) |
| Output validate | `before_output_validate` (719), `after_output_validate` (744), `wrap_output_validate` (768), `on_output_validate_error` (784) |
| Output process | `before_output_process` (804), `after_output_process` (823), `wrap_output_process` (837), `on_output_process_error` (856) |

Plus contribution getters: `get_instructions`, `get_description`, `get_model_settings`, `get_toolset`,
`get_native_tools`, `get_wrapper_toolset`, `get_ordering`. The graph invokes
`root_capability.{before,after}_model_request`, `wrap_model_request`, `on_model_request_error`,
`wrap_run_event_stream` directly (confirmed in `_agent_graph.py`).

### 5.4 Decorator-registered callbacks on the `Agent`
- `@agent.tool` / `@agent.tool_plain` (`agent/__init__.py:2040`, `:2176`) — register tools.
- `@agent.system_prompt` (`:1907`) / `@agent.instructions` (`:1817`) — dynamic prompts.
- `@agent.output_validator` (`:1983`) — output validation callback (may raise `ModelRetry`).
- `@agent.toolset` (`:2311`) — register a toolset function.

---

## 6. Streaming — `StreamedRunResult` & `AgentStream`

### 6.1 `StreamedRunResult` (`result.py:390`)
```python
@dataclass(init=False)
class StreamedRunResult(Generic[AgentDepsT, OutputDataT]):
    """Result of a streamed run that returns structured data via a tool call."""

    _all_messages: list[_messages.ModelMessage]
    _new_message_index: int
    _stream_response: AgentStream[AgentDepsT, OutputDataT] | None = None
    _on_complete: Callable[[], Awaitable[None]] | None = None
    _run_result: AgentRunResult[OutputDataT] | None = None

    is_complete: bool = field(default=False, init=False)
    """True once stream_output / stream_text / stream_response / get_output completes."""

    def __init__(  # (two overloads; runtime signature)
        self,
        all_messages: list[_messages.ModelMessage],
        new_message_index: int,
        stream_response: AgentStream[AgentDepsT, OutputDataT] | None = None,
        on_complete: Callable[[], Awaitable[None]] | None = None,
        run_result: AgentRunResult[OutputDataT] | None = None,
    ) -> None: ...
```

Public consumption API (all `result.py`):

| Method / property | Line | Signature → returns |
| --- | --- | --- |
| `stream_output` | 510 | `async stream_output(*, debounce_by: float \| None = 0.1) -> AsyncIterator[OutputDataT]` — validated output, partial-validated per chunk. **(replaces v1 `stream()`)** |
| `stream_text` | 535 | `async stream_text(*, delta: bool = False, debounce_by: float \| None = 0.1) -> AsyncIterator[str]` — text only; raises `UserError` if not a text response. |
| `stream_response` | 565 | `async stream_response(*, debounce_by: float \| None = 0.1) -> AsyncIterator[_messages.ModelResponse]` — full response objects. |
| `get_output` | 596 | `async get_output() -> OutputDataT` — await the complete validated output. |
| `validate_response_output` | 673 | async validation helper. |
| `all_messages` / `all_messages_json` | 445 / 462 | message history (+ JSON bytes). |
| `new_messages` / `new_messages_json` | 478 / 494 | messages produced this run. |
| `response` (property) | 610 | latest `ModelResponse`. |
| `usage` (property) | 630 | `RunUsage`. |
| `metadata` (property) | 620 | resolved run metadata. |
| `run_id` / `conversation_id` (properties) | 654 / 664 | identifiers. |
| `timestamp` (property) | 644 | `datetime`. |
| `cancel` / `cancelled` | 700 / 716 | cancel the underlying stream / check state. |

`debounce_by=0.1` default groups chunks to reduce validation overhead; `None` disables debouncing.
A sync mirror **`StreamedRunResultSync`** exists (`result.py:723`, returned by `run_stream_sync`) with
`Iterator`-based equivalents.

### 6.2 `AgentStream` (`result.py:51`) — what events/deltas are yielded
```python
@dataclass(kw_only=True)
class AgentStream(Generic[AgentDepsT, OutputDataT]): ...
    def __aiter__(self) -> AsyncIterator[ModelResponseStreamEvent]:  # line 362
        """Stream ModelResponseStreamEvents."""
```
- **Async-iterating an `AgentStream` yields `ModelResponseStreamEvent` objects** (i.e. incremental
  part deltas — `PartStartEvent`, `PartDeltaEvent`, etc. from `pydantic_ai.messages`).
- Convenience methods mirror `StreamedRunResult`: `stream_output` (72), `stream_response` (101),
  `stream_text` (122), `get_output` (208), plus `cancel` (156), `drain` (160), `cancelled` (166),
  and properties `response`, `usage`, `timestamp`, `run_id`, `conversation_id`, `metadata`.
- At the agent-event level (used by `run_stream_events` / `event_stream_handler`), the stream yields
  **`AgentStreamEvent`** items (model-response deltas + tool-call/return `HandleResponseEvent`s),
  terminated by `AgentRunResultEvent` in `run_stream_events`.

---

## 7. Exception types (`exceptions.py`, `__all__` lines 19–37)

Full hierarchy:

```
Exception
├─ ModelRetry                 (40)  raise in tools/output validators/capability hooks → retry prompt to model
├─ CallDeferred               (80)  defer a tool call (metadata kwarg)
├─ ApprovalRequired           (98)  human-in-the-loop tool approval (metadata kwarg)
├─ SkipModelRequest           (116) raise in before/wrap model-request hook; .response used instead of calling model
├─ SkipToolValidation         (133) skip tool validation; .validated_args used
├─ SkipToolExecution          (146) skip tool execution; .result used
├─ ToolRetryError             (273) internal: signals a ToolRetry message to the LLM (.tool_retry)
└─ RuntimeError
   ├─ UserError               (159) developer usage mistake (.message)
   │  └─ UndrainedPendingMessagesError (170) run ended with messages still queued via enqueue
   └─ AgentRunError           (181) base for errors during a run (.message)
      ├─ UsageLimitExceeded   (195) usage exceeded UsageLimits
      ├─ ConcurrencyLimitExceeded (199) concurrency queue depth exceeded max_queued
      ├─ UnexpectedModelBehavior (203) unexpected model behavior / retry limits exceeded (.message, .body)
      │  ├─ ContentFilterError (232) provider content filter → empty response
      │  └─ IncompleteToolCall (308) token limit hit mid-tool-call
      └─ ModelAPIError        (236) provider API request failed (.model_name, .message)
         └─ ModelHTTPError    (250) 4xx/5xx from provider (.status_code, .model_name, .body)

ExceptionGroup
└─ FallbackExceptionGroup     (269) raised when all fallback models fail
```
(`ModelRetry` is serializable — has a Pydantic core schema, lines 61–77.)

Related helper: `capture_run_messages()` context manager (in `_agent_graph.py`) to inspect message
history when a run raises.

---

## 8. Working code examples

### 8.1 Basic run
```python
from pydantic_ai import Agent

agent = Agent('openai:gpt-5.2', system_prompt='Be concise.')

# sync
result = agent.run_sync('What is the capital of Italy?')
print(result.output)        # -> 'The capital of Italy is Rome.'
print(result.usage())       # RunUsage(...)

# async
async def main():
    result = await agent.run('What is the capital of France?')
    print(result.output)    # -> 'The capital of France is Paris.'
```

### 8.2 Streaming run (`run_stream`)
```python
from pydantic_ai import Agent

agent = Agent('openai:gpt-5.2')

async def main():
    async with agent.run_stream('What is the capital of the UK?') as response:
        # incremental text
        async for chunk in response.stream_text(delta=True):
            print(chunk, end='', flush=True)
        # or the complete validated output:
        print(await response.get_output())   # -> 'The capital of the UK is London.'
        print(response.usage())
```
Structured streaming:
```python
from pydantic import BaseModel
from pydantic_ai import Agent

class City(BaseModel):
    name: str
    country: str

agent = Agent('openai:gpt-5.2', output_type=City)

async def main():
    async with agent.run_stream('Tell me about Paris.') as response:
        async for partial in response.stream_output(debounce_by=0.1):
            print(partial)   # progressively validated City(...)
```

### 8.3 Event streaming (`run_stream_events`)
```python
from pydantic_ai import Agent, AgentRunResultEvent, AgentStreamEvent

agent = Agent('openai:gpt-5.2')

async def main():
    collected: list[AgentStreamEvent | AgentRunResultEvent] = []
    async with agent.run_stream_events('What is the capital of France?') as events:
        async for event in events:
            collected.append(event)
    # last item is AgentRunResultEvent(result=AgentRunResult(output='...'))
```

### 8.4 Step-through with `iter` / `AgentRun`
```python
from pydantic_ai import Agent
from pydantic_graph import End

agent = Agent('openai:gpt-5.2')

async def main():
    async with agent.iter('What is the capital of France?') as agent_run:
        async for node in agent_run:          # UserPromptNode, ModelRequestNode, CallToolsNode, End
            print(type(node).__name__)
        print(agent_run.result.output)        # -> 'The capital of France is Paris.'
        print(agent_run.usage)                # RunUsage(...)
```
Manual driving (inspect/mutate nodes), with a usage limit guarding the tool loop:
```python
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from pydantic_graph import End

agent = Agent('openai:gpt-5.2')

async def main():
    async with agent.iter(
        'Use the tools to answer.',
        usage_limits=UsageLimits(request_limit=5, tool_calls_limit=10),
    ) as agent_run:
        node = agent_run.next_node
        while not isinstance(node, End):
            # inspect/modify `node` here if desired
            node = await agent_run.next(node)
        print(agent_run.result.output)
```

### 8.5 Instrumentation (Logfire)
```python
import logfire
from pydantic_ai import Agent

logfire.configure()
logfire.instrument_pydantic_ai()      # global instrumentation
# or per-agent: agent.instrument = True
# or all agents:  Agent.instrument_all(True)

agent = Agent('openai:gpt-5.2')
agent.run_sync('hello')               # emits OTel spans: messages, tool calls, usage, latency
```

---

## Self-validation (Task 8)

- `Agent.__init__` (`agent/__init__.py:322`) — all 19 parameters captured from the literal source
  signature (lines 322–343); no omissions. `instrument` confirmed to be a **property/setter**, not an
  `__init__` kwarg, in this version.
- Run methods reconciled: `run`, `run_sync`, `run_stream`, `run_stream_sync`, `run_stream_events`,
  `iter` — all signatures taken verbatim from `agent/abstract.py` (concrete `iter` at
  `agent/__init__.py:935`). Confirmed `event_stream_handler` is present on `run`/`run_sync`/`run_stream`
  but **absent** on `iter`.
- Lifecycle node order and `run_step`/usage-limit/retry mechanics verified directly in
  `_agent_graph.py` (line numbers cited).
- `StreamedRunResult` / `AgentStream` consumption methods and the yielded event type
  (`ModelResponseStreamEvent` / `AgentStreamEvent`) verified in `result.py`.
- Exception list matches `exceptions.__all__` plus the internal `ToolRetryError`.
- Docs (`pydantic.dev/docs/ai/core-concepts/agent/`) cross-checked: confirms the five run methods, the
  four node types, `UsageLimits(request_limit, output_tokens_limit, tool_calls_limit)`,
  `event_stream_handler` signature, Logfire instrumentation, `end_strategy` (`graceful`/`exhaustive`),
  and exceptions (`UsageLimitExceeded`, `UnexpectedModelBehavior`, `ModelRetry`,
  `ConcurrencyLimitExceeded`).

### Caveats / discrepancies for the orchestrator
1. **"v2" naming**: there is no separate `pydantic-ai-v2` package — the package is `pydantic-ai-slim`
   and `main` is the active (v2) line. v2 markers found in code: `end_strategy` default
   `early`→`graceful`; `Agent.run().stream()` → `StreamedRunResult.stream_output()`; capability system;
   `agent.py`→`agent/` package.
2. **File-path corrections** vs the task brief: `agent.py` is a package; `_run.py` does not exist (it is
   `run.py`); the run methods live in `agent/abstract.py`.
3. **Docs migration**: `ai.pydantic.dev/agents/` 301-redirects to
   `pydantic.dev/docs/ai/core-concepts/agent/`.
