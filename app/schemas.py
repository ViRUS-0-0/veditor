from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EventBase(BaseModel):
    name: str


class EventCreate(EventBase):
    pass


class EventRead(EventBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ClientBase(BaseModel):
    event_ids: list[int] = []


class ClientCreate(ClientBase):
    hashed_key: str


class ClientRead(ClientBase):
    id: int
    hashed_key: str
    model_config = ConfigDict(from_attributes=True)


class TalkBase(BaseModel):
    title: str
    room: str | None = None
    start: datetime
    end: datetime
    status: str = "waiting_for_files"


class TalkCreate(TalkBase):
    event_id: int


class TalkRead(TalkBase):
    id: int
    event_id: int
    model_config = ConfigDict(from_attributes=True)


class JobBase(BaseModel):
    kind: str
    status: str
    log_path: str | None = None


class JobCreate(JobBase):
    talk_id: int


class JobRead(JobBase):
    id: int
    talk_id: int
    model_config = ConfigDict(from_attributes=True)


class ReviewBase(BaseModel):
    decision: str
    note: str | None = None


class ReviewCreate(ReviewBase):
    talk_id: int


class ReviewRead(ReviewBase):
    id: int
    talk_id: int
    model_config = ConfigDict(from_attributes=True)


class TalkWithJobsRead(TalkRead):
    jobs: list[JobRead] = []
