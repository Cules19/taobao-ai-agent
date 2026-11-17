import os

from openai import OpenAI


def ask_model(message: str) -> str:
    """把一条用户消息发给模型，返回回复文本。"""
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    base_url = os.getenv("OPENAI_BASE_URL")

    if not api_key or not model:
        raise RuntimeError("请设置 OPENAI_API_KEY 和 OPENAI_MODEL")

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": message}],
    )

    reply = response.choices[0].message.content
    if not reply:
        raise RuntimeError("模型没有返回文本")
    return reply