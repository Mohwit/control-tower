# Q6 — pydantic-ai v2 Message Types & Conversation History

Source: `pydantic_ai_slim/pydantic_ai/messages.py` (2780 lines, main branch) + docs.
Date: 2026-06-30

---

## 1. Message type hierarchy (text tree)

```
ModelMessage = Annotated[ModelRequest | ModelResponse, Discriminator('kind')]
│
├── ModelRequest            kind='request'
│     parts: Sequence[ModelRequestPart]
│
└── ModelResponse           kind='response'
      parts: Sequence[ModelResponsePart]

ModelRequestPart  (Discriminator on part_kind / tool_kind)
├── SystemPromptPart                 part_kind='system-prompt'
├── UserPromptPart                   part_kind='user-prompt'
├── ToolReturnPart                   part_kind='tool-return'        ┐ subclass of BaseToolReturnPart
│     └── ToolSearchReturnPart       part_kind='tool-return', tool_kind='tool-search'
├── LoadCapabilityReturnPart         part_kind='capability-load-return'
└── RetryPromptPart                  part_kind='retry-prompt'

ModelResponsePart  (Discriminator on part_kind / tool_kind)
├── TextPart                         part_kind='text'
├── ThinkingPart                     part_kind='thinking'
├── CompactionPart                   part_kind='compaction'
├── FilePart                         part_kind='file'
├── ToolCallPart                     part_kind='tool-call'          ┐ subclass of BaseToolCallPart
│     └── ToolSearchCallPart         tool_kind='tool-search'
├── LoadCapabilityCallPart           part_kind='capability-load-call'
├── NativeToolCallPart               part_kind='builtin-tool-call'  ┐ subclass of BaseToolCallPart
│     └── NativeToolSearchCallPart   tool_kind='tool-search'
└── NativeToolReturnPart             part_kind='builtin-tool-return' ┐ subclass of BaseToolReturnPart
      └── NativeToolSearchReturnPart tool_kind='tool-search'

Base (not standalone union members):
├── BaseToolReturnPart   (parent of ToolReturnPart, NativeToolReturnPart)
└── BaseToolCallPart     (parent of ToolCallPart, NativeToolCallPart)

Content / supporting value types:
├── FileUrl (ABC)  → VideoUrl, AudioUrl, ImageUrl, DocumentUrl
├── TextContent, BinaryContent → BinaryImage, UploadedFile, CachePoint
├── ToolReturn (Generic) — wrapper to return content+metadata from a tool
└── InstructionPart — structured instruction block

Streaming deltas & events (separate from messages):
├── TextPartDelta, ThinkingPartDelta, ToolCallPartDelta  → ModelResponsePartDelta union
├── PartStartEvent, PartDeltaEvent, PartEndEvent, FinalResultEvent → ModelResponseStreamEvent union
├── ToolCallEvent → FunctionToolCallEvent, OutputToolCallEvent
├── ToolResultEvent → FunctionToolResultEvent, OutputToolResultEvent  → HandleResponseEvent union
└── AgentStreamEvent = Annotated[ModelResponseStreamEvent | HandleResponseEvent, Discriminator('event_kind')]
```

> **`ArgsDict` / `ArgsJson` no longer exist.** The original prompt referenced these (old v0 API). In current `main`, tool-call arguments are a single field `args: str | dict[str, Any] | None` on `BaseToolCallPart`, with helper methods `args_as_dict()` and `args_as_json_str()`.

---

## 2. Every message/part class with all fields

All parts are `@dataclass(repr=False)`. `_: KW_ONLY` marks the boundary after which fields are keyword-only.

### ModelRequest (kind='request')
```python
parts: Sequence[ModelRequestPart]
# KW_ONLY:
timestamp: datetime | None = None         # None for back-compat with old serialized msgs
instructions: str | None = None           # rendered instruction string
kind: Literal['request'] = 'request'
run_id: str | None = None
conversation_id: str | None = None        # spans multiple runs sharing history
metadata: dict[str, Any] | None = None    # not sent to LLM
state: ModelRequestState = 'complete'     # 'complete' | 'interrupted'
# classmethod: user_text_prompt(user_prompt, *, instructions=None) -> ModelRequest
```

