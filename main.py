from fastapi import FastAPI, HTTPException
from openai import APIError
from pydantic import BaseModel, Field

import model_client

app = FastAPI(title="淘宝商城 AI 导购智能体")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, str]:
    """接收用户消息，返回模型回复。"""
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="消息不能为空")

    try:
        reply = model_client.ask_model(message)
    except (RuntimeError, APIError) as exc:
        raise HTTPException(
            status_code=503,
            detail="模型服务暂时不可用",
        ) from exc

    return {"reply": reply}