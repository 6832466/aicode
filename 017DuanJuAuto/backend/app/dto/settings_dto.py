from typing import Optional

from pydantic import BaseModel


class SettingsResponseDTO(BaseModel):
    output_dir: str = ""
    user_data_dir: str = ""
    silent_mode: bool = False


class SettingsUpdateDTO(BaseModel):
    output_dir: Optional[str] = None
    user_data_dir: Optional[str] = None
    silent_mode: Optional[bool] = None
