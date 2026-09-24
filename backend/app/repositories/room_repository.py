from abc import abstractmethod

from app.domain import Room
from app.repositories.base import Repository


class RoomRepository(Repository[Room]):
    @abstractmethod
    def get_by_code(self, code: str) -> Room | None: ...
