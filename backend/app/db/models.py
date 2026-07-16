from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Float, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..db.session import Base
import uuid


def generate_uuid():
    return str(uuid.uuid4())


class Character(Base):
    __tablename__ = "characters"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, default="")
    personality = Column(Text, default="")
    scenario = Column(Text, default="")
    first_message = Column(Text, default="")
    normalized_json = Column(Text, default="{}")
    raw_json = Column(Text, default="{}")
    avatar_path = Column(String, default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    sessions = relationship("ChatSession", back_populates="character", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="character", cascade="all, delete-orphan")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, default=generate_uuid)
    character_id = Column(String, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, default="新对话")
    persona_id = Column(String, ForeignKey("personas.id", ondelete="SET NULL"), nullable=True)
    group_id = Column(String, ForeignKey("character_groups.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    character = relationship("Character", back_populates="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan", order_by="Message.sequence")
    memories = relationship("Memory", back_populates="session", cascade="all, delete-orphan")
    runtime_state = relationship("SessionState", back_populates="session", cascade="all, delete-orphan", uselist=False)
    turn_snapshots = relationship("TurnSnapshot", back_populates="session", cascade="all, delete-orphan")
    branches = relationship("SessionBranch", back_populates="session", cascade="all, delete-orphan")
    persona = relationship("Persona")
    group = relationship("CharacterGroup")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("session_id", "sequence", name="uq_message_session_sequence"),)

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # user, assistant, system
    content = Column(Text, default="")
    sequence = Column(Integer, default=0)
    generation_status = Column(String, default="complete")  # complete, generating, stopped, error
    segments_json = Column(Text, default="[]")
    artifacts_json = Column(Text, default="[]")
    speaker_metadata_json = Column(Text, default="{}")
    render_version = Column(Integer, default=2)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    session = relationship("ChatSession", back_populates="messages")
    turn_snapshot = relationship("TurnSnapshot", back_populates="message", cascade="all, delete-orphan", uselist=False)


class SessionState(Base):
    __tablename__ = "session_states"

    session_id = Column(String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), primary_key=True)
    profile_json = Column(Text, default="{}")
    initial_state_json = Column(Text, default="{}")
    state_json = Column(Text, default="{}")
    revision = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    session = relationship("ChatSession", back_populates="runtime_state")


class TurnSnapshot(Base):
    __tablename__ = "turn_snapshots"
    __table_args__ = (
        UniqueConstraint("message_id", name="uq_turn_snapshot_message"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    state_before_json = Column(Text, default="{}")
    patch_json = Column(Text, default="[]")
    state_after_json = Column(Text, default="{}")
    events_json = Column(Text, default="[]")
    choices_json = Column(Text, default="[]")
    dice_json = Column(Text, default="[]")
    battle_checks_json = Column(Text, default="[]")
    battle_json = Column(Text, default="null")
    expression = Column(String, default="")
    triggered_lorebook_json = Column(Text, default="[]")
    rejected_patch_json = Column(Text, default="[]")
    parser_errors_json = Column(Text, default="[]")
    created_at = Column(DateTime, server_default=func.now())

    session = relationship("ChatSession", back_populates="turn_snapshots")
    message = relationship("Message", back_populates="turn_snapshot")


class Memory(Base):
    __tablename__ = "memories"

    id = Column(String, primary_key=True, default=generate_uuid)
    character_id = Column(String, ForeignKey("characters.id", ondelete="CASCADE"), nullable=True)
    session_id = Column(String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=True)
    category = Column(String, default="general")  # fact, relationship, event, preference, pending
    content = Column(Text, default="")
    importance = Column(Float, default=0.5)
    keywords = Column(String, default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    character = relationship("Character", back_populates="memories")
    session = relationship("ChatSession", back_populates="memories")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, default="")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Persona(Base):
    __tablename__ = "personas"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, default="")
    pronouns = Column(String, default="")
    avatar_path = Column(String, default="")
    metadata_json = Column(Text, default="{}")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CharacterGroup(Base):
    __tablename__ = "character_groups"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, default="")
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan", order_by="GroupMember.position")


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "character_id", name="uq_group_character"),)

    id = Column(String, primary_key=True, default=generate_uuid)
    group_id = Column(String, ForeignKey("character_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    character_id = Column(String, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, default="member")
    position = Column(Integer, default=0)

    group = relationship("CharacterGroup", back_populates="members")
    character = relationship("Character")


class SessionBranch(Base):
    __tablename__ = "session_branches"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, default="剧情分支")
    parent_message_id = Column(String, default="")
    messages_json = Column(Text, default="[]")
    runtime_state_json = Column(Text, default="{}")
    runtime_revision = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    session = relationship("ChatSession", back_populates="branches")
