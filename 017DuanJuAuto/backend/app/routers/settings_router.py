from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.response import Res
from app.db.database import get_db
from app.dto.settings_dto import SettingsResponseDTO, SettingsUpdateDTO
from app.repositories.settings_repository import SettingsRepository
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])


def get_settings_service(db: Session = Depends(get_db)) -> SettingsService:
    return SettingsService(SettingsRepository(db))


@router.get("", response_model=Res[SettingsResponseDTO])
def get_settings(service: SettingsService = Depends(get_settings_service)):
    data = service.get_settings()
    return Res(data=data)


@router.put("", response_model=Res[SettingsResponseDTO])
def update_settings(
    dto: SettingsUpdateDTO,
    service: SettingsService = Depends(get_settings_service),
):
    data = service.update_settings(dto)
    return Res(data=data)