### ModelResponse (kind='response')
```python
parts: Sequence[ModelResponsePart]
# KW_ONLY:
usage: RequestUsage = field(default_factory=RequestUsage)   # per-request usage
model_name: str | None = None
timestamp: datetime = field(default_factory=_now_utc)
kind: Literal['response'] = 'response'
provider_name: str | None = None
provider_url: str | None = None
provider_details: dict[str, Any] | None = None    # alias accepts 'vendor_details'
provider_response_id: str | None = None           # alias accepts 'vendor_id'
finish_reason: FinishReason | None = None
run_id: str | None = None
conversation_id: str | None = None
metadata: dict[str, Any] | None = None
state: ModelResponseState = 'complete'            # 'complete'|'incomplete'|'interrupted'
# properties: .text, .thinking, .files, .images, .tool_calls, .native_tool_calls
# methods: .cost() -> PriceCalculation (via genai-prices), .otel_message_parts(settings)
```

### SystemPromptPart (part_kind='system-prompt')
```python
content: str
# KW_ONLY:
timestamp: datetime = field(default_factory=_now_utc)
dynamic_ref: str | None = None
part_kind: Literal['system-prompt'] = 'system-prompt'
```

### UserPromptPart (part_kind='user-prompt')
```python
content: str | Sequence[UserContent]   # UserContent = str | TextContent | MultiModalContent | CachePoint
# KW_ONLY:
timestamp: datetime = field(default_factory=_now_utc)
part_kind: Literal['user-prompt'] = 'user-prompt'
```

### BaseToolReturnPart (parent)
```python
tool_name: str
content: ToolReturnContent                              # may include multimodal
tool_call_id: str = field(default_factory=_generate_tool_call_id)
# KW_ONLY:
tool_kind: ToolPartKind | None = None                   # 'tool-search' | 'capability-load' | None
metadata: Any = None                                    # NOT sent to LLM
timestamp: datetime = field(default_factory=_now_utc)
outcome: Literal['success', 'failed', 'denied'] = 'success'
# property: .files ; methods: .content_items(...), _split_content(), _unwrap_data()
```

### ToolReturnPart(BaseToolReturnPart) (part_kind='tool-return')
```python
part_kind: Literal['tool-return'] = 'tool-return'
# staticmethod narrow_type(part, *, tool_kind=None) -> ToolReturnPart
```

### NativeToolReturnPart(BaseToolReturnPart) (part_kind='builtin-tool-return')
```python
provider_name: str | None = None
provider_details: dict[str, Any] | None = None
part_kind: Literal['builtin-tool-return'] = 'builtin-tool-return'
```

### RetryPromptPart (part_kind='retry-prompt')
```python
content: list[pydantic_core.ErrorDetails] | str    # error list if from ValidationError
# KW_ONLY:
tool_name: str | None = None
tool_call_id: str = field(default_factory=_generate_tool_call_id)
timestamp: datetime = field(default_factory=_now_utc)
part_kind: Literal['retry-prompt'] = 'retry-prompt'
# method: model_response() -> str   (renders the retry message + "Fix the errors and try again.")
```
Docstring lists triggers: tool-arg validation failure, `ModelRetry` from a tool, unknown tool name, plain text when structured expected, structured-response validation failure, `ModelRetry` from an output validator.

### TextPart (part_kind='text')
```python
content: str
# KW_ONLY:
id: str | None = None
provider_name: str | None = None
provider_details: dict[str, Any] | None = None
part_kind: Literal['text'] = 'text'
# method: has_content() -> bool
```

### ThinkingPart (part_kind='thinking')
```python
content: str
# KW_ONLY:
id: str | None = None
signature: str | None = None          # Anthropic/Bedrock signature, Google thought_signature, OpenAI encrypted_content
provider_name: str | None = None
provider_details: dict[str, Any] | None = None
part_kind: Literal['thinking'] = 'thinking'
```

