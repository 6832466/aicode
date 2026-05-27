from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime

from app.db.database import Base


class AppSettingsPO(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    output_dir = Column(String(500), nullable=False, default="")
    user_data_dir = Column(String(500), nullable=False, default="")
    silent_mode = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
