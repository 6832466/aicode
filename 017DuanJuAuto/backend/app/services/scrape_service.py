"""采集服务 —— 引擎编排与批量管理。"""
from __future__ import annotations

import logging

from app.core.scraper_engine import ScraperEngine, get_scraper_engine
from app.core.ws_manager import manager
from app.dto.scrape_dto import DramaRowDTO, ScrapeStatusDTO


class ScrapeService:
    def __init__(self):
        self.engine = get_scraper_engine()
        self._batch_queue: list[dict] = []
        self._batch_idx: int = 0
        self._batch_output_dir: str = ""
        self._in_batch: bool = False

    def get_engine(self) -> ScraperEngine:
        return self.engine

    def start_list_scrape(self, user_data_dir: str, headless: bool):
        self.engine.start(user_data_dir, headless)
        self.engine.submit_list_scrape()

    def start_detail_scrape(self, drama_name: str, output_dir: str, detail_url: str, user_data_dir: str, headless: bool):
        self.engine.start(user_data_dir, headless)
        self.engine.submit_detail_scrape(drama_name, output_dir, detail_url)

    def start_batch_scrape(self, items: list, output_dir: str, user_data_dir: str, headless: bool):
        self.engine.start(user_data_dir, headless)
        self._batch_queue = items
        self._batch_idx = 0
        self._batch_output_dir = output_dir
        self._in_batch = True
        self._process_next_batch()

    def _process_next_batch(self):
        if self._batch_idx >= len(self._batch_queue):
            self._in_batch = False
            return
        item = self._batch_queue[self._batch_idx]
        self.engine.submit_detail_scrape(
            item.get("drama_name", ""),
            self._batch_output_dir,
            item.get("detail_url", ""),
        )

    def on_batch_item_finished(self, success: bool):
        """由引擎在详情采集完成时回调，推进批量队列。"""
        self._batch_idx += 1
        if self._in_batch:
            if self._batch_idx < len(self._batch_queue):
                payload = {
                    "type": "batch_progress",
                    "current": self._batch_idx,
                    "total": len(self._batch_queue),
                }
                manager.broadcast_sync(payload)
                self._process_next_batch()
            else:
                self._in_batch = False
                payload = {
                    "type": "batch_complete",
                    "total_processed": len(self._batch_queue),
                }
                manager.broadcast_sync(payload)

    def stop(self):
        self._in_batch = False
        self._batch_queue.clear()
        self.engine.request_stop()

    def get_status(self) -> ScrapeStatusDTO:
        status = self.engine.get_status()
        return ScrapeStatusDTO(
            running=status.get("running", False),
            task_type=status.get("task_type"),
            drama_name=status.get("drama_name"),
        )


scrape_service = ScrapeService()
