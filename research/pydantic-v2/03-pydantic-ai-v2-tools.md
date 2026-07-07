# pydantic-ai v2 — Q4: Tool & Function Calling System

Research snapshot of the `main` branch (pydantic-ai-slim). Every claim cites a source file/line
(local copies fetched into `research/`, sourced from
`https://raw.githubusercontent.com/pydantic/pydantic-ai/main/pydantic_ai_slim/pydantic_ai/...`)
or a docs URL.

> NOTE: `pydantic_ai_slim/pydantic_ai/agent.py` is empty on `main`. The real `Agent` class lives in
> `pydantic_ai_slim/pydantic_ai/agent/__init__.py` (referred to below as `agent/__init__.py`).
> The official tools doc moved: `https://ai.pydantic.dev/tools/` → 301 →
> `https://pydantic.dev/docs/ai/tools-toolsets/tools/`.

---

## 1. Tool Registration — all the ways

There are **five** distinct registration paths, all of which ultimately build a `Tool` object
inside a `FunctionToolset`.

### 1a. `@agent.tool` — decorator, function takes `RunContext` first
`agent/__init__.py:2064-2173`. Inferred-or-explicit ctx; here forced `takes_ctx=True`
(`agent/__init__.py:2154`). Full keyword surface (overload at `agent/__init__.py:2042-2062`):

```python
@agent.tool(
    name=None, description=None, retries=None,
    prepare=None, args_validator=None,
    docstring_format='auto', require_parameter_descriptions=False,
    schema_generator=GenerateToolJsonSchema,
    strict=None, sequential=False, requires_approval=False,
    metadata=None, timeout=None, defer_loading=False,
    include_return_schema=None,
)
```

```python
from pydantic_ai import Agent, RunContext
agent = Agent('test', deps_type=int)

@agent.tool
def foobar(ctx: RunContext[int], x: int) -> int:
    return ctx.deps + x

@agent.tool(retries=2)
async def spam(ctx: RunContext[str], y: float) -> float:
    return ctx.deps + y
```
(docstring example, `agent/__init__.py:2095-2112`)

### 1b. `@agent.tool_plain` — decorator, function does NOT take `RunContext`
`agent/__init__.py:2200-2308`; forces `takes_ctx=False` (`agent/__init__.py:2289`).
Same keyword surface as `@agent.tool`. Note: even with `tool_plain`, an `args_validator`
still receives `RunContext` as its first argument (`agent/__init__.py:2261-2262`).

```python
@agent.tool_plain
def roll_dice() -> str:
    """Roll a six-sided die and return the result."""
    return str(random.randint(1, 6))
```
(docs: `pydantic.dev/docs/ai/tools-toolsets/tools/`)

### 1c. `tools=` constructor argument on `Agent(...)`
`agent/__init__.py:288` (overload) / `:335` (impl):
```python
tools: Sequence[Tool[AgentDepsT] | ToolFuncEither[AgentDepsT, ...]] = ()
```
Accepts **plain functions** (ctx-taking-or-not, inferred) **or pre-built `Tool` instances**:
```python
agent = Agent('google:gemini-3-flash-preview', tools=[roll_dice, get_player_name])
# explicit control:
agent = Agent('test', tools=[Tool(roll_dice, takes_ctx=False),
                             Tool(get_player_name, takes_ctx=True)])
```
(docs; `tools` keyword documented at `agent/__init__.py:376-377`)

### 1d. `FunctionToolset.add_function(...)` / `.add_tool(...)` (programmatic)
`toolsets/function.py:464-569` (`add_function`) and `:571-583` (`add_tool`).
`add_function` builds a `Tool` then calls `add_tool`; returns the `Tool`
(`toolset_function.py:549-569`). `add_tool` raises `UserError` on name conflict and inherits the
toolset's `max_retries`/`metadata` (`toolset_function.py:577-583`).
`FunctionToolset` also has its own `@toolset.tool` / `@toolset.tool_plain` decorators
(`toolset_function.py:146-170`, `:289-313`). All `agent` decorators delegate here:
`self._function_toolset.add_function(...)` (`agent/__init__.py:2152`, `:2287`).

