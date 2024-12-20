from __future__ import annotations
from pydantic import BaseModel, Field
from beanie import PydanticObjectId
from src.db import ProxyMember
from typing import Annotated


class MemberModel(BaseModel):
    id: PydanticObjectId = Field(description='the id of the member')
    name: str = Field(
        description='the name of the member',
        min_length=1, max_length=50)
    avatar: PydanticObjectId | None = Field(
        None,
        description='the avatar uuid of the member; overrides the group avatar'
    )
    proxy_tags: Annotated[list[ProxyMember.ProxyTag], Field(max_length=5)] = Field(
        [],
        description='proxy tags for the member'
    )


class MemberUpdateModel(BaseModel):
    name: str = Field(
        None, description='the name of the member', min_length=1, max_length=50)
    avatar: PydanticObjectId | None = Field(
        None,
        description='the avatar uuid of the member; overrides the group avatar'
    )
    group: PydanticObjectId = Field(
        None,
        description='group id for the member')
    proxy_tags: Annotated[list[ProxyMember.ProxyTag], Field(max_length=5)] = Field(
        None,
        description='proxy tags for the member'
    )


class CreateMemberModel(BaseModel):
    name: str = Field(
        description='the name of the group',
        min_length=1, max_length=32)
    avatar: PydanticObjectId | None = Field(
        None,
        description='the avatar uuid of the group'
    )
    proxy_tags: Annotated[list[ProxyMember.ProxyTag], Field(max_length=5)] = Field(
        [],
        description='proxy tags for the member'
    )
