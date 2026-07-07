# pydantic-ai v2 — Research Index

**Package:** `pydantic-ai` / `pydantic-ai-slim` **v2.1.0** (main branch)  
**Research date:** 2026-06-30  
**Purpose:** Decision guide for building an AI harness SDK on top of pydantic-ai v2.

> **Critical version note.** There is no separate "v2" PyPI package name. The distributed package is
> still `pydantic-ai` (umbrella) and `pydantic-ai-slim` (real code). The "v2" designation refers to
> the current `main`-branch architecture, which introduced the `capabilities/` subpackage and a broad
> set of API renames from the older v0/v1 line. Key renames: `RunResult` → `AgentRunResult`,
> `result.data` → `result.output`, `ResultValidator` → `OutputValidator`, `result_type=` →
> `output_type=`, `stream()` → `stream_output()`. If you pin a released version rather than `main`,
> verify the capabilities layer is present in that release.

---

## Research Documents

| Document | Topics Covered |
|---|---|
| [pydantic-ai-v2-overview.md](01-pydantic-ai-v2-overview.md) | Q1: Package surface area, extras, public API. Q2: Model ABC, all concrete models, ModelSettings, KnownModelName |
| [pydantic-ai-v2-agent-lifecycle.md](02-pydantic-ai-v2-agent-lifecycle.md) | Q3: Agent.__init__ (19 params), all run methods, internal graph lifecycle, retries, streaming, iter() API |
| [pydantic-ai-v2-tools.md](03-pydantic-ai-v2-tools.md) | Q4: Tool class (17 fields), 5 registration paths, RunContext (29 attrs), schema gen, execution flow, MCP |
| [pydantic-ai-v2-capabilities.md](04-pydantic-ai-v2-capabilities.md) | Q5: Full capabilities/ subpackage (31 files), AbstractCapability hook system, all 20+ built-in capabilities |
| [pydantic-ai-v2-messages-history.md](05-pydantic-ai-v2-messages-history.md) | Q6: Full message type hierarchy, history passing, serialization, multi-turn patterns |
| [pydantic-ai-v2-deps-context.md](06-pydantic-ai-v2-deps-context.md) | Q7: Dependency injection, Agent[DepsT, OutputT] generics, RunContext full definition, test utilities |
| [pydantic-ai-v2-results.md](07-pydantic-ai-v2-results.md) | Q8: AgentRunResult, StreamedRunResult, OutputValidator, output modes, usage/cost tracking |
| [pydantic-ai-v2-primitives.md](08-pydantic-ai-v2-primitives.md) | Q9: Model ABC, WrapperModel, InstrumentedModel, FallbackModel, custom model implementation guide |

---

## Key Findings Per Area

### Q1 & Q2 — Package Surface & Model Abstraction
[→ pydantic-ai-v2-overview.md](01-pydantic-ai-v2-overview.md)

`pydantic-ai-slim` is the real package. Required (no-extras) deps include `pydantic>=2.12`,
`pydantic-graph`, `httpx`, `opentelemetry-api`, `genai-prices`, and `griffelib`. There are 28 optional
extras. The `pydantic-ai` umbrella installs `[openai,anthropic,google,mcp,cli,evals,logfire,retries,web,ag-ui]`
by default.

`Model` is `class Model(ABC, Generic[InterfaceClient])` with 3 required abstract members: `async
request()`, `model_name` property, and `system` property. 13 concrete model classes exist across 10
provider files (`openai.py`, `anthropic.py`, `google.py`, `ollama.py`, `mistral.py`, `groq.py`,
`bedrock.py`, `cohere.py`, `xai.py`, `huggingface.py`). The `model=` parameter on `Agent` accepts a
`Model` instance, a `KnownModelName` string, or any plain string (resolved at run time via
`infer_model()`). `ModelSettings` is a `TypedDict(total=False)` with 16 fields — it is **not** a
Pydantic model.

### Q3 — Agent Class & Run Lifecycle
[→ pydantic-ai-v2-agent-lifecycle.md](02-pydantic-ai-v2-agent-lifecycle.md)

`Agent` is now a package (`agent/__init__.py`). Its `__init__` takes 19 parameters. Run methods are
defined in `agent/abstract.py` and include `run`, `run_sync`, `run_stream`, `run_stream_sync`,
`run_stream_events`, and `iter`. The internal execution graph is in `_agent_graph.py`:
`UserPromptNode → ModelRequestNode → CallToolsNode → (loop | End(FinalResult))`. There is **no
max_steps** — looping is bounded by `UsageLimits` (`request_limit`, `tool_calls_limit`, token limits).
Retries are controlled by `AgentRetries(tools=1, output=1)` by default. `end_strategy` defaults to
`'graceful'` (changed from `'early'` in v1). `instrument` is a property/setter, not a constructor
kwarg. Streaming is via `StreamedRunResult.stream_output()` (renamed from `stream()` in v2).

