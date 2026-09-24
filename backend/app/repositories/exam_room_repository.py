from abc import abstractmethod

from app.domain import ExamRoom
from app.repositories.base import Repository


class ExamRoomRepository(Repository[ExamRoom]):
    @abstractmethod
    def list_by_exam(self, exam_id: int) -> list[ExamRoom]: ...

    @abstractmethod
    def get_by_exam_and_room(self, exam_id: int, room_id: int) -> ExamRoom | None: ...