### CompactionPart (part_kind='compaction')
History-summarization part round-tripped to the same provider (Anthropic readable text summary etc.).

### FilePart (part_kind='file')
A model-emitted file/binary (used in `ModelResponse.files` / `.images`).

### InstructionPart (part_kind='instruction')
```python
content: str
# KW_ONLY:
dynamic: bool = False     # False = literal Agent(instructions=...); True = @agent.instructions / template / toolset
part_kind: Literal['instruction'] = 'instruction'
# staticmethods: join(parts) -> str|None ; sorted(parts) -> list (static before dynamic)
```

### BaseToolCallPart (parent)
```python
tool_name: str
args: str | dict[str, Any] | None = None     # JSON string OR dict
tool_call_id: str = field(default_factory=_generate_tool_call_id)
# KW_ONLY:
tool_kind: ToolPartKind | None = None
id: str | None = None
provider_name: str | None = None
provider_details: dict[str, Any] | None = None
# methods: args_as_dict(*, raise_if_invalid=False) -> dict
#          args_as_json_str() -> str
#          has_content() -> bool
```

### ToolCallPart(BaseToolCallPart) (part_kind='tool-call')
```python
part_kind: Literal['tool-call'] = 'tool-call'
# staticmethod narrow_type(part, *, tool_kind=None)
```

### NativeToolCallPart(BaseToolCallPart) (part_kind='builtin-tool-call')
For provider-native ("built-in") tool calls (e.g. tool_search).

### ToolReturn (Generic[_ToolReturnValueT])
A return-value wrapper a tool can return to carry `return_value`, `content`, `metadata` separately.

---

## 3. Union type definitions (exact)

```python
ModelRequestPart = Annotated[
    Annotated[SystemPromptPart,        Tag('system-prompt')]
    | Annotated[UserPromptPart,        Tag('user-prompt')]
    | Annotated[ToolSearchReturnPart,  Tag('tool-search-return')]
    | Annotated[LoadCapabilityReturnPart, Tag('capability-load-return')]
    | Annotated[ToolReturnPart,        Tag('tool-return')]
    | Annotated[RetryPromptPart,       Tag('retry-prompt')],
    Discriminator(_model_request_part_discriminator),
]

ModelResponsePart = Annotated[
    Annotated[TextPart,                  Tag('text')]
    | Annotated[ToolSearchCallPart,      Tag('tool-search-call')]
    | Annotated[LoadCapabilityCallPart,  Tag('capability-load-call')]
    | Annotated[ToolCallPart,            Tag('tool-call')]
    | Annotated[NativeToolSearchCallPart,   Tag('builtin-tool-search-call')]
    | Annotated[NativeToolCallPart,         Tag('builtin-tool-call')]
    | Annotated[NativeToolSearchReturnPart, Tag('builtin-tool-search-return')]
    | Annotated[NativeToolReturnPart,       Tag('builtin-tool-return')]
    | Annotated[ThinkingPart,            Tag('thinking')]
    | Annotated[CompactionPart,          Tag('compaction')]
    | Annotated[FilePart,                Tag('file')],
    Discriminator(_model_response_part_discriminator),
]

ModelMessage = Annotated[ModelRequest | ModelResponse, Discriminator('kind')]
```
Discriminators are **callable** (`_model_request_part_discriminator` / `_model_response_part_discriminator`): they dispatch on `part_kind` and, for typed subclasses, on the `(part_kind, tool_kind)` pair via `_TYPED_PART_TAGS`. This lets a user tool sharing a name with a framework tool deserialize safely as the base part.

---

## 4. Serialization / deserialization utilities

Source: `messages.py` ~line 2262.
```python
ModelMessagesTypeAdapter = pydantic.TypeAdapter(list[ModelMessage], ...)
"""Pydantic TypeAdapter for (de)serializing messages."""
```
Exported from top-level `pydantic_ai` (`from pydantic_ai import ModelMessagesTypeAdapter`). Usage:
```python
# serialize
as_json_bytes = ModelMessagesTypeAdapter.dump_json(messages)
as_python = ModelMessagesTypeAdapter.dump_python(messages)
# deserialize
messages = ModelMessagesTypeAdapter.validate_json(json_bytes)
messages = ModelMessagesTypeAdapter.validate_python(python_objs)
```
Result objects also expose `all_messages_json()` / `new_messages_json()` which call `ModelMessagesTypeAdapter.dump_json(...)` internally. Other internal adapters: `tool_return_ta`, `error_details_ta`.

