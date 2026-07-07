# pydantic-ai v2 — Q1 (Package Surface Area) + Q2 (Model Abstraction Layer)

Research date: 2026-06-30. Target: pydantic-ai **v2.1.0** (main branch).
Sources: PyPI JSON API, GitHub `main` raw source (`pydantic_ai_slim/pydantic_ai/...`).

> Note on scope vs. original task list: in v2 the package was restructured. `gemini.py` and
> `vertexai.py no longer exist as standalone model files — Gemini/Vertex are served by `google.py`
> (`GoogleModel`). `ollama.py` still exists but is a thin subclass of `OpenAIChatModel`. The
> `KnownModelName` alias moved out of `models/__init__.py` into `models/_known_model_names.py`.
> `agent.py` is now the package `pydantic_ai/agent/__init__.py`. All findings below reflect the
> actual v2 layout, confirmed via the GitHub contents API directory listing.

---

# 1. Package Surface Area (Q1)

## 1.1 Version & PyPI metadata
- **`pydantic-ai`**: version **2.1.0**. Summary: "Agent Framework / shim to use Pydantic with LLMs."
  Python `>=3.10`. This is an **umbrella meta-package** — it has almost no code of its own; it
  pulls in `pydantic-ai-slim` with a broad set of extras.
  - Source: https://pypi.org/pypi/pydantic-ai/json
- **`pydantic-ai-slim`**: version **2.1.0**. This is the **real codebase** (all the source files
  referenced below live here). Installing slim lets you pick only the provider extras you need.
  - Source: https://pypi.org/pypi/pydantic-ai-slim/json

`pydantic-ai` (umbrella) depends on:
- `pydantic-ai-slim[anthropic,cli,evals,google,logfire,mcp,openai,retries,web]==2.1.0`
- `pydantic-ai-slim[ag-ui]==2.1.0`
(So a plain `pip install pydantic-ai` gives you OpenAI + Anthropic + Google + MCP + CLI + evals + logfire + retries + web + ag-ui out of the box.)

## 1.2 `pydantic-ai-slim` required (non-optional) dependencies
Source: https://pypi.org/pypi/pydantic-ai-slim/json (`requires_dist`)
- `pydantic>=2.12`
- `pydantic-graph==2.1.0`
- `griffelib>=2.0`
- `httpx>=0.27`
- `genai-prices>=0.0.62`
- `opentelemetry-api>=1.28.0`
- `typing-inspection>=0.4.0`
- `exceptiongroup>=1.2.2` (only on Python < 3.11)

## 1.3 All optional extras (dependency groups) on `pydantic-ai-slim`
Source: https://pypi.org/pypi/pydantic-ai-slim/json

| Extra | Packages pulled in |
|-------|--------------------|
| `ag-ui` | `ag-ui-protocol>=0.1.10`, `starlette>=0.46.2` |
| `anthropic` | `anthropic>=0.108.0` |
| `bedrock` | `boto3>=1.42.63` |
| `cli` | `argcomplete>=3.5.0`, `prompt-toolkit>=3`, `pyperclip>=1.9.0`, `pyyaml>=6.0.2`, `rich>=13` |
| `cohere` | `cohere>=5.20.6` (platform-gated) |
| `dbos` | `dbos>=2.10.0` |
| `duckduckgo` | `ddgs>=9.0.0` |
| `evals` | `pydantic-evals==2.1.0` |
| `exa` | `exa-py>=2.0.0` |
| `google` | `google-genai>=1.70.0` |
| `groq` | `groq>=0.25.0` |
| `huggingface` | `huggingface-hub>=1.3.4,<2.0.0`, `hf-xet<1.5.0` |
| `logfire` | `logfire[httpx]>=4.16.0` |
| `mcp` | `fastmcp-slim[client]>=3.3.0` |
| `mistral` | `mistralai>=2.0.0,!=2.4.6` |
| `openai` | `openai>=2.29.0`, `tiktoken>=0.12.0` |
| `openrouter` | `openai>=2.8.0` |
| `prefect` | `prefect>=3.6.13` |
| `retries` | `tenacity>=8.2.3` |
| `sentence-transformers` | `sentence-transformers>=5.2.0` (Python < 3.14) |
| `spec` | `pydantic-handlebars>=0.1.0`, `pyyaml>=6.0.2` |
| `tavily` | `tavily-python>=0.5.0` |
| `temporal` | `temporalio>=1.24.0` |
| `ui` | `starlette>=0.46.2` |
| `voyageai` | `voyageai>=0.3.7` (Python < 3.14) |
| `web` | `httpx>=0.27.0`, `starlette>=0.46.2`, `uvicorn>=0.38.0` |
| `web-fetch` | `markdownify>=1.2` |
| `xai` | `xai-sdk>=1.14.0` |

The umbrella `pydantic-ai` additionally exposes an `examples` extra (`pydantic-ai-examples==2.1.0`).

## 1.4 Models sub-package layout
Files in `pydantic_ai_slim/pydantic_ai/models/` (GitHub contents API, ref=main):
```
__init__.py                       # Model ABC, infer_model, StreamedResponse, ModelRequestParameters
_known_model_names.py             # KnownModelName Literal alias
_tool_choice.py
_anthropic_bedrock_count_tokens.py
anthropic.py    bedrock.py    cerebras.py   cohere.py    fallback.py
function.py     google.py     groq.py       huggingface.py
mcp_sampling.py mistral.py    ollama.py     openai.py    openrouter.py
test.py         xai.py        wrapper.py    instrumented.py   concurrency.py
```
Notable: no `gemini.py`, no `vertexai.py` (folded into `google.py`); `cerebras.py`,
`openrouter.py`, `huggingface.py`, `xai.py`, `mcp_sampling.py` are new in v2.

## 1.5 Public API — full top-level `__all__`
Source: https://raw.githubusercontent.com/pydantic/pydantic-ai/main/pydantic_ai_slim/pydantic_ai/__init__.py

Complete `__all__` (verbatim, in order):

```python
__all__ = (
    '__version__',
    # agent
    'Agent', 'AgentModelSettings', 'AgentRetries', 'AgentSpec', 'EndStrategy',
    'CallToolsNode', 'ModelRequestNode', 'UserPromptNode', 'capture_run_messages',
    'InstrumentationSettings',
    # embeddings
    'Embedder', 'EmbeddingModel', 'EmbeddingSettings', 'EmbeddingResult',
    # concurrency
    'AbstractConcurrencyLimiter', 'AnyConcurrencyLimit', 'ConcurrencyLimit',
    'ConcurrencyLimitedModel', 'ConcurrencyLimiter', 'limit_model_concurrency',
    # exceptions
    'AgentRunError', 'CallDeferred', 'ApprovalRequired', 'ConcurrencyLimitExceeded',
    'ModelRetry', 'ModelAPIError', 'ModelHTTPError', 'FallbackExceptionGroup',
    'IncompleteToolCall', 'SkipModelRequest', 'SkipToolExecution', 'SkipToolValidation',
    'UndrainedPendingMessagesError', 'UnexpectedModelBehavior', 'UsageLimitExceeded', 'UserError',
    # messages / content / events
    'AgentStreamEvent', 'AudioFormat', 'AudioMediaType', 'AudioUrl',
    'BaseToolCallPart', 'BaseToolReturnPart', 'BinaryContent',
    'NativeToolCallPart', 'NativeToolReturnPart', 'CachePoint', 'CompactionPart',
    'DocumentFormat', 'DocumentMediaType', 'DocumentUrl', 'FileUrl', 'FilePart',
    'FinalResultEvent', 'FinishReason', 'FunctionToolCallEvent', 'FunctionToolResultEvent',
    'HandleResponseEvent', 'ImageFormat', 'ImageMediaType', 'ImageUrl', 'BinaryImage',
    'InstructionPart', 'ModelMessage', 'ModelMessagesTypeAdapter', 'ModelRequest',
    'ModelRequestPart', 'ModelRequestState', 'ModelResponse', 'ModelResponsePart',
    'ModelResponsePartDelta', 'ModelResponseState', 'ModelResponseStreamEvent',
    'MultiModalContent', 'OutputToolCallEvent', 'OutputToolResultEvent',
    'PartDeltaEvent', 'PartEndEvent', 'PartStartEvent', 'RetryPromptPart',
    'SystemPromptPart', 'TextContent', 'TextPart', 'TextPartDelta', 'ThinkingPart',
    'ThinkingPartDelta', 'ToolCallEvent', 'ToolCallPart', 'ToolCallPartDelta',
    'ToolResultEvent', 'ToolReturn', 'ToolReturnPart', 'UploadedFile', 'UserContent',
    'UserPromptPart', 'VideoFormat', 'VideoMediaType', 'VideoUrl',
    # profiles
    'ModelProfile', 'ModelProfileSpec', 'DEFAULT_PROFILE',
    'InlineDefsJsonSchemaTransformer', 'JsonSchemaTransformer',
    # tools
    'AgentNativeTool', 'Tool', 'ToolDefinition', 'RunContext',
    'DeferredToolRequests', 'DeferredToolResults', 'ToolApproved', 'ToolDenied',
    # toolsets
    'AbstractToolset', 'AgentToolset', 'ApprovalRequiredToolset', 'CombinedToolset',
    'DeferredLoadingToolset', 'ExternalToolset', 'FilteredToolset', 'FunctionToolset',
    'IncludeReturnSchemasToolset', 'PrefixedToolset', 'PreparedToolset', 'RenamedToolset',
    'SetMetadataToolset', 'ToolsetFunc', 'ToolsetTool', 'WrapperToolset',
    # native/builtin tools
    'CodeExecutionTool', 'FileSearchTool', 'ImageGenerationTool', 'MCPServerTool',
    'MemoryTool', 'WebFetchTool', 'WebSearchTool', 'WebSearchUserLocation', 'XSearchTool',
    # capabilities
    'AgentCapability', 'CapabilityFunc',
    # output
    'ToolOutput', 'NativeOutput', 'PromptedOutput', 'TextOutput', 'StructuredDict',
    'TemplateStr', 'format_as_xml',
    # settings
    'ModelRequestContext', 'ModelSettings', 'ToolChoice', 'ToolOrOutput',
    # usage
    'RunUsage', 'RequestUsage', 'UsageLimits',
    # run results
    'AgentRun', 'AgentRunResult', 'AgentRunResultEvent',
)
```

## 1.6 Base-package vs extras breakdown
Everything in the `__all__` above is importable from the **base `pydantic-ai-slim` install with no
extras** — these are pure-Python abstractions (agent, messages, tools, toolsets, settings, usage,
profiles, exceptions, `TestModel`/`FunctionModel` via `pydantic_ai.models.test`/`.function`).
Concrete provider model classes live in `pydantic_ai.models.<provider>` and import lazily; importing
them requires the matching extra:
- `pydantic_ai.models.openai` → needs `[openai]`
- `pydantic_ai.models.anthropic` → needs `[anthropic]`
- `pydantic_ai.models.google` → needs `[google]`
- `pydantic_ai.models.groq` → needs `[groq]`; `.mistral` → `[mistral]`; `.cohere` → `[cohere]`;
  `.bedrock` → `[bedrock]`; `.huggingface` → `[huggingface]`; `.xai` → `[xai]`
- `pydantic_ai.models.ollama` / `.openrouter` / `.cerebras` → reuse `[openai]` (OpenAI-compatible)
- `pydantic_ai.models.test`, `.function`, `.fallback`, `.wrapper`, `.mcp_sampling` → **no extra**
  (pure Python; `mcp_sampling` needs `[mcp]` only to actually run).

---

# 2. Model Abstraction Layer (Q2)

Primary source: https://raw.githubusercontent.com/pydantic/pydantic-ai/main/pydantic_ai_slim/pydantic_ai/models/__init__.py

## 2.1 `Model` ABC — full class signature

```python
class Model(ABC, Generic[InterfaceClient]):
    """Abstract class for a model."""
