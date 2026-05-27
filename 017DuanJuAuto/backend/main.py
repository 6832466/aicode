from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware

from app.core.config import get_config_path
from app.core.ws_manager import manager
from app.db.database import Base, engine
from app.routers import settings_router, scrape_router


def _ignore_proactor_assertion(loop, context):
    exc = context.get("exception")
    if isinstance(exc, AssertionError):
        return
    loop.default_exception_handler(context)


def _cleanup_residuals():
    import glob as _glob
    import shutil as _shutil
    config_dir = get_config_path()
    patterns = [".hongguo_*", ".webengine_profile*"]
    for pattern in patterns:
        for full in _glob.glob(os.path.join(config_dir, pattern)):
            try:
                _shutil.rmtree(full, ignore_errors=True)
            except Exception:
                try:
                    os.remove(full)
                except Exception:
                    pass


log_file_path = os.path.join(get_config_path(), "app.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file_path, encoding="utf-8"),
    ],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_ignore_proactor_assertion)
    Base.metadata.create_all(bind=engine)
    logging.info("数据库表已初始化")
    yield
    try:
        from app.services.scrape_service import scrape_service
        scrape_service.stop()
    except Exception:
        pass
    _cleanup_residuals()
    logging.info("已清理残留文件")


app = FastAPI(
    title="短剧素材采集工具",
    description="短剧素材采集后端服务",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(settings_router.router)
app.include_router(scrape_router.router)


@app.get("/")
def read_root():
    return {"msg": "短剧素材采集工具 后端服务运行中"}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    logging.info("WebSocket 客户端已连接")
    try:
        while True:
            msg_text = await ws.receive_text()
            try:
                data = json.loads(msg_text)
            except json.JSONDecodeError:
                data = {}

            msg_type = data.get("type")
            if msg_type == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
                continue
            elif msg_type:
                logging.debug(f"未知 WS 消息类型: {msg_type}")

    except WebSocketDisconnect:
        logging.info("WebSocket 客户端主动断开")
        manager.disconnect(ws)
    except Exception as e:
        logging.warning(f"WebSocket 连接异常: {e}")
        manager.disconnect(ws)
    except BaseException:
        manager.disconnect(ws)
        raise


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8200
    uvicorn.run(app, host="127.0.0.1", port=port, log_config=None)
