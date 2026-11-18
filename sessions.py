from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from uuid import UUID, uuid4

HISTORY_TURNS = 6


@dataclass
class Session:
    turns: deque[list[dict]] = field(default_factory=lambda: deque(maxlen=HISTORY_TURNS))
    favorites: list[str] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)


SESSIONS: dict[UUID, Session] = {}
SESSIONS_LOCK = Lock()


def get_session(session_id: UUID | None) -> tuple[UUID, Session]:
    """找到已有会话；首次使用或服务重启后创建一个新会话。"""
    with SESSIONS_LOCK:
        if session_id in SESSIONS:
            return session_id, SESSIONS[session_id]
        new_id = uuid4()
        session = Session()
        SESSIONS[new_id] = session
        return new_id, session
