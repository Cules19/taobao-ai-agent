import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from threading import BoundedSemaphore
from uuid import uuid4

from langsmith import Client

logger = logging.getLogger("uvicorn.error.shop_trace")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shop-trace")
_slots = BoundedSemaphore(16)
NODES = {"load_session": "chain", "model": "llm", "tools": "chain", "finalize": "chain",
         "search_products": "tool", "get_product_detail": "tool", "list_coupons": "tool",
         "query_order": "tool", "manage_favorites": "tool", "retrieve_knowledge": "retriever"}
OUTCOMES = {"ok", "error", "invalid", "not_found", "unavailable", "limit"}


@lru_cache(maxsize=1)
def smith_client(key, endpoint, workspace):
    return Client(api_key=key, api_url=endpoint, workspace_id=workspace or None,
                  timeout_ms=2500, auto_batch_tracing=False, omit_traced_runtime_info=True,
                  hide_inputs=True, otel_enabled=False)


class TurnTrace:
    def __init__(self, request_id):
        self.request_id = request_id
        self.events = []
        self.start = datetime.now(timezone.utc)

    def record(self, node, start, outcome):
        if node in NODES and outcome in OUTCOMES:
            self.events.append((node, start, datetime.now(timezone.utc), outcome))

    def finish(self, outcome):
        key = os.getenv("LANGSMITH_API_KEY")
        if os.getenv("SHOP_LANGSMITH_TRACING", "").lower() not in {"1", "true"} or not key:
            return
        if not _slots.acquire(blocking=False):
            logger.warning("trace_queue_full")
            return
        try:
            end = datetime.now(timezone.utc)
            _pool.submit(self.publish, key, end, outcome, tuple(self.events))
        except Exception:
            _slots.release()
            logger.warning("trace_queue_unavailable")

    def publish(self, key, end, outcome, events):
        try:
            client = smith_client(key, os.getenv("LANGSMITH_ENDPOINT") or "https://api.smith.langchain.com",
                                  os.getenv("LANGSMITH_WORKSPACE_ID", ""))
            project = os.getenv("LANGSMITH_PROJECT") or "select-studio"
            root = uuid4()
            order = dotted_order(self.start, root)
            metadata = {"request_id": self.request_id, "redaction": "metadata-only"}
            client.create_run("shop.turn", {}, "chain", id=root, trace_id=root, dotted_order=order,
                              project_name=project, start_time=self.start, end_time=end,
                              outputs={"status": outcome}, extra={"metadata": metadata},
                              error="turn_failed" if outcome == "error" else None)
            for node, started, ended, status in events:
                child = uuid4()
                client.create_run(node, {}, NODES[node], id=child, trace_id=root, parent_run_id=root,
                                  dotted_order=order + "." + dotted_order(started, child),
                                  project_name=project, start_time=started, end_time=ended,
                                  outputs={"status": status}, extra={"metadata": metadata},
                                  error="node_failed" if status == "error" else None)
        except Exception as exc:
            logger.warning("trace_export_failed type=%s", type(exc).__name__)
        finally:
            _slots.release()


def dotted_order(moment, identifier):
    return moment.strftime("%Y%m%dT%H%M%S%fZ") + str(identifier)
