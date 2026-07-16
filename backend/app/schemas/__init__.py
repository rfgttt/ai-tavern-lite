from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import re


class CharacterBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=300_000)
    personality: str = Field(default="", max_length=200_000)
    scenario: str = Field(default="", max_length=300_000)
    first_message: str = Field(default="", max_length=200_000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("角色名称不能为空")
        return cleaned


class CharacterCreate(CharacterBase):
    raw_json: str = "{}"
    normalized_json: str = "{}"
    avatar_path: str = ""


class CharacterUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=300_000)
    personality: Optional[str] = Field(None, max_length=200_000)
    scenario: Optional[str] = Field(None, max_length=300_000)
    first_message: Optional[str] = Field(None, max_length=200_000)
    normalized_json: Optional[str] = Field(None, max_length=1_500_000)


class CharacterResponse(CharacterBase):
    id: str
    avatar_path: str = ""
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CharacterExport(BaseModel):
    id: str
    name: str
    data: Dict[str, Any]


class LorebookEntry(BaseModel):
    id: Optional[int] = None
    keys: List[str] = Field(default_factory=list)
    secondary_keys: List[str] = Field(default_factory=list)
    comment: str = ""
    content: str = ""
    constant: bool = False
    selective: bool = False
    enabled: bool = True
    insertion_order: int = 0
    position: str = "before_char"
    use_regex: bool = False
    probability: int = 100
    extensions: Dict[str, Any] = Field(default_factory=dict)


class Lorebook(BaseModel):
    entries: List[LorebookEntry] = Field(default_factory=list)


class ChatSessionBase(BaseModel):
    title: str = "新对话"


class ChatSessionCreate(ChatSessionBase):
    character_id: str
    persona_id: Optional[str] = None
    group_id: Optional[str] = None


class ChatSessionUpdate(BaseModel):
    title: Optional[str] = None
    persona_id: Optional[str] = None
    group_id: Optional[str] = None


class ChatSessionResponse(ChatSessionBase):
    id: str
    character_id: str
    persona_id: Optional[str] = None
    group_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageBase(BaseModel):
    role: str
    content: str = ""


class MessageCreate(MessageBase):
    session_id: str
    sequence: int = 0


class MessageUpdate(BaseModel):
    content: Optional[str] = None
    role: Optional[str] = None
    generation_status: Optional[str] = None


class MessageResponse(MessageBase):
    id: str
    session_id: str
    sequence: int
    generation_status: str
    segments: List[Dict[str, Any]] = Field(default_factory=list)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    speaker_metadata: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    render_version: int = 2
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def hydrate_render_data(cls, value):
        from ..services.rendering.message_ast import parse_message_ast
        if isinstance(value, dict):
            data = dict(value)
        else:
            data = {
                "id": value.id,
                "session_id": value.session_id,
                "role": value.role,
                "content": value.content,
                "sequence": value.sequence,
                "generation_status": value.generation_status,
                "segments_json": getattr(value, "segments_json", "[]"),
                "artifacts_json": getattr(value, "artifacts_json", "[]"),
                "speaker_metadata_json": getattr(value, "speaker_metadata_json", "{}"),
                "render_version": getattr(value, "render_version", 2) or 2,
                "created_at": value.created_at,
                "updated_at": value.updated_at,
            }
        try:
            segments = json.loads(data.pop("segments_json", "[]") or "[]")
        except (TypeError, json.JSONDecodeError):
            segments = []
        try:
            artifacts = json.loads(data.pop("artifacts_json", "[]") or "[]")
        except (TypeError, json.JSONDecodeError):
            artifacts = []
        try:
            speakers = json.loads(data.pop("speaker_metadata_json", "{}") or "{}")
        except (TypeError, json.JSONDecodeError):
            speakers = {}
        if not segments and data.get("content"):
            parsed = parse_message_ast(data["content"])
            segments = parsed["segments"]
            speakers = parsed["speaker_metadata"]
        data["segments"] = segments
        data["artifacts"] = artifacts
        data["speaker_metadata"] = speakers
        data["render_version"] = int(data.get("render_version") or 2)
        return data


class MemoryBase(BaseModel):
    category: str = "general"
    content: str = ""
    importance: float = 0.5
    keywords: str = ""
    enabled: bool = True


class MemoryCreate(MemoryBase):
    character_id: Optional[str] = None
    session_id: Optional[str] = None


class MemoryUpdate(BaseModel):
    category: Optional[str] = None
    content: Optional[str] = None
    importance: Optional[float] = None
    keywords: Optional[str] = None
    enabled: Optional[bool] = None


class MemoryResponse(MemoryBase):
    id: str
    character_id: Optional[str] = None
    session_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SettingsResponse(BaseModel):
    provider_name: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 1024
    context_window: int = 8192
    username: str = "用户"
    mock_llm: bool = False
    auto_memory_extraction: bool = False
    api_key_configured: bool = False
    api_key_masked: str = ""
    custom_headers: Dict[str, str] = Field(default_factory=dict)
    settings_writable: bool = True
    diagnostics_enabled: bool = True
    selftest_enabled: bool = True


