import ast
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import redis.exceptions

from scripts.run_worker import main


def test_eager_import_tasks_rationale():
    """Verify that scripts/run_worker.py statically imports app.tasks

    for boot-time preloading.
    """
    script_path = Path(__file__).parent.parent / "scripts" / "run_worker.py"
    tree = ast.parse(script_path.read_text(encoding="utf-8"))

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}" if module else alias.name)

    assert any(imp == "app.tasks" or imp.startswith("app.tasks.") for imp in imports), (
        "scripts/run_worker.py must eagerly import app.tasks"
    )


@patch("scripts.run_worker.redis.from_url")
@patch("scripts.run_worker.Worker")
def test_worker_default_queues(mock_worker_cls, mock_redis_from_url):
    mock_redis = MagicMock()
    mock_redis_from_url.return_value = mock_redis
    mock_worker = MagicMock()
    mock_worker_cls.return_value = mock_worker

    main([])

    mock_redis.ping.assert_called_once()
    mock_worker_cls.assert_called_once_with(
        ["light", "heavy"], connection=mock_redis, name=None
    )
    mock_worker.work.assert_called_once_with(burst=False)


@patch("scripts.run_worker.redis.from_url")
@patch("scripts.run_worker.Worker")
def test_worker_explicit_queues(mock_worker_cls, mock_redis_from_url):
    mock_redis = MagicMock()
    mock_redis_from_url.return_value = mock_redis
    mock_worker = MagicMock()
    mock_worker_cls.return_value = mock_worker

    main(["light"])
    mock_worker_cls.assert_called_with(["light"], connection=mock_redis, name=None)

    main(["heavy"])
    mock_worker_cls.assert_called_with(["heavy"], connection=mock_redis, name=None)

    main(["light", "heavy", "custom_queue"])
    mock_worker_cls.assert_called_with(
        ["light", "heavy", "custom_queue"], connection=mock_redis, name=None
    )


@patch("scripts.run_worker.redis.from_url")
@patch("scripts.run_worker.Worker")
def test_worker_burst_and_name_flags(mock_worker_cls, mock_redis_from_url):
    mock_redis = MagicMock()
    mock_redis_from_url.return_value = mock_redis
    mock_worker = MagicMock()
    mock_worker_cls.return_value = mock_worker

    main(["light", "--burst", "--name", "test-worker-1"])
    mock_worker_cls.assert_called_once_with(
        ["light"], connection=mock_redis, name="test-worker-1"
    )
    mock_worker.work.assert_called_once_with(burst=True)


@patch("scripts.run_worker.redis.from_url")
def test_worker_redis_connection_error_fast_fail(mock_redis_from_url, capsys):
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = redis.exceptions.ConnectionError(
        "Connection refused by Redis server"
    )
    mock_redis_from_url.return_value = mock_redis

    with pytest.raises(SystemExit) as exc_info:
        main(["light"])

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error: Could not connect to Redis" in captured.err, (
        f"Expected clean error on stderr, got: {captured.err}"
    )
    assert "Connection refused" in captured.err


def test_worker_redis_url_unset_fast_fail(capsys):
    with patch("scripts.run_worker.settings.redis_url", ""):
        with pytest.raises(SystemExit) as exc_info:
            main(["light"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error: REDIS_URL is unset." in captured.err


def test_worker_cli_help():
    result = subprocess.run(
        [sys.executable, "scripts/run_worker.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Run an RQ worker for VEditor" in result.stdout
    assert "queues" in result.stdout
