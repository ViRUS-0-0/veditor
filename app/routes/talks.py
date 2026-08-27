from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_client, verify_event_access
from app.db import get_db
from app.storage import StorageBackend, get_storage

router = APIRouter(
    prefix="/talks",
    tags=["talks"],
    dependencies=[Depends(get_client)],
)


@router.post(
    "",
    response_model=schemas.TalkRead,
    status_code=status.HTTP_201_CREATED,
)
def create_or_upsert_talk(
    payload: schemas.TalkCreate,
    client: Annotated[models.Client, Depends(get_client)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
):
    """
    Creates or upserts a Talk scoped to the calling client's event.
    Idempotent on natural key (event_id, title, start).
    """
    verify_event_access(payload.event_id, client)

    existing_talk = (
        db.query(models.Talk)
        .filter(
            models.Talk.event_id == payload.event_id,
            models.Talk.title == payload.title,
            models.Talk.start == payload.start,
        )
        .first()
    )
    if existing_talk:
        existing_talk.room = payload.room
        existing_talk.end = payload.end
        db.commit()
        db.refresh(existing_talk)
        response.status_code = status.HTTP_200_OK
        return existing_talk

    talk = models.Talk(
        event_id=payload.event_id,
        title=payload.title,
        room=payload.room,
        start=payload.start,
        end=payload.end,
        status="waiting_for_files",
    )
    db.add(talk)
    db.commit()
    db.refresh(talk)
    return talk


@router.get(
    "/{talk_id}",
    response_model=schemas.TalkDetailRead,
)
def get_talk(
    talk_id: int,
    client: Annotated[models.Client, Depends(get_client)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
):
    """
    Retrieves talk details and preview URLs.
    Returns 404 if talk is not found or not in caller's event_ids.
    """
    allowed_events = client.event_ids or []
    talk = (
        db.query(models.Talk)
        .filter(
            models.Talk.id == talk_id,
            models.Talk.event_id.in_(allowed_events),
        )
        .first()
    )
    if not talk or talk.event_id not in allowed_events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Talk not found",
        )

    preview_urls: list[str] = []
    preview_key = f"{talk.id}/preview/preview.mp4"
    if storage.exists(preview_key):
        preview_urls.append(storage.url(preview_key))

    return schemas.TalkDetailRead(
        id=talk.id,
        event_id=talk.event_id,
        title=talk.title,
        room=talk.room,
        start=talk.start,
        end=talk.end,
        status=talk.status,
        preview_urls=preview_urls,
    )
