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
