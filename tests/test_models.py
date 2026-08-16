import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import Base
from app.models import Event, Client, Talk, Job, Review

# Use the postgres instance from docker-compose, but we will wrap tests in a transaction
engine = create_engine(settings.database_url)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield

@pytest.fixture
def db_session(setup_database):
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

def test_create_event_and_talk_relationships(db_session):
    event = Event(name="FOSSASIA 2026")
    db_session.add(event)
    db_session.flush()

    talk = Talk(
        event_id=event.id,
        title="Keynote",
        room="Main Hall",
        start=datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
    )
    db_session.add(talk)
    db_session.flush()
    
    # Test relationships
    assert talk.event == event
    assert len(event.talks) == 1
    assert event.talks[0] == talk
    
    job = Job(talk_id=talk.id, kind="cut", status="running")
    db_session.add(job)
    
    review = Review(talk_id=talk.id, decision="approved", note="Looks good")
    db_session.add(review)
    db_session.flush()
    
    assert job.talk == talk
    assert review.talk == talk
    assert len(talk.jobs) == 1
    assert talk.jobs[0] == job
    assert len(talk.reviews) == 1
    assert talk.reviews[0] == review

def test_required_fields_enforced(db_session):
    # Event missing name
    with pytest.raises(IntegrityError):
        event = Event()
        db_session.add(event)
        db_session.flush()
    db_session.rollback()

    event = Event(name="Test")
    db_session.add(event)
    db_session.flush()

    # Talk missing title
    with pytest.raises(IntegrityError):
        talk = Talk(
            event_id=event.id,
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc)
        )
        db_session.add(talk)
        db_session.flush()
    db_session.rollback()

def test_client_model(db_session):
    client = Client(hashed_key="hash123", event_ids=[1, 2, 3])
    db_session.add(client)
    db_session.flush()
    
    assert client.id is not None
    assert client.hashed_key == "hash123"
    assert client.event_ids == [1, 2, 3]
