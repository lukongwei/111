"""Semantic Layer v0.1 的持久化服务。

本服务记录 Problem、Goal、Module、Implementation 及其解释性关系。
它不做 Goal 优化、冲突消解、必要性判断或自动修改 Mathematical Problem。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from CORE.index.database import IndexDatabase
from .models import SemanticObject, SemanticRelation


OBJECT_TYPES = {"problem", "goal", "module", "implementation"}
PROVENANCE = {"Human", "AI", "System"}
STATES = {"proposed", "active", "modified", "deprecated"}
TABLES = {
    "problem": "semantic_problems",
    "goal": "semantic_goals",
    "module": "semantic_modules",
    "implementation": "semantic_implementations",
}
RELATION_SHAPES = {
    ("problem", "derives", "goal"),
    ("module", "implements", "goal"),
    ("module", "realized_by", "implementation"),
    ("goal", "conflict", "goal"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 不能为空")
    return value.strip()


class SemanticService:
    """在现有 Index 数据库上提供 Semantic Layer 的最小闭环。"""

    def __init__(self, database: IndexDatabase) -> None:
        self.database = database
        self.connection = database.connection

    def create_problem(
        self, title: str, definition: str, formalization: str = "",
        constraints: str = "", human: str = "Human",
    ) -> SemanticObject:
        """创建由 Human 定义的问题；不接受 AI/System 作为定义者。"""

        if human != "Human":
            raise PermissionError("Mathematical Problem 只能由 Human 定义")
        values = (
            _required_text(title, "title"), _required_text(definition, "definition"),
            formalization.strip(), constraints.strip(), _now(), human,
        )
        with self.database.transaction():
            problem_id = self._allocate_id("semantic_problem", "MP")
            self.connection.execute(
                "INSERT INTO semantic_problems(problem_id, title, definition, formalization, "
                "constraints, provenance, state, created_at, created_by) "
                "VALUES (?, ?, ?, ?, ?, 'Human', 'active', ?, ?)",
                (problem_id, *values),
            )
            self._history("problem", problem_id, "created", self._get("problem", problem_id), "Human", human)
        return self.get("problem", problem_id)

    def create_goal(
        self, title: str, description: str, provenance: str = "AI", created_by: str = "AI",
    ) -> SemanticObject:
        return self._create_simple("goal", title, description, provenance, created_by)

    def create_module(
        self, name: str, function: str, goal_id: str, rationale: str,
        trigger: str, gap: str, response: str,
        provenance: str = "AI", created_by: str = "AI",
    ) -> SemanticObject:
        self._validate_provenance(provenance)
        self._get("goal", goal_id)
        name = _required_text(name, "name")
        function = _required_text(function, "function")
        relation_values = tuple(_required_text(value, field) for value, field in (
            (rationale, "rationale"), (trigger, "trigger"),
            (gap, "gap"), (response, "response"),
        ))
        timestamp = _now()
        with self.database.transaction():
            module_id = self._allocate_id("semantic_module", "M")
            self.connection.execute(
                "INSERT INTO semantic_modules(module_id, name, function, primary_goal_id, provenance, state, created_at, updated_at, created_by) "
                "VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)",
                (module_id, name, function, goal_id, provenance, timestamp, timestamp, created_by),
            )
            self._history("module", module_id, "created", self._get("module", module_id), provenance, created_by)
            self.connection.execute(
                "INSERT INTO semantic_relations(source_type, source_id, relation_type, target_type, target_id, "
                "rationale, reason_trigger, reason_gap, reason_response, provenance, state, created_at, created_by) "
                "VALUES ('module', ?, 'implements', 'goal', ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
                (module_id, goal_id, *relation_values, provenance, timestamp, created_by),
            )
        return self.get("module", module_id)

    def create_implementation(
        self, reference_type: str, reference_id: str, observed_meaning: str,
        project_id: str | None = None, created_by: str = "System",
    ) -> SemanticObject:
        if reference_type not in {"file", "symbol", "runtime", "other"}:
            raise ValueError("不支持的 implementation reference_type")
        meaning = _required_text(observed_meaning, "observed_meaning")
        reference_id = _required_text(reference_id, "reference_id")
        if reference_type in {"file", "symbol"} and project_id is None:
            raise ValueError("file / symbol implementation 必须指定 project_id")
        if project_id is not None:
            self._project_exists(project_id)
        if reference_type == "file":
            row = self.connection.execute(
                "SELECT 1 FROM files WHERE file_id = ? AND project_id = ? AND status = 'active'",
                (reference_id, project_id),
            ).fetchone()
            if row is None:
                raise KeyError("Implementation File 不存在、已删除或不属于指定 Project")
        elif reference_type == "symbol":
            row = self.connection.execute(
                "SELECT 1 FROM symbols WHERE symbol_id = ? AND project_id = ?",
                (reference_id, project_id),
            ).fetchone()
            if row is None:
                raise KeyError("Implementation Symbol 不存在或不属于指定 Project")
        timestamp = _now()
        with self.database.transaction():
            implementation_id = self._allocate_id("semantic_implementation", "I")
            self.connection.execute(
                "INSERT INTO semantic_implementations(implementation_id, reference_type, reference_id, "
                "project_id, observed_meaning, provenance, state, created_at, updated_at, created_by) "
                "VALUES (?, ?, ?, ?, ?, 'System', 'active', ?, ?, ?)",
                (implementation_id, reference_type, reference_id,
                 project_id, meaning, timestamp, timestamp, created_by),
            )
            self._history("implementation", implementation_id, "created", self._get("implementation", implementation_id), "System", created_by)
        return self.get("implementation", implementation_id)

    def relate(
        self, source_type: str, source_id: str, relation_type: str,
        target_type: str, target_id: str, rationale: str,
        trigger: str, gap: str, response: str,
        provenance: str = "AI", created_by: str = "AI", state: str = "active",
    ) -> SemanticRelation:
        self._validate_type(source_type)
        self._validate_type(target_type)
        self._validate_state(state)
        self._validate_provenance(provenance)
        if (source_type, relation_type, target_type) not in RELATION_SHAPES:
            raise ValueError("Semantic relation 类型与端点不符合 v0.1 关系模型")
        self._get(source_type, source_id)
        self._get(target_type, target_id)
        values = tuple(_required_text(value, field) for value, field in (
            (relation_type, "relation_type"), (rationale, "rationale"),
            (trigger, "trigger"), (gap, "gap"), (response, "response"),
        ))
        with self.database.transaction():
            cursor = self.connection.execute(
                "INSERT INTO semantic_relations(source_type, source_id, relation_type, target_type, target_id, "
                "rationale, reason_trigger, reason_gap, reason_response, provenance, state, created_at, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (source_type, source_id, values[0], target_type, target_id, *values[1:], provenance, state, _now(), created_by),
            )
            relation_id = int(cursor.lastrowid)
        return self.get_relation(relation_id)

    def set_state(
        self, object_type: str, object_id: str, state: str,
        provenance: str, actor: str, rationale: str,
    ) -> SemanticObject:
        """追加生命周期版本；Mathematical Problem 不允许通过此接口修改。"""

        self._validate_type(object_type)
        self._validate_state(state)
        self._validate_provenance(provenance)
        if object_type == "problem":
            raise PermissionError("Mathematical Problem 只能经 Human 确认流程修改；该流程尚未实现")
        rationale = _required_text(rationale, "rationale")
        current = self._get(object_type, object_id)
        table = TABLES[object_type]
        id_column = f"{object_type}_id"
        timestamp = _now()
        with self.database.transaction():
            self._history(object_type, object_id, "before_state_change", current, provenance, actor)
            self.connection.execute(
                f"UPDATE {table} SET state = ?, updated_at = ? WHERE {id_column} = ?",
                (state, timestamp, object_id),
            )
            updated = self._get(object_type, object_id)
            self._history(object_type, object_id, f"state:{state}; rationale:{rationale}", updated, provenance, actor)
        return self.get(object_type, object_id)

    def annotate(
        self, object_type: str, object_id: str, meaning: str,
        engineering_problem: str = "", engineering_goal: str = "",
        mathematical_problem: str = "", origin_type: str = "Manual",
        origin_id: str | None = None, trigger: str = "", gap: str = "",
        response: str = "", provenance: str = "AI", created_by: str = "AI",
        state: str = "active",
    ) -> int:
        self._validate_type(object_type)
        self._validate_provenance(provenance)
        self._validate_state(state)
        self._get(object_type, object_id)
        self._required_annotation_reason(origin_type, trigger, gap, response)
        if object_type == "module":
            _required_text(engineering_problem, "engineering_problem")
            _required_text(engineering_goal, "engineering_goal")
            _required_text(mathematical_problem, "mathematical_problem")
        with self.database.transaction():
            cursor = self.connection.execute(
                "INSERT INTO semantic_annotations(object_type, object_id, meaning, engineering_problem, "
                "engineering_goal, mathematical_problem, origin_type, origin_id, reason_trigger, reason_gap, "
                "reason_response, provenance, state, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (object_type, object_id, _required_text(meaning, "meaning"), engineering_problem,
                 engineering_goal, mathematical_problem, _required_text(origin_type, "origin_type"), origin_id,
                 trigger, gap, response, provenance, state, _now(), created_by),
            )
            return int(cursor.lastrowid)

    def record_drift(self, implementation_id: str, declared_meaning: str, observed_meaning: str, evidence: str) -> int:
        self._get("implementation", implementation_id)
        with self.database.transaction():
            cursor = self.connection.execute(
                "INSERT INTO semantic_drift(implementation_id, declared_meaning, observed_meaning, evidence, state, created_at) "
                "VALUES (?, ?, ?, ?, 'review_required', ?)",
                (implementation_id, _required_text(declared_meaning, "declared_meaning"),
                 _required_text(observed_meaning, "observed_meaning"), _required_text(evidence, "evidence"), _now()),
            )
            return int(cursor.lastrowid)

    def revise(
        self, object_type: str, object_id: str, changes: dict[str, str],
        provenance: str, actor: str, rationale: str,
    ) -> SemanticObject:
        """Append before/after snapshots for a meaning change; Problem is excluded."""

        self._validate_type(object_type)
        self._validate_provenance(provenance)
        if object_type == "problem":
            raise PermissionError("Mathematical Problem 修改必须经 Human 提案确认流程；该流程尚未实现")
        allowed = {
            "goal": {"title", "description"},
            "module": {"name", "function"},
            "implementation": {"observed_meaning"},
        }[object_type]
        if not changes or set(changes) - allowed:
            raise ValueError(f"可修改字段仅限: {sorted(allowed)}")
        normalized = {key: _required_text(value, key) for key, value in changes.items()}
        rationale = _required_text(rationale, "rationale")
        current = self._get(object_type, object_id)
        if object_type == "implementation" and provenance != "System":
            raise PermissionError("Implementation 是 System observed fact，只能由 System provenance 修订")
        table = TABLES[object_type]
        id_column = f"{object_type}_id"
        assignments = ", ".join(f"{field} = ?" for field in normalized)
        parameters = [*normalized.values(), _now(), object_id]
        with self.database.transaction():
            self._history(object_type, object_id, "before_revision", current, provenance, actor)
            self.connection.execute(
                f"UPDATE {table} SET {assignments}, updated_at = ? WHERE {id_column} = ?", parameters
            )
            updated = self._get(object_type, object_id)
            self._history(object_type, object_id, f"revision:{rationale}", updated, provenance, actor)
        return self.get(object_type, object_id)

    def get(self, object_type: str, object_id: str) -> SemanticObject:
        self._validate_type(object_type)
        row = self.connection.execute(
            f"SELECT * FROM {TABLES[object_type]} WHERE {object_type}_id = ?" if object_type != "implementation"
            else "SELECT * FROM semantic_implementations WHERE implementation_id = ?", (object_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"未知 Semantic {object_type}: {object_id}")
        return SemanticObject(object_type, object_id, dict(row))

    def get_relation(self, relation_id: int) -> SemanticRelation:
        row = self.connection.execute(
            "SELECT * FROM semantic_relations WHERE relation_id = ?", (relation_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"未知 semantic relation: {relation_id}")
        return SemanticRelation(**{key: row[key] for key in SemanticRelation.__dataclass_fields__})

    def relations_for(self, object_type: str, object_id: str) -> list[SemanticRelation]:
        self._get(object_type, object_id)
        rows = self.connection.execute(
            "SELECT * FROM semantic_relations WHERE (source_type = ? AND source_id = ?) "
            "OR (target_type = ? AND target_id = ?) ORDER BY relation_id",
            (object_type, object_id, object_type, object_id),
        ).fetchall()
        return [SemanticRelation(**{key: row[key] for key in SemanticRelation.__dataclass_fields__}) for row in rows]

    def history(self, object_type: str, object_id: str) -> list[dict[str, Any]]:
        self._get(object_type, object_id)
        rows = self.connection.execute(
            "SELECT * FROM semantic_history WHERE object_type = ? AND object_id = ? ORDER BY version",
            (object_type, object_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def annotations_for(self, object_type: str, object_id: str) -> list[dict[str, Any]]:
        self._get(object_type, object_id)
        rows = self.connection.execute(
            "SELECT * FROM semantic_annotations WHERE object_type = ? AND object_id = ? ORDER BY annotation_id",
            (object_type, object_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def _create_simple(self, object_type: str, name: str, description: str, provenance: str, created_by: str) -> SemanticObject:
        if object_type != "goal":
            raise ValueError("仅 Goal 使用通用创建路径；Module 创建必须绑定 Goal")
        self._validate_provenance(provenance)
        name = _required_text(name, "name")
        description = _required_text(description, "description")
        timestamp = _now()
        with self.database.transaction():
            object_id = self._allocate_id("semantic_goal", "G")
            self.connection.execute(
                "INSERT INTO semantic_goals(goal_id, title, description, provenance, state, created_at, updated_at, created_by) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)",
                (object_id, name, description, provenance, timestamp, timestamp, created_by),
            )
            self._history(object_type, object_id, "created", self._get(object_type, object_id), provenance, created_by)
        return self.get(object_type, object_id)

    def _history(self, object_type: str, object_id: str, event_type: str, snapshot: SemanticObject, provenance: str, actor: str) -> None:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM semantic_history WHERE object_type = ? AND object_id = ?",
            (object_type, object_id),
        ).fetchone()
        self.connection.execute(
            "INSERT INTO semantic_history(object_type, object_id, version, event_type, snapshot, provenance, actor, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (object_type, object_id, row[0], event_type, json.dumps(snapshot.data, ensure_ascii=False, default=str), provenance, actor, _now()),
        )

    def _get(self, object_type: str, object_id: str) -> SemanticObject:
        return self.get(object_type, object_id)

    def _allocate_id(self, counter: str, prefix: str) -> str:
        row = self.connection.execute("SELECT next_value FROM counters WHERE name = ?", (counter,)).fetchone()
        value = row[0] if row else 1
        self.connection.execute(
            "INSERT INTO counters(name, next_value) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET next_value = excluded.next_value",
            (counter, value + 1),
        )
        return f"{prefix}-{value:06d}"

    def _project_exists(self, project_id: str) -> None:
        if self.connection.execute("SELECT 1 FROM projects WHERE project_id = ?", (project_id,)).fetchone() is None:
            raise KeyError(f"未知项目 ID: {project_id}")

    @staticmethod
    def _validate_type(object_type: str) -> None:
        if object_type not in OBJECT_TYPES:
            raise ValueError(f"不支持的 Semantic object type: {object_type}")

    @staticmethod
    def _validate_provenance(provenance: str) -> None:
        if provenance not in PROVENANCE:
            raise ValueError(f"不支持的 provenance: {provenance}")

    @staticmethod
    def _validate_state(state: str) -> None:
        if state not in STATES:
            raise ValueError(f"不支持的 semantic state: {state}")

    @staticmethod
    def _required_annotation_reason(origin_type: str, trigger: str, gap: str, response: str) -> None:
        _required_text(origin_type, "origin_type")
        _required_text(trigger, "trigger")
        _required_text(gap, "gap")
        _required_text(response, "response")
