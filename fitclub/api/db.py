"""Modelos y motor de base de datos (SQLModel / Postgres)."""
import os
from datetime import date, datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint, create_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./fitclub.db")
_connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
engine = create_engine(DATABASE_URL, connect_args=_connect_args, echo=False)


def _now_naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    display_name: str
    password_hash: str
    tz: str = "America/Argentina/Buenos_Aires"
    created_at: datetime = Field(default_factory=_now_naive_utc)


class Activity(SQLModel, table=True):
    __tablename__ = "activity"
    __table_args__ = (
        UniqueConstraint("user_id", "external_id", name="uq_user_external"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    external_id: Optional[str] = Field(default=None, index=True)
    name: str
    type: str = "other"  # run, walk, bike, swim, strength, workout...
    start_utc: datetime = Field(index=True)  # siempre UTC naive
    duration_min: Optional[float] = None
    distance_km: Optional[float] = None
    calories: Optional[int] = None
    steps: Optional[int] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    rpe: Optional[int] = None
    source: str = "manual"  # manual, fitbit_csv, fitbit_api
    created_at: datetime = Field(default_factory=_now_naive_utc)


class DailyMetric(SQLModel, table=True):
    __tablename__ = "daily_metric"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    date: date = Field(index=True)
    steps: Optional[int] = None
    resting_hr: Optional[int] = None
    sleep_hours: Optional[float] = None
    sleep_score: Optional[int] = None
    deep_sleep_min: Optional[int] = None
    stress: Optional[int] = None
    vo2max: Optional[float] = None
    weight_kg: Optional[float] = None


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
