from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.pipeline.detect import DETECT_DURATION_TOLERANCE_SECONDS, detect
from tests.conftest import (
    generate_clip,
    generate_corrupt_clip,
    generate_mismatched_duration_clip,
)


def test_detect_passes_clip_within_scheduled_window(tmp_path: Path):
    scheduled_start = datetime(2026, 3, 20, 9, 0, tzinfo=UTC)
    scheduled_end = scheduled_start + timedelta(seconds=1)
    clip = generate_clip(1, output_dir=tmp_path)

    result = detect(clip, scheduled_start, scheduled_end)

    assert result.passed
    assert result.actual_duration_seconds > 0
    assert result.has_video
    assert result.has_audio
    assert result.reason is None


def test_detect_fails_clip_with_mismatched_duration(tmp_path: Path):
    scheduled_start = datetime(2026, 3, 20, 9, 0, tzinfo=UTC)
    scheduled_duration = DETECT_DURATION_TOLERANCE_SECONDS + 2
    scheduled_end = scheduled_start + timedelta(seconds=scheduled_duration)
    clip = generate_mismatched_duration_clip(
        scheduled_start,
        scheduled_end,
        -(DETECT_DURATION_TOLERANCE_SECONDS + 1),
        output_dir=tmp_path,
    )

    result = detect(clip, scheduled_start, scheduled_end)

    assert not result.passed
    assert result.actual_duration_seconds > 0
    assert result.has_video
    assert "duration" in result.reason


def test_detect_fails_audio_only_clip_as_missing_video(tmp_path: Path):
    scheduled_start = datetime(2026, 3, 20, 9, 0, tzinfo=UTC)
    scheduled_end = scheduled_start + timedelta(seconds=1)
    clip = generate_clip(1, has_video=False, output_dir=tmp_path)

    result = detect(clip, scheduled_start, scheduled_end)

    assert not result.passed
    assert result.actual_duration_seconds > 0
    assert not result.has_video
    assert result.has_audio
    assert "video" in result.reason


def test_detect_fails_corrupt_clip_without_raising(tmp_path: Path):
    scheduled_start = datetime(2026, 3, 20, 9, 0, tzinfo=UTC)
    scheduled_end = scheduled_start + timedelta(seconds=1)
    clip = generate_corrupt_clip(output_dir=tmp_path)

    result = detect(clip, scheduled_start, scheduled_end)

    assert not result.passed
    assert result.actual_duration_seconds == 0.0
    assert not result.has_video
    assert not result.has_audio
    assert "unreadable" in result.reason


def test_detect_fails_nonexistent_file_without_raising(tmp_path: Path):
    scheduled_start = datetime(2026, 3, 20, 9, 0, tzinfo=UTC)
    scheduled_end = scheduled_start + timedelta(seconds=1)
    missing_path = tmp_path / "missing.mp4"

    result = detect(missing_path, scheduled_start, scheduled_end)

    assert not result.passed
    assert result.actual_duration_seconds == 0.0
    assert not result.has_video
    assert not result.has_audio
    assert "file not found" == result.reason


def test_detect_fails_empty_file(tmp_path: Path):
    scheduled_start = datetime(2026, 3, 20, 9, 0, tzinfo=UTC)
    scheduled_end = scheduled_start + timedelta(seconds=1)
    empty_path = tmp_path / "empty.mp4"
    empty_path.touch()

    result = detect(empty_path, scheduled_start, scheduled_end)

    assert not result.passed
    assert result.actual_duration_seconds == 0.0
    assert not result.has_video
    assert not result.has_audio
    assert "file is empty" in result.reason
