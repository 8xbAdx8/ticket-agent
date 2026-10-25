# -*- coding: utf-8 -*-
"""RAG 政策检索。

两种检索方式：
  - 默认关键词打分（零依赖，离线可跑，成员 A 第一天就能用）
  - USE_VECTOR_RAG=1 时启用本地向量检索（需 pip install sentence-transformers faiss-cpu）
"""
import re
import math
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

_CACHE = None


def load_chunks():
    """把 policies.md 按 '## [doc_id] 标题' 切成知识块。"""
    global _CACHE
    if _CACHE:
        return _CACHE
    text = config.POLICY_PATH.read_text(encoding="utf-8")
    blocks = re.split(r"\n## ", text)
    chunks = []
    for b in blocks:
        m = re.match(r"\[(P\d+)\]\s*(.*)", b.strip())
        if not m:
            continue
        doc_id, title = m.group(1), m.group(2).strip()
        body = b.split("\n", 1)[1].strip() if "\n" in b else ""
        chunks.append({"doc_id": doc_id, "title": title, "content": body})
    _CACHE = chunks
    return chunks


def _tokenize(s):
    # 中文按字切分 + 英文数字按词切分，够用且零依赖
    return [c for c in s if "\u4e00" <= c <= "\u9fff"] + re.findall(r"[a-zA-Z0-9]+", s)


def keyword_search(query, top_k=None):
    chunks = load_chunks()
    q = set(_tokenize(query))
    scored = []
    for ch in chunks:
        text = ch["title"] + ch["content"]
        tokens = _tokenize(text)
        if not tokens:
            continue
        tf = sum(1 for t in tokens if t in q)
        score = tf / math.sqrt(len(tokens))
        if score > 0:
            scored.append((score, ch))
    scored.sort(key=lambda x: -x[0])
    top_k = top_k or config.TOP_K
    return [{"doc_id": c["doc_id"], "source": "data/policies.md#" + c["doc_id"], "title": c["title"], "content": c["content"],
             "score": round(s, 4)} for s, c in scored[:top_k]]


def vector_search(query, top_k=None):
    """可选：本地向量检索（首次会下载 bge-small-zh 模型）。"""
    from sentence_transformers import SentenceTransformer
    import faiss
    import numpy as np
    chunks = load_chunks()
    model = SentenceTransformer(config.EMBED_MODEL)
    emb = model.encode([c["title"] + c["content"] for c in chunks], normalize_embeddings=True)
    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(np.array(emb, dtype="float32"))
    q = model.encode([query], normalize_embeddings=True)
    top_k = min(top_k or config.TOP_K, len(chunks))
    scores, idx = index.search(np.array(q, dtype="float32"), top_k)
    return [{"doc_id": chunks[i]["doc_id"], "source": "data/policies.md#" + chunks[i]["doc_id"], "title": chunks[i]["title"],
             "content": chunks[i]["content"], "score": float(scores[0][j])}
            for j, i in enumerate(idx[0]) if i >= 0]


def search_policy(question):
    """统一入口：返回带 doc_id 的政策片段，回答时必须引用 doc_id。"""
    import os
    if os.getenv("AGENT_RAG_MODE"):
        from target.rag_service import retrieve
        return retrieve(question,allow_network=os.getenv("RAG_ALLOW_NETWORK")=="1")
    try:
        hits = vector_search(question) if config.USE_VECTOR_RAG else keyword_search(question)
    except Exception:
        if config.PROVIDER in ("deepseek","bailian"):
            raise  # A Live vector failure must never masquerade as successful keyword retrieval.
        hits = keyword_search(question)  # 可选向量依赖不可用时保留离线能力
    return {"question": question, "hits": hits, "count": len(hits)}
