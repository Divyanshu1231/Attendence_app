from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="employee", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    face_descriptor: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    attendance: Mapped[list["Attendance"]] = relationship(back_populates="employee")

class Attendance(Base):
    __tablename__ = "attendance"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    work_date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    check_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lunch_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lunch_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="present", nullable=False)
    check_in_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_in_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_in_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    employee: Mapped[User] = relationship(back_populates="attendance")


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
