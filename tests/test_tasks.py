from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models import Job, Talk
from app.pipeline.detect import DetectResult
from app.tasks import (
    STAGE_CONFIG,
    job_cut,
    job_detect,
    job_loudness,
    job_preview,
    job_publish,
    job_transcode,
)


class MockDBContext:
    def __init__(self, talk: Talk, jobs_dict: dict[int, Job]):
        self.talk = talk
        self.jobs_dict = jobs_dict
        self.open_sessions = 0
        self.next_job_id = 100

    def __call__(self):
        ctx = self

        class Session:
            def __enter__(self_inner):
                ctx.open_sessions += 1
                session_mock = MagicMock()

                def get_mock(model, obj_id):
                    if model == Talk and obj_id == ctx.talk.id:
                        return ctx.talk
                    if model == Job and obj_id in ctx.jobs_dict:
                        return ctx.jobs_dict[obj_id]
                    return None

                def add_mock(obj):
                    if isinstance(obj, Job):
                        if obj.id is None:
                            obj.id = ctx.next_job_id
                            ctx.next_job_id += 1
                        ctx.jobs_dict[obj.id] = obj

                session_mock.get.side_effect = get_mock
                session_mock.add.side_effect = add_mock
                session_mock.commit = MagicMock()
                session_mock.refresh = MagicMock()
                return session_mock

            def __exit__(self_inner, exc_type, exc_val, exc_tb):
                ctx.open_sessions -= 1

        return Session()


@pytest.fixture
def dummy_talk():
    return Talk(
        id=1,
        event_id=1,
        title="Test Talk",
        room="Room A",
        start=datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
        end=datetime(2026, 8, 29, 10, 30, tzinfo=UTC),
        status="waiting_for_files",
    )


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.get.return_value = Path("/tmp/fake_media.mp4")
    storage.put.return_value = None
    return storage


def test_no_db_session_held_during_detect(dummy_talk, mock_storage):
    jobs = {}
    db_ctx = MockDBContext(dummy_talk, jobs)

    def fake_detect(raw_path, scheduled_start, scheduled_end):
        assert db_ctx.open_sessions == 0, "DB session was open during detect!"
        return DetectResult(
            passed=True,
            actual_duration_seconds=1800.0,
            has_video=True,
            has_audio=True,
            reason=None,
        )

    with (
        patch("app.tasks.SessionLocal", side_effect=db_ctx),
        patch("app.tasks.get_storage", return_value=mock_storage),
        patch("app.tasks.detect", side_effect=fake_detect),
        patch("app.tasks.light_queue.enqueue") as mock_enqueue,
    ):
        job_detect(1, "1/raw/raw.mp4")

    assert dummy_talk.status == "pending_approval"
    assert len(jobs) == 1
    job = next(iter(jobs.values()))
    assert job.status == "done"
    assert job.kind == "detect"
    mock_enqueue.assert_not_called()  # Halts at pending_approval


def test_detect_failure_advances_to_broken(dummy_talk, mock_storage):
    jobs = {}
    db_ctx = MockDBContext(dummy_talk, jobs)

    with (
        patch("app.tasks.SessionLocal", side_effect=db_ctx),
        patch("app.tasks.get_storage", return_value=mock_storage),
        patch(
            "app.tasks.detect",
            return_value=DetectResult(
                passed=False,
                actual_duration_seconds=10.0,
                has_video=False,
                has_audio=False,
                reason="duration too short",
            ),
        ),
        pytest.raises(ValueError, match="Detection failed"),
    ):
        job_detect(1, "1/raw/raw.mp4")

    assert dummy_talk.status == "broken"
    assert len(jobs) == 1
    job = next(iter(jobs.values()))
    assert job.status == "failed"
    assert job.log_path == f"1/logs/job_{job.id}.log"
    mock_storage.put.assert_called_once()


def test_failure_on_already_broken_talk_does_not_crash(dummy_talk, mock_storage):
    dummy_talk.status = "broken"
    jobs = {}
    db_ctx = MockDBContext(dummy_talk, jobs)

    with (
        patch("app.tasks.SessionLocal", side_effect=db_ctx),
        patch("app.tasks.get_storage", return_value=mock_storage),
        patch("app.tasks.detect", side_effect=RuntimeError("Unexpected error")),
        pytest.raises(RuntimeError, match="Unexpected error"),
    ):
        job_detect(1, "1/raw/raw.mp4")

    assert dummy_talk.status == "broken"
    assert len(jobs) == 1
    job = next(iter(jobs.values()))
    assert job.status == "failed"


def test_no_db_session_held_during_cut_and_enqueues_preview(dummy_talk, mock_storage):
    dummy_talk.status = "cutting"
    jobs = {}
    db_ctx = MockDBContext(dummy_talk, jobs)

    def fake_cut(input_path, output_path, start_s, end_s):
        assert db_ctx.open_sessions == 0, "DB session was open during cut!"

    with (
        patch("app.tasks.SessionLocal", side_effect=db_ctx),
        patch("app.tasks.get_storage", return_value=mock_storage),
        patch("app.tasks.cut", side_effect=fake_cut),
        patch("app.tasks.light_queue.enqueue") as mock_enqueue,
    ):
        job_cut(1, "1/raw/raw.mp4", "1/cut/cut.mp4")

    assert dummy_talk.status == "generating_previews"
    job = next(iter(jobs.values()))
    assert job.status == "done"
    mock_enqueue.assert_called_once_with(
        job_preview,
        1,
        "1/cut/cut.mp4",
        "1/preview/preview.mp4",
        job_timeout=STAGE_CONFIG["preview"]["job_timeout"],
    )


