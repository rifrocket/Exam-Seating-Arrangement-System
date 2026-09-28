from app.domain import ExaminationSession
from app.repositories.base import Repository


class ExaminationSessionRepository(Repository[ExaminationSession]):
    """The base get/list/count/add methods are sufficient — a session has
    no natural lookup key besides its id (unlike Room's `code` or
    Course's `code`), so no extra abstract method is needed here."""
