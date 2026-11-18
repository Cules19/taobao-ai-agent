import os

from openai import OpenAI


def create_model_client() -> tuple[OpenAI, str]:
    """读取环境变量，返回 SDK 客户端和模型名。"""
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    base_url = os.getenv("OPENAI_BASE_URL")

    if not api_key or not model:
        raise RuntimeError("请设置 OPENAI_API_KEY 和 OPENAI_MODEL")

    return OpenAI(api_key=api_key, base_url=base_url), model


def ask_model(message: str) -> str:
    """把一条用户消息发给模型，返回回复文本。"""
    client, model = create_model_client()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": message}],
    )

    reply = response.choices[0].message.content if response.choices else None
    if not reply:
        raise RuntimeError("模型没有返回文本")
    return reply
