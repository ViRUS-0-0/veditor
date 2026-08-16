import sys
import pytest
from unittest.mock import MagicMock, patch

from app.cli import create_client, main
from app import models


@patch("app.cli.secrets.token_urlsafe")
@patch("app.cli.hash_api_key")
def test_create_client_with_new_event(mock_hash, mock_secrets):
    mock_secrets.return_value = "raw-key"
    mock_hash.return_value = "hashed-key"

    mock_session = MagicMock()

    # We'll use a side effect to set `id` on the event/client when `refresh` is called
    def mock_refresh(obj):
        obj.id = 1

    mock_session.refresh.side_effect = mock_refresh

    create_client(mock_session, event_name="New Event", event_id=None)

    # Check that add was called twice (Event, then Client)
    assert mock_session.add.call_count == 2

    added_event = mock_session.add.call_args_list[0][0][0]
    assert isinstance(added_event, models.Event)
    assert added_event.name == "New Event"

    added_client = mock_session.add.call_args_list[1][0][0]
    assert isinstance(added_client, models.Client)
    assert added_client.hashed_key == "hashed-key"
    assert added_client.event_ids == [1]


@patch("app.cli.secrets.token_urlsafe")
@patch("app.cli.hash_api_key")
def test_create_client_with_existing_event(mock_hash, mock_secrets):
    mock_secrets.return_value = "raw-key"
    mock_hash.return_value = "hashed-key"

    mock_session = MagicMock()
    mock_event = models.Event(id=2, name="Existing")
    mock_session.query.return_value.filter.return_value.first.return_value = mock_event

    def mock_refresh(obj):
        obj.id = 2

    mock_session.refresh.side_effect = mock_refresh

    create_client(mock_session, event_name=None, event_id=2)

    # Should only add Client
    assert mock_session.add.call_count == 1
    added_client = mock_session.add.call_args_list[0][0][0]
    assert isinstance(added_client, models.Client)
    assert added_client.hashed_key == "hashed-key"
    assert added_client.event_ids == [2]


def test_create_client_missing_args():
    mock_session = MagicMock()
    with pytest.raises(SystemExit) as excinfo:
        create_client(mock_session, event_name=None, event_id=None)
    assert excinfo.value.code == 1


def test_create_client_conflicting_args():
    mock_session = MagicMock()
    with pytest.raises(SystemExit) as excinfo:
        create_client(mock_session, event_name="A", event_id=1)
    assert excinfo.value.code == 1


def test_create_client_invalid_event_id():
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(SystemExit) as excinfo:
        create_client(mock_session, event_name=None, event_id=99)
    assert excinfo.value.code == 1


@patch("app.cli.create_client")
@patch("app.cli.SessionLocal")
def test_cli_main(mock_session_local, mock_create_client):
    test_args = ["veditor", "admin", "create-client", "--event-name", "Test"]
    with patch.object(sys, "argv", test_args):
        main()

    mock_session_local.assert_called_once()
    mock_create_client.assert_called_once_with(
        mock_session_local.return_value, "Test", None
    )
    mock_session_local.return_value.close.assert_called_once()