### Q4 — Tool System
[→ pydantic-ai-v2-tools.md](03-pydantic-ai-v2-tools.md)

Five registration paths: `@agent.tool` (with RunContext), `@agent.tool_plain` (no context),
`tools=` constructor list, `FunctionToolset.add_function`, and `Tool(...)` directly or via
`Tool.from_schema`. All funnel into `FunctionToolset`. The `Tool` dataclass has 17 fields including
v2 additions: `args_validator`, `sequential`, `requires_approval`, `timeout`, `defer_loading`,
`include_return_schema`. `ToolDefinition` has 19 fields. `RunContext` has 29 attributes. Schema
generation uses griffe for docstring parsing + Pydantic core schema → JSON schema. Sync tools
automatically run via `run_in_executor`. Retry is via `RetryPromptPart`. MCP is first-class via
`MCPToolset` (FastMCP-based).

### Q5 — Capabilities Module
[→ pydantic-ai-v2-capabilities.md](04-pydantic-ai-v2-capabilities.md)

**`pydantic_ai.capabilities` exists as a full 31-file subpackage.** This is the central harness
layer of v2. `AbstractCapability` is a generic base class (`Generic[AgentDepsT]`) providing a
complete onion of lifecycle hooks: `before_run` / `after_run`, `before_node` / `after_node`,
`wrap_model_request` / `on_model_request_error`, `before_tool_validate` / `after_tool_validate`,
`before_tool_execute` / `after_tool_execute`, `before_output_validate` / `after_output_validate`,
`before_output_process` / `after_output_process`. Capabilities are ordered by `CapabilityOrdering`
(topological sort). 20+ built-in capabilities include: `Instrumentation`, `MCP`, `Thinking`,
`WebSearch`, `WebFetch`, `ToolSearch`, `ProcessHistory`, `NativeTool`, `PrefixTools`, `PrepareTools`,
`ReinjectSystemPrompt`, `Hooks`, `HandleDeferredToolCalls`, and more. Additional harness layers:
`toolsets/` subpackage, `ui/` (ag-ui, vercel_ai), `durable_exec/` (temporal, dbos, prefect), and
`ext/langchain.py`.

### Q6 — Message Types & History
[→ pydantic-ai-v2-messages-history.md](05-pydantic-ai-v2-messages-history.md)

`ModelMessage = ModelRequest | ModelResponse` (discriminated union on `kind`). Request parts:
`SystemPromptPart`, `UserPromptPart`, `ToolReturnPart`, `RetryPromptPart`. Response parts:
`TextPart`, `ToolCallPart`, `ThinkingPart`. **`ArgsDict`/`ArgsJson` are gone** — tool call args are
now `str | dict | None` with `args_as_dict()` / `args_as_json_str()` methods. History is passed via
`message_history: Sequence[ModelMessage] | None` on every `run*()` call. Extracted via
`result.all_messages()` / `result.new_messages()` and their `_json` variants. Serialization is via
`ModelMessagesTypeAdapter`.

### Q7 — Dependency Injection & RunContext
[→ pydantic-ai-v2-deps-context.md](06-pydantic-ai-v2-deps-context.md)

`Agent[DepsT, OutputT]` — `DepsT` is a type-only generic (not enforced at runtime). Deps are passed
as `deps=` on every `run*()` call and accessed in tools/system-prompts via `ctx.deps`. `RunContext`
has 29 fields including `deps`, `model`, `usage`, `messages`, `retry`, `run_step`, `tool_name`,
`prompt`, and v2 capability fields. Deps are fixed for the duration of a run but can be overridden
per-test via `agent.override(deps=...)` (backed by a `ContextVar`). Testing uses `TestModel` and
`capture_run_messages` context manager.

### Q8 — Results & Structured Output
[→ pydantic-ai-v2-results.md](07-pydantic-ai-v2-results.md)

