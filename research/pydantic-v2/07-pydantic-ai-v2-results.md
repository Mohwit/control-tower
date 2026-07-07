# Q8 — pydantic-ai v2 Result Types, Output Enforcement & Usage

Sources: `run.py`, `result.py`, `_output.py`, `output.py` (public), `usage.py`, `agent/abstract.py` (main branch) + docs.
Date: 2026-06-30

> **Naming changes vs. the old API (important):**
> - **`RunResult` → `AgentRunResult`** (in `pydantic_ai/run.py`, not `result.py`).
> - **`result.data` → `result.output`** — the `.data` attribute is **gone**; use `.output`.
> - **`ResultValidator` → `OutputValidator`** (in `pydantic_ai/_output.py`); registered via `@agent.output_validator`.
> - **`result_type=` → `output_type=`** on `Agent` and `run()`.
> - `result.py` now holds the **streaming** result types (`AgentStream`, `StreamedRunResult`, `StreamedRunResultSync`, `FinalResult`).

---

## 1. `output_type` (formerly `result_type`) — valid types

`OutputSpec[OutputDataT]` (public `output.py`). Accepted values:
- Scalars: `str` (default), `int`, `float`, `bool`, etc.
- Collections: `list`, `dict`, `TypedDict`, `StructuredDict`
- Structured models: Pydantic `BaseModel`, dataclasses
- Unions: `Fruit | Vehicle` or list form `[Fruit, Vehicle]`
- Output functions / bound methods (`OutputTypeOrFunction`, `TextOutputFunc`)
- `None` (optional output)
- `BinaryImage` (image generation)
- Mode wrappers: `ToolOutput(...)`, `NativeOutput(...)`, `PromptedOutput(...)`, `TextOutput(...)`

Output mode types (public `output.py`):
```python
OutputMode = Literal['text','tool','native','prompted','tool_or_text','image','auto']
StructuredOutputMode = Literal['tool','native','prompted']
```

Mode wrapper classes (`output.py`): `ToolOutput`, `NativeOutput`, `PromptedOutput`, `TextOutput`, plus `OutputObjectDefinition` and `OutputContext`.

---

## 2. `AgentRunResult` — COMPLETE definition

Source: `pydantic_ai_slim/pydantic_ai/run.py` (lines 473–614).
```python
@dataclasses.dataclass
class AgentRunResult(Generic[OutputDataT]):
    """The final result of an agent run."""

    output: OutputDataT
    # private (repr=False, compare=False):
    _output_tool_name: str | None = None
    _state: _agent_graph.GraphAgentState = field(default_factory=GraphAgentState)
    _new_message_index: int = 0
    _traceparent_value: str | None = None
```

**Methods / properties:**
| Member | Kind | Returns | Notes |
|---|---|---|---|
| `output` | field | `OutputDataT` | the validated final output |
| `all_messages(*, output_tool_return_content=None)` | method | `list[ModelMessage]` | full history (incl. prior runs) |
| `all_messages_json(*, output_tool_return_content=None)` | method | `bytes` | via `ModelMessagesTypeAdapter` |
| `new_messages(*, output_tool_return_content=None)` | method | `list[ModelMessage]` | this run only (slice at `_new_message_index`) |
| `new_messages_json(*, output_tool_return_content=None)` | method | `bytes` | |
| `response` | property | `ModelResponse` | last `ModelResponse` in history |
| `usage` | property | `RunUsage` | whole-run usage (`self._state.usage`) |
| `timestamp` | property | `datetime` | last response timestamp |
| `metadata` | property | `dict[str, Any] \| None` | run metadata |
| `run_id` | property | `str` | unique run id |
| `conversation_id` | property | `str` | conversation id |
| `_set_output_tool_return(content)` | method | `list[ModelMessage]` | rewrite output-tool return |

