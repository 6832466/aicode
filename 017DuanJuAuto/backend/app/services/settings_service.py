import os
import tempfile

from sqlalchemy.orm import Session

from app.dto.settings_dto import SettingsResponseDTO, SettingsUpdateDTO
from app.repositories.settings_repository import SettingsRepository


class SettingsService:
    def __init__(self, repository: SettingsRepository):
        self.repository = repository

    def get_settings(self) -> SettingsResponseDTO:
        po = self.repository.get_settings()
        if not po:
            po = self.repository.create_default()
        return SettingsResponseDTO(
            output_dir=po.output_dir or "",
            user_data_dir=po.user_data_dir or os.path.join(tempfile.gettempdir(), "playwright_chrome_profile"),
            silent_mode=bool(po.silent_mode),
        )

    def update_settings(self, dto: SettingsUpdateDTO) -> SettingsResponseDTO:
        po = self.repository.get_settings()
        if not po:
            po = self.repository.create_default()
        updates = {}
        if dto.output_dir is not None:
            updates["output_dir"] = dto.output_dir
        if dto.user_data_dir is not None:
            updates["user_data_dir"] = dto.user_data_dir
        if dto.silent_mode is not None:
            updates["silent_mode"] = 1 if dto.silent_mode else 0
        self.repository.update_settings(po, updates)
        return self.get_settings()
