import logging
import sqlite3
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from time import perf_counter, time
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import APIError
from pydantic import BaseModel, Field

import agent
from knowledge_index import knowledge_status
from boundary import RequestBoundary, visitor
from runtime import Settings
from storage import ConversationBusy, ConversationMissing, QuotaExceeded, Store
from tracing import TurnTrace

WEB_DIR = Path(__file__).resolve().parent / "web"
logger = logging.getLogger("uvicorn.error.shop_chat")
settings = Settings.from_env()


@lru_cache
def get_store() -> Store:
    return Store(settings.database, settings.retention_days)


@asynccontextmanager
async def lifespan(app):
    app.dependency_overrides.get(get_store, get_store)()
    yield


app = FastAPI(title="选物助手", version="3.0.0", lifespan=lifespan,
              docs_url=None if settings.production else "/docs",
              openapi_url=None if settings.production else "/openapi.json", redoc_url=None)
app.add_middleware(RequestBoundary, settings=settings)
app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")


@app.exception_handler(ConversationMissing)
async def missing_conversation(request, exc):
    return JSONResponse({"detail": "对话不存在或已过期"}, 404)


@app.exception_handler(ConversationBusy)
async def busy_conversation(request, exc):
    return JSONResponse({"detail": "这个对话正在处理另一条消息，请稍后再试"}, 409)


@app.exception_handler(sqlite3.Error)
async def storage_unavailable(request, exc):
    logger.error("storage_failure type=%s", type(exc).__name__)
    return JSONResponse({"detail": "会话存储暂时不可用"}, 503)


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/healthz", include_in_schema=False)
def live():
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
def ready(store: Store = Depends(get_store)):
    with store.connect() as db:
        db.execute("SELECT id FROM conversations LIMIT 1").fetchall()
    return {"status": "ready"}


@app.get("/api/knowledge/status")
def knowledge():
    return knowledge_status()


@app.get("/api/conversations")
def conversations(request: Request, response: Response, store: Store = Depends(get_store)):
    return {"items": store.list(visitor(request, response, settings), int(time()))}


@app.get("/api/conversations/{conversation_id}")
def load_conversation(conversation_id: UUID, request: Request, response: Response,
                      store: Store = Depends(get_store)):
    return store.read(visitor(request, response, settings), conversation_id.hex, int(time()))


@app.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID, request: Request, response: Response,
                        store: Store = Depends(get_store)):
    store.delete(visitor(request, response, settings), conversation_id.hex, int(time()))


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: UUID | None = None


@app.post("/chat")
def chat(payload: ChatRequest, request: Request, response: Response, store: Store = Depends(get_store)) -> dict:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="消息不能为空")

    owner = visitor(request, response, settings)
    now = int(time())
    try:
        store.charge(owner, settings, now)
    except QuotaExceeded as exc:
        raise HTTPException(429, "消息发送额度已达上限，请稍后再试",
                            headers={"Retry-After": str(exc.retry_after)}) from exc

    session_id, lease, session, visible, title = store.begin(
        owner, payload.session_id.hex if payload.session_id else None, now)
    request_id = uuid4().hex
    trace = TurnTrace(request_id)
    response.headers["X-Request-ID"] = request_id
    started = perf_counter()
    outcome = "error"
    try:
        result = agent.run_turn(message, session, trace=trace)
        status = result.get("turn_status", "completed")
        if status == "completed":
            store.finish(owner, session_id, lease, session, visible, title, message, result, int(time()))
        outcome = {"completed": "ok", "limited": "limit", "failed": "error"}[status]
        return {"session_id": str(UUID(hex=session_id)), **result}
    except (RuntimeError, APIError) as exc:
        logger.warning("chat_failure request_id=%s type=%s provider_status=%s",
                       request_id, type(exc).__name__, getattr(exc, "status_code", None))
        raise HTTPException(503, "模型服务暂时不可用", headers={"X-Request-ID": request_id}) from exc
    finally:
        try:
            if title is not None and outcome != "ok":
                store.release(owner, session_id, lease)
        finally:
            trace.finish(outcome)
            logger.info("chat request_id=%s status=%s elapsed_ms=%.1f",
                        request_id, outcome, (perf_counter() - started) * 1000)
