from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from app.tasks import STAGE_CONFIG, job_detect, job_transcode


def test_stage_config_contains_all_stages():
    expected_stages = {"detect", "cut", "preview", "loudness", "transcode", "publish"}
    assert set(STAGE_CONFIG.keys()) == expected_stages


def test_stage_config_queue_assignments():
    for cfg in STAGE_CONFIG.values():
        assert "queue" in cfg
        assert "job_timeout" in cfg
        assert isinstance(cfg["job_timeout"], int)
        assert cfg["job_timeout"] > 0

    assert STAGE_CONFIG["detect"]["queue"] == "light"
    assert STAGE_CONFIG["cut"]["queue"] == "light"
    assert STAGE_CONFIG["preview"]["queue"] == "light"
    assert STAGE_CONFIG["loudness"]["queue"] == "light"
    assert STAGE_CONFIG["transcode"]["queue"] == "heavy"
    assert STAGE_CONFIG["publish"]["queue"] == "light"


def test_transcode_timeout_profile():
    # Heavy transcode timeout must be significantly longer than light stages
    assert STAGE_CONFIG["transcode"]["job_timeout"] >= 3600
    assert STAGE_CONFIG["detect"]["job_timeout"] <= 600
    assert STAGE_CONFIG["cut"]["job_timeout"] <= 1800


@patch("app.tasks.light_queue.enqueue")
def test_light_queue_enqueue_job_timeout(mock_enqueue):
    mock_enqueue.return_value = MagicMock()
    mock_enqueue(
        job_detect,
        1,
        "1/raw/video.mp4",
        job_timeout=STAGE_CONFIG["detect"]["job_timeout"],
    )

    mock_enqueue.assert_called_once_with(
        job_detect,
        1,
        "1/raw/video.mp4",
        job_timeout=300,
    )


@patch("app.tasks.heavy_queue.enqueue")
def test_heavy_queue_enqueue_job_timeout(mock_enqueue):
    mock_enqueue.return_value = MagicMock()
    mock_enqueue(
        job_transcode,
        1,
        "1/cut/cut_loud.mp4",
        "1/final/final.mp4",
        job_timeout=STAGE_CONFIG["transcode"]["job_timeout"],
    )

    mock_enqueue.assert_called_once_with(
        job_transcode,
        1,
        "1/cut/cut_loud.mp4",
        "1/final/final.mp4",
        job_timeout=14400,
    )


def test_docker_compose_worker_concurrency():
    compose_path = Path(__file__).parent.parent / "docker-compose.yml"
    assert compose_path.is_file()

    with open(compose_path, "r", encoding="utf-8") as f:
        compose = yaml.safe_load(f)

    services = compose.get("services", {})
    assert "worker-light" in services
    assert "worker-heavy" in services

    light_cmd = services["worker-light"]["command"]
    heavy_cmd = services["worker-heavy"]["command"]

    assert "--concurrency" in light_cmd
    assert "--concurrency" in heavy_cmd
