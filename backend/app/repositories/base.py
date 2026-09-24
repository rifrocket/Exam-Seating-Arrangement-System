from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TEntity = TypeVar("TEntity")


class Repository(ABC, Generic[TEntity]):
    """Minimal CRUD boundary shared by all aggregate repositories.

    Operates purely on domain dataclasses (app.domain.*) — never on
    SQLAlchemy models or HTTP request/response types — so services and
    seating strategies can depend on this interface without depending on
    SQLAlchemy or FastAPI.
    """

    @abstractmethod
    def get(self, entity_id: int) -> TEntity | None: ...

    @abstractmethod
    def list(self, limit: int | None = None, offset: int = 0) -> list[TEntity]: ...

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def add(self, entity: TEntity) -> TEntity: ...
