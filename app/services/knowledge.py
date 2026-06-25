import hashlib
import math
import re
from collections import Counter

from sqlalchemy.orm import Session

from app import models, schemas
from app.services.audit import audit


WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> list[str]:
    return [word.lower() for word in WORD_RE.findall(text)]


def chunks_for(content: str, size: int = 900) -> list[str]:
    paragraphs = [p.strip() for p in content.splitlines() if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [content]:
        if len(current) + len(paragraph) + 1 > size and current:
            chunks.append(current.strip())
            current = paragraph
        else:
            current = f"{current}\n{paragraph}".strip()
    if current:
        chunks.append(current.strip())
    return chunks


def create_source(db: Session, business_id: int, payload: schemas.KnowledgeSourceCreate, created_by: int | None = None) -> models.KnowledgeSource:
    checksum = hashlib.sha256(payload.content.encode()).hexdigest()
    source = models.KnowledgeSource(
        business_id=business_id,
        type=payload.type,
        title=payload.title,
        source_uri=payload.source_uri,
        checksum=checksum,
        created_by=created_by,
        status="ready",
    )
    db.add(source)
    db.flush()
    for idx, content in enumerate(chunks_for(payload.content)):
        db.add(
            models.KnowledgeChunk(
                business_id=business_id,
                source_id=source.id,
                chunk_index=idx,
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                token_count=len(tokenize(content)),
                metadata_json={"title": payload.title, "type": payload.type, "source_uri": payload.source_uri},
            )
        )
    audit(db, business_id=business_id, actor_user_id=created_by, action="knowledge.source.created", entity_type="knowledge_source", entity_id=str(source.id))
    db.commit()
    db.refresh(source)
    return source


def search(db: Session, business_id: int, query: str, top_k: int = 5) -> list[dict]:
    q_tokens = Counter(tokenize(query))
    if not q_tokens:
        return []
    rows = db.query(models.KnowledgeChunk).filter(models.KnowledgeChunk.business_id == business_id).all()
    scored: list[tuple[float, models.KnowledgeChunk]] = []
    for chunk in rows:
        c_tokens = Counter(tokenize(chunk.content))
        overlap = sum(min(q_tokens[token], c_tokens[token]) for token in q_tokens)
        if overlap == 0:
            continue
        norm = math.sqrt(sum(v * v for v in c_tokens.values())) or 1
        score = overlap / norm
        scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "id": chunk.id,
            "source_id": chunk.source_id,
            "content": chunk.content,
            "score": round(score, 4),
            "metadata": chunk.metadata_json,
        }
        for score, chunk in scored[:top_k]
    ]