> **`usage` is a property** here (call as `result.usage`, not `result.usage()`), whereas on the **streaming** result types it is a **method** `usage()`. (See §3/§4.) The docs example shows `result.usage` for the non-streaming `AgentRunResult`.

Related: `AgentRunResultEvent(Generic[OutputDataT])` wraps a final result as a stream event (`event_kind='agent_run_result'`).

---

## 3. `AgentStream` — streaming primitive

Source: `result.py` (lines 51–388). `@dataclass(kw_only=True) class AgentStream(Generic[AgentDepsT, OutputDataT])`. Key members:
- `stream_output(*, debounce_by=0.1) -> AsyncIterator[OutputDataT]`
- `stream_response(*, debounce_by=0.1) -> AsyncIterator[ModelResponse]`
- `stream_text(*, delta=False, debounce_by=0.1) -> AsyncIterator[str]`
- `cancel()`, `drain()` (async); `cancelled` (property)
- `get_output() -> OutputDataT` (async)
- `validate_response_output(message, *, allow_partial=False)` (async)
- properties: `run_id`, `conversation_id`, `metadata`, `response`, `usage() -> RunUsage`, `timestamp`
- `__aiter__() -> AsyncIterator[ModelResponseStreamEvent]`

---

## 4. `StreamedRunResult` — COMPLETE definition

Source: `result.py` (lines 390–721). `@dataclass(init=False) class StreamedRunResult(Generic[AgentDepsT, OutputDataT])`.
```python
_all_messages: list[ModelMessage]
_new_message_index: int
_stream_response: AgentStream | None = None
_on_complete: Callable[[], Awaitable[None]] | None = None
_run_result: AgentRunResult[OutputDataT] | None = None
is_complete: bool = field(default=False, init=False)   # True once a stream/ get_output completes
```

**Methods / properties:**
| Member | Kind | Returns |
|---|---|---|
| `all_messages(*, output_tool_return_content=None)` | method | `list[ModelMessage]` |
| `all_messages_json(...)` | method | `bytes` |
| `new_messages(*, output_tool_return_content=None)` | method | `list[ModelMessage]` |
| `new_messages_json(...)` | method | `bytes` |
| `stream_output(*, debounce_by=0.1)` | async iter | `AsyncIterator[OutputDataT]` |
| `stream_text(*, delta=False, debounce_by=0.1)` | async iter | `AsyncIterator[str]` |
| `stream_response(*, debounce_by=0.1)` | async iter | `AsyncIterator[ModelResponse]` |
| `get_output()` | async | `OutputDataT` |
| `validate_response_output(message, *, allow_partial=False)` | async | `OutputDataT` |
| `response` | property | `ModelResponse` |
| `metadata` | property | `dict \| None` |
| `usage()` | **method** | `RunUsage` |
| `timestamp` | property | `datetime` |
| `run_id` / `conversation_id` | property | `str` |
| `cancel()` | async | `None` |
| `cancelled` | property | `bool` |
| `is_complete` | field | `bool` |

A **sync wrapper** `StreamedRunResultSync(Generic[AgentDepsT, OutputDataT])` (lines 723+) mirrors all of the above with synchronous iterators (`stream_output`/`stream_text`/`stream_response` return `Iterator[...]`, `get_output()`/`usage()` are sync).

`FinalResult(Generic[OutputDataT])` (line 897) is the internal end-of-run marker (`output`, `tool_name`, etc.).

---

## 5. `OutputValidator` (formerly `ResultValidator`) — type signature