---

## 5. Passing history to a run — parameter & type

On `AbstractAgent.run` / `run_sync` / `run_stream` / `run_stream_events` and `iter` (`agent/abstract.py`):
```python
message_history: Sequence[_messages.ModelMessage] | None = None
```
Related run params (same signature):
```python
deferred_tool_results: DeferredToolResults | None = None   # results for deferred tool calls in history
conversation_id: str | None = None     # 'new' to fork; else most-recent on history or fresh UUID7
usage: _usage.RunUsage | None = None    # seed usage when resuming
```
Docs note: **"If `message_history` is set and not empty, a new system prompt is not generated"** — the framework assumes the history already contains one.

---

## 6. Extracting history from a result

`AgentRunResult` (`run.py`) and `StreamedRunResult` (`result.py`) both expose:

| Method | Returns | Notes |
|---|---|---|
| `all_messages(*, output_tool_return_content=None)` | `list[ModelMessage]` | all messages incl. prior runs |
| `new_messages(*, output_tool_return_content=None)` | `list[ModelMessage]` | only this run's messages (slices at `_new_message_index`) |
| `all_messages_json(*, output_tool_return_content=None)` | `bytes` | JSON via `ModelMessagesTypeAdapter` |
| `new_messages_json(*, output_tool_return_content=None)` | `bytes` | JSON of new messages |

`AgentRun` (the `async with agent.iter(...)` object) also exposes `all_messages()`, `all_messages_json()`, `new_messages()`, `new_messages_json()`.

The `output_tool_return_content` kwarg lets you overwrite the output-tool's return content in the last message before continuing the conversation.

---

## 7. Processing history before requests — `ProcessHistory` capability

In v2, history transformation is a **capability**, not a constructor kwarg:
```python
from pydantic_ai import Agent, ModelMessage, ModelRequest
from pydantic_ai.capabilities import ProcessHistory

def filter_responses(messages: list[ModelMessage]) -> list[ModelMessage]:
    return [m for m in messages if isinstance(m, ModelRequest)]

agent = Agent('openai:gpt-5.2', capabilities=[ProcessHistory(filter_responses)])
```
Processor functions may optionally accept a `RunContext` parameter.

---

## 8. Working code examples

### Continue a conversation
```python
from pydantic_ai import Agent

agent = Agent('openai:gpt-5.2')
r1 = agent.run_sync('Tell me a joke.')
r2 = agent.run_sync('Explain?', message_history=r1.new_messages())
print(r2.output)
```

### Persist & restore history (round-trip)
```python
from pydantic_ai import ModelMessagesTypeAdapter

blob: bytes = r1.all_messages_json()              # store in DB/file
history = ModelMessagesTypeAdapter.validate_json(blob)   # restore
r3 = agent.run_sync('And another?', message_history=history)
```

### Inspect parts of the last response
```python
resp = r1.response                  # last ModelResponse
print(resp.text)                    # joined TextPart content
for call in resp.tool_calls:        # list[ToolCallPart]
    print(call.tool_name, call.args_as_dict())
```

---

## Sources
- `pydantic_ai_slim/pydantic_ai/messages.py` (classes, unions, `ModelMessagesTypeAdapter`)
- `pydantic_ai_slim/pydantic_ai/agent/abstract.py` (run signatures, `message_history` param)
- `pydantic_ai_slim/pydantic_ai/run.py` (`AgentRunResult`, `AgentRun` history methods)
- `pydantic_ai_slim/pydantic_ai/result.py` (`StreamedRunResult` history methods)
- Docs: https://pydantic.dev/docs/ai/core-concepts/message-history/
