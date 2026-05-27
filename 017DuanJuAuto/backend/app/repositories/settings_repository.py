from sqlalchemy.orm import Session

from app.models.po import AppSettingsPO


class SettingsRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_settings(self) -> AppSettingsPO | None:
        return self.db.query(AppSettingsPO).filter(AppSettingsPO.id == 1).first()

    def create_default(self) -> AppSettingsPO:
        po = AppSettingsPO(id=1, output_dir="", user_data_dir="", silent_mode=0)
        self.db.add(po)
        self.db.commit()
        self.db.refresh(po)
        return po

    def update_settings(self, po: AppSettingsPO, updates: dict) -> AppSettingsPO:
        for key, value in updates.items():
            if value is not None and hasattr(po, key):
                setattr(po, key, value)
        self.db.commit()
        self.db.refresh(po)
        return po