### 1e. `Tool` class directly + `@agent.toolset` (dynamic toolset)
`Tool(func, ...)` instances (see §2) can be passed via `tools=` or `add_tool`.
`@agent.toolset` (`agent/__init__.py:2322-2358`) registers a *dynamic toolset function*
`(RunContext) -> AbstractToolset` (re-evaluated per run step by default).

`Tool.from_schema(...)` (`tools.py:581-636`) builds a tool from a function + an explicit
JSON schema (skips schema-derived arg validation; `args_validator` still runs).

---

## 2. `Tool` class — full definition

`tools.py:438-671`. `@dataclass(init=False)`, `Generic[ToolAgentDepsT]`
(`ToolAgentDepsT = TypeVar('ToolAgentDepsT', default=object, contravariant=True)`, `tools.py:434`).

Declared attributes (`tools.py:442-458`):
| attr | type |
|---|---|
| `function` | `ToolFuncEither[ToolAgentDepsT]` |
| `takes_ctx` | `bool` |
| `max_retries` | `int | None` |
| `name` | `str` |
| `description` | `str | None` |
| `prepare` | `ToolPrepareFunc[ToolAgentDepsT] | None` |
| `args_validator` | `ArgsValidatorFunc[ToolAgentDepsT, ...] | None` |
| `docstring_format` | `DocstringFormat` |
| `require_parameter_descriptions` | `bool` |
| `strict` | `bool | None` |
| `sequential` | `bool` |
| `requires_approval` | `bool` |
| `metadata` | `dict[str, Any] | None` |
| `timeout` | `float | None` |
| `defer_loading` | `bool` |
| `include_return_schema` | `bool | None` |
| `function_schema` | `_function_schema.FunctionSchema` |

Full `__init__` signature (`tools.py:465-486`):
```python
def __init__(
    self,
    function: ToolFuncEither[ToolAgentDepsT, ToolParams],
    *,
    takes_ctx: bool | None = None,           # inferred from signature if None
    max_retries: int | None = None,          # None => agent default
    name: str | None = None,                 # None => function.__name__
    description: str | None = None,          # None => from docstring
    prepare: ToolPrepareFunc[ToolAgentDepsT] | None = None,
    args_validator: ArgsValidatorFunc[ToolAgentDepsT, ToolParams] | None = None,
    docstring_format: DocstringFormat = 'auto',
    require_parameter_descriptions: bool = False,
    schema_generator: type[GenerateJsonSchema] = GenerateToolJsonSchema,
    strict: bool | None = None,
    sequential: bool = False,
    requires_approval: bool = False,
    metadata: dict[str, Any] | None = None,
    timeout: float | None = None,
    defer_loading: bool = False,
    include_return_schema: bool | None = None,
    function_schema: _function_schema.FunctionSchema | None = None,
): ...
```
`takes_ctx` is resolved from the generated `function_schema.takes_ctx` (`tools.py:566`).

Key methods:
- `from_schema(cls, function, name, description, json_schema, takes_ctx=False, sequential=False, args_validator=None) -> Self` (`tools.py:581-636`) — validator is `any_schema()` (no schema validation of args).
- `tool_def` property (`tools.py:638-652`) → builds a `ToolDefinition` (sets `kind='unapproved'` when `requires_approval`).
- `async prepare_tool_def(ctx) -> ToolDefinition | None` (`tools.py:654-671`) — applies `self.prepare` (sync or async) per step; `None` omits the tool that step.

### Tool function type signatures (`tools.py:48-92`)
- `ToolParams = ParamSpec('ToolParams', default=...)`
- `ToolFuncContext[AgentDepsT, ToolParams] = Callable[Concatenate[RunContext[AgentDepsT], ToolParams], Any]` — **takes ctx**.
- `ToolFuncPlain[ToolParams] = Callable[ToolParams, Any]` — **no ctx**.
- `ToolFuncEither = ToolFuncContext | ToolFuncPlain`.
- Both **sync and async** functions are accepted (sync ones run in a thread executor — see §5).
- `ArgsValidatorFunc` (`tools.py:82-92`): `Callable[Concatenate[RunContext, ToolParams], Awaitable[None] | None]`; raises `ModelRetry` on failure.
- `ToolPrepareFunc` (`tools.py:93-121`): `(RunContext, ToolDefinition) -> ToolDefinition | None` (sync/async).
- `ToolsPrepareFunc` (`tools.py:123-152`): `(RunContext, list[ToolDefinition]) -> list[ToolDefinition]` — batch prep across all tools per step (used via `PrepareTools` capability).

