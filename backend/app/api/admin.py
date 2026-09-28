"""Admin-only, destructive database operations.

`POST /admin/database/reset` is protected by `Settings.admin_password`
(`APP_ADMIN_PASSWORD`) — the same administrator secret the frontend's
login page already uses, configured separately on this side only
because the FastAPI backend and the Next.js frontend are two
independent processes with their own environment, never two
independently-managed passwords. See `app.config.Settings.admin_password`
and docs/architecture.md's "Database reset" section for exactly where
this is set.

Every existing endpoint in this API is otherwise unauthenticated (the
frontend's login only gates its own pages, not calls to this backend) —
this endpoint is deliberately the one exception, because it is the one
genuinely destructive operation the API exposes.
"""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.reset import reset_database
from app.db.session import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


class DatabaseResetRequest(BaseModel):
    # Not required at the JSON-schema level (empty string default rather
    # than a required field) so a missing password is rejected with the
    # same 401 a wrong one gets, instead of leaking a different status
    # code (422) for "the field was absent" versus "the field was wrong."
    password: str = ""


class DatabaseResetResponse(BaseModel):
    status: str
    detail: str


def _verify_admin_password(payload: DatabaseResetRequest, settings: Settings) -> None:
    configured = settings.admin_password
    if not configured:
        # Not a 401/403: there is nothing configured to check the
        # password *against*, which is a deployment/configuration
        # problem, not a wrong-credentials one — mirrors the frontend's
        # own login route's identical "not configured" case.
        raise HTTPException(
            status_code=500,
            detail="Database reset is not configured on this server (APP_ADMIN_PASSWORD is not set).",
        )
    # secrets.compare_digest, not `==`, so comparing the password never
    # leaks its length/prefix through response-timing differences.
    if not payload.password or not secrets.compare_digest(payload.password, configured):
        raise HTTPException(status_code=401, detail="Invalid administrator password.")


@router.post("/admin/database/reset", response_model=DatabaseResetResponse)
def reset_application_database(
    payload: DatabaseResetRequest,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DatabaseResetResponse:
    """Deletes every row from every application table (students, courses,
    registrations, exams, rooms, exam_rooms, examination_sessions,
    session_exams, seating_generations, seat_assignments), leaving the
    schema itself intact and immediately usable — see `reset_database`'s
    own docstring for exactly why this is table-row deletion, not a
    schema drop/recreate. One transaction: either every table is cleared
    or (on any failure) none of them are — a partially reset database is
    never left behind."""
    _verify_admin_password(payload, settings)

    try:
        reset_database(session)
        session.commit()
    except Exception as exc:
        session.rollback()
        # The exception itself is logged for diagnosis, but never the
        # request payload — the password is never written to a log.
        logger.exception("Database reset failed; the transaction was rolled back.")
        raise HTTPException(status_code=500, detail="Database reset failed; no data was changed.") from exc

    return DatabaseResetResponse(status="ok", detail="The application database has been reset.")