`AgentRunResult` (in `run.py`) is the final result. **`result.data` is gone — use `result.output`.**
`output_type=` (renamed from `result_type=`) accepts scalars, Pydantic models, TypedDicts, unions,
and mode wrappers (`ToolOutput`, `NativeOutput`, `PromptedOutput`, `TextOutput`). Output mode is
`Literal['text','tool','native','prompted','tool_or_text','image','auto']`. Output validators are
`@agent.output_validator` (renamed from `@agent.result_validator`). The library auto-retries on
validation errors via `RetryPromptPart` (output budget default 1). `AgentRunResult` has
`all_messages()`, `new_messages()`, `all_messages_json()`, `new_messages_json()`, `usage`
(property), and `cost()` (via genai-prices). Streaming results are `StreamedRunResult` (via
`AgentStream`); consume via `stream_output()`, `stream_text()`, `stream_response()`, `get_output()`.

### Q9 — Low-Level Extensible Primitives
[→ pydantic-ai-v2-primitives.md](08-pydantic-ai-v2-primitives.md)

**`AgentModel`, `StreamTextResponse`, `StreamStructuredResponse`, `EitherStreamedResponse` are all
removed in v2.** The current primitives: `Model` (ABC, 3 abstract members), `StreamedResponse` (single
unified ABC), `WrapperModel` (delegate-all base for wrapping), `InstrumentedModel` (OTel tracing via
`WrapperModel`), `FallbackModel` (tries models in sequence, raises `FallbackExceptionGroup`),
`TestModel` and `FunctionModel` (for testing). `ModelRequestParameters` carries tool/output config
per-call (replaces `AgentModel`). Custom models implement: `async request(messages, model_settings,
model_request_parameters) -> ModelResponse`, `model_name: str` property, `system: str` property.
For streaming, also implement `async request_stream(...)` returning a `StreamedResponse` subclass
with `_get_event_iterator()`, `model_name`, `provider_name`, `provider_url`, `timestamp`. The
recommended copy-from reference for production custom models is `OpenAIChatModel`.

---

## Build vs. Reuse Decision Matrix

| Feature | Already in pydantic-ai | Needs to be built in SDK | Notes |
|---|---|---|---|
| Agent loop (request → tool execute → loop) | ✅ `_agent_graph.py` | — | `UserPromptNode→ModelRequestNode→CallToolsNode` |
| Model abstraction / swap | ✅ `Model` ABC + `infer_model()` | — | 13 concrete providers; custom via subclass |
| Tool registration (fn → JSON schema) | ✅ `Tool`, `FunctionToolset`, griffe | — | 5 registration paths, async, retry |
| RunContext / dependency injection | ✅ `RunContext`, `deps=` param | — | 29 attrs; ContextVar-backed override |
| Conversation history | ✅ `message_history=`, `all_messages()` | — | Full serialization via TypeAdapter |
| Structured output / validation | ✅ `output_type=`, `OutputValidator` | — | Tool/native/prompted modes; auto-retry |
| Usage & cost tracking | ✅ `RunUsage`, `RequestUsage`, genai-prices | — | `result.usage`, `result.cost()` |
| Streaming (text + structured) | ✅ `StreamedRunResult`, `AgentStream` | — | `stream_output()`, `stream_text()` |
| Step-through / manual control | ✅ `iter()` / `AgentRun` | — | Async iterator over graph nodes |
| Capability / middleware hooks | ✅ `AbstractCapability` (31-file subpackage) | — | Full before/after/wrap/on_error per lifecycle phase |
| Instrumentation / tracing | ✅ `InstrumentedModel`, logfire extra | — | OTel-based via `WrapperModel` |
| Model fallback / retry | ✅ `FallbackModel` | — | Exception-type-based routing |
| MCP tool integration | ✅ `MCPToolset` + `capabilities/mcp.py` | — | FastMCP-based, stdio/SSE/HTTP |
| Multi-agent (agent as tool) | ✅ via `@agent.tool` calling another agent | — | Documented in multi-agent docs |
| LangChain integration | ✅ `ext/langchain.py` | — | Thin adapter |
| Durable execution (Temporal, DBOS, Prefect) | ✅ `durable_exec/` subpackage | — | Optional extras |
| UI streaming (ag-ui, Vercel AI) | ✅ `ui/` subpackage | — | Optional extras |
| Custom model backend | ✅ `Model` ABC + `WrapperModel` | implement `request()` + `model_name` + `system` | ~50 lines for basic; copy `OpenAIChatModel` for production |
| Agent orchestration / routing | ⚠️ partial (agents-as-tools, multi-agent patterns) | Higher-level workflow/routing logic | Coordinate which agent runs when |
| State persistence between runs | ❌ not built-in | Serialize `all_messages_json()` + storage layer | Messages are in-memory by default |
| Agent registry / discovery | ❌ not built-in | Name → Agent mapping | Nothing like a service registry |
| Rate limiting / backpressure | ❌ not built-in | Wrap `FallbackModel` or `WrapperModel` | `tenacity` extra available |
| Cross-agent context / shared memory | ❌ not built-in | Pass via `deps=` or external store | No shared state primitive |
| Evaluation framework | ✅ `pydantic-evals` (separate package) | — | Part of `pydantic-ai[evals]` |
| Prompt templating | ⚠️ `spec` extra (`pydantic-handlebars`) | More complex templating | Basic f-string system prompts are native |
| Observability beyond OTel | ⚠️ `InstrumentedModel` covers OTel | Custom sinks/dashboards | OTel export pipeline is user's responsibility |