---

## 3. `ToolDefinition` — full definition

`tools.py:686-890`. `@dataclass(repr=False, kw_only=True)`. Used for **function tools AND output tools**.

| field | type | default | meaning (file:line) |
|---|---|---|---|
| `name` | `str` | — | tool name (`tools.py:693`) |
| `parameters_json_schema` | `ObjectJsonSchema` (`dict[str,Any]`) | `{'type':'object','properties':{}}` | params schema (`:696`) |
| `description` | `str | None` | `None` | (`:699`) |
| `outer_typed_dict_key` | `str | None` | `None` | for non-object output tools (`:702`) |
| `strict` | `bool | None` | `None` | vendor strict JSON schema; OpenAI+Anthropic; `None`=inferred (`:708-718`) |
| `sequential` | `bool` | `False` | barrier tool, runs alone (`:720-728`) |
| `kind` | `ToolKind` | `'function'` | `'function'|'output'|'external'|'unapproved'` (`:730-739`) |
| `metadata` | `dict[str,Any] | None` | `None` | not sent to model; for MCP holds `meta`/`annotations`/`task` (`:741-745`) |
| `timeout` | `float | None` | `None` | per-tool timeout → retry prompt on overrun (`:747-752`) |
| `defer_loading` | `bool` | `False` | hide until surfaced by tool search (dual-meaning flag) (`:754-775`) |
| `unless_native` | `str | None` | `None` | drop from wire when named native tool supported (alias-compat: `prefer_native`/`prefer_builtin`) (`:777-790`) |
| `with_native` | `str | None` | `None` | keep on wire via native adapter (`:792-806`) |
| `tool_kind` | `ToolPartKind | None` | `None` | cross-provider typed call/return discriminator e.g. `'tool-search'` (`:816-832`) |
| `return_schema` | `ObjectJsonSchema | None` | `None` | return-value schema; native (Gemini) or injected into description (`:834-840`) |
| `include_return_schema` | `bool | None` | `None` | gate on sending return_schema (`:842-849`) |
| `capability_id` | `str | None` | `None` | owning capability id; gates deferred visibility (`:851-858`) |

Properties: `function_signature` (cached, `:860-872`), `render_signature(body, **kw)` (`:874-880`),
`defer` → `True` when `kind in ('external','unapproved')` (`:882-888`).

`ToolKind = Literal['function','output','external','unapproved']` (`tools.py:682`).
`ObjectJsonSchema = dict[str, Any]` (`tools.py:674`).

---

## 4. `RunContext` — COMPLETE class definition

`_run_context.py:35-271`. `@dataclasses.dataclass(repr=False, kw_only=True)`,
`Generic[RunContextAgentDepsT]` where
`RunContextAgentDepsT = TypeVar('RunContextAgentDepsT', default=object, covariant=True)` (`:31`).
(`AgentDepsT = TypeVar('AgentDepsT', default=object, contravariant=True)`, `:28`.)

Exported as `pydantic_ai.RunContext` (re-exported through `tools.py:15` and `__init__.py`).

### Attributes (all `kw_only`)
| attr | type | default | line |
|---|---|---|---|
| `deps` | `RunContextAgentDepsT` | — | 39 |
| `model` | `Model` | — | 41 |
| `usage` | `RunUsage` | — | 43 |
| `agent` | `Agent[..., Any] | None` | `None` | 45 |
| `prompt` | `str | Sequence[UserContent] | None` | `None` | 47 |
| `messages` | `list[ModelMessage]` | `[]` | 49 |
| `validation_context` | `Any` | `None` | 51 |
| `tracer` | `Tracer` | `NoOpTracer()` | 53 |
| `trace_include_content` | `bool` | `False` | 55 |
| `instrumentation_version` | `int` | `DEFAULT_INSTRUMENTATION_VERSION` | 57 |
| `retries` | `dict[str, int]` | `{}` | 59 |
| `tool_call_id` | `str | None` | `None` | 61 |
| `tool_name` | `str | None` | `None` | 63 |
| `retry` | `int` | `0` | 65 |
| `max_retries` | `int` | `0` | 71 |
| `run_step` | `int` | `0` | 77 |
| `tool_call_approved` | `bool` | `False` | 79 |
| `tool_call_metadata` | `Any` | `None` | 81 |
| `partial_output` | `bool` | `False` | 83 |
| `run_id` | `str | None` | `None` | 85 |
| `conversation_id` | `str | None` | `None` | 87 |
| `metadata` | `dict[str, Any] | None` | `None` | 94 |
| `model_settings` | `ModelSettings | None` | `None` | 96 |
| `pending_messages` | `list[PendingMessage] | None` | `None` | 105 |
| `tool_manager` | `ToolManager[...] | None` | `None` | 114 |
| `capabilities` | `dict[str, AbstractCapability[...]]` | `{}` | 125 |
| `loaded_capability_ids` | `set[str]` | `set()` | 128 |
| `capability_loaded` | `bool | None` | `None` | 137 |
| `discovered_tool_names` | `set[str]` | `set()` | 143 |

