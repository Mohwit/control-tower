# pydantic-ai — Low-Level Extensible Primitives & Custom Model Implementation (Q9)

Source of truth: `pydantic/pydantic-ai` @ `main` branch.
Docs site: `https://ai.pydantic.dev` now 301-redirects to `https://pydantic.dev/docs/ai/`.

> **CRITICAL API-VERSION NOTE.** The Q9 brief asks for v1-era symbols `AgentModel`,
> `StreamTextResponse`, `StreamStructuredResponse`, and `EitherStreamedResponse`. **None of
> these exist on current `main`.** They were removed in the v1→v2 refactor. The current
> low-level model API is:
> - `Model` (ABC) — methods take request parameters directly; there is **no** per-call
>   `AgentModel` wrapper any more. The role `AgentModel` used to play (carrying tools/output
>   config for a specific agent) is now filled by the `ModelRequestParameters` dataclass passed
>   into each `request()` call.
> - `StreamedResponse` (single ABC) — replaces the old split between `StreamTextResponse` and
>   `StreamStructuredResponse`; there is no `EitherStreamedResponse` union (one class handles
>   text, tool-calls, thinking, and files uniformly).
>
> Everything below documents the **actual current API**.

File references (all under `pydantic_ai_slim/pydantic_ai/`):
- `models/__init__.py` — `Model`, `StreamedResponse`, `ModelRequestParameters`, `ModelRequestContext`
- `models/wrapper.py` — `WrapperModel`, `CompletedStreamedResponse`
- `models/instrumented.py` — `InstrumentedModel`, `InstrumentationSettings`
- `models/fallback.py` — `FallbackModel`
- `models/test.py` — `TestModel`
- `models/function.py` — `FunctionModel`, `AgentInfo`, delta types
- `models/mcp_sampling.py` — `MCPSamplingModel` (reference minimal custom model)
- `messages.py` — `ModelRequest`, `ModelResponse`, parts, stream events
- `agent/__init__.py` — `@agent.system_prompt`, `@agent.instructions`, `output_validator`
- `direct.py` — low-level `model_request*` helpers

---

## 1. Abstract Base Classes and Protocols

### 1.1 `Model` (ABC)
File: `models/__init__.py` (lines ~192-658).

```python
class Model(ABC, Generic[InterfaceClient]):
    """Abstract class for a model."""

    _provider: Provider[InterfaceClient]
    _profile: ModelProfileSpec | None = None
    _settings: ModelSettings | None = None

    def __init__(self, *, settings: ModelSettings | None = None,
                 profile: ModelProfileSpec | None = None) -> None: ...
```

**Abstract members that MUST be implemented by a subclass** (decorated `@abstractmethod`):

```python
@abstractmethod
async def request(
    self,
    messages: list[ModelMessage],
    model_settings: ModelSettings | None,
    model_request_parameters: ModelRequestParameters,
) -> ModelResponse:
    """Make a request to the model."""

@property
@abstractmethod
def model_name(self) -> str:
    """The model name."""

@property
@abstractmethod
def system(self) -> str:
    """The model provider, ex: openai. Used for gen_ai.system OTel attribute."""
```

That is the entire **minimal** abstract surface: `request`, `model_name`, `system`.

**Optional/overridable (have default implementations, NOT abstract):**

```python
async def count_tokens(self, messages, model_settings, model_request_parameters) -> RequestUsage:
    # default: raises NotImplementedError. Implement to support
    # UsageLimits.count_tokens_before_request.

async def compact_messages(self, request_context: ModelRequestContext, *,
                           instructions: str | None = None) -> ModelResponse:
    # default: raises NotImplementedError. Only OpenAI Responses overrides.

@asynccontextmanager
async def request_stream(
    self,
    messages: list[ModelMessage],
    model_settings: ModelSettings | None,
    model_request_parameters: ModelRequestParameters,
    run_context: RunContext[Any] | None = None,
) -> AsyncGenerator[StreamedResponse]:
    # default: raises NotImplementedError. Implement to support streaming.

def customize_request_parameters(self, model_request_parameters) -> ModelRequestParameters:
    # default: applies the profile's json_schema_transformer to tool/output schemas.

def prepare_request(self, model_settings, model_request_parameters
                    ) -> tuple[ModelSettings | None, ModelRequestParameters]:
    # merges self.settings, runs customize_request_parameters, resolves thinking,
    # native-tool swaps, output-mode defaults. Subclass `request()` should call this first.

def prepare_messages(self, messages: list[ModelMessage]) -> list[ModelMessage]:
    # framework-called pre-processing (tool-search synthesis, non-leading system prompt wrapping).
```

