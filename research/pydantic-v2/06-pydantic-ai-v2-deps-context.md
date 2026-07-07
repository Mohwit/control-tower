# Q7 — pydantic-ai v2 Dependency Injection & RunContext

Sources: `_run_context.py`, `agent/__init__.py`, `agent/abstract.py`, `tools.py`, `models/test.py` (main branch) + docs.
Date: 2026-06-30

---

## 1. `deps_type` parameter

Defined on the `Agent` constructor (`agent/__init__.py`):
```python
class Agent(AbstractAgent[AgentDepsT, OutputDataT]):
    _deps_type: type[AgentDepsT] = dataclasses.field(repr=False)

    def __init__(self, model=..., *, output_type=str, deps_type: type[AgentDepsT] = object, ...):
        ...
        self._deps_type = deps_type
```
Docstring: *"deps_type: The type used for dependency injection, this parameter exists solely to allow you to fully ..."* and the docs confirm: **"we're passing the type here, NOT an instance, this parameter is not actually used at runtime, it's here so we can get full type checking of the agent."**

So `deps_type` is a **pure typing hook** — it parameterizes the agent's `AgentDepsT` type variable so the type checker can verify `ctx.deps` access and the `deps=` argument. It is exposed read-only via the property:
```python
@property
def deps_type(self) -> type:  # returns self._deps_type
```

`AgentDepsT` (from `_run_context.py`):
```python
AgentDepsT = TypeVar('AgentDepsT', default=object, contravariant=True)
RunContextAgentDepsT = TypeVar('RunContextAgentDepsT', default=object, covariant=True)
```

---

## 2. Agent generic typing — `Agent[MyDeps, MyResult]`

`Agent` is `Generic[AgentDepsT, OutputDataT]` (via `AbstractAgent[AgentDepsT, OutputDataT]`). You parameterize it by passing `deps_type=` and `output_type=`; the type checker infers the two type args:
```python
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext

@dataclass
class MyDeps:
    api_key: str

class MyResult(BaseModel):
    answer: str

agent = Agent('openai:gpt-5.2', deps_type=MyDeps, output_type=MyResult)
# inferred type: Agent[MyDeps, MyResult]
```
Now `RunContext[MyDeps]` is required in tools/system-prompts, `deps=` at run time must be `MyDeps`, and `result.output` is typed `MyResult`. `OutputDataT` defaults to `str`; `AgentDepsT` defaults to `object`.

A per-run `output_type=` override on `run()` rebinds the result type to `RunOutputDataT` for that call.

---

## 3. `RunContext` — COMPLETE class definition

Source: `pydantic_ai_slim/pydantic_ai/_run_context.py` (re-exported as `pydantic_ai.tools.RunContext` / `pydantic_ai.RunContext`).

```python
@dataclasses.dataclass(repr=False, kw_only=True)
class RunContext(Generic[RunContextAgentDepsT]):
    """Information about the current call."""

    deps: RunContextAgentDepsT
    model: Model
    usage: RunUsage
    agent: Agent[RunContextAgentDepsT, Any] | None = field(default=None, repr=False)
    prompt: str | Sequence[messages.UserContent] | None = None
    messages: list[messages.ModelMessage] = field(default_factory=list)
    validation_context: Any = None
    tracer: Tracer = field(default_factory=NoOpTracer)
    trace_include_content: bool = False
    instrumentation_version: int = DEFAULT_INSTRUMENTATION_VERSION
    retries: dict[str, int] = field(default_factory=dict)
    tool_call_id: str | None = None
    tool_name: str | None = None
    retry: int = 0
    max_retries: int = 0
    run_step: int = 0
    tool_call_approved: bool = False
    tool_call_metadata: Any = None
    partial_output: bool = False
    run_id: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] | None = None
    model_settings: ModelSettings | None = None
    pending_messages: list[PendingMessage] | None = field(default=None, repr=False)
    tool_manager: ToolManager[RunContextAgentDepsT] | None = None
    capabilities: dict[str, AbstractCapability[RunContextAgentDepsT]] = field(default_factory=dict)
    loaded_capability_ids: set[str] = field(default_factory=set)
    capability_loaded: bool | None = None
    discovered_tool_names: set[str] = field(default_factory=set)
```

**Properties:**
| Property | Returns | Meaning |
|---|---|---|
| `last_attempt` | `bool` | `retry == max_retries` |
| `available_capability_ids` | `set[str]` | non-deferred caps ∪ loaded deferred caps |
| `available_tool_names` | `set[str]` | always-visible ∪ tool-search-revealed ∪ loaded-capability tools |
| `tools` | `dict[str, ToolDefinition]` | all tool defs this turn (incl. deferred) |

**Method:**
```python
def enqueue(self, *content: EnqueueContent, priority: PendingMessagePriority = 'asap') -> None
```
Injects content (user/model parts) into the conversation mid-run; `priority` is `'asap'` or `'when_idle'`. Raises `UserError` if the context isn't backed by a running agent's queue.