```
(approx. line 195) — note it is now **generic** over the underlying client type (`InterfaceClient`),
e.g. `Model[AsyncOpenAI]`.

### Abstract members (must be implemented by every concrete model)

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
    """The model provider, ex: openai."""
```

### Concrete (non-abstract) members defined on `Model`

```python
async def request_stream(
    self,
    messages: list[ModelMessage],
    model_settings: ModelSettings | None,
    model_request_parameters: ModelRequestParameters,
    run_context: RunContext[Any] | None = None,
) -> AsyncGenerator[StreamedResponse]:
    """Make a request to the model and return a streaming response."""

async def count_tokens(
    self,
    messages: list[ModelMessage],
    model_settings: ModelSettings | None,
    model_request_parameters: ModelRequestParameters,
) -> RequestUsage:
    """Count the number of tokens in the request."""

def customize_request_parameters(
    self, model_request_parameters: ModelRequestParameters
) -> ModelRequestParameters: ...

def prepare_request(
    self,
    model_settings: ModelSettings | None,
    model_request_parameters: ModelRequestParameters,
) -> tuple[ModelSettings | None, ModelRequestParameters]: ...

def prepare_messages(self, messages: list[ModelMessage]) -> list[ModelMessage]: ...

@property
def settings(self) -> ModelSettings | None:
    """Get the model settings configured at construction time."""

@cached_property
def profile(self) -> ModelProfile:
    """The model profile (capabilities/JSON-schema transformer)."""
```

