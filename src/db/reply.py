from beanie import Document, PydanticObjectId
from src.models import ReplyAttachment
from pymongo import IndexModel
from datetime import datetime
from pydantic import Field


class Reply(Document):
    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    class Settings:
        name = 'replies'
        validate_on_save = True
        use_state_management = True
        indexes = [
            ('bot_id', 'channel'),  # ? compound index
            IndexModel('ts', expireAfterSeconds=300)
        ]

    id: PydanticObjectId = Field(default_factory=PydanticObjectId)
    bot_id: int = Field(description='bot id')
    channel: int = Field(description='the channel id of the reply')
    content: str | None = Field(description='the userproxy content')
    attachment: ReplyAttachment | None = Field(
        description='the message attachment')
    ts: datetime = Field(
        default_factory=datetime.utcnow,
        description='timestamp for the reply; used for ttl')
