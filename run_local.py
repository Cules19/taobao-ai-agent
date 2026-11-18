import os
from getpass import getpass

import uvicorn


def main() -> None:
    """在交互式终端运行本地商城，缺少 Key 时通过隐藏输入读取。"""
    if not os.getenv("OPENAI_MODEL") and not os.getenv("OPENAI_BASE_URL"):
        os.environ["OPENAI_MODEL"] = "deepseek-flash"
        os.environ["OPENAI_BASE_URL"] = "https://api.deepseek.com"
    if not os.getenv("OPENAI_MODEL"):
        raise SystemExit("请先设置 OPENAI_MODEL。")
    if not os.getenv("OPENAI_API_KEY"):
        api_key = getpass("请输入所选服务商的 API Key（输入不会显示）：").strip()
        if not api_key:
            raise SystemExit("未输入 API Key，服务未启动。")
        os.environ["OPENAI_API_KEY"] = api_key

    uvicorn.run("main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