class SettingsUpdate(BaseModel):
    provider_name: Optional[str] = Field(None, max_length=100)
    base_url: Optional[str] = Field(None, max_length=2048)
    api_key: Optional[str] = Field(None, max_length=4096)
    model: Optional[str] = Field(None, max_length=200)
    temperature: Optional[float] = Field(None, ge=0, le=2)
    top_p: Optional[float] = Field(None, ge=0, le=1)
    max_tokens: Optional[int] = Field(None, ge=1, le=32_768)
    context_window: Optional[int] = Field(None, ge=128, le=1_000_000)
    username: Optional[str] = Field(None, min_length=1, max_length=100)
    mock_llm: Optional[bool] = None
    auto_memory_extraction: Optional[bool] = None
    custom_headers: Optional[Dict[str, str]] = None
    clear_api_key: Optional[bool] = False

    @field_validator("custom_headers")
    @classmethod
    def validate_custom_headers(cls, value):
        if value is None:
            return value
        if len(value) > 20:
            raise ValueError("自定义请求头最多允许 20 项")
        blocked = {
            "host", "content-length", "transfer-encoding", "connection",
            "proxy-authorization", "proxy-authenticate", "upgrade", "te", "trailer",
        }
        token = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
        normalized = {}
        for raw_name, raw_value in value.items():
            name = str(raw_name).strip()
            header_value = str(raw_value)
            if not token.fullmatch(name):
                raise ValueError("自定义请求头名称无效")
            if name.lower() in blocked:
                raise ValueError(f"不允许设置请求头: {name}")
            if len(header_value) > 4096 or "\r" in header_value or "\n" in header_value:
                raise ValueError(f"请求头 {name} 的值无效")
            normalized[name] = header_value
        return normalized

    @model_validator(mode="after")
    def validate_token_budget(self):
        if (
            self.max_tokens is not None
            and self.context_window is not None
            and self.max_tokens >= self.context_window
        ):
            raise ValueError("max_tokens 必须小于 context_window")
        return self


class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    model: Optional[str] = None


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(default="", max_length=50_000)
    # Internal regeneration metadata. Normal /chat/stream callers leave these empty.
    replacement_message_id: Optional[str] = Field(default=None, exclude=True)
    replacement_state_json: Optional[str] = Field(default=None, exclude=True)


class PromptPreviewRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(default="", max_length=50_000)


class PromptSection(BaseModel):
    name: str
    content: str
    estimated_tokens: int
    source: str = ""


class PromptPreviewResponse(BaseModel):
    sections: List[PromptSection] = Field(default_factory=list)
    total_estimated_tokens: int = 0
    context_budget: int = 8192


class HealthResponse(BaseModel):
    status: str
    version: str = "2.2.0-preview.1"
    mock_mode: bool = False


class RuntimeStateUpdate(BaseModel):
    state: Dict[str, Any]


class RuntimeRollbackRequest(BaseModel):
    message_id: str


class TurnRuntimeResponse(BaseModel):
    id: str
    message_id: str
    state_before: Dict[str, Any] = Field(default_factory=dict)
    patch: List[Dict[str, Any]] = Field(default_factory=list)
    state_after: Dict[str, Any] = Field(default_factory=dict)
    events: List[str] = Field(default_factory=list)
    choices: List[str] = Field(default_factory=list)
    dice: List[Dict[str, Any]] = Field(default_factory=list)
    battle_checks: List[Dict[str, Any]] = Field(default_factory=list)
    battle: Optional[Dict[str, Any]] = None
    expression: str = ""
    triggered_lorebook: List[Dict[str, Any]] = Field(default_factory=list)
    rejected_patch: List[Dict[str, Any]] = Field(default_factory=list)
    parser_errors: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class RuntimeSessionResponse(BaseModel):
    session_id: str
    profile: Dict[str, Any] = Field(default_factory=dict)
    initial_state: Dict[str, Any] = Field(default_factory=dict)
    state: Dict[str, Any] = Field(default_factory=dict)
    revision: int = 0
    last_turn: Optional[TurnRuntimeResponse] = None
    updated_at: Optional[datetime] = None


class PersonaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    pronouns: str = ""
    avatar_path: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class PersonaUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    pronouns: Optional[str] = None
    avatar_path: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None


class PersonaResponse(PersonaCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    character_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GroupResponse(GroupCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class BranchCreate(BaseModel):
    title: str = Field(default="剧情分支", min_length=1, max_length=200)
    parent_message_id: Optional[str] = None


class BranchResponse(BaseModel):
    id: str
    session_id: str
    title: str
    parent_message_id: str = ""
    message_count: int
    runtime_revision: int
    created_at: datetime
