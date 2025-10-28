from pydantic import BaseModel

class Message(BaseModel):
    message: str

class Event(BaseModel):
    event_id: str
    message: str

