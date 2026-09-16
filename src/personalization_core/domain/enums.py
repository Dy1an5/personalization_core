from enum import StrEnum


class Polarity(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class EvidenceSourceType(StrEnum):
    CONVERSATION = "conversation"
    EVENT = "event"
    USER = "user"
    SYSTEM = "system"
    IMPORT = "import"


class IdempotencyDecision(StrEnum):
    DIFFERENT_SCOPE = "different_scope"
    REPLAY = "replay"
    CONFLICT = "conflict"


class MemoryKind(StrEnum):
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    GOAL = "goal"
    FACT = "fact"
    INSTRUCTION = "instruction"


class MemoryAuthority(StrEnum):
    EXPLICIT = "explicit"
    CONFIRMED = "confirmed"
    INFERRED = "inferred"


class MemoryScope(StrEnum):
    GLOBAL = "global"
    USE_CASE = "use_case"
    TOPIC = "topic"
    ENTITY = "entity"


class MemoryState(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    DELETED = "deleted"


class MemoryTransitionType(StrEnum):
    CONFIRM = "confirm"
    SUPERSEDE = "supersede"
    EXPIRE = "expire"
    DELETE = "delete"
    RESTORE = "restore"


class MemoryConflictType(StrEnum):
    SLOT = "slot"
    SEMANTIC = "semantic"
    TEMPORAL = "temporal"