So the minimal contract to implement a custom model = override `request`, `model_name`, `system`;
optionally override `request_stream` and `count_tokens`.

## 2.2 `ModelRequestParameters` dataclass
(approx. lines near top of models/__init__.py)

```python
@dataclass(repr=False, kw_only=True)
class ModelRequestParameters:
    """Configuration for an agent's request to a model."""
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
```

## 2.3 `StreamedResponse` base class
(approx. lines 553-754)

```python
@dataclass
class StreamedResponse(ABC):
    """Streamed response from an LLM when calling a tool."""
    model_request_parameters: ModelRequestParameters
    final_result_event: FinalResultEvent | None = field(default=None, init=False)
    provider_response_id: str | None = field(default=None, init=False)
    provider_details: dict[str, Any] | None = field(default=None, init=False)
    finish_reason: FinishReason | None = field(default=None, init=False)
```

## 2.4 `infer_model` — string-to-Model resolver
(approx. lines 790-845)

```python
def infer_model(
    model: Model | KnownModelName | str,
    provider_factory: Callable[[str], Provider[Any]] = infer_provider,
) -> Model:
    """Infer the model from the name."""
```
This is what turns a `'openai:gpt-5'`-style string into a concrete `Model` instance. The string
format is `'<provider>:<model_name>'` (e.g. `anthropic:claude-sonnet-4-5`); `infer_model` splits on
the first `:` and dispatches to the right provider/model class.