**Concrete helpers / properties provided by the base class:**
- `provider -> Provider | None` (reads `_provider`)
- `settings -> ModelSettings | None`
- `model_id -> str` → `f'{self.system}:{self.model_name}'`
- `label -> str` (human-friendly display name)
- `base_url -> str | None` (default `None`)
- `profile -> ModelProfile` (`@cached_property`; resolution order: DEFAULT_PROFILE → provider profile → user `profile=` arg → intersect with `supported_native_tools()`)
- `@classmethod supported_native_tools() -> frozenset[type[AbstractNativeTool]]` (default empty)
- `async __aenter__ / __aexit__` — delegate to provider's HTTP client lifecycle
- `_get_instruction_parts(...)`, `_validate_uploaded_file_provider(...)`, `_resolve_native_tool_swap(...)` (internal)

`InterfaceClient` is the generic provider-client type (`from ..providers import InterfaceClient`).

### 1.2 `AgentModel` — DOES NOT EXIST
There is no `AgentModel` ABC on current `main`. The old `Model.agent_model(...)` → `AgentModel`
two-step was collapsed: tool/output configuration now travels per-call inside
`ModelRequestParameters` (Section 2.1), so `Model.request()` is called directly.

### 1.3 `StreamedResponse` (ABC)
File: `models/__init__.py` (lines ~661-885). This is the **single** streaming abstraction
(replaces the v1 `StreamTextResponse` / `StreamStructuredResponse` / `EitherStreamedResponse`).

```python
@dataclass
class StreamedResponse(ABC):
    """Streamed response from an LLM when calling a tool."""

    model_request_parameters: ModelRequestParameters

    final_result_event: FinalResultEvent | None = field(default=None, init=False)
    provider_response_id: str | None = field(default=None, init=False)
    provider_details: dict[str, Any] | None = field(default=None, init=False)
    finish_reason: FinishReason | None = field(default=None, init=False)

    _event_iterator: AsyncIterator[ModelResponseStreamEvent] | None = field(default=None, init=False)
    _usage: RequestUsage = field(default_factory=RequestUsage, init=False)
    _cancelled: bool = field(default=False, init=False)
    _finished: bool = field(default=False, init=False)
```

**Abstract members the subclass MUST implement:**

```python
@abstractmethod
async def _get_event_iterator(self) -> AsyncIterator[ModelResponseStreamEvent]:
    """Translate the vendor stream into pydantic_ai ModelResponseStreamEvents.
    Use self._parts_manager to handle deltas and update self._usage."""

@property
@abstractmethod
def model_name(self) -> str: ...

@property
@abstractmethod
def provider_name(self) -> str | None: ...

@property
@abstractmethod
def provider_url(self) -> str | None: ...

@property
@abstractmethod
def timestamp(self) -> datetime: ...
```

(Note the in-source `TODO: We should not have public private methods which need to be
overwritten.` above `_get_event_iterator` — the framework authors flag this leading-underscore
abstract method as a wart.)

**Concrete members provided:**
- `def __aiter__(self) -> AsyncIterator[ModelResponseStreamEvent]` — wraps `_get_event_iterator()`
  with three composed generators: `iterator_with_final_event` (emits `FinalResultEvent` on first
  output match), `iterator_with_part_end` (emits `PartEndEvent`), and `iterator_with_cancel_guard`
  (suppresses transport errors on cancel; flips `_finished=True` only on natural completion).
- `@cached_property _parts_manager -> ModelResponsePartsManager` — built lazily from
  `model_request_parameters`; auto-promotes streamed `ToolCallPart`s to typed subclasses.
- `def get(self) -> ModelResponse` — assembles the `ModelResponse` from parts collected so far;
  sets `state` to `'complete'` (`_finished`), `'interrupted'` (`_cancelled`), or `'incomplete'`.
- `@property usage -> RequestUsage`
- `@property cancelled -> bool`
- `async def cancel(self) -> None` — sets `_cancelled` then calls `close_stream()`.
- `def get_stream_cancel_errors(self) -> tuple[type[BaseException], ...]` — default
  `(httpx.StreamError, httpx.TransportError)`; override for gRPC/botocore transports.
- `async def close_stream(self) -> None` — **must be overridden** to support cancellation
  (default raises `NotImplementedError`); tears down the underlying connection.

### 1.4 Module-level globals / functions (`models/__init__.py`)
- `ALLOW_MODEL_REQUESTS: bool = True` — global kill-switch.
- `check_allow_model_requests() -> None` — raises `RuntimeError` if disabled; call this inside
  your custom `request()`/`request_stream()` if the model has real cost/latency.