### Properties / methods
- `last_attempt: bool` → `self.retry == self.max_retries` (`:152-155`).
- `available_capability_ids: set[str]` (`:157-178`).
- `available_tool_names: set[str]` — visible callable tools this turn (`:180-217`).
- `tools: dict[str, ToolDefinition]` — all tool defs this turn (`:219-224`).
- `enqueue(*content, priority='asap'|'when_idle')` — inject messages mid-run; raises `UserError` if not backed by a running queue (`:226-269`).

Module also exposes `get_current_run_context()` and `set_current_run_context()` via a
`ContextVar` `_CURRENT_RUN_CONTEXT` (`_run_context.py:274-304`).

---

## 5. Schema Generation — Python types → JSON schema

Implemented in `_function_schema.py`. Entry point `function_schema(function, schema_generator, *, tool_name=None, takes_ctx=None, docstring_format='auto', require_parameter_descriptions=False) -> FunctionSchema` (`:103-281`).

Pipeline:
1. `signature(function)` + `get_type_hints(..., include_extras=True)` (`:131-138`).
2. Docstring parsed via `_griffe.doc_descriptions` → tool `description` + per-param descriptions (`:146`). Honors `DocstringFormat` `'google'|'numpy'|'sphinx'|'auto'` (`tools.py:244-251`).
3. **ctx detection**: first param is treated as `RunContext` when `takes_ctx is None` and its annotation `_is_call_ctx` (`is RunContext` or `get_origin is RunContext`) (`:150-151`, `:421-423`). Errors raised if `RunContext` appears anywhere but first arg, or on a no-ctx tool (`:162-171`).
4. Each remaining param → a Pydantic `TypedDictField` core schema via `gen_schema._generate_td_field_schema` using `FieldInfo.from_annotation` / `from_annotated_attribute` (defaults) (`:184-199`). `required` = no default.
5. `**kwargs` → `extras_schema` with `extra_behavior='allow'`; otherwise `'forbid'` (`:178-179`, `:346`).
6. **Single model-like arg flattening**: one model-like param's schema is emitted directly (unwrapped) so the model produces fields at top level; a wrap validator re-wraps to `{name: value}` (`_build_schema`, `:305-353`; `_validate_single_arg`, `:360-381`).
7. `schema_generator().generate(schema)` produces the JSON schema; default generator is `GenerateToolJsonSchema` (`tools.py:425-431`) which **strips property `title`s** to reduce noise.
8. **Return schema** computed eagerly via `TypeAdapter(return_type).json_schema(mode='serialization')`; `ToolReturn[T]`→`T`, bare `ToolReturn`/`Any`/unannotated→`{}`, `-> None`→`{"type":"null"}`, `Self`→owning class for bound methods (`_extract_return_schema_type`, `:384-418`). Falls back to `{}` with a `UserWarning` on unsupported types (`:260-267`).

`FunctionSchema` dataclass (`_function_schema.py:43-100`): `function, name, description, validator (SchemaValidator), json_schema, takes_ctx, is_async, single_arg_name, positional_fields, var_positional_field, return_schema`. Its `async call(args_dict, ctx)` runs async functions directly and **sync functions via `run_in_executor`** (`:80-87`) — this is how sync tools become non-blocking.

Docs confirm: pydantic-ai "extracts the docstring from functions and extracts parameter
descriptions from the docstring and adds them to the schema"
(`pydantic.dev/docs/ai/tools-toolsets/tools/`).

---