## 2.5 `ModelSettings` — every field
Source: https://raw.githubusercontent.com/pydantic/pydantic-ai/main/pydantic_ai_slim/pydantic_ai/settings.py

`ModelSettings` is a **`TypedDict`** with `total=False` (every field optional — there is no
"default value" in the dataclass sense; absent = use provider default). Provider-specific settings
subclass this (e.g. `OpenAIChatModelSettings`, `AnthropicModelSettings`, `GroqModelSettings`,
`GoogleModelSettings`, `BedrockModelSettings`, `XaiModelSettings`).

| Field | Type | Meaning |
|-------|------|---------|
| `max_tokens` | `int` | Max tokens to generate before stopping. |
| `temperature` | `float` | Sampling randomness; lower = more deterministic. |
| `top_p` | `float` | Nucleus sampling probability mass (alternative to temperature). |
| `top_k` | `int` | Sample only from top-K tokens each step. |
| `timeout` | `float \| httpx.Timeout` | Override default client timeout (seconds). |
| `parallel_tool_calls` | `bool` | Whether to allow parallel tool calls. |
| `tool_choice` | `ToolChoice` | Which/whether function tools the model may use. |
| `seed` | `int` | Random seed for (best-effort) determinism. |
| `presence_penalty` | `float` | Penalize tokens already present in text. |
| `frequency_penalty` | `float` | Penalize tokens by existing frequency. |
| `logit_bias` | `dict[str, int]` | Per-token likelihood bias. |
| `stop_sequences` | `list[str]` | Sequences that stop generation. |
| `extra_headers` | `dict[str, str]` | Extra HTTP headers sent to the model. |
| `thinking` | `ThinkingLevel` | Enable/configure reasoning (bool or effort string). |
| `service_tier` | `ServiceTier` | Cross-provider tier: `auto`/`default`/`flex`/`priority`. |
| `extra_body` | `object` | Extra request body fields. |