Source: `_output.py`.
```python
OutputValidatorFunc = (
    Callable[[RunContext[AgentDepsT], OutputDataT_inv], OutputDataT_inv]
    | Callable[[RunContext[AgentDepsT], OutputDataT_inv], Awaitable[OutputDataT_inv]]
    | Callable[[OutputDataT_inv], OutputDataT_inv]
    | Callable[[OutputDataT_inv], Awaitable[OutputDataT_inv]]
)
# i.e. may/may not take RunContext, may/may not be async; takes & returns the output type

@dataclass
class OutputValidator(Generic[AgentDepsT, OutputDataT_inv]):
    function: OutputValidatorFunc[AgentDepsT, OutputDataT_inv]
    _takes_ctx: bool = field(init=False)   # detected from signature (>1 param)
    _is_async: bool = field(init=False)

    async def validate(self, result: T, run_context: RunContext[AgentDepsT]) -> T: ...
```
`validate()` calls the user function (sync functions run in an executor) and **propagates `ModelRetry` unwrapped** — the caller decides whether to wrap it for retry handling.

Registered via decorator:
```python
@agent.output_validator
async def validate_sql(ctx: RunContext, output: Success) -> Success:
    if invalid:
        raise ModelRetry('Invalid query: ...')
    return output
```

---

## 6. Structured output enforcement mechanism

Three modes (`_output.py` output processors + `output.py` mode wrappers):

1. **Tool output (DEFAULT)** — `ToolOutputSchema` / `ObjectOutputProcessor`. The output type's JSON schema becomes the **parameters schema of a special output tool**; the model produces the structured result by calling that tool. Default `StructuredOutputMode` resolves to `'tool'` (`_output.py` returns `'tool'`).
2. **Native output** — `NativeOutputSchema` via `NativeOutput(...)`. Uses the provider's native Structured Outputs / JSON-schema response format; the model is **forced to emit text matching the JSON schema**.
3. **Prompted output** — `PromptedOutputSchema` via `PromptedOutput(...)`. The JSON schema is injected into instructions; the model is **asked** to comply (no hard enforcement).

Other processors: `TextOutputSchema`/`TextOutputProcessor`/`TextFunctionOutputProcessor` (plain/text-function output), `ImageOutputSchema` (image gen), `UnionOutputProcessor`/`UnionOutputModel`/`UnionOutputResult` (union outputs), `AutoOutputSchema` (`'auto'` mode). All processors implement `validate(...)` and `tool_def: ToolDefinition | None`.

---

## 7. Validation-error retry behavior — YES, the library retries

When validation fails the framework feeds the error back to the model and asks it to try again, using a `RetryPromptPart` (`messages.py`):

- A failed Pydantic validation of tool args or structured output, an unknown tool name, plain text where structured output was expected, or a user `ModelRetry` raised from a tool or **output validator** → produces a `RetryPromptPart`. Its `content` is the list of `pydantic_core.ErrorDetails` (or a string), rendered by `RetryPromptPart.model_response()` as JSON errors followed by *"Fix the errors and try again."*
- **Output retry budget defaults to `1`** (docs). Each `ModelRetry` from an output validator/structured-output failure **consumes one unit** of the run's output retry budget. Configure via `Agent(retries={'output': N})` (and `output_retries` / `AgentRetries`); override per-run with `retries=`.
- **Tool calls have their own per-tool retry counter** (`RunContext.retries` is `dict[str, int]`, `ctx.retry` / `ctx.max_retries` / `ctx.last_attempt`). Per-tool limit settable via `ToolOutput(max_retries=N)` for output tools and per-tool `retries=` for function tools.

So validation failure does NOT immediately raise — it triggers a model retry up to the budget, then raises `UnexpectedModelBehavior` (exhausted retries) if still failing.

---

## 8. Usage / cost tracking — `usage.py`

Source: `pydantic_ai_slim/pydantic_ai/usage.py`.

### `UsageBase` (`@dataclass(kw_only=True)`) — shared fields
```python
input_tokens: int = 0
cache_write_tokens: int = 0
cache_read_tokens: int = 0
output_tokens: int = 0
input_audio_tokens: int = 0
cache_audio_read_tokens: int = 0
output_audio_tokens: int = 0
details: dict[str, int] = field(default_factory=dict)
# property total_tokens; opentelemetry_attributes(); has_values(); __copy__
```