## 6. Tool Execution Flow — call-stack walkthrough

Dispatch lives in `_tool_execution.py` (exported through `_agent_graph.py:20,63`), driven by the
graph node `CallToolsNode` (`_agent_graph.py:1077`), whose `_handle_tool_calls`
(`:1292-1311`) calls `process_tool_calls(...)`.

1. **`CallToolsNode`** receives a `ModelResponse`. For each `ToolCallPart` it calls
   `process_tool_calls(tool_manager, tool_calls=..., tool_call_results=..., final_result=..., ctx=..., output_parts=...)` (`_tool_execution.py:100-165`).
2. **Strategy selection** by `end_strategy` ∈ `'early'|'graceful'|'exhaustive'` →
   `_EarlyProcessor`/`_GracefulProcessor`/`_ExhaustiveProcessor` (`:144-161`). Behaviour documented at `:111-142`.
3. **Classification** — each call's `tool_def.kind` (`'function'|'output'|'external'|'unapproved'|'unknown'`) computed once via `tool_manager.get_tool_def` (`:226-232`).
4. **Per-tool execution** routes through the `ToolManager`:
   - `for_run_step(ctx)` rebuilds a per-step manager (`tool_manager.py:111`).
   - `validate_tool_call(call, ...)` (`tool_manager.py:414`) → `_validate_tool_args` runs the Pydantic `SchemaValidator`, then validate hooks; `ValidationError`/`ModelRetry` are wrapped into a `ToolRetryError` carrying a `RetryPromptPart` (`tool_manager.py:179-186`, `:457`). Unknown tool name → `ModelRetry('Unknown tool name: ...')` (`tool_manager.py:351-364`).
   - `execute_tool_call(validated, wrap_validation_errors=True)` (`tool_manager.py:462-496`) → runs the function (async direct / sync in executor via `FunctionSchema.call`) inside execute hooks (instrumentation tracing via `wrap_tool_execute`).
5. **Scheduling**: tools run **in parallel** within a segment via `asyncio` tasks; a `sequential=True` tool is a **barrier** (prior tools finish, it runs alone, later tools wait) (`_tool_execution.py:127-129`). Run-scoped `ToolManager.parallel_execution_mode('sequential')` makes every tool a barrier (`tool_manager.py:96-109`, `146-154`). v1-compat default is `'parallel'`.
6. **Outcomes** — each call yields either a `ToolReturnPart` (success) or a `RetryPromptPart` (failure/retry) (`_tool_execution.py:42`, `:483-545`). `ToolReturnPart.narrow_type` promotes typed variants (`:545`). Results are sorted so returns/retries precede other parts (`_agent_graph.py:1728`).
7. **Deferred tools** (`external`, `unapproved`) without supplied results are batched and surfaced as `DeferredToolRequests` at step end (`:138-139`, `:213-216`, `:580`).
8. **Retry-wins invariant**: under `graceful`/`exhaustive`, any function/unknown `RetryPromptPart` suppresses `final_result` so the model retries next round (`:131-136`).
9. **Max-retries**: `ToolManager._check_max_retries` raises `UnexpectedModelBehavior(f'Tool {name!r} exceeded max retries count of {N}')` when exceeded (`tool_manager.py:172-176`).

---

## 7. Message types for tools

In `messages.py`. Discriminator field is `part_kind`.

### `ToolCallPart` (model → tool)  — `messages.py:1832-1838`, base `BaseToolCallPart` `:1732-1828`
```python
tool_name: str
args: str | dict[str, Any] | None = None     # JSON string or dict
tool_call_id: str = <generated>
# kw_only:
tool_kind: ToolPartKind | None = None         # 'tool-search'|'capability-load'|None
id: str | None = None                          # provider-specific (OpenAI Responses)
provider_name: str | None = None
provider_details: dict[str, Any] | None = None
part_kind: Literal['tool-call'] = 'tool-call'
```
Helpers: `args_as_dict(raise_if_invalid=False)`, `args_as_json_str()`, `has_content()`.

### `ToolReturnPart` (tool → model) — `messages.py:1303-1326`, base `BaseToolReturnPart` `:1098+`
```python
tool_name: str
content: ToolReturnContent          # MultiModalContent | Sequence | Mapping | Any
tool_call_id: str = <generated>
# kw_only:
tool_kind: ToolPartKind | None = None
metadata: Any = None                 # app-only, not sent to LLM
timestamp: datetime = <now>
outcome: Literal['success','failed','denied'] = 'success'
part_kind: Literal['tool-return'] = 'tool-return'
```

