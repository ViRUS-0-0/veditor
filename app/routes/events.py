import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import CurrentUser, check_event_access, require_role
from app.db import get_db
from app.storage import StorageBackend, get_storage_backend

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/events",
    tags=["events"],
)


@router.post("", response_model=schemas.EventRead, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: schemas.EventCreate,
    user: Annotated[CurrentUser, Depends(require_role("organizer"))],
    db: Annotated[Session, Depends(get_db)],
):
    created_by = user.user_id if not user.is_machine else None
    event = models.Event(
        name=payload.name,
        retention_overrides=payload.retention_overrides,
        created_by_user_id=created_by,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("", response_model=list[schemas.EventRead], status_code=status.HTTP_200_OK)
def list_events(
    user: Annotated[CurrentUser, Depends(require_role("organizer"))],
    db: Annotated[Session, Depends(get_db)],
):
    if user.role == "admin":
        return db.query(models.Event).all()
    else:
        return (
            db.query(models.Event)
            .filter(models.Event.created_by_user_id == user.user_id)
            .all()
        )


@router.patch("/{event_id}", response_model=schemas.EventRead)
def update_event(
    event_id: int,
    payload: schemas.EventUpdate,
    user: Annotated[CurrentUser, Depends(require_role("organizer"))],
    db: Annotated[Session, Depends(get_db)],
):
    event = check_event_access(event_id, user, db)

    if payload.name is not None:
        clean_name = payload.name.strip()
        if not clean_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Event name cannot be empty",
            )
        event.name = clean_name

    if payload.retention_overrides is not None:
        event.retention_overrides = payload.retention_overrides

    db.commit()
    db.refresh(event)
    return event


@router.delete("/{event_id}")
def delete_event(
    event_id: int,
    user: Annotated[CurrentUser, Depends(require_role("organizer"))],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(get_storage_backend)],
):
    event = check_event_access(event_id, user, db)

    for talk in event.talks:
        try:
            storage.delete(str(talk.id))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed deleting storage for talk %s: %s", talk.id, exc)

    db.delete(event)
    db.commit()
    return {"status": "ok", "deleted_id": event_id}
