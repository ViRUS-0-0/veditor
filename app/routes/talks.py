from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_client, verify_event_access
from app.config import settings
from app.db import get_db
from app.ingest import IngestPathRejectedError, stage_recording
from app.queue import light_queue
from app.states import advance
from app.storage import StorageBackend, get_storage_backend
from app.tasks import STAGE_CONFIG, job_cut, job_detect

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


@router.post(
    "/{talk_id}/recordings",
    response_model=schemas.TalkRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_recording(
    talk_id: int,
    payload: schemas.RecordingIngestRequest,
    client: Annotated[models.Client, Depends(get_client)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(get_storage_backend)],
):
    """
    Ingests a recording file for the given talk and queues the detect job.
    Returns 404 if talk not found or not in caller's event_ids.
    Returns 409 if talk status is not 'waiting_for_files'.
    Returns 400 if ingest path validation fails.
    """
    talk = db.query(models.Talk).filter(models.Talk.id == talk_id).first()
    if not talk or talk.event_id not in client.event_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Talk not found"
        )

    if talk.status != "waiting_for_files":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot ingest recording for talk in status '{talk.status}'",
        )

    try:
        raw_key = stage_recording(talk.id, payload, storage)
    except IngestPathRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    light_queue.enqueue(
        job_detect,
        talk.id,
        raw_key,
        job_timeout=STAGE_CONFIG["detect"]["job_timeout"],
    )

    return talk


@router.post(
    "/{talk_id}/approve",
    response_model=schemas.TalkRead,
    status_code=status.HTTP_200_OK,
)
def approve_talk(
    talk_id: int,
    client: Annotated[models.Client, Depends(get_client)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(get_storage_backend)],
    payload: schemas.TalkApproveRequest | None = None,
):
    """
    Approves a talk in pending_approval state, advances state to cutting, and queues the cut job.
    Returns 404 if talk not found or not in caller's event_ids.
    Returns 409 if talk status is not 'pending_approval'.
    Returns 400 if no raw recording file is found.
    """
    talk = db.query(models.Talk).filter(models.Talk.id == talk_id).first()
    if not talk or talk.event_id not in client.event_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Talk not found"
        )

    if talk.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot approve talk in status '{talk.status}'",
        )

    raw_key = payload.raw_key if payload and payload.raw_key else None
    if raw_key and not raw_key.startswith(f"{talk.id}/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid raw_key: must belong to talk {talk.id}",
        )

    if not raw_key:
        raw_keys = storage.list_keys(f"{talk.id}/raw/")
        if raw_keys:
            raw_key = raw_keys[0]

    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No raw recording found for talk",
        )

    advance(talk, "cutting")
    db.commit()
    db.refresh(talk)

    light_queue.enqueue(
        job_cut,
        talk.id,
        raw_key,
        job_timeout=STAGE_CONFIG["cut"]["job_timeout"],
    )

    return talk
