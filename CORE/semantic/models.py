"""公共的 Semantic Layer 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SemanticObject:
    object_type: str
    object_id: str
    data: dict[str, Any]


@dataclass(frozen=True)
class SemanticRelation:
    relation_id: int
    source_type: str
    source_id: str
    relation_type: str
    target_type: str
    target_id: str
    rationale: str
    reason_trigger: str
    reason_gap: str
    reason_response: str
    provenance: str
    state: str