- `@contextmanager override_allow_model_requests(allow: bool)`.
- `infer_model(model: Model | KnownModelName | str, provider_factory=infer_provider) -> Model`.
- `infer_model_profile(model: str) -> ModelProfile`.
- `parse_model_id(model: str) -> tuple[str | None, str]`.
- `known_model_names() -> tuple[str, ...]`.
- `create_async_http_client(*, timeout=600, connect=5) -> httpx.AsyncClient`.
- `async download_item(item: FileUrl, data_format=..., type_format=...) -> DownloadedItem` (SSRF-protected).
- `get_user_agent() -> str`.
- `DEFAULT_HTTP_TIMEOUT: int = 600`.

---

## 2. `ModelRequestParameters` and `ModelRequestContext`

### 2.1 `ModelRequestParameters` (the per-request tool/output config)
File: `models/__init__.py` (lines ~121-175). This dataclass is what replaced v1 `AgentModel`'s role.

```python
@dataclass(repr=False, kw_only=True)
class ModelRequestParameters:
    """Configuration for an agent's request to a model, related to tools and output handling."""

    function_tools: list[ToolDefinition] = field(default_factory=list[ToolDefinition])
    native_tools: list[AbstractNativeTool] = field(default_factory=list[AbstractNativeTool])

    output_mode: OutputMode = 'text'
    output_object: OutputObjectDefinition | None = None
    output_tools: list[ToolDefinition] = field(default_factory=list[ToolDefinition])
    prompted_output_template: str | Literal[False] | None = None
    allow_text_output: bool = True
    allow_image_output: bool = False

    instruction_parts: list[InstructionPart] | None = None
    thinking: ThinkingLevel | None = None

    @cached_property
    def tool_defs(self) -> dict[str, ToolDefinition]: ...        # name -> ToolDefinition
    @cached_property
    def prompted_output_instructions(self) -> str | None: ...
    def with_default_output_mode(self, output_mode: StructuredOutputMode) -> ModelRequestParameters: ...
```

### 2.2 `ModelRequestContext` (hook payload)
File: `models/__init__.py` (lines ~178-189). Passed to `compact_messages` and used by
`InstrumentedModel` as a future-proof bundle of request inputs.

```python
@dataclass(kw_only=True)
class ModelRequestContext:
    model: Model
    messages: list[ModelMessage]
    model_settings: ModelSettings | None
    model_request_parameters: ModelRequestParameters
```

---

## 3. `ModelRequest` — full definition
File: `messages.py` (lines ~1503-1549).

```python
@dataclass(repr=False)
class ModelRequest:
    """A request generated by Pydantic AI and sent to a model."""

    parts: Sequence[ModelRequestPart]
    _: KW_ONLY
    timestamp: datetime | None = None
    instructions: str | None = None
    kind: Literal['request'] = 'request'
    run_id: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] | None = None
    state: ModelRequestState = 'complete'   # Literal['complete', 'interrupted']

    @classmethod
    def user_text_prompt(cls, user_prompt: str, *, instructions: str | None = None) -> ModelRequest: ...
```

**`ModelRequestPart` union** (`messages.py` ~1997, discriminated on `part_kind`):
`SystemPromptPart | UserPromptPart | ToolSearchReturnPart | LoadCapabilityReturnPart |
ToolReturnPart | RetryPromptPart`. (Note: `InstructionPart` exists as a separate metadata-bearing
type used inside `ModelRequestParameters.instruction_parts`, not in this union.)

---

## 4. `ModelResponse` — full definition
File: `messages.py` (lines ~2053-2200).

```python
@dataclass(repr=False)
class ModelResponse:
    """A response from a model."""

    parts: Sequence[ModelResponsePart]
    _: KW_ONLY
    usage: RequestUsage = field(default_factory=RequestUsage)
    model_name: str | None = None
    timestamp: datetime = field(default_factory=_now_utc)
    kind: Literal['response'] = 'response'
    provider_name: str | None = None
    provider_url: str | None = None
    provider_details: dict[str, Any] | None = None   # alias-compatible w/ legacy 'vendor_details'
    provider_response_id: str | None = None           # alias-compatible w/ legacy 'vendor_id'
    finish_reason: FinishReason | None = None
    run_id: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] | None = None
    state: ModelResponseState = 'complete'            # Literal['complete','incomplete','interrupted']
```

Convenience properties/methods: `text`, `thinking`, `files`, `images`, `tool_calls`,
`native_tool_calls`, `cost()` (via genai-prices), `otel_message_parts(settings)`.

**`ModelResponsePart` union** (`messages.py` ~2036, discriminated via callable `_model_response_part_discriminator`):
`TextPart | ToolSearchCallPart | LoadCapabilityCallPart | ToolCallPart | NativeToolSearchCallPart |
NativeToolCallPart | NativeToolSearchReturnPart | NativeToolReturnPart | ThinkingPart |
CompactionPart | FilePart`.

**`ModelMessage`** = `Annotated[ModelRequest | ModelResponse, pydantic.Discriminator('kind')]`
(`messages.py` ~2258). TypeAdapter: `ModelMessagesTypeAdapter`.

