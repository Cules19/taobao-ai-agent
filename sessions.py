from collections import deque
from dataclasses import dataclass, field
from threading import Lock

HISTORY_TURNS = 6


@dataclass
class Session:
    turns: deque[list[dict]] = field(default_factory=lambda: deque(maxlen=HISTORY_TURNS))
    favorites: list[str] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)