### `RequestUsage(UsageBase)` — per single model request
Adds `requests` (property == 1), `incr(incr_usage)`, `__add__`, and classmethod `extract(data, *, provider, provider_url, provider_fallback, api_flavor='default', details=None)` (parses provider response usage via genai-prices). Stored on `ModelResponse.usage`.

### `RunUsage(UsageBase)` — accumulated across a run
```python
requests: int = 0          # number of LLM API requests
tool_calls: int = 0        # successful tool calls
input_tokens: int = 0
cache_write_tokens: int = 0
cache_read_tokens: int = 0
input_audio_tokens: int = 0
cache_audio_read_tokens: int = 0
output_tokens: int = 0
details: dict[str, int] = field(default_factory=dict)
# incr(incr_usage: RunUsage | RequestUsage); __add__
```
Returned by `result.usage` (AgentRunResult property) / `result.usage()` (streaming).

### `UsageLimits` (`@dataclass(kw_only=True)`)
```python
request_limit: int | None = 50        # default cap on # requests
tool_calls_limit: int | None = None
input_tokens_limit: int | None = None
output_tokens_limit: int | None = None
total_tokens_limit: int | None = None
count_tokens_before_request: bool = False
# has_token_limits(); check_before_request(usage); check_tokens(usage); check_before_tool_call(projected_usage)
```
Passed via `usage_limits=` on `run()`.

### Cost
`ModelResponse.cost() -> genai_types.PriceCalculation` computes price from usage using the [`genai-prices`](https://github.com/pydantic/genai-prices) library (matches by `provider_url` then `provider_name`).

---

## 9. Working code examples

### Structured output + validator + usage
```python
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext, ModelRetry

class SQLResult(BaseModel):
    query: str

agent = Agent('openai:gpt-5.2', output_type=SQLResult)  # default = tool mode

@agent.output_validator
def must_be_select(output: SQLResult) -> SQLResult:
    if not output.query.lower().startswith('select'):
        raise ModelRetry('Only SELECT queries allowed.')   # uses 1 retry from budget (default 1)
    return output

result = agent.run_sync('Get all users')
print(result.output.query)     # validated SQLResult
print(result.usage)            # RunUsage(requests=..., input_tokens=..., output_tokens=...)
print(result.usage.total_tokens)
```

### Native vs prompted mode + usage limits
```python
from pydantic_ai import Agent
from pydantic_ai.output import NativeOutput
from pydantic_ai.usage import UsageLimits

agent = Agent('openai:gpt-5.2', output_type=NativeOutput(SQLResult))
r = agent.run_sync('Get users', usage_limits=UsageLimits(request_limit=3, total_tokens_limit=10_000))
```

### Streaming result
```python
async with agent.run_stream('Tell me a story') as stream:   # -> StreamedRunResult
    async for chunk in stream.stream_text(delta=True):
        print(chunk, end='')
    final = await stream.get_output()
    print(stream.usage())     # NOTE: method on streaming result
```

---

## Sources
- `pydantic_ai_slim/pydantic_ai/run.py` (`AgentRunResult`, `AgentRunResultEvent`)
- `pydantic_ai_slim/pydantic_ai/result.py` (`AgentStream`, `StreamedRunResult`, `StreamedRunResultSync`, `FinalResult`)
- `pydantic_ai_slim/pydantic_ai/_output.py` (`OutputValidator`, `OutputValidatorFunc`, output schemas/processors)
- `pydantic_ai_slim/pydantic_ai/output.py` (`OutputSpec`, `OutputMode`, `StructuredOutputMode`, `ToolOutput`/`NativeOutput`/`PromptedOutput`/`TextOutput`)
- `pydantic_ai_slim/pydantic_ai/usage.py` (`UsageBase`, `RequestUsage`, `RunUsage`, `UsageLimits`)
- `pydantic_ai_slim/pydantic_ai/messages.py` (`RetryPromptPart`)
- Docs: https://pydantic.dev/docs/ai/core-concepts/output/