Key part shapes used in custom models:
```python
@dataclass(repr=False)
class TextPart:
    content: str
    _: KW_ONLY
    id: str | None = None
    provider_name: str | None = None
    provider_details: dict[str, Any] | None = None
    part_kind: Literal['text'] = 'text'

@dataclass(repr=False)
class BaseToolCallPart:
    tool_name: str
    args: str | dict[str, Any] | None = None
    tool_call_id: str = field(default_factory=_generate_tool_call_id)
    _: KW_ONLY
    tool_kind: ToolPartKind | None = None
    id: str | None = None
    # ...
class ToolCallPart(BaseToolCallPart):
    _: KW_ONLY
    part_kind: Literal['tool-call'] = 'tool-call'
```

**How they are constructed during a run:** `_agent_graph.ModelRequestNode._make_request` calls
`model.prepare_messages(...)` then `model.request(...)` (or `request_stream`). The model returns a
`ModelResponse`; for streaming, `StreamedResponse.get()` assembles a `ModelResponse` from the
`ModelResponsePartsManager`. (See `Model.request` docstring: "ultimately called by
`pydantic_ai._agent_graph.ModelRequestNode._make_request(...)`".)

---

## 5. Custom Model Implementation Guide

### 5.1 Minimal interface
To write a custom **non-streaming** model backend, subclass `Model` and implement exactly three
members: `request()` (async), `model_name` (property), `system` (property). Recommended first line
of `request()`: `model_settings, model_request_parameters = self.prepare_request(model_settings,
model_request_parameters)` and (if real cost) `check_allow_model_requests()`.

To add **streaming**, also: (a) subclass `StreamedResponse` implementing `_get_event_iterator`,
`model_name`, `provider_name`, `provider_url`, `timestamp` (and ideally `close_stream`); and
(b) override `Model.request_stream` as an `@asynccontextmanager` that yields your `StreamedResponse`.

The official docs are sparse and explicitly say: *"The best place to start is to review the source
code for existing implementations, e.g. `OpenAIChatModel`"* and *"If a model API is compatible with
the OpenAI API, you do not need a custom model class — provide a custom provider instead."*
(`https://pydantic.dev/docs/ai/models/overview/`). The simplest in-repo reference is
`models/mcp_sampling.py::MCPSamplingModel`.

### 5.2 Complete working example (non-streaming + streaming)

```python
from __future__ import annotations
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic_ai import usage
from pydantic_ai._run_context import RunContext
from pydantic_ai.messages import (
    ModelMessage, ModelRequest, ModelResponse, ModelResponseStreamEvent,
    TextPart, UserPromptPart,
)
from pydantic_ai.models import (
    Model, ModelRequestParameters, StreamedResponse, check_allow_model_requests,
)
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage
from pydantic_ai._utils import now_utc


class EchoModel(Model):
    """A trivial custom backend that echoes the last user prompt in upper-case."""

    def __init__(self, *, settings: ModelSettings | None = None) -> None:
        super().__init__(settings=settings)

    # ---- required abstract members ----
    @property
    def model_name(self) -> str:
        return 'echo-1'

    @property
    def system(self) -> str:
        return 'echo'                       # used for the gen_ai.system OTel attribute

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        check_allow_model_requests()
        # merge settings + apply schema transforms + resolve output mode/thinking:
        model_settings, model_request_parameters = self.prepare_request(
            model_settings, model_request_parameters
        )
        text = self._last_user_text(messages).upper()
        return ModelResponse(
            parts=[TextPart(content=text)],
            model_name=self.model_name,
            provider_name=self.system,
            usage=RequestUsage(input_tokens=len(text), output_tokens=len(text)),
        )

    # ---- optional: streaming support ----
    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncGenerator[StreamedResponse]:
        check_allow_model_requests()
        model_settings, model_request_parameters = self.prepare_request(
            model_settings, model_request_parameters
        )
        text = self._last_user_text(messages).upper()
        yield EchoStreamedResponse(
            model_request_parameters=model_request_parameters,
            _model_name=self.model_name,
            _text=text,
        )

    @staticmethod
    def _last_user_text(messages: list[ModelMessage]) -> str:
        for m in reversed(messages):
            if isinstance(m, ModelRequest):
                for p in m.parts:
                    if isinstance(p, UserPromptPart) and isinstance(p.content, str):
                        return p.content
        return ''


@dataclass
class EchoStreamedResponse(StreamedResponse):
    _model_name: str
    _text: str
    _timestamp: datetime = field(default_factory=now_utc)

    async def _get_event_iterator(self) -> AsyncIterator[ModelResponseStreamEvent]:
        # Feed deltas through the parts manager so consumers see typed parts + correct events.
        for chunk in self._text.split(' '):
            self._usage += usage.RequestUsage(output_tokens=1)
            for event in self._parts_manager.handle_text_delta(
                vendor_part_id='content', content=chunk + ' '
            ):
                yield event

    async def close_stream(self) -> None:
        # No real connection; cancellation is a no-op.
        pass

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def provider_name(self) -> str | None:
        return 'echo'

    @property
    def provider_url(self) -> str | None:
        return None

    @property
    def timestamp(self) -> datetime:
        return self._timestamp


# usage:
# from pydantic_ai import Agent
# agent = Agent(EchoModel())
# print(agent.run_sync('hello world').output)   # -> 'HELLO WORLD'
```

Notes confirmed from source:
- `prepare_request` is concrete on the base and does settings merge + schema transform +
  output-mode/thinking resolution + native-tool swap. `TestModel`/`FunctionModel` both call it
  first in their `request()` (`models/test.py` ~122, `models/function.py` ~133).
- Streaming deltas are pushed via `self._parts_manager.handle_text_delta / handle_tool_call_delta /
  handle_thinking_delta / handle_part` (see `FunctionStreamedResponse._get_event_iterator`,
  `models/function.py` ~316-359).
- `StreamedResponse.get()` (base) builds the final `ModelResponse` automatically; you usually do
  NOT override it (durable-exec `CompletedStreamedResponse` is the exception).

### 5.3 OpenAI-compatible shortcut
For any OpenAI-compatible API, skip the custom `Model` entirely and pass a custom `Provider`
to `OpenAIChatModel` / `OpenAIResponsesModel` (per docs). `infer_model` routes `openai-chat` and
the `OpenAIChatCompatibleProvider` literals (`alibaba, azure, cerebras, deepseek, fireworks,
github, heroku, litellm, moonshotai, nebius, ollama, openrouter, ovhcloud, sambanova, together,
vercel`) to `OpenAIChatModel` (`models/__init__.py` ~1027).

---

## 6. Middleware / Interception — the Wrapper pattern

### 6.1 `WrapperModel`
File: `models/wrapper.py` (lines ~65-159). The base interception primitive — "Does nothing on its
own, used as a base class." It delegates **every** `Model` method to `self.wrapped` and forwards
unknown attributes via `__getattr__`. Subclass it and override only the methods you want to
intercept (e.g. wrap `request`/`request_stream`).

```python
@dataclass(init=False)
class WrapperModel(Model):
    wrapped: Model
    def __init__(self, wrapped: Model | KnownModelName):
        super().__init__()
        self.wrapped = infer_model(wrapped)
    # forwards: __aenter__/__aexit__, request, count_tokens, compact_messages,
    # request_stream, customize_request_parameters, prepare_request, prepare_messages,
    # provider, model_name, system, profile, settings, and __getattr__.
```

### 6.2 `InstrumentedModel` (the canonical interception use)
File: `models/instrumented.py` (lines ~236+). Subclasses `WrapperModel`; wraps `request` /
`request_stream` in an OpenTelemetry span via `open_model_request_span(...)`. It builds a
`ModelRequestContext` from the call args, opens the span, calls the wrapped model, then `finish(response)`.
This is the concrete `before_model_call` / `after_model_call` pattern — there is **no** separate
hook-registration API; you intercept by subclassing `WrapperModel` (or by attaching the
`Instrumentation` capability — see below).

### 6.3 `InstrumentationSettings`
File: `models/instrumented.py` (lines ~52-156).

```python
class InstrumentationSettings:
    tracer: Tracer
    include_binary_content: bool = True
    include_content: bool = True
    version: Literal[2, 3, 4, 5] = DEFAULT_INSTRUMENTATION_VERSION   # default 5
    use_aggregated_usage_attribute_names: bool = True

    def __init__(self, *, tracer_provider=None, meter_provider=None,
                 include_binary_content=True, include_content=True,
                 version=DEFAULT_INSTRUMENTATION_VERSION,
                 use_aggregated_usage_attribute_names=True): ...
```
Versions 2/3/4 are deprecated (emit `PydanticAIDeprecationWarning`); 5 is current. Used in three
places (per docstring): the `Instrumentation` capability, `Agent.instrument` / `Agent.instrument_all()`,
and `InstrumentedModel`.

### 6.4 The `instrument=` parameter & `instrument_all()`
`Agent(..., instrument=True | InstrumentationSettings(...))` and the class method
`Agent.instrument_all(...)` turn on OTel/logfire by wrapping the model in `InstrumentedModel`
(plumbed through the `pydantic_ai.capabilities.instrumentation.Instrumentation` capability).
`InstrumentationSettings.__init__` notes it's used in `Agent.instrument` / `Agent.instrument_all()`.

### 6.5 Other wrapper-pattern models
- `mcp_sampling.MCPSamplingModel` — a real minimal `Model` that delegates generation to an MCP
  server's sampling endpoint (good reference for a from-scratch custom model).
- Durable-exec wrappers (`durable_exec/temporal/_model.py`, `prefect/_model.py`, `dbos/_model.py`)
  wrap a model for Temporal/Prefect/DBOS and use `CompletedStreamedResponse` (`models/wrapper.py`
  ~20-62) when the real stream is consumed inside an activity and only the final `ModelResponse`
  is returned.

---

## 7. Streaming Abstractions — detailed walkthrough

`StreamedResponse` (Section 1.3) is the only streaming class. The flow:

1. `Model.request_stream` (your `@asynccontextmanager`) constructs and `yield`s your
   `StreamedResponse` subclass, passing `model_request_parameters`.
2. Consumer iterates `async for event in streamed_response:`. `__aiter__` lazily builds the
   composed pipeline once: `iterator_with_cancel_guard(iterator_with_part_end(
   iterator_with_final_event(self._get_event_iterator())))`.
3. Your `_get_event_iterator()` translates vendor chunks into `ModelResponseStreamEvent`s, pushing
   deltas through `self._parts_manager` (which auto-promotes tool-call parts to typed subclasses)
   and accumulating `self._usage`.
4. `iterator_with_final_event` watches for the first part that satisfies the output schema and
   emits a `FinalResultEvent`; `iterator_with_part_end` emits `PartEndEvent`s for
   `TextPart`/`ThinkingPart`/`BaseToolCallPart`; `iterator_with_cancel_guard` flips `_finished`.
5. `get()` returns a `ModelResponse` assembled from `_parts_manager.get_parts()` with the correct
   lifecycle `state`.
6. `cancel()` → sets `_cancelled` → `close_stream()` (you must override `close_stream` to actually
   stop generation/billing; default raises).

**`ModelResponseStreamEvent`** = `Annotated[PartStartEvent | PartDeltaEvent | PartEndEvent |
FinalResultEvent, pydantic.Discriminator('event_kind')]` (`messages.py` ~2681).
Part deltas: `TextPartDelta`, `ThinkingPartDelta`, `ToolCallPartDelta`
(union `ModelResponsePartDelta`, `messages.py` ~2591).

`Parts manager` API surfaced to custom streamers (from `FunctionStreamedResponse`):
`handle_text_delta(vendor_part_id, content)`, `handle_thinking_delta(vendor_part_id, content,
signature, provider_name)`, `handle_tool_call_delta(vendor_part_id, tool_name, args, tool_call_id)`,
`handle_part(vendor_part_id, part)`, `get_parts()`.

---

## 8. `FallbackModel` — how it works
File: `models/fallback.py`. Subclasses `Model` (NOT `WrapperModel`); holds `models: list[Model]`.

```python
@dataclass(init=False)
class FallbackModel(Model):
    models: list[Model]
    def __init__(self, default_model: Model | KnownModelName | str,
                 *fallback_models: Model | KnownModelName | str,
                 fallback_on: FallbackOn = (ModelAPIError,)): ...
```

`FallbackOn` (`fallback.py` ~33) accepts: an exception type, a tuple of exception types, an
**exception handler** `(Exception) -> bool` (sync or async), a **response handler**
`(ModelResponse) -> bool` (sync or async), or a sequence mixing these. Handler kind is auto-detected
by type-hint inspection: if the first parameter is annotated exactly `ModelResponse` it is a
response handler, else an exception handler (`_is_response_handler`, ~50). Empty `fallback_on`
raises `UserError`.

`request()` (~212): iterates `self.models`; for each it runs `model.prepare_request(...)` and
`model.prepare_messages(...)` (per-model, since each has its own profile), then `model.request(...)`.
On exception → if `_should_fallback(exc)` collect & continue, else re-raise. On success → if a
response handler says `_should_fallback(response)` collect as rejected & continue, else set span
attributes and return. If all fail → `_raise_fallback_exception_group(...)` raises
`FallbackExceptionGroup` (with a `ResponseRejected` entry counting rejected responses).
`request_stream()` (~246) mirrors this with an `AsyncExitStack`.

Identity/properties: `model_name` / `model_id` / `system` are `f'fallback:{...joined...}'`;
`base_url` = first model's; `provider` = `None`; `profile` raises `NotImplementedError`
(no own profile, so `prepare_messages` defers to each inner model). `__aenter__`/`__aexit__` use a
reference-counted `AsyncExitStack` (`_enter_lock` is a lazy `anyio.Lock` to bind to the right loop,
Temporal-safe). Docs: *"use `FallbackModel` to attempt multiple models in sequence until one succeeds."*

---

## 9. `TestModel` and `FunctionModel`

### 9.1 `TestModel` (`models/test.py`)
```python
@dataclass(init=False)
class TestModel(Model):
    __test__ = False                      # avoid pytest discovery
    call_tools: list[str] | Literal['all'] = 'all'
    custom_output_text: str | None = None
    custom_output_args: Any | None = None
    seed: int = 0
    last_model_request_parameters: ModelRequestParameters | None = None   # init=False
    def __init__(self, *, call_tools='all', custom_output_text=None,
                 custom_output_args=None, seed=0, model_name='test',
                 profile=None, settings=None): ...
```
Behavior: by default calls **all** available tools (or the named subset in `call_tools`), then
returns a tool/output response if possible, otherwise plain text. `custom_output_text` forces final
text; `custom_output_args` forces output-tool args; `seed` drives random structured data.
`last_model_request_parameters` records the params from the last request (useful for assertions).
`system` is `'test'`. Implements `request` and `request_stream` (yielding `TestStreamedResponse`),
calling `self.prepare_request(...)` first. `supported_native_tools()` returns the full set for
testing flexibility. Not gated by `ALLOW_MODEL_REQUESTS`.

### 9.2 `FunctionModel` (`models/function.py`)
```python
@dataclass(init=False)
class FunctionModel(Model):
    function: FunctionDef | None
    stream_function: StreamFunctionDef | None
    def __init__(self, function=None, *, stream_function=None,
                 model_name=None, profile=None, settings=None): ...
        # Either function or stream_function required (both allowed).
        # Default profile: supports_json_schema_output=True, supports_json_object_output=True.
```
Lets you script model behavior with a plain function:
```python
FunctionDef       = Callable[[list[ModelMessage], AgentInfo], ModelResponse | Awaitable[ModelResponse]]
StreamFunctionDef = Callable[[list[ModelMessage], AgentInfo],
                             AsyncIterator[str | DeltaToolCalls | DeltaThinkingCalls | BuiltinToolCallsReturns]]
```
`request()` builds an `AgentInfo` and calls `function`; `request_stream()` wraps `stream_function`
output in `FunctionStreamedResponse`. `system='function'`; estimates usage if the function didn't set it.

`AgentInfo` (frozen dataclass passed as 2nd arg):
```python
@dataclass(frozen=True, kw_only=True)
class AgentInfo:
    function_tools: list[ToolDefinition]
    allow_text_output: bool
    output_tools: list[ToolDefinition]
    model_settings: ModelSettings | None
    model_request_parameters: ModelRequestParameters
    instructions: str | None
```
Streaming delta primitives (`function.py` ~250-303): `DeltaToolCall(name, json_args, tool_call_id)`,
`DeltaThinkingPart(content, signature)`; aliases `DeltaToolCalls = dict[int, DeltaToolCall]`,
`DeltaThinkingCalls = dict[int, DeltaThinkingPart]`,
`BuiltinToolCallsReturns = dict[int, NativeToolCallPart | NativeToolReturnPart]`. A stream function
must yield homogeneously (all text, OR all `DeltaToolCalls`, OR all `DeltaThinkingCalls`, OR all
`BuiltinToolCallsReturns`).

---

## 10. System-Prompt & Other Extension Points

### 10.1 `@agent.system_prompt` decorator
File: `agent/__init__.py` (lines ~1907-1980).
```python
def system_prompt(self, func=None, /, *, dynamic: bool = False
                  ) -> Callable[[SystemPromptFunc], SystemPromptFunc] | SystemPromptFunc:
```
Usable bare (`@agent.system_prompt`) or called (`@agent.system_prompt(dynamic=True)`). The decorated
function may be sync or async and may optionally take a single `RunContext[AgentDepsT]` arg.
`dynamic=True` re-evaluates the prompt even when `message_history` is provided (linked to
`SystemPromptPart.dynamic_ref`). Registers a `_system_prompt.SystemPromptRunner` on the agent.
```python
@agent.system_prompt
def simple() -> str: return 'foobar'

@agent.system_prompt(dynamic=True)
async def with_deps(ctx: RunContext[str]) -> str: return f'{ctx.deps} is the best'
```

### 10.2 `@agent.instructions` decorator
File: `agent/__init__.py` (lines ~1817-1876). Same calling conventions as `system_prompt`
(sync/async, optional `RunContext`). Instructions differ from system prompts: they are NOT preserved
in message history across runs and feed `ModelRequestParameters.instruction_parts` /
`ModelRequest.instructions`. The static/dynamic distinction is carried by `InstructionPart`
(`messages.py` ~1464; `dynamic: bool`), enabling cache-boundary placement for providers like Anthropic.

### 10.3 `@agent.output_validator` decorator
File: `agent/__init__.py` (~1982+). Registers a post-generation validator
`(RunContext, OutputDataT) -> OutputDataT` (sync/async; `RunContext` optional). Raise
`ModelRetry` to force a re-request. This is the custom result-parser/validation hook.

### 10.4 Custom message types / parts
Parts are discriminated unions (`ModelRequestPart`, `ModelResponsePart`) keyed on `part_kind`
(+ `tool_kind` for typed tool-call subclasses via `_TYPED_PART_TAGS`). The framework registers typed
subclasses through narrowers (`ToolCallPart.narrow_type`, `_TOOL_CALL_NARROWERS`). There is **no
public registration API** for third-party message-part types; extension is intended via the
capabilities/toolsets system, not new wire parts.

### 10.5 Model profiles — `ModelProfile` / `ModelProfileSpec`
A `Model` accepts `profile=` (a partial `ModelProfile` dict OR a callable `(default) -> profile`).
`Model.profile` resolves: `DEFAULT_PROFILE` → provider profile → user override → intersect with
`supported_native_tools()`. Profiles carry `json_schema_transformer`, `supports_tools`,
`supports_json_schema_output`, `default_structured_output_mode`, `supports_thinking`,
`supported_native_tools`, etc. This is the primary per-model behavior-customization point.

### 10.6 Capabilities & Toolsets (the real v2 plugin systems)
Current `main` introduces two large pluggable subsystems (each with `abstract.py` + a `wrapper.py`
decorator base):
- **Capabilities** (`pydantic_ai/capabilities/`): `AbstractCapability` (`abstract.py`),
  `WrapperCapability` (`wrapper.py`), `CombinedCapability` (`combined.py`), plus concrete
  capabilities (`instrumentation.py`, `mcp.py`, `web_search.py`, `web_fetch.py`,
  `image_generation.py`, `thinking.py`, `prepare_tools.py`, `process_history.py`,
  `process_event_stream.py`, `reinject_system_prompt.py`, `prefix_tools.py`, `set_tool_metadata.py`,
  `include_return_schemas.py`, `deferred_tool_handler.py`, `hooks.py`, etc.). This is the v2
  extension/plugin framework — behaviors are composed by attaching capabilities to an agent.
- **Toolsets** (`pydantic_ai/toolsets/`): `AbstractToolset` (`abstract.py`), `WrapperToolset`
  (`wrapper.py`), `CombinedToolset`, `FunctionToolset`, `FilteredToolset`, `PrefixedToolset`,
  `RenamedToolset`, `PreparedToolset`, `ApprovalRequiredToolset`, `ExternalToolset`,
  `DeferredLoadingToolset`, etc. Pluggable, wrappable tool sources.

### 10.7 Low-level direct API (`pydantic_ai/direct.py`)
Bypass the `Agent` graph entirely and call a model directly:
- `async model_request(model, messages, *, ...) -> ModelResponse`
- `model_request_sync(model, messages, *, ...) -> ModelResponse`
- `model_request_stream(model, messages, *, ...)` (async CM yielding `StreamedResponse`)
- `model_request_stream_sync(model, messages, *, ...) -> StreamedResponseSync`
These are the lowest-level public primitives for invoking a `Model` without an agent.

### 10.8 LangChain bridge
`ext/langchain.py` adapts LangChain tools into pydantic-ai. `common_tools/` ships ready-made tools
(duckduckgo, exa, tavily, web_fetch, x_search, image_generation).

---

## Self-Validation (Task 10)
- Every ABC has complete signatures: `Model` (3 abstract + all concrete) ✓; `StreamedResponse`
  (5 abstract + concrete) ✓. `AgentModel`/`StreamTextResponse`/`StreamStructuredResponse`/
  `EitherStreamedResponse` confirmed **non-existent** on `main` (removed in v2) ✓.
- Custom-model guide is complete and runnable: minimal interface (`request`, `model_name`,
  `system`) + streaming (`request_stream` + `StreamedResponse` subclass) with a full working
  `EchoModel` example ✓.
- Streaming abstractions documented (pipeline, parts manager, events, cancel) ✓.
- Extension points enumerated: WrapperModel/InstrumentedModel interception, FallbackModel,
  Test/FunctionModel, profiles, `system_prompt`/`instructions`/`output_validator` decorators,
  capabilities + toolsets subsystems, `direct.py` ✓.

## Caveats / limits of this pass
- `OpenAIChatModel`/`anthropic`/`google` concrete adapters were NOT read line-by-line (out of Q9
  scope; they are the recommended copy-from references for production custom models).
- The `capabilities/` subsystem is summarized from filenames + cross-references, not a full read of
  each capability module.
- The docs site is mid-migration (ai.pydantic.dev → pydantic.dev/docs/ai); the dedicated "custom
  models" page is thin and defers to source — source was used as the authority throughout.