`ToolChoice` and `ModelRequestContext` are exported alongside `ModelSettings` from the top-level
package (see §1.5).

## 2.6 "ModelCapabilities" — what exists instead
There is **no class literally named `ModelCapabilities`** in v2. Capability/feature descriptors are
expressed through the **`ModelProfile`** system (exported as `ModelProfile`, `ModelProfileSpec`,
`DEFAULT_PROFILE` from the top-level package). A `ModelProfile` carries flags such as
`supports_tools`, `supports_json_schema_output`, `supports_json_object_output`, and a
`json_schema_transformer` (`JsonSchemaTransformer` / `InlineDefsJsonSchemaTransformer`). The
`Model.profile` cached property returns the resolved `ModelProfile` for an instance, and every
concrete model constructor accepts `profile: ModelProfileSpec | None = None` to override it. (Example:
`OllamaModel` flips `supports_json_schema_output` off when it detects Ollama Cloud routing.)

## 2.7 Concrete model implementations — constructor signatures
All provider models share the v2 convention: positional `model_name`, then keyword-only
`provider` (string shorthand or a `Provider[...]` instance), `profile`, and `settings`.

### OpenAI — `pydantic_ai.models.openai`
Exports: `OpenAIChatModel`, `OpenAIResponsesModel`, `OpenAIChatModelSettings`,
`OpenAIResponsesModelSettings`, `OpenAIModelName`, `DEPRECATED_OPENAI_MODELS`.
(No deprecated `OpenAIModel` alias present in this file's `__all__`.)

```python
class OpenAIChatModel(Model):
    def __init__(
        self,
        model_name: OpenAIModelName,
        *,
        provider: OpenAIChatCompatibleProvider
                | Literal['openai', 'openai-chat', 'gateway']
                | Provider[AsyncOpenAI] = 'openai',
        profile: ModelProfileSpec | None = None,
        settings: ModelSettings | None = None,
    ): ...

class OpenAIResponsesModel(Model):
    def __init__(
        self,
        model_name: OpenAIModelName,
        *,
        provider: OpenAIResponsesCompatibleProvider
                | Literal['openai', 'gateway']
                | Provider[AsyncOpenAI] = 'openai',
        profile: ModelProfileSpec | None = None,
        settings: ModelSettings | None = None,
    ): ...
```

### Anthropic — `pydantic_ai.models.anthropic`
Exports: `AnthropicModel`, `AnthropicModelSettings`, `AnthropicModelName`,
`LatestAnthropicModelNames`, `AnthropicTaskBudget`.

```python
class AnthropicModel(Model):
    def __init__(
        self,
        model_name: AnthropicModelName,
        *,
        provider: Literal['anthropic', 'gateway'] | Provider[AsyncAnthropicClient] = 'anthropic',
        profile: ModelProfileSpec | None = None,
        settings: ModelSettings | None = None,
    ): ...
```

### Google (Gemini + Vertex; replaces old gemini.py/vertexai.py) — `pydantic_ai.models.google`
Exports: `GoogleModel`, `GoogleModelSettings`, `GoogleModelName`, `LatestGoogleModelNames`,
`GeminiStreamedResponse`, `GoogleCloudServiceTier`.

```python
class GoogleModel(Model):
    def __init__(
        self,
        model_name: GoogleModelName,
        *,
        provider: Literal['google', 'google-cloud', 'gateway'] | Provider[Client] = 'google',
        profile: ModelProfileSpec | None = None,
        settings: ModelSettings | None = None,
    ): ...
```
`provider='google'` = Gemini Developer API; `provider='google-cloud'` = Vertex AI.

### Groq — `pydantic_ai.models.groq`
Exports: `GroqModel`, `GroqModelSettings`, `GroqModelName`.

```python
class GroqModel(Model):
    def __init__(
        self,
        model_name: GroqModelName,
        *,
        provider: Literal['groq', 'gateway'] | Provider[AsyncGroq] = 'groq',
        profile: ModelProfileSpec | None = None,
        settings: ModelSettings | None = None,
    ): ...
```

### Mistral — `pydantic_ai.models.mistral`
Exports: `MistralModel`, `MistralModelSettings`, `MistralModelName`, `LatestMistralModelNames`,
`MistralStreamedResponse`.

```python
class MistralModel(Model):
    def __init__(
        self,
        model_name: MistralModelName,
        *,
        provider: Literal['mistral'] | Provider[Mistral] = 'mistral',
        profile: ModelProfileSpec | None = None,
        json_mode_schema_prompt: str = (
            'Answer in JSON Object, respect the format:\n```\n{schema}\n```\n'
        ),
        settings: ModelSettings | None = None,
    ): ...
```
(Note: Mistral is the one provider whose constructor carries an extra param,
`json_mode_schema_prompt`.)

### Cohere — `pydantic_ai.models.cohere`
Exports: `CohereModel`, `CohereModelSettings`, `CohereModelName`, `LatestCohereModelNames`.

```python
class CohereModel(Model):
    def __init__(
        self,
        model_name: CohereModelName,
        *,
        provider: Literal['cohere'] | Provider[AsyncClientV2] = 'cohere',
        profile: ModelProfileSpec | None = None,
        settings: ModelSettings | None = None,
    ): ...
```

### Bedrock — `pydantic_ai.models.bedrock`
Exports: `BedrockConverseModel`, `BedrockModelSettings`, `BedrockModelName`,
`LatestBedrockModelNames`, `BedrockStreamedResponse`. (Class is `BedrockConverseModel`, uses the
Bedrock Converse API.) `BedrockModelSettings` adds `bedrock_*` fields (guardrail_config,
performance_configuration, request_metadata, inference_profile, cache_messages, service_tier, etc.).

```python
class BedrockConverseModel(Model):
    def __init__(
        self,
        model_name: BedrockModelName,
        *,
        provider: Literal['bedrock', 'gateway'] | Provider[BaseClient] = 'bedrock',
        profile: ModelProfileSpec | None = None,
        settings: ModelSettings | None = None,
    ): ...
```

### xAI — `pydantic_ai.models.xai`
Exports: `XaiModel`, `XaiModelSettings`, `XaiStreamedResponse`, `XSearch`.

```python
class XaiModel(Model):
    def __init__(
        self,
        model_name: XaiModelName,
        *,
        provider: Literal['xai'] | Provider[AsyncClient] = 'xai',
        profile: ModelProfileSpec | None = None,
        settings: ModelSettings | None = None,
    ): ...
```

### Ollama — `pydantic_ai.models.ollama`  (`__all__ = ('OllamaModel',)`)
`OllamaModel` **subclasses `OpenAIChatModel`** (OpenAI-compatible API). It auto-detects Ollama Cloud
routing via an internal `_routes_to_ollama_cloud()` and disables `supports_json_schema_output` in the
resolved profile when Cloud is detected.

```python
class OllamaModel(OpenAIChatModel):
    def __init__(
        self,
        model_name: str,
        *,
        provider: Literal['ollama'] | Provider[AsyncOpenAI] = 'ollama',
        profile: ModelProfileSpec | None = None,
        settings: ModelSettings | None = None,
    ): ...
```

### TestModel — `pydantic_ai.models.test` (no extra needed)
A dataclass that simulates model behaviour for unit tests (`__test__ = False` so pytest ignores it).

```python
@dataclass
class TestModel(Model):
    call_tools: list[str] | Literal['all'] = 'all'
    custom_output_text: str | None = None
    custom_output_args: Any | None = None
    seed: int = 0
    last_model_request_parameters: ModelRequestParameters | None = field(default=None, init=False)
    _model_name: str = 'test'   # exposed via .model_name property
    _system: str = 'test'       # exposed via .system property (always 'test')
```

### FunctionModel — `pydantic_ai.models.function` (no extra needed)
Drives responses from a local Python function (sync or streaming). Exports: `FunctionModel`,
`AgentInfo`, `DeltaToolCall`, `DeltaToolCalls`, `DeltaThinkingPart`, `DeltaThinkingCalls`,
`BuiltinToolCallsReturns`, `FunctionDef`, `StreamFunctionDef`, `FunctionStreamedResponse`.

```python
class FunctionModel(Model):
    def __init__(
        self,
        function: FunctionDef | None = None,
        *,
        stream_function: StreamFunctionDef | None = None,
        model_name: str | None = None,
        profile: ModelProfileSpec | None = None,
        settings: ModelSettings | None = None,
    ) -> None: ...
```

### FallbackModel — `pydantic_ai.models.fallback` (no extra needed)
Tries models in order, falling back on matching exceptions. Exports: `FallbackModel`, `FallbackOn`,
`ResponseRejected` (plus type aliases `ExceptionHandler`, `ResponseHandler`).

```python
class FallbackModel(Model):
    def __init__(
        self,
        default_model: Model | KnownModelName | str,
        *fallback_models: Model | KnownModelName | str,
        fallback_on: FallbackOn = (ModelAPIError,),
    ): ...
```

## 2.8 How `model=` works on `Agent`
Source: https://raw.githubusercontent.com/pydantic/pydantic-ai/main/pydantic_ai_slim/pydantic_ai/agent/__init__.py

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

So `model` accepts three shapes:
1. a concrete `Model` instance (`OpenAIChatModel(...)`, `FallbackModel(...)`, `TestModel()`, …),
2. a `KnownModelName` string literal (e.g. `'anthropic:claude-sonnet-4-5'`) — type-checked, autocompletes,
3. an arbitrary `str` (escape hatch for names not yet in the literal),
4. or `None` (defer; supply the model at `.run(...)`/`.run_sync(...)` time).

When a string is passed it is resolved lazily via `infer_model()` (§2.4). Passing
`defer_model_check=True` skips eager validation of the string at construction.

## 2.9 `KnownModelName` — string shorthands
Source: https://raw.githubusercontent.com/pydantic/pydantic-ai/main/pydantic_ai_slim/pydantic_ai/models/_known_model_names.py

`KnownModelName` is a `TypeAliasType` wrapping a giant `Literal[...]`. Format is
`'<provider>:<model>'` (plus the bare `'test'`). The provider prefixes present in v2.1.0 are:

`anthropic:`, `bedrock:`, `cerebras:`, `cohere:`, `deepseek:`, `google:`, `google-cloud:`,
`groq:`, `heroku:`, `huggingface:`, `mistral:`, `moonshotai:`, `openai:`, `openai-chat:`,
`xai:`, the bare `test`, plus **gateway-routed** variants
`gateway/anthropic:`, `gateway/bedrock:`, `gateway/google:`, `gateway/google-cloud:`,
`gateway/groq:`, `gateway/openai:`.

Representative literals per provider (the full alias is hundreds of entries — full enumeration was
captured from the source; key examples below):
- **anthropic:** `claude-opus-4-5`, `claude-opus-4-1`, `claude-opus-4-0`, `claude-sonnet-4-5`,
  `claude-sonnet-4-0`, `claude-haiku-4-5`, `claude-3-haiku-20240307`, dated SKUs like
  `claude-sonnet-4-5-20250929`, `claude-opus-4-5-20251101`.
- **openai / openai-chat:** `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-5-pro`, `gpt-5-codex`,
  `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`,
  `gpt-3.5-turbo`, `o1`, `o1-pro`, `o3`, `o3-mini`, `o3-pro`, `o4-mini`,
  `o3-deep-research`, `o4-mini-deep-research`, `computer-use-preview`. (The `openai:` prefix
  targets the Responses API by default; `openai-chat:` targets Chat Completions.)
- **google / google-cloud:** `gemini-2.0-flash`, `gemini-2.0-flash-lite`, `gemini-2.5-flash`,
  `gemini-2.5-flash-lite`, `gemini-2.5-pro`, `gemini-2.5-flash-image`, `gemini-flash-latest`,
  `gemini-flash-lite-latest`, plus preview SKUs (`gemini-3-pro-preview`, `gemini-3-flash-preview`).
- **groq:** `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`,
  `meta-llama/llama-4-scout-17b-16e-instruct`, `meta-llama/llama-4-maverick-17b-128e-instruct`,
  `moonshotai/kimi-k2-instruct-0905`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`,
  `qwen/qwen-3-32b`, `whisper-large-v3`.
- **mistral:** `mistral-large-latest`, `mistral-small-latest`, `codestral-latest`,
  `mistral-moderation-latest`.
- **cohere:** `command-r-08-2024`, `command-r-plus-08-2024`, `command-r7b-12-2024`,
  `command-nightly`, `c4ai-aya-expanse-8b`, `c4ai-aya-expanse-32b`.
- **bedrock:** `anthropic.claude-3-5-sonnet-20241022-v2:0`, `us.anthropic.claude-sonnet-4-5-20250929-v1:0`,
  `eu.anthropic.claude-sonnet-4-5-20250929-v1:0`, `amazon.titan-text-express-v1`,
  `us.amazon.nova-pro-v1:0`, `meta.llama3-1-405b-instruct-v1:0`,
  `mistral.mistral-large-2407-v1:0`, `cohere.command-r-plus-v1:0` (region-prefixed `us.`/`eu.`/`global.` variants exist).
- **xai:** `grok-3`, `grok-3-mini`, `grok-4`, `grok-4-fast`, `grok-4-fast-reasoning`,
  `grok-code-fast-1`.
- **deepseek:** `deepseek-chat`, `deepseek-reasoner`, `deepseek-v4-flash`, `deepseek-v4-pro`.
- **cerebras:** `gpt-oss-120b`, `llama3.1-8b`, `qwen-3-235b-a22b-instruct-2507`, `zai-glm-4.7`.
- **moonshotai:** `kimi-latest`, `kimi-k2-0711-preview`, `kimi-thinking-preview`, `moonshot-v1-8k/32k/128k` (+ vision-preview variants).
- **heroku:** `claude-4-5-sonnet`, `claude-4-5-haiku`, `gpt-oss-120b`, `nova-pro`, `qwen3-coder-480b`, etc.
- **huggingface:** `Qwen/Qwen3-32B`, `Qwen/Qwen3-235B-A22B`, `deepseek-ai/DeepSeek-R1`,
  `meta-llama/Llama-3.3-70B-Instruct`, `meta-llama/Llama-4-Scout-17B-16E-Instruct`, etc.
- **gateway/\*:** mirror subsets of the above, routed through Pydantic's model gateway
  (e.g. `gateway/openai:gpt-5`, `gateway/anthropic:claude-sonnet-4-5`, `gateway/google:gemini-2.5-pro`).
- **bare:** `test`.

> The exhaustive literal list (every dated SKU) is large and version-volatile; the authoritative,
> always-current source is `_known_model_names.py` on the pinned tag. The provider-prefix taxonomy
> above is stable and is what callers actually need.

---

## Working code examples

```python
# 1. String shorthand (KnownModelName) — simplest
from pydantic_ai import Agent
agent = Agent('anthropic:claude-sonnet-4-5', system_prompt='Be concise.')
print(agent.run_sync('What is 2+2?').output)

# 2. Explicit model instance with settings
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.settings import ModelSettings
model = OpenAIChatModel('gpt-5', settings=ModelSettings(temperature=0.2, max_tokens=1024))
agent = Agent(model)

# 3. Fallback across providers
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.anthropic import AnthropicModel
fallback = FallbackModel(
    OpenAIChatModel('gpt-5'),
    AnthropicModel('claude-sonnet-4-5'),
)
agent = Agent(fallback)

# 4. Deterministic unit test — no network, no extras
from pydantic_ai.models.test import TestModel
test_agent = Agent(TestModel(custom_output_text='hello'))
assert test_agent.run_sync('anything').output == 'hello'

# 5. Override model at run time (model=None at construction)
agent = Agent(system_prompt='translate to French')
result = agent.run_sync('Hello', model='google:gemini-2.5-flash')
```
