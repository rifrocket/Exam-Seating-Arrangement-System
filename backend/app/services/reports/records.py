class GenerationNotFoundError(Exception):
    def __init__(self, generation_id: int) -> None:
        super().__init__(f"Seating generation {generation_id} not found.")
        self.generation_id = generation_id


class EmptyGenerationError(Exception):
    """Raised when a generation exists but has zero SeatAssignment rows —
    e.g. status FAILED, or an exam with no rooms scheduled. A report is
    not produced for this case; the API surfaces it as a clear error
    rather than an empty-but-technically-valid PDF."""

    def __init__(self, generation_id: int) -> None:
        super().__init__(f"Seating generation {generation_id} has no assignments to report.")
        self.generation_id = generation_id
