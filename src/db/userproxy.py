from __future__ import annotations
from beanie import Document, PydanticObjectId
from typing import TYPE_CHECKING
from pydantic import Field

if TYPE_CHECKING:
    from src.db.member import Member


class UserProxy(Document):
    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    class Settings:
        name = 'userproxies'
        validate_on_save = True
        use_state_management = True
        indexes = [('bot_id', 'member')]  # ? compound index

    id: PydanticObjectId = Field(default_factory=PydanticObjectId)
    bot_id: int = Field(description='bot id')
    user_id: int = Field(description='user id')
    member: PydanticObjectId = Field(description='the userproxy member id')
    public_key: str = Field(description='the userproxy public key')
    token: str | None = Field(
        None,
        description='the bot token, only stored when autosyncing is enabled')
    command: str | None = Field(
        'proxy', description='name of the proxy command')

    @property
    def autosync(self) -> bool:
        return self.token is not None

    async def get_member(self) -> Member:
        from src.db.member import Member
        member = await Member.get(self.member)
        assert member is not None
        return member