**Field notes (v2-specific):**
- `deps` is generic over `RunContextAgentDepsT` (covariant); your typed deps instance.
- `model_settings` is populated before each model request (merged: model → agent → capability → run); `None` in tool hooks / output validators / construction.
- `capabilities`, `loaded_capability_ids`, `capability_loaded`, `discovered_tool_names` are the capability/tool-search machinery (new in v2).
- `tool_manager`, `pending_messages` are internal/per-run wiring.

Module-level context-var helpers:
```python
get_current_run_context() -> RunContext[Any] | None
set_current_run_context(run_context)  # contextmanager
# backed by ContextVar _CURRENT_RUN_CONTEXT
```

---

## 4. Passing deps at runtime

`deps=` is a keyword arg on every run entry point (`run`, `run_sync`, `run_stream`, `run_stream_events`, `iter`) — signature in `agent/abstract.py`:
```python
deps: AgentDepsT = None
```
```python
result = await agent.run('Tell me a joke.', deps=MyDeps(api_key='...'))
```
Accessed in tools and instruction/system-prompt functions via `ctx.deps`:
```python
@agent.system_prompt
async def sysprompt(ctx: RunContext[MyDeps]) -> str:
    return await ctx.deps.http_client.get('https://example.com')

@agent.tool
async def lookup(ctx: RunContext[MyDeps], q: str) -> str:
    return await ctx.deps.http_client.get(f'https://example.com?q={q}')
```
`@agent.tool` receives `RunContext` as the first param; `@agent.tool_plain` does not (no deps). Same for capability tools (`Capability.tool` / `.tool_plain`) and output validators.

---

## 5. Testing with mocked deps

### 5.1 `agent.override(deps=...)` — the primary testing seam
Source: `agent/__init__.py` (`override`, contextmanager). Full signature:
```python
@contextmanager
def override(self, *,
    name: str | Unset = UNSET,
    deps: AgentDepsT | Unset = UNSET,
    model: Model | KnownModelName | str | Unset = UNSET,
    toolsets=UNSET, tools=UNSET, native_tools=UNSET,
    instructions=UNSET, metadata=UNSET, model_settings=UNSET,
    retries: int | AgentRetries | Unset = UNSET,
    spec: dict[str, Any] | AgentSpec | None = None,
) -> Generator[None]
```
Backed by `ContextVar`s (`_override_deps`, `_override_model`, `_override_model_settings`) so overrides are scoped to the `with` block:
```python
test_deps = TestMyDeps('test_key', None)
with joke_agent.override(deps=test_deps):
    result = await application_code('Tell me a joke.')
```
You can also override the model in the same call: `with agent.override(model=TestModel(), deps=test_deps): ...`.

### 5.2 `TestModel` (mock the model, not just deps)
Source: `pydantic_ai_slim/pydantic_ai/models/test.py`.
```python
class TestModel(Model):
    def __init__(self, *,
        call_tools: list[str] | Literal['all'] = 'all',
        custom_output_text: str | None = None,
        custom_output_args: Any | None = None,
        seed: int = 0,
        model_name: str = 'test',
        profile: ModelProfileSpec | None = None,
        settings: ModelSettings | None = None,
    ): ...
    last_model_request_parameters: ModelRequestParameters | None  # captured for assertions
```
`TestModel` auto-calls tools and synthesizes structured output from the output schema — useful for deps-driven integration tests without hitting a real provider. `FunctionModel` (same module) lets you script responses with a function.

---

## 6. Working example (end to end)

```python
from dataclasses import dataclass
import httpx
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel

@dataclass
class Deps:
    http_client: httpx.AsyncClient
    api_key: str

agent = Agent('openai:gpt-5.2', deps_type=Deps)   # -> Agent[Deps, str]

@agent.tool
async def weather(ctx: RunContext[Deps], city: str) -> str:
    r = await ctx.deps.http_client.get(
        'https://api.example.com/weather',
        params={'city': city}, headers={'X-Key': ctx.deps.api_key},
    )
    return r.text

async def main():
    async with httpx.AsyncClient() as client:
        deps = Deps(http_client=client, api_key='live-key')
        result = await agent.run('Weather in Paris?', deps=deps)
        print(result.output)

# --- test: override model + deps, no network/key ---
async def test_main():
    fake = Deps(http_client=httpx.AsyncClient(), api_key='x')
    with agent.override(model=TestModel(), deps=fake):
        result = await agent.run('Weather in Paris?', deps=fake)
        assert result.output
```

---

## Sources
- `pydantic_ai_slim/pydantic_ai/_run_context.py` (RunContext full definition)
- `pydantic_ai_slim/pydantic_ai/agent/__init__.py` (`deps_type`, `override`, generic class)
- `pydantic_ai_slim/pydantic_ai/agent/abstract.py` (`deps=` on run signatures)
- `pydantic_ai_slim/pydantic_ai/models/test.py` (`TestModel`, `FunctionModel`)
- Docs: https://pydantic.dev/docs/ai/core-concepts/dependencies/
