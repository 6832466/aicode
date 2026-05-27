from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.response import Res
from app.core.ws_manager import manager
from app.db.database import get_db
from app.dto.scrape_dto import ScrapeDetailRequestDTO, ScrapeBatchRequestDTO, ScrapeStatusDTO
from app.repositories.settings_repository import SettingsRepository
from app.services.scrape_service import scrape_service
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/api/scrape", tags=["scrape"])


def _validate_output_dir(output_dir: str) -> str | None:
    """验证保存目录存在且可写，返回错误消息或 None。"""
    import os as _os
    if not output_dir:
        return "请先在设置中配置保存目录"
    if not _os.path.isdir(output_dir):
        return f"保存目录不存在: {output_dir}"
    if not _os.access(output_dir, _os.W_OK):
        return f"保存目录无写入权限: {output_dir}"
    return None


def _get_settings(svc: SettingsService) -> dict:
    s = svc.get_settings()
    return {"user_data_dir": s.user_data_dir, "headless": s.silent_mode, "output_dir": s.output_dir}


@router.post("/list", response_model=Res[dict])
def start_list_scrape(db: Session = Depends(get_db)):
    svc = SettingsService(SettingsRepository(db))
    s = _get_settings(svc)
    err = _validate_output_dir(s["output_dir"])
    if err:
        return Res(code=400, message=err)
    scrape_service.start_list_scrape(s["user_data_dir"], s["headless"])
    return Res(data={"status": "started"})


@router.post("/detail", response_model=Res[dict])
def start_detail_scrape(dto: ScrapeDetailRequestDTO, db: Session = Depends(get_db)):
    svc = SettingsService(SettingsRepository(db))
    s = _get_settings(svc)
    err = _validate_output_dir(s["output_dir"])
    if err:
        return Res(code=400, message=err)
    scrape_service.start_detail_scrape(dto.drama_name, s["output_dir"], dto.detail_url, s["user_data_dir"], s["headless"])
    return Res(data={"status": "started"})


@router.post("/detail/batch", response_model=Res[dict])
def start_batch_scrape(dto: ScrapeBatchRequestDTO, db: Session = Depends(get_db)):
    svc = SettingsService(SettingsRepository(db))
    s = _get_settings(svc)
    err = _validate_output_dir(s["output_dir"])
    if err:
        return Res(code=400, message=err)
    items = [{"drama_name": item.drama_name, "detail_url": item.detail_url} for item in dto.items]
    scrape_service.start_batch_scrape(items, s["output_dir"], s["user_data_dir"], s["headless"])
    return Res(data={"status": "started", "total": len(items)})


@router.post("/stop", response_model=Res[dict])
def stop_scrape():
    scrape_service.stop()
    return Res(data={"status": "stopped"})


@router.get("/status", response_model=Res[ScrapeStatusDTO])
def get_scrape_status():
    return Res(data=scrape_service.get_status())
