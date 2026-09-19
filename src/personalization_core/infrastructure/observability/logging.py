from __future__ import annotations

from typing import Any

from personalization_core.domain.identifiers import SubjectRef
from personalization_core.ports.audit_sink import sanitize_log_fields, subject_digest


def redact_fields(value: Any) -> Any:
    """Return a recursively sanitized value suitable for standard logging."""
    return sanitize_log_fields(value)


def safe_subject_metadata(subject: SubjectRef) -> dict[str, str]:
    """Expose only a stable digest when adding a subject to log metadata."""
    return {"scope_digest": subject_digest(subject)}
