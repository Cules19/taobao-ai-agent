import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    production: bool = False
    origin: str = ""
    secret: str = secrets.token_urlsafe(48)
    database: Path = Path(".shop-state/store.sqlite3")
    visitor_limit: int = 12
    site_limit: int = 120
    daily_limit: int = 600
    retention_days: int = 7

    @classmethod
    def from_env(cls):
        production = os.getenv("SHOP_ENV", "development") == "production"
        database = Path(os.getenv("SHOP_DB_PATH", str(cls.database)))
        origin = os.getenv("SHOP_PUBLIC_ORIGIN", "").rstrip("/")
        secret = os.getenv("SHOP_SESSION_SECRET", "")
        if production:
            url = urlsplit(origin)
            if (url.scheme != "https" or not url.hostname or url.username or url.path
                    or url.query or url.fragment or len(secret) < 32
                    or not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_MODEL")):
                raise RuntimeError("生产环境需要 HTTPS origin、独立会话密钥以及模型配置")
            base = urlsplit(os.getenv("OPENAI_BASE_URL") or "https://api.openai.com")
            if base.scheme != "https" or not base.hostname:
                raise RuntimeError("生产模型接口必须使用 HTTPS")
        if not secret:
            secret_file = database.parent / "visitor.key"
            secret_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                with secret_file.open("x", encoding="ascii") as file:
                    file.write(cls.secret)
            except FileExistsError:
                pass
            secret = secret_file.read_text(encoding="ascii")
            if len(secret) < 32:
                raise RuntimeError("本地会话密钥文件无效")
        settings = cls(production, origin, secret, database,
                       int(os.getenv("SHOP_VISITOR_LIMIT", "12")),
                       int(os.getenv("SHOP_SITE_LIMIT", "120")),
                       int(os.getenv("SHOP_DAILY_LIMIT", "600")),
                       int(os.getenv("SHOP_RETENTION_DAYS", "7")))
        if min(settings.visitor_limit, settings.site_limit, settings.daily_limit, settings.retention_days) < 1:
            raise RuntimeError("额度和保留天数必须大于零")
        return settings
