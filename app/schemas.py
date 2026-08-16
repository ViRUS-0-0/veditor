from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict

class EventBase(BaseModel):
    name: str

class EventCreate(EventBase):
    pass

class EventRead(EventBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ClientBase(BaseModel):
    event_ids: List[int] = []

class ClientCreate(ClientBase):
    hashed_key: str

class ClientRead(ClientBase):
    id: int
    hashed_key: str
    model_config = ConfigDict(from_attributes=True)


class TalkBase(BaseModel):
    title: str
    room: Optional[str] = None
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
    log_path: Optional[str] = None

class JobCreate(JobBase):
    talk_id: int

class JobRead(JobBase):
    id: int
    talk_id: int
    model_config = ConfigDict(from_attributes=True)


class ReviewBase(BaseModel):
    decision: str
    note: Optional[str] = None

class ReviewCreate(ReviewBase):
    talk_id: int

class ReviewRead(ReviewBase):
    id: int
    talk_id: int
    model_config = ConfigDict(from_attributes=True)
