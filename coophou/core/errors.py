"""Typed, serializable failures for the portable core."""

from dataclasses import dataclass
from enum import Enum


MODEL_VERSION = 1


class ErrorCode(str, Enum):
    SCHEMA_UNSUPPORTED_VERSION = "SCHEMA_UNSUPPORTED_VERSION"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    OPERATION_UNKNOWN_TYPE = "OPERATION_UNKNOWN_TYPE"
    OPERATION_INVALID_PAYLOAD = "OPERATION_INVALID_PAYLOAD"
    TRANSACTION_INVALID = "TRANSACTION_INVALID"
    CAPABILITY_INCOMPATIBLE = "CAPABILITY_INCOMPATIBLE"
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    ENTITY_DELETED = "ENTITY_DELETED"
    ENTITY_ALREADY_EXISTS = "ENTITY_ALREADY_EXISTS"
    NAME_CONFLICT = "NAME_CONFLICT"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    DUPLICATE_CONFLICT = "DUPLICATE_CONFLICT"
    HISTORY_GAP = "HISTORY_GAP"
    HISTORY_UNAVAILABLE = "HISTORY_UNAVAILABLE"
    QUEUE_OVERFLOW = "QUEUE_OVERFLOW"
    APPLICATION_FAILED = "APPLICATION_FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_MISMATCH = "SESSION_MISMATCH"
    SEQUENCE_CONTRADICTION = "SEQUENCE_CONTRADICTION"
    STALE_CONNECTION_GENERATION = "STALE_CONNECTION_GENERATION"


@dataclass(frozen=True)
class ErrorDetail:
    version: int
    code: ErrorCode
    message: str
    context: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        if self.version != MODEL_VERSION:
            raise ValueError("unsupported error-detail version")
        if not isinstance(self.code, ErrorCode):
            raise TypeError("code must be ErrorCode")
        if not isinstance(self.message, str) or not self.message or len(self.message) > 1024:
            raise ValueError("message must be a non-empty bounded string")
        if len(self.context) > 32:
            raise ValueError("error context is too large")
        for pair in self.context:
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not all(isinstance(item, str) for item in pair)
            ):
                raise TypeError("error context must contain string pairs")

    def to_dict(self):
        return {
            "version": self.version,
            "code": self.code.value,
            "message": self.message,
            "context": [[key, value] for key, value in self.context],
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise DomainError(ErrorCode.SCHEMA_INVALID, "error detail must be an object")
        if set(data) != {"version", "code", "message", "context"}:
            raise DomainError(ErrorCode.SCHEMA_INVALID, "invalid error-detail fields")
        try:
            code = ErrorCode(data["code"])
        except (TypeError, ValueError):
            raise DomainError(ErrorCode.SCHEMA_INVALID, "invalid error code") from None
        return cls(
            version=data["version"],
            code=code,
            message=data["message"],
            context=tuple(tuple(pair) for pair in data["context"]),
        )


class DomainError(Exception):
    def __init__(self, code, message, **context):
        self.detail = ErrorDetail(
            version=MODEL_VERSION,
            code=ErrorCode(code),
            message=message,
            context=tuple(sorted((str(key), str(value)) for key, value in context.items())),
        )
        super().__init__(f"{self.detail.code.value}: {self.detail.message}")


def fail(code, message, **context):
    raise DomainError(code, message, **context)
