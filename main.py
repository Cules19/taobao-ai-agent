import logging
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import APIError
from pydantic import BaseModel, Field

import agent
from sessions import get_session

app = FastAPI(title="淘宝商城 AI 导购智能体")
WEB_DIR = Path(__file__).resolve().parent / "web"
logger = logging.getLogger("uvicorn.error.shop_chat")
app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    """返回原生聊天页面。"""
    return FileResponse(WEB_DIR / "index.html")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: UUID | None = None


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    """接收消息与可选会话编号，返回回复、商品卡片数据和收藏。"""
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="消息不能为空")

    session_id, session = get_session(request.session_id)
    try:
        result = agent.run_turn(message, session)
    except (RuntimeError, APIError) as exc:
        logger.warning("chat_failure type=%s provider_status=%s",
                       type(exc).__name__, getattr(exc, "status_code", None))
        raise HTTPException(
            status_code=503,
            detail="模型服务暂时不可用",
        ) from exc

    return {"session_id": str(session_id), **result}
