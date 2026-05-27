from typing import Optional, List

from pydantic import BaseModel


class DramaRowDTO(BaseModel):
    name: str = ""
    manju_id: str = ""
    publisher: str = ""
    publish_status: str = ""
    created_time: str = ""
    gender: str = ""
    category: str = ""
    detail_url: str = ""


class ScrapeDetailRequestDTO(BaseModel):
    drama_name: str
    detail_url: str = ""


class ScrapeBatchRequestDTO(BaseModel):
    items: List[ScrapeDetailRequestDTO]


class ScrapeStatusDTO(BaseModel):
    running: bool = False
    task_type: Optional[str] = None
    drama_name: Optional[str] = None