---

## Key Integration Points for SDK Authors

These are the classes/protocols to compose or subclass when building the SDK:

```python
# 1. Custom model backend — implement these 3 members:
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.messages import ModelMessage, ModelResponse, ModelSettings

class MyModel(Model):
    async def request(self, messages, model_settings, model_request_parameters) -> ModelResponse: ...
    @property
    def model_name(self) -> str: ...
    @property
    def system(self) -> str: ...

# 2. Model middleware / wrapping:
from pydantic_ai.models.wrapper import WrapperModel
class RateLimitedModel(WrapperModel):
    async def request(self, messages, settings, params):
        await self._rate_limiter.acquire()
        return await self.wrapped.request(messages, settings, params)

# 3. Custom capability (lifecycle hooks):
from pydantic_ai.capabilities.abstract import AbstractCapability
class AuditCapability(AbstractCapability):
    async def before_run(self, ctx): ...
    async def after_run(self, ctx, result): ...
    async def before_tool_execute(self, ctx, tool_call): ...

# 4. Structured output with validation:
from pydantic import BaseModel
from pydantic_ai import Agent

class MyOutput(BaseModel):
    answer: str
    confidence: float

agent = Agent(model='openai:gpt-4o', output_type=MyOutput)

@agent.output_validator
async def validate_output(ctx, output: MyOutput) -> MyOutput:
    if output.confidence < 0.5:
        raise ValueError("Low confidence — retry")
    return output

# 5. Multi-turn conversation:
result1 = await agent.run("First question", deps=my_deps)
result2 = await agent.run("Follow-up", deps=my_deps,
                          message_history=result1.all_messages())

# 6. Dependency injection:
from dataclasses import dataclass
from pydantic_ai import RunContext

@dataclass
class Deps:
    db: Database
    user_id: str

agent: Agent[Deps, str] = Agent(model='openai:gpt-4o')

@agent.tool
async def get_user_data(ctx: RunContext[Deps]) -> str:
    return await ctx.deps.db.fetch(ctx.deps.user_id)
```

---

## Quick-Start for SDK Builders — 5 Things to Know

1. **The capabilities subpackage is your primary extension point.** `AbstractCapability` gives you
   lifecycle hooks before/after every phase of a run — model requests, tool validation, tool
   execution, output validation, and output processing. Register capabilities via
   `Agent(capabilities=[...])` or per-run via `agent.run(capabilities=[...])`. Build any
   cross-cutting SDK concern (logging, rate limiting, access control, audit) as a capability.

2. **Use `WrapperModel` for model-level wrapping, not `Model` directly.** If you need to intercept
   model calls (rate limiting, caching, A/B routing, logging), subclass `WrapperModel`. It delegates
   all methods to `self.wrapped` by default — you only override what you need. `InstrumentedModel`
   and `FallbackModel` both use this pattern.

3. **History is your multi-turn primitive.** There is no built-in session store. The SDK pattern is:
   serialize with `result.all_messages_json()`, store externally, deserialize with
   `ModelMessagesTypeAdapter.validate_json()`, and pass back via `message_history=`. Build your
   session/persistence layer around this interface.

4. **`deps=` is your DI container.** Pass any object graph (database connections, config, user
   context) as `deps=` at `agent.run()` time. Tools and system-prompt functions receive it via
   `RunContext.deps`. Use `agent.override(deps=mock_deps)` in tests. This is the correct place to
   inject SDK-managed services into agent executions.

5. **`output_type=` with mode wrappers gives full output control.** Use `ToolOutput(MyModel)` for
   tool-call-based extraction (most compatible), `NativeOutput(MyModel)` for models with native JSON
   schema support, or `PromptedOutput(MyModel)` as a fallback. Register `@agent.output_validator`
   for domain-level validation with auto-retry via `RetryPromptPart`.