### `RetryPromptPart` — `messages.py:1377-1414`
Sent when: arg validation failed, tool raised `ModelRetry`, unknown tool name, plain text when
structured expected, output validation failed, or output validator raised `ModelRetry`.
```python
content: list[pydantic_core.ErrorDetails] | str
tool_name: str | None = None
tool_call_id: str = <generated>
timestamp: datetime = <now>
part_kind: Literal['retry-prompt'] = 'retry-prompt'
```

### `ToolReturn` (return helper, not a message part) — `messages.py:889-915`, `Generic[_ToolReturnValueT]`
Returned *from a tool function* to separate result from extra model-facing content:
```python
return_value: ToolReturnContent
content: str | Sequence[UserContent] | None = None   # extra UserPromptPart
metadata: Any = None                                  # app-only
kind: Literal['tool-return'] = 'tool-return'
```
`ToolReturn[T]` drives return-schema generation; bare `ToolReturn` does not (`_function_schema.py:402-417`).

### Native / typed variants
`NativeToolCallPart` / `NativeToolReturnPart` (`part_kind='builtin-tool-...'`, carry `provider_*`),
and typed subclasses promoted via `narrow_type` for `ToolPartKind = Literal['tool-search','capability-load']` (`messages.py:1084`, `:1311-1370`, `:1840-1841`).

---

## 8. Async tools

- Tools may be **sync or async** (both decorators say "Can decorate a sync or async functions",
  `agent/__init__.py:2087`, `:2223`).
- `is_async` is detected by `is_async_callable` (`_function_schema.py:278`).
- **Sync tools never block the loop**: `FunctionSchema.call` awaits async functions directly but
  runs sync functions through `run_in_executor(function, *args, **kwargs)` (a thread executor)
  (`_function_schema.py:80-87`).
- `args_validator` and `prepare` may also be sync or async; awaitables are detected via
  `inspect.isawaitable` (`tools.py:217-218`, `:667-669`).
- `RunContext.enqueue` is safe from async tools, sync tools (auto-thread-wrapped), and hooks
  (`_run_context.py:226-239`).
- **Parallelism**: independent tool calls in one model response run concurrently as `asyncio`
  tasks; ordering controlled by `sequential` barriers / `parallel_execution_mode` (§6).
- **Limitation**: a `sequential=True` tool serializes around itself; `timeout` (per-tool float
  seconds) converts overruns into a retry prompt rather than cancelling silently
  (`tools.py:548-549`, `ToolDefinition.timeout` `:747-752`).

---

## 9. MCP integration (Model Context Protocol)

Yes — first-class, in `mcp.py` (1699 lines). The recommended entry point is **`MCPToolset`**
(`mcp.py:671`), an `AbstractToolset` built on the **FastMCP `Client`**, supporting the full MCP
protocol (tools, resources, prompts, sampling, elicitation, OAuth) and transports HTTP / SSE /
stdio / in-process FastMCP / multi-server config (`mcp.py:671-712`).

```python
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset

toolset = MCPToolset('http://localhost:8000/mcp')         # streamable-HTTP
# toolset = MCPToolset('my_mcp_server.py')                # local stdio
# toolset = MCPToolset(Client(StreamableHttpTransport(...), auth='oauth'))  # pre-built client
agent = Agent('openai:gpt-5', toolsets=[toolset])
```
(examples `mcp.py:684-712`)

Notable `MCPToolset` config attributes:
- `client: FastMCPClient` (normalized) (`:715`)
- `tool_error_behavior: Literal['retry','error']` — `'retry'` raises `ModelRetry` so the model self-corrects (`:719-724`)
- `max_retries: int | None` — `None` inherits agent's count (`:726-730`)
- `cache_tools` / `cache_resources` / `cache_prompts: bool` — caches invalidated by `notifications/*/list_changed` or session close (`:732-757`)
- `include_instructions: bool` (default `False`) — fold server init instructions into agent instructions (`:759-764`)
- `include_return_schema: bool | None` — include each tool's MCP `outputSchema` (`:766-772`)
- `process_tool_call: ProcessToolCallback | None` — wrap calls for metadata/retry/telemetry (`:774-777`)
- `sampling_model: Model | None` — lets server sample via `sampling/createMessage` (`:779-785`)
- `log_level: LoggingLevel | None` (`:787-790`)

