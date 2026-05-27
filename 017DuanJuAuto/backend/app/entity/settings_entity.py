from dataclasses import dataclass


@dataclass
class SettingsEntity:
    id: int = 1
    output_dir: str = ""
    user_data_dir: str = ""
    silent_mode: bool = False
