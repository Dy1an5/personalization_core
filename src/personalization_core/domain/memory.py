from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import (
    ConfigDict,
    Field,
    model_validator,
)

from .base import StrictFrozenDomainModel
from .enums import (
    MemoryAuthority,
    MemoryConflictType,
    MemoryKind,
    MemoryScope,
    MemoryState,
    MemoryTransitionType,
    Polarity,
)
from .errors import (
    MemoryError as _MemoryError,
)
from .errors import (
    MemoryProtectionError,
    MemoryTransitionError,
    RevisionConflictError,
)
from .identifiers import SubjectRef
from .types import JsonValue, NonEmptyString, UtcDatetime

MemoryError = _MemoryError


class PreferenceTarget(StrictFrozenDomainModel):
    model_config = ConfigDict(strict=True)

    dimension: NonEmptyString
    value_key: NonEmptyString


class MemoryCandidate(StrictFrozenDomainModel):
    """
    尚未被系统正式接受为 active Memory 的候选。
    MemoryExtractor 后续返回的就是这种对象。
    注意：
    Candidate 本身不允许决定 authority=explicit，
    因为模型 / 行为推断不能自行获得“用户明确声明”的权限。
    """

    key: NonEmptyString
    kind: MemoryKind

    content: NonEmptyString

    structured_value: dict[str, JsonValue] | None = None
    target: PreferenceTarget | None = None

    polarity: Polarity = Polarity.UNKNOWN

    scope: MemoryScope = MemoryScope.GLOBAL
    scope_value: NonEmptyString | None = None

    confidence: float = Field(ge=0.0, le=1.0)

    valid_from: UtcDatetime | None = None
    valid_until: UtcDatetime | None = None

    @model_validator(mode="after")
    def validate_candidate(self) -> MemoryCandidate:
        _validate_scope(
            scope=self.scope,
            scope_value=self.scope_value,
        )

        _validate_validity_window(
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        return self


class MemoryRecord(StrictFrozenDomainModel):
    id: UUID
    subject: SubjectRef

    key: NonEmptyString
    kind: MemoryKind

    content: NonEmptyString

    structured_value: dict[str, JsonValue] | None = None
    target: PreferenceTarget | None = None

    authority: MemoryAuthority
    polarity: Polarity

    scope: MemoryScope
    scope_value: NonEmptyString | None = None

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    state: MemoryState

    valid_from: UtcDatetime | None
    valid_until: UtcDatetime | None

    evidence_count: int = Field(
        ge=0,
        default=0,
    )

    revision: int = Field(
        ge=1,
    )

    created_at: UtcDatetime
    updated_at: UtcDatetime

    deleted_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def validate_memory(self) -> MemoryRecord:
        _validate_scope(
            scope=self.scope,
            scope_value=self.scope_value,
        )

        _validate_validity_window(
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")

        if self.state == MemoryState.DELETED:
            if self.deleted_at is None:
                raise ValueError("deleted Memory must have deleted_at")

        elif self.deleted_at is not None:
            raise ValueError("non-deleted Memory cannot have deleted_at")

        return self


class MemoryTransition(StrictFrozenDomainModel):
    """
    描述一次领域状态变化
    """

    memory_id: UUID

    transition: MemoryTransitionType

    actor: NonEmptyString
    reason: NonEmptyString

    previous_state: MemoryState
    new_state: MemoryState

    previous_revision: int = Field(ge=1)
    new_revision: int = Field(ge=2)

    occurred_at: UtcDatetime

    related_memory_id: UUID | None = None

    @model_validator(mode="after")
    def validate_transition(self) -> MemoryTransition:
        if self.new_revision != self.previous_revision + 1:
            raise ValueError("new_revision must equal previous_revision + 1")

        return self


class MemoryTransitionResult(StrictFrozenDomainModel):
    memory: MemoryRecord
    transition: MemoryTransition


class MemoryConflict(StrictFrozenDomainModel):
    """
    Memory 冲突的数据表示。
    这里只表示“冲突已经被别的组件检测出来”。
    """

    id: UUID = Field(default_factory=uuid4)

    subject: SubjectRef

    left_memory_id: UUID
    right_memory_id: UUID

    conflict_type: MemoryConflictType

    reason: NonEmptyString

    detected_at: UtcDatetime

    @model_validator(mode="after")
    def validate_conflict(self) -> MemoryConflict:
        if self.left_memory_id == self.right_memory_id:
            raise ValueError("a Memory cannot conflict with itself")

        return self


def create_explicit_memory(
    *,
    subject: SubjectRef,
    key: str,
    kind: MemoryKind,
    content: str,
    polarity: Polarity = Polarity.UNKNOWN,
    structured_value: dict[str, JsonValue] | None = None,
    target: PreferenceTarget | None = None,
    scope: MemoryScope = MemoryScope.GLOBAL,
    scope_value: str | None = None,
    confidence: float = 1.0,
    valid_from: UtcDatetime | None = None,
    valid_until: UtcDatetime | None = None,
    evidence_count: int = 0,
    now: UtcDatetime,
    memory_id: UUID | None = None,
) -> MemoryRecord:
    """
    用户明确表达的 Memory：
        authority = explicit
        state = active
    对应阶段 3.3。
    """

    return MemoryRecord(
        id=memory_id or uuid4(),
        subject=subject,
        key=key,
        kind=kind,
        content=content,
        structured_value=structured_value,
        target=target,
        authority=MemoryAuthority.EXPLICIT,
        polarity=polarity,
        scope=scope,
        scope_value=scope_value,
        confidence=confidence,
        state=MemoryState.ACTIVE,
        valid_from=valid_from,
        valid_until=valid_until,
        evidence_count=evidence_count,
        revision=1,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def create_inferred_memory(
    *,
    subject: SubjectRef,
    candidate: MemoryCandidate,
    evidence_count: int = 0,
    now: UtcDatetime,
    memory_id: UUID | None = None,
) -> MemoryRecord:
    """
    行为 / 模型推断生成的 Memory：
        authority = inferred
        state = candidate
    不允许直接进入 active。
    对应阶段 3.4。
    """

    return MemoryRecord(
        id=memory_id or uuid4(),
        subject=subject,
        key=candidate.key,
        kind=candidate.kind,
        content=candidate.content,
        structured_value=candidate.structured_value,
        target=candidate.target,
        authority=MemoryAuthority.INFERRED,
        polarity=candidate.polarity,
        scope=candidate.scope,
        scope_value=candidate.scope_value,
        confidence=candidate.confidence,
        state=MemoryState.CANDIDATE,
        valid_from=candidate.valid_from,
        valid_until=candidate.valid_until,
        evidence_count=evidence_count,
        revision=1,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def assert_revision(
    memory: MemoryRecord,
    expected_revision: int,
) -> None:
    """
    乐观锁。

    application 层以后执行：

        load memory
        -> assert_revision(...)
        -> domain transition
        -> repository update WHERE revision = expected_revision

    数据库层还会再次保护并发竞争。
    """

    if expected_revision != memory.revision:
        raise RevisionConflictError(
            expected_revision=expected_revision,
            actual_revision=memory.revision,
        )


def confirm_memory(
    memory: MemoryRecord,
    *,
    expected_revision: int,
    actor: NonEmptyString,
    reason: NonEmptyString,
    now: UtcDatetime,
) -> MemoryTransitionResult:
    """
    模型推断 Memory + 用户 confirms -> active confirmed
    """

    assert_revision(memory, expected_revision)

    if memory.state != MemoryState.CANDIDATE:
        raise MemoryTransitionError("only candidate Memory can be confirmed")

    if memory.authority != MemoryAuthority.INFERRED:
        raise MemoryTransitionError("only inferred Memory can be confirmed")

    updated = memory.model_copy(
        update={
            "authority": MemoryAuthority.CONFIRMED,
            "state": MemoryState.ACTIVE,
            "revision": memory.revision + 1,
            "updated_at": now,
        },
    )

    transition = _build_transition(
        before=memory,
        after=updated,
        transition=MemoryTransitionType.CONFIRM,
        actor=actor,
        reason=reason,
        occurred_at=now,
    )

    return MemoryTransitionResult(
        memory=updated,
        transition=transition,
    )


def supersede_memory(
    memory: MemoryRecord,
    *,
    replacement: MemoryRecord,
    expected_revision: int,
    actor: str,
    reason: str,
    now: UtcDatetime,
) -> MemoryTransitionResult:
    """
    active Memory + replaced by newwe Memory -> superseded
    不自动判断两条 Memory 是否“语义冲突”,application / resolver 必须先明确决定：
    replacement 是否真的应该替代 memory。
    """

    assert_revision(memory, expected_revision)

    if memory.state != MemoryState.ACTIVE:
        raise MemoryTransitionError("only active Memory can be superseded")

    if replacement.state != MemoryState.ACTIVE:
        raise MemoryTransitionError("replacement Memory must already be active")

    if memory.id == replacement.id:
        raise MemoryTransitionError("Memory cannot supersede itself")

    if memory.subject != replacement.subject:
        raise MemoryTransitionError(
            "replacement Memory must belong to the same subject"
        )

    if not same_memory_slot(memory, replacement):
        raise MemoryTransitionError(
            "replacement Memory must use the same key and scope"
        )

    """
    explicit > confirmed > inferred
    inferred / comfirmed 不得静默覆盖 explicit
    """

    if (
        memory.authority == MemoryAuthority.EXPLICIT
        and replacement.authority != MemoryAuthority.EXPLICIT
    ):
        raise MemoryProtectionError(
            "non-explicit Memory cannot supersede explicit Memory"
        )

    if replacement.authority == MemoryAuthority.INFERRED:
        raise MemoryProtectionError(
            "inferred Memory cannot directly supersede active Memory"
        )

    updated = memory.model_copy(
        update={
            "state": MemoryState.SUPERSEDED,
            "revision": memory.revision + 1,
            "updated_at": now,
        },
    )

    transition = _build_transition(
        before=memory,
        after=updated,
        transition=MemoryTransitionType.SUPERSEDE,
        actor=actor,
        reason=reason,
        occurred_at=now,
        related_memory_id=replacement.id,
    )

    return MemoryTransitionResult(
        memory=updated,
        transition=transition,
    )


def expire_memory(
    memory: MemoryRecord,
    *,
    expected_revision: int,
    actor: str,
    reason: str,
    now: UtcDatetime,
) -> MemoryTransitionResult:
    """
    candidate / active + validity ends -> expired
    """

    assert_revision(memory, expected_revision)

    allowed_states = {
        MemoryState.CANDIDATE,
        MemoryState.ACTIVE,
    }

    if memory.state not in allowed_states:
        raise MemoryTransitionError(
            f"cannot expire Memory from state {memory.state.value}"
        )

    updated = memory.model_copy(
        update={
            "state": MemoryState.EXPIRED,
            "revision": memory.revision + 1,
            "updated_at": now,
        },
    )

    transition = _build_transition(
        before=memory,
        after=updated,
        transition=MemoryTransitionType.EXPIRE,
        actor=actor,
        reason=reason,
        occurred_at=now,
    )

    return MemoryTransitionResult(
        memory=updated,
        transition=transition,
    )


def soft_delete_memory(
    memory: MemoryRecord,
    *,
    expected_revision: int,
    actor: str,
    reason: str,
    now: UtcDatetime,
) -> MemoryTransitionResult:
    """
    任意未删除 Memory + deleted -> 数据仍然存在,只是不再参与正常读取
    """

    assert_revision(memory, expected_revision)

    if memory.state == MemoryState.DELETED:
        raise MemoryTransitionError("Memory is already deleted")

    updated = memory.model_copy(
        update={
            "state": MemoryState.DELETED,
            "revision": memory.revision + 1,
            "updated_at": now,
            "deleted_at": now,
        },
    )

    transition = _build_transition(
        before=memory,
        after=updated,
        transition=MemoryTransitionType.DELETE,
        actor=actor,
        reason=reason,
        occurred_at=now,
    )

    return MemoryTransitionResult(
        memory=updated,
        transition=transition,
    )


def restore_memory(
    memory: MemoryRecord,
    *,
    restore_to: MemoryState,
    expected_revision: int,
    actor: str,
    reason: str,
    now: UtcDatetime,
) -> MemoryTransitionResult:
    """
    deleted
        ↓
    candidate / active / superseded / expired

    为什么必须显式传 restore_to？

    因为 plan 中 MemoryRecord 没有 deleted_from_state 字段。

    真正进入阶段 8 后，
    application service 可以从 memory_revisions 中读取删除前状态，
    再把它传给这里。
    """

    assert_revision(memory, expected_revision)

    if memory.state != MemoryState.DELETED:
        raise MemoryTransitionError("only deleted Memory can be restored")

    allowed_targets = {
        MemoryState.CANDIDATE,
        MemoryState.ACTIVE,
        MemoryState.SUPERSEDED,
        MemoryState.EXPIRED,
    }

    if restore_to not in allowed_targets:
        raise MemoryTransitionError(
            f"cannot restore Memory to state {restore_to.value}"
        )

    # inferred Memory 不能通过 restore 绕过 confirm，
    # 直接进入 active。
    if (
        restore_to == MemoryState.ACTIVE
        and memory.authority == MemoryAuthority.INFERRED
    ):
        raise MemoryProtectionError(
            "inferred Memory cannot be restored directly to active"
        )

    updated = memory.model_copy(
        update={
            "state": restore_to,
            "revision": memory.revision + 1,
            "updated_at": now,
            "deleted_at": None,
        },
    )

    transition = _build_transition(
        before=memory,
        after=updated,
        transition=MemoryTransitionType.RESTORE,
        actor=actor,
        reason=reason,
        occurred_at=now,
    )

    return MemoryTransitionResult(
        memory=updated,
        transition=transition,
    )


def is_within_validity_window(
    memory: MemoryRecord,
    *,
    at: UtcDatetime,
) -> bool:
    """
    只判断时间窗口。

    valid_from inclusive
    valid_until exclusive

    即 valid_from <= at < valid_until
    """
    if memory.valid_from is not None and at < memory.valid_from:
        return False

    return memory.valid_until is None or at < memory.valid_until


def is_memory_effective(
    memory: MemoryRecord,
    *,
    at: UtcDatetime,
) -> bool:
    """
    Memory 当前是否真正生效。

    必须同时满足：

    1. state == active
    2. 没有 deleted
    3. 当前时间位于有效时间窗口
    """

    if memory.state != MemoryState.ACTIVE:
        return False

    if memory.deleted_at is not None:
        return False

    return is_within_validity_window(
        memory,
        at=at,
    )


def same_memory_slot(
    left: MemoryRecord,
    right: MemoryRecord,
) -> bool:
    """
    对应数据库未来的唯一槽位：

        subject
        + key
        + scope
        + scope_value

    同一槽位最多一个 active Memory。
    """

    return (
        left.subject == right.subject
        and left.key == right.key
        and left.scope == right.scope
        and left.scope_value == right.scope_value
    )


def _validate_scope(*, scope: MemoryScope, scope_value: str | None) -> None:
    if scope == MemoryScope.GLOBAL:
        if scope_value is not None:
            raise ValueError("global scope requires scope_value=None")

        return

    if scope_value is None:
        raise ValueError(f"{scope.value} scope requires scope_value")


def _validate_validity_window(
    *,
    valid_from: UtcDatetime | None,
    valid_until: UtcDatetime | None,
) -> None:
    if valid_from is not None and valid_until is not None and valid_until <= valid_from:
        raise ValueError("valid_until must be later than valid_from")


def _build_transition(
    *,
    before: MemoryRecord,
    after: MemoryRecord,
    transition: MemoryTransitionType,
    actor: NonEmptyString,
    reason: NonEmptyString,
    occurred_at: UtcDatetime,
    related_memory_id: UUID | None = None,
) -> MemoryTransition:
    return MemoryTransition(
        memory_id=before.id,
        transition=transition,
        actor=actor,
        reason=reason,
        previous_state=before.state,
        new_state=after.state,
        previous_revision=before.revision,
        new_revision=after.revision,
        occurred_at=occurred_at,
        related_memory_id=related_memory_id,
    )