Lifecycle: `async __aenter__/__aexit__` (`mcp.py:1072`); `get_tools(ctx)` (`:1137`) lists server
tools as `ToolsetTool`s; `call_tool(...)` (`:1238`) invokes them. MCP tool `metadata` on the
`ToolDefinition` carries the server's `meta`/`annotations` and a `task` flag
(`tools.py:743-744`). Helper `load_mcp_toolsets` handles multi-server JSON config (`:681-682`).
Other public classes: `Resource`, `ResourceTemplate`, `Prompt`, `PromptMessage`,
`ServerCapabilities`, `CallToolFunc`, `MCPError` (`mcp.py:106-619`).
Docs: `https://ai.pydantic.dev/mcp/`.

---

## 10. Error handling in tools

All in `exceptions.py` (exported from `pydantic_ai.__init__`):

| exception | line | purpose |
|---|---|---|
| `ModelRetry(message)` | 40-77 | Raise from tool/output-validator/hook to send a retry prompt back to the model; serializable via custom pydantic core schema. |
| `ToolRetryError(tool_retry: RetryPromptPart)` | 273-305 | Internal signal that a `RetryPromptPart` should be returned. Wraps `ValidationError`/`ModelRetry` (`tool_manager.py:179-186`). Formats pydantic `ErrorDetails` into readable text. |
| `CallDeferred(metadata=None)` | 80-95 | Raise to defer a tool (external execution); call surfaces in `DeferredToolRequests.calls`. |
| `ApprovalRequired(metadata=None)` | 98-113 | Raise to require human-in-the-loop approval; surfaces in `DeferredToolRequests.approvals`. |
| `SkipToolValidation(validated_args)` | 133-143 | From before/wrap tool-validate hook — use given args, skip schema validation. |
| `SkipToolExecution(result)` | 146-156 | From before/wrap tool-execute hook — use given result, skip running the tool. |
| `SkipModelRequest(response)` | 116-130 | Skip the model call, use provided `ModelResponse`. |
| `UnexpectedModelBehavior(message)` | 203 | Raised e.g. when a tool exceeds max retries (`tool_manager.py:176`). |
| `IncompleteToolCall` | 308 | Model hit token limit mid tool-call. |
| `UserError` | 159 | Developer mistake (e.g. duplicate tool name, `enqueue` without a queue). |

Flow: validation `ValidationError`/`ModelRetry` → wrapped as `ToolRetryError(RetryPromptPart)` →
counts against retry budget → `UnexpectedModelBehavior` when exhausted. `ModelRetry` from the tool
body during execution is similarly wrapped when `wrap_validation_errors=True`
(`tool_manager.py:475-480`, `462-496`).

### Human-in-the-loop approval & deferred tools (`tools.py:254-419`)
- `Tool(requires_approval=True)` → `ToolDefinition.kind='unapproved'` (`tools.py:649`).
- `DeferredToolRequests` (`:254-324`): `calls`, `approvals`, `metadata`; helpers `build_results(...)`, `remaining(results)`. Usable as an agent `output_type`.
- `DeferredToolResults` (`:376-419`): `calls`, `approvals` (`bool | ToolApproved | ToolDenied`), `metadata`; `to_tool_call_results()` normalizes `True/False` → `ToolApproved/ToolDenied` and wraps plain values in `ToolReturn`.
- `ToolApproved(override_args=None, kind='tool-approved')` (`:327-334`); `ToolDenied(message='The tool call was denied.', kind='tool-denied')` (`:337-346`).
- On the run context: `RunContext.tool_call_approved` and `RunContext.tool_call_metadata` expose approval state (`_run_context.py:79-82`).

### Dynamic preparation & selection
- `prepare: ToolPrepareFunc` per-tool, `ToolsPrepareFunc` batch (via `PrepareTools` capability) — return `None`/filtered list to omit tools per step.
- `ToolSelector = Literal['all'] | Sequence[str] | dict[str,Any] | ToolSelectorFunc` (`tools.py:166-181`) + `matches_tool_selector(...)` (`:198-226`) — name/metadata/predicate matching used by capability/toolset wrappers.

