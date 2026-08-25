from pathlib import Path

import av

from app.config import settings
from app.schemas import RecordingIngestRequest
from app.storage import StorageBackend


class IngestPathRejectedError(ValueError):
    pass


def validate_media_file(path: Path) -> None:
    try:
        with av.open(str(path)) as container:
            has_video = any(s.type == "video" for s in container.streams)
    except av.FFmpegError as exc:
        raise IngestPathRejectedError(f"Invalid media file: {exc}") from exc

    if not has_video:
        raise IngestPathRejectedError(
            "File is not a valid video (no video stream found)"
        )


def stage_recording(
    talk_id: int, payload: RecordingIngestRequest, backend: StorageBackend
) -> str:
    path_str = payload.source_path or payload.relative_key
    if "\0" in path_str:
        raise IngestPathRejectedError("Invalid path")

    target_path = Path(path_str)
    resolved_path = None

    # Resolve against roots
    roots = [Path(r).resolve() for r in settings.ingest_roots]

    matched_root = None
    if payload.source_path:
        if not target_path.is_absolute():
            raise IngestPathRejectedError("source_path must be absolute")
        try:
            candidate = target_path.resolve(strict=True)
            for root in roots:
                if candidate.is_relative_to(root):
                    resolved_path = candidate
                    matched_root = root
                    break
        except OSError, RuntimeError:
            pass
    else:
        if target_path.is_absolute():
            raise IngestPathRejectedError("relative_key must be relative")
        for root in roots:
            try:
                candidate = (root / target_path).resolve(strict=True)
                if candidate.is_relative_to(root):
                    resolved_path = candidate
                    matched_root = root
                    break
            except OSError, RuntimeError:
                pass

    if not resolved_path or not resolved_path.is_file() or not matched_root:
        raise IngestPathRejectedError("Invalid or missing ingest path")

    validate_media_file(resolved_path)

    rel_path = resolved_path.relative_to(matched_root)
    key = f"{talk_id}/raw/{rel_path}"
    backend.put(key=key, source=resolved_path)
    return key
