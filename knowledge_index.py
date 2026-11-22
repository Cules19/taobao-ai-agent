import argparse
import hashlib
import json
import logging
import math
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

MODEL = "BAAI/bge-small-zh-v1.5"
FORMAT = 1
LABEL = "选物模拟资料"
DOCUMENTS = Path(__file__).resolve().parent / "knowledge" / "documents.json"
logger = logging.getLogger("uvicorn.error.shop_knowledge")


def index_path():
    return Path(os.getenv("SHOP_KB_INDEX", ".shop-state/knowledge.json"))


def cache_path():
    return os.getenv("SHOP_EMBEDDING_CACHE", ".shop-state/embeddings")


@lru_cache(maxsize=4)
def embedder(cache, offline, model_path=None):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=MODEL, cache_dir=cache, threads=2, local_files_only=offline,
                         specific_model_path=model_path)


def configured_embedder(offline):
    local_model = Path(cache_path()) / "model"
    model_path = os.getenv("SHOP_EMBEDDING_MODEL_PATH")
    if not model_path and (local_model / "model_optimized.onnx").is_file():
        model_path = str(local_model)
    return embedder(cache_path(), offline, model_path)


def unit_vector(vector):
    values = [float(value) for value in vector]
    norm = math.hypot(*values)
    if not norm or not math.isfinite(norm):
        raise ValueError("无效嵌入向量")
    return [value / norm for value in values]


def build_index(path, model, documents=DOCUMENTS):
    raw = documents.read_bytes()
    records = json.loads(raw)
    splitter = RecursiveCharacterTextSplitter(chunk_size=115, chunk_overlap=20,
                                               separators=["\n\n", "\n", "。", "；", "，", ""])
    chunks = []
    ids = set()
    for doc in sorted(records, key=lambda item: item["id"]):
        if doc["id"] in ids or doc["label"] != LABEL:
            raise ValueError("文档 ID 重复或缺少模拟标签")
        ids.add(doc["id"])
        for position, fragment in enumerate(splitter.split_text(doc["text"]), 1):
            chunks.append({**{key: doc[key] for key in ("id", "title", "topic", "version", "label")},
                           "chunk_id": f"{doc['id']}-{position:02}", "snippet": fragment})
    vectors = [unit_vector(vector) for vector in model.passage_embed(
        [f"{chunk['title']}。{chunk['snippet']}" for chunk in chunks], batch_size=16)]
    if not chunks or len(chunks) != len(vectors) or len({len(vector) for vector in vectors}) != 1:
        raise ValueError("嵌入结果与分块不匹配")
    payload = {"format": FORMAT, "model": MODEL, "documents": len(records),
               "source_sha256": hashlib.sha256(raw).hexdigest(), "dimension": len(vectors[0]),
               "chunks": [{**chunk, "vector": vector} for chunk, vector in zip(chunks, vectors)]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            json.dump(payload, output, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        except Exception:
            output.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


@lru_cache(maxsize=4)
def load_index(path, modified, size, source_hash):
    index = json.loads(path.read_text(encoding="utf-8"))
    if (index["format"] != FORMAT or index["model"] != MODEL or not index["chunks"]
            or index["source_sha256"] != source_hash):
        raise ValueError("索引不兼容或资料已变更")
    seen = set()
    for chunk in index["chunks"]:
        if (chunk["label"] != LABEL or chunk["chunk_id"] in seen
                or len(chunk["vector"]) != index["dimension"]
                or not all(math.isfinite(value) for value in chunk["vector"])
                or any(not isinstance(chunk[key], str) for key in
                       ("id", "chunk_id", "title", "topic", "version", "snippet"))):
            raise ValueError("索引块结构无效")
        seen.add(chunk["chunk_id"])
    return index


def current_index():
    path = index_path().resolve()
    stat = path.stat()
    return load_index(path, stat.st_mtime_ns, stat.st_size, hashlib.sha256(DOCUMENTS.read_bytes()).hexdigest())


def knowledge_status():
    try:
        index = current_index()
        return {"status": "indexed", "documents": index["documents"], "chunks": len(index["chunks"])}
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "unavailable", "documents": 0, "chunks": 0}


def retrieve(query, model=None):
    try:
        index = current_index()
        model = model if model is not None else configured_embedder(True)
        vector = unit_vector(next(iter(model.query_embed(query))))
        if len(vector) != index["dimension"]:
            raise ValueError("查询向量与索引维度不一致")
        threshold = float(os.getenv("SHOP_KB_MIN_SCORE", "0.65"))
        if not 0 < threshold <= 1:
            raise ValueError("相似度阈值无效")
        ranked = sorted(((sum(left * right for left, right in zip(vector, chunk["vector"])), chunk)
                         for chunk in index["chunks"]), key=lambda pair: (-pair[0], pair[1]["chunk_id"]))
    except Exception as error:
        logger.warning("knowledge_unavailable type=%s", type(error).__name__)
        return {"status": "unavailable", "message": "模拟知识库暂不可用，无法核对这部分资料。", "sources": []}
    sources = []
    seen = set()
    for score, chunk in ranked:
        if score >= threshold and chunk["id"] not in seen:
            seen.add(chunk["id"])
            sources.append({key: value for key, value in chunk.items() if key != "vector"})
        if len(sources) == 3:
            break
    if not sources:
        return {"status": "not_found", "message": "选物模拟资料没有找到足够相关的证据，无法核对这部分问题。",
                "sources": []}
    return {"status": "ok", "sources": sources}


def main():
    parser = argparse.ArgumentParser(description="构建选物本地向量索引")
    parser.add_argument("--offline", action="store_true", help="只使用已缓存的嵌入权重")
    options = parser.parse_args()
    result = build_index(index_path(), configured_embedder(options.offline))
    print(f"indexed documents={result['documents']} chunks={len(result['chunks'])} model={MODEL}")


if __name__ == "__main__":
    main()