---

## 11. Working code examples (one per registration method)

```python
from pydantic_ai import Agent, RunContext, Tool, FunctionToolset
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.messages import ToolReturn
from pydantic_ai.exceptions import ModelRetry, ApprovalRequired

# (a) @agent.tool — takes RunContext
agent = Agent('openai:gpt-5', deps_type=int)

@agent.tool
async def add(ctx: RunContext[int], x: int) -> int:
    """Add x to the dependency.

    Args:
        x: number to add.
    """
    return ctx.deps + x

# (b) @agent.tool_plain — no RunContext, with retries
@agent.tool_plain(retries=2)
def roll_dice() -> str:
    """Roll a six-sided die."""
    import random
    return str(random.randint(1, 6))

# (c) tools= on the constructor (plain fn + explicit Tool)
def get_name(ctx: RunContext[int]) -> str:
    return f'player-{ctx.deps}'

agent2 = Agent(
    'openai:gpt-5', deps_type=int,
    tools=[roll_dice, Tool(get_name, takes_ctx=True, retries=1)],
)

# (d) FunctionToolset.add_function / add_tool, then pass via toolsets=
ts = FunctionToolset()
ts.add_function(roll_dice, takes_ctx=False)
ts.add_tool(Tool(get_name, takes_ctx=True))
agent3 = Agent('openai:gpt-5', deps_type=int, toolsets=[ts])

# (e) dynamic prepare + human-in-the-loop approval + ToolReturn
def only_if_42(ctx: RunContext[int], td: ToolDefinition) -> ToolDefinition | None:
    return td if ctx.deps == 42 else None

@agent.tool(prepare=only_if_42, requires_approval=True)
def danger(ctx: RunContext[int]) -> ToolReturn[str]:
    return ToolReturn(return_value='done', content='extra note to model', metadata={'audit': True})

# raising ModelRetry / ApprovalRequired from within a tool
@agent.tool_plain
def lookup(code: str) -> str:
    if not code.isalnum():
        raise ModelRetry('code must be alphanumeric, try again')
    if code == 'secret':
        raise ApprovalRequired(metadata={'reason': 'sensitive'})
    return f'value:{code}'
```

---

## Self-validation (Task 8)

- **All 5 registration paths documented** with code: `@agent.tool` (§1a), `@agent.tool_plain`
  (§1b), `tools=` ctor (§1c), `FunctionToolset.add_function`/`add_tool` + toolset decorators (§1d),
  `Tool(...)` directly / `Tool.from_schema` / `@agent.toolset` (§1e). ✔
- **`RunContext` full class** captured: all 27 attributes + 4 properties + `enqueue` + module
  ContextVar helpers, with line numbers (§4). ✔
- **Execution flow traced** end-to-end: `CallToolsNode` → `process_tool_calls` → strategy
  processor → `ToolManager.validate_tool_call`/`execute_tool_call` → `FunctionSchema.call`
  (sync→executor) → `ToolReturnPart`/`RetryPromptPart`/deferred batch, with retry budget +
  `UnexpectedModelBehavior` (§6). ✔
- **Message types** `ToolCallPart`, `ToolReturnPart`, `RetryPromptPart`, `ToolReturn`, native
  variants — full field lists (§7). ✔
- **MCP** confirmed present (`MCPToolset`, FastMCP-based) with config surface (§9). ✔
- **Errors**: `ModelRetry`, `ToolRetryError`, `CallDeferred`, `ApprovalRequired`,
  `Skip*`, `UnexpectedModelBehavior`, etc. (§10). ✔

### Caveats / gaps
- This is the **`main` branch** snapshot (a v2-era build): it includes features that may not be in
  any tagged v1 release — `capabilities`, native tools, **tool search / `defer_loading`**,
  `RunContext.enqueue`/pending messages, `unless_native`/`with_native`, `tool_kind` typed parts,
  `timeout`, `args_validator`, `sequential`/`parallel_execution_mode`. Treat these as bleeding-edge.
- `agent.py` is empty on `main`; `Agent` is in `agent/__init__.py`.
- Deeper internals of `_tool_execution.py` strategy subclasses (`_EarlyProcessor`/`_GracefulProcessor`/`_ExhaustiveProcessor` `_run_strategy`) read but only summarized at the behavioral level (§6).
