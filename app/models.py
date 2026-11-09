from datetime import datetime
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, Boolean, BigInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(190), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str|None] = mapped_column(String(190), nullable=True)
    role: Mapped[str] = mapped_column(String(30), default='user')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)

class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str|None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)

class ProjectMember(Base):
    __tablename__ = 'project_members'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    role: Mapped[str] = mapped_column(String(40), default='viewer')
    relationship: Mapped[str] = mapped_column(String(24), default='member')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ProjectInvitation(Base):
    __tablename__ = 'project_invitations'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'), index=True)
    email: Mapped[str] = mapped_column(String(190), index=True)
    role: Mapped[str] = mapped_column(String(40), default='editor')
    relationship: Mapped[str] = mapped_column(String(24), default='member')
    status: Mapped[str] = mapped_column(String(24), default='pending', index=True)
    invited_by: Mapped[int|None] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint('project_id', 'email', name='uq_project_invitation_project_email'),)

class Chat(Base):
    __tablename__ = 'chats'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'), index=True)
    title: Mapped[str] = mapped_column(String(255), default='Hlavní chat')
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)

class Message(Base):
    __tablename__ = 'chat_messages'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey('chats.id'), index=True)
    user_id: Mapped[int|None] = mapped_column(ForeignKey('users.id'), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default='user')
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'), index=True)
    chat_id: Mapped[int|None] = mapped_column(ForeignKey('chats.id'), nullable=True, index=True)
    source_message_id: Mapped[int|None] = mapped_column(BigInteger, nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str|None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='todo', index=True)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)

class ProjectFile(Base):
    __tablename__ = 'project_files'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'), index=True)
    chat_id: Mapped[int|None] = mapped_column(ForeignKey('chats.id'), nullable=True, index=True)
    task_id: Mapped[int|None] = mapped_column(ForeignKey('tasks.id'), nullable=True, index=True)
    message_id: Mapped[int|None] = mapped_column(BigInteger, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    mime_type: Mapped[str|None] = mapped_column(String(190), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    kind: Mapped[str] = mapped_column(String(30), default='input')
    status: Mapped[str] = mapped_column(String(30), default='current')
    parent_file_id: Mapped[int|None] = mapped_column(ForeignKey('project_files.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ProjectMemory(Base):
    __tablename__ = 'project_memory'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'), index=True)
    kind: Mapped[str] = mapped_column(String(50), default='fact', index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ProjectEvent(Base):
    __tablename__ = 'project_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'), index=True)
    user_id: Mapped[int|None] = mapped_column(ForeignKey('users.id'), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    detail: Mapped[str|None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class LibraryItem(Base):
    __tablename__ = 'library_items'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int|None] = mapped_column(ForeignKey('users.id'), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(80), default='other')
    description: Mapped[str|None] = mapped_column(Text, nullable=True)
    stored_name: Mapped[str|None] = mapped_column(String(255), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProjectStage(Base):
    """Seven immutable stage identities; user-editable planning and acceptance data."""
    __tablename__ = 'project_stages'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'), index=True)
    stage_no: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    objective: Mapped[str|None] = mapped_column(Text, nullable=True)
    acceptance: Mapped[str|None] = mapped_column(Text, nullable=True)
    start_date: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    due_date: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='planned')
    note: Mapped[str|None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('project_id','stage_no',name='uq_project_stage_number'),)
