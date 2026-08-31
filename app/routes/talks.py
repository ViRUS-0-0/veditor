from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_client, verify_event_access
from app.config import settings
from app.db import get_db
from app.storage import StorageBackend, get_storage_backend

router = APIRouter(
    prefix="/talks",
    tags=["talks"],
    dependencies=[Depends(get_client)],
)


@router.post("", response_model=schemas.TalkRead, status_code=status.HTTP_201_CREATED)
def create_or_update_talk(
    payload: schemas.TalkCreate,
    response: Response,
    client: Annotated[models.Client, Depends(get_client)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Creates or updates a Talk row scoped to the caller's authorized event.
    Idempotent on the natural key (event_id, title, start).
    Returns 201 Created on insert, 200 OK on update (preserving existing talk status).
    """
    verify_event_access(payload.event_id, client)

    talk = (
        db.query(models.Talk)
        .filter(
            models.Talk.event_id == payload.event_id,
            models.Talk.title == payload.title,
            models.Talk.start == payload.start,
        )
        .first()
    )

    if talk:
        talk.room = payload.room
        talk.end = payload.end
        db.commit()
        db.refresh(talk)
        response.status_code = status.HTTP_200_OK
        return talk

    talk = models.Talk(
        event_id=payload.event_id,
        title=payload.title,
        room=payload.room,
        start=payload.start,
        end=payload.end,
        status="waiting_for_files",
    )
    db.add(talk)
    try:
        db.commit()
        db.refresh(talk)
        response.status_code = status.HTTP_201_CREATED
        return talk
    except IntegrityError:
        db.rollback()
        talk = (
            db.query(models.Talk)
            .filter(
                models.Talk.event_id == payload.event_id,
                models.Talk.title == payload.title,
                models.Talk.start == payload.start,
            )
            .first()
        )
        if not talk:
            raise
        talk.room = payload.room
        talk.end = payload.end
        db.commit()
        db.refresh(talk)
        response.status_code = status.HTTP_200_OK
        return talk


@router.get("/{talk_id}", response_model=schemas.TalkRead)
def get_talk(
    talk_id: int,
    client: Annotated[models.Client, Depends(get_client)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(get_storage_backend)],
):
    """
    Retrieves talk metadata, current status, and preview URLs.
    Returns 404 if the talk does not exist or is not authorized under caller's event_ids.
    """
    talk = db.query(models.Talk).filter(models.Talk.id == talk_id).first()
    if not talk or talk.event_id not in client.event_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Talk not found"
        )

    candidate_keys = [
        f"{talk.id}/preview/{name}.mp4" for name in settings.preview_presets
    ]
    candidate_keys.append(f"{talk.id}/preview/preview.mp4")

    preview_urls = [storage.url(key) for key in candidate_keys if storage.exists(key)]
    preview_urls = list(dict.fromkeys(preview_urls))

    talk_data = schemas.TalkRead.model_validate(talk)
    talk_data.preview_urls = preview_urls
    return talk_data
