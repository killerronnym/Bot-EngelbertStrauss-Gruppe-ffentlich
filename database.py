import os
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy import create_engine

# Path to the SQLite database file
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "bot_database.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

Base = declarative_base()
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True) # Telegram User ID
    username = Column(String)
    full_name = Column(String)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    is_blocked = Column(Boolean, default=False)
    
    activities = relationship("Activity", back_populates="user")
    invite_profile = relationship("InviteProfile", back_populates="user", uselist=False)

class Activity(Base):
    __tablename__ = "activities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow)
    chat_id = Column(Integer)
    chat_type = Column(String)
    chat_title = Column(String)
    thread_id = Column(Integer, nullable=True)
    message_id = Column(Integer)
    user_id = Column(Integer, ForeignKey("users.id"))
    text = Column(Text, nullable=True)
    msg_type = Column(String) # text, photo, video, etc.
    has_media = Column(Boolean, default=False)
    media_kind = Column(String, nullable=True)
    file_id = Column(String, nullable=True)
    is_command = Column(Boolean, default=False)
    
    user = relationship("User", back_populates="activities")

class InviteProfile(Base):
    __tablename__ = "invite_profiles"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    answers = Column(JSON) # Stores all form answers as JSON object
    created_at = Column(DateTime, default=datetime.utcnow)
    is_approved = Column(Boolean, default=False)
    
    user = relationship("User", back_populates="invite_profile")

class Topic(Base):
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer)
    topic_id = Column(Integer) # Telegram thread_id
    name = Column(String)

class Broadcast(Base):
    __tablename__ = "broadcasts"
    id = Column(String, primary_key=True) # UUID
    text = Column(Text)
    topic_id = Column(Integer, nullable=True)
    send_mode = Column(String) # immediate, scheduled
    scheduled_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    status = Column(String, default="pending") # pending, sent, error, scheduled
    pin_message = Column(Boolean, default=False)
    silent_send = Column(Boolean, default=False)
    media_name = Column(String, nullable=True)
    error_msg = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ModerationLog(Base):
    __tablename__ = "moderation_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow)
    chat_id = Column(Integer)
    user_id = Column(Integer)
    admin_id = Column(Integer, nullable=True)
    action = Column(String) # warn, delete, ban, mute
    reason = Column(Text, nullable=True)
    message_id = Column(Integer, nullable=True)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