def test_cut_exception_leads_to_broken(dummy_talk, mock_storage):
    dummy_talk.status = "cutting"
    jobs = {}
    db_ctx = MockDBContext(dummy_talk, jobs)

    with (
        patch("app.tasks.SessionLocal", side_effect=db_ctx),
        patch("app.tasks.get_storage", return_value=mock_storage),
        patch("app.tasks.cut", side_effect=RuntimeError("FFmpeg cut failed")),
        patch("app.tasks.light_queue.enqueue") as mock_enqueue,
        pytest.raises(RuntimeError, match="FFmpeg cut failed"),
    ):
        job_cut(1, "1/raw/raw.mp4")

    assert dummy_talk.status == "broken"
    job = next(iter(jobs.values()))
    assert job.status == "failed"
    assert job.log_path is not None
    mock_enqueue.assert_not_called()


def test_no_db_session_held_during_preview_and_halts(dummy_talk, mock_storage):
    dummy_talk.status = "generating_previews"
    jobs = {}
    db_ctx = MockDBContext(dummy_talk, jobs)

    def fake_preview(input_path, output_path, preset):
        assert db_ctx.open_sessions == 0, "DB session was open during preview!"

    with (
        patch("app.tasks.SessionLocal", side_effect=db_ctx),
        patch("app.tasks.get_storage", return_value=mock_storage),
        patch("app.tasks.generate_preview", side_effect=fake_preview),
        patch("app.tasks.light_queue.enqueue") as mock_enqueue,
    ):
        job_preview(1, "1/cut/cut.mp4", "1/preview/preview.mp4")

    assert dummy_talk.status == "preview"
    job = next(iter(jobs.values()))
    assert job.status == "done"
    mock_enqueue.assert_not_called()  # Halts at preview for human review


def test_loudness_enqueues_transcode_on_heavy(dummy_talk, mock_storage):
    dummy_talk.status = "transcoding"
    jobs = {}
    db_ctx = MockDBContext(dummy_talk, jobs)

    def fake_loudness(input_path, output_path):
        assert db_ctx.open_sessions == 0, "DB session was open during loudness!"

    with (
        patch("app.tasks.SessionLocal", side_effect=db_ctx),
        patch("app.tasks.get_storage", return_value=mock_storage),
        patch("app.tasks.normalize_loudness", side_effect=fake_loudness),
        patch("app.tasks.heavy_queue.enqueue") as mock_heavy_enqueue,
    ):
        job_loudness(1, "1/cut/cut.mp4", "1/cut/cut_loud.mp4")

    job = next(iter(jobs.values()))
    assert job.status == "done"
    assert dummy_talk.status == "transcoding"
    mock_heavy_enqueue.assert_called_once_with(
        job_transcode,
        1,
        "1/cut/cut_loud.mp4",
        "1/final/final.mp4",
        job_timeout=STAGE_CONFIG["transcode"]["job_timeout"],
    )


def test_transcode_enqueues_publish_on_light(dummy_talk, mock_storage):
    dummy_talk.status = "transcoding"
    jobs = {}
    db_ctx = MockDBContext(dummy_talk, jobs)

    def fake_transcode(input_path, output_path):
        assert db_ctx.open_sessions == 0, "DB session was open during transcode!"

    with (
        patch("app.tasks.SessionLocal", side_effect=db_ctx),
        patch("app.tasks.get_storage", return_value=mock_storage),
        patch("app.tasks.transcode", side_effect=fake_transcode),
        patch("app.tasks.light_queue.enqueue") as mock_light_enqueue,
    ):
        job_transcode(1, "1/cut/cut_loud.mp4", "1/final/final.mp4")

    assert dummy_talk.status == "uploading"
    job = next(iter(jobs.values()))
    assert job.status == "done"
    mock_light_enqueue.assert_called_once_with(
        job_publish,
        1,
        "1/final/final.mp4",
        job_timeout=STAGE_CONFIG["publish"]["job_timeout"],
    )


def test_publish_advances_to_done_and_halts(dummy_talk, mock_storage):
    dummy_talk.status = "uploading"
    jobs = {}
    db_ctx = MockDBContext(dummy_talk, jobs)

    def fake_publish(input_path, output_path):
        assert db_ctx.open_sessions == 0, "DB session was open during publish!"

    with (
        patch("app.tasks.SessionLocal", side_effect=db_ctx),
        patch("app.tasks.get_storage", return_value=mock_storage),
        patch("app.tasks.publish", side_effect=fake_publish),
        patch("app.tasks.light_queue.enqueue") as mock_enqueue,
    ):
        job_publish(1, "1/final/final.mp4")

    assert dummy_talk.status == "done"
    job = next(iter(jobs.values()))
    assert job.status == "done"
    mock_enqueue.assert_not_called()  # Terminal state
