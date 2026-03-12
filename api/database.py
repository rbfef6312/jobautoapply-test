"""SQLite 数据库模型"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import DATA_DIR

DATABASE_URL = f"sqlite:///{DATA_DIR / 'jobsdb_web.db'}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class MonitorSettings(Base):
    __tablename__ = "monitor_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    enabled = Column(Boolean, default=False)
    interval_min = Column(Integer, default=4)
    interval_max = Column(Integer, default=6)
    mode1_enabled = Column(Boolean, default=True)
    mode2_enabled = Column(Boolean, default=False)
    mode2_keywords = Column(String(500), default="")
    mode3_enabled = Column(Boolean, default=False)
    mode3_category = Column(String(100), default="")
    # 自动投递：单模式 1/2/3，间隔小时，最大页数 1-8，填表偏好
    mode = Column(Integer, default=1)
    interval_hours = Column(Integer, default=6)
    max_pages = Column(Integer, default=3)
    experience_years = Column(Integer, default=3)
    expected_salary = Column(String(20), default="16K")
    next_run_at = Column(DateTime, nullable=True)
    last_run_started_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_or_create_monitor_settings(db: Session, user_id: int) -> MonitorSettings:
    s = db.query(MonitorSettings).filter(MonitorSettings.user_id == user_id).first()
    if s is None:
        s = MonitorSettings(user_id=user_id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s
