from __future__ import annotations
from .enums import ChannelType, OverwriteType, VideoQualityMode, ChannelFlag, Permission
from src.discord.http import Route, request, File
from src.discord.types import Snowflake
from typing import TYPE_CHECKING
from src.models import project
from .base import RawBaseModel
from datetime import datetime
from .user import User

if TYPE_CHECKING:
    from .message import Message, MessageReference, AllowedMentions
    from .component import Component
    from .webhook import Webhook
    from .embed import Embed
    from .poll import Poll


class ChannelMention(RawBaseModel):
    id: Snowflake
    guild_id: Snowflake
    type: ChannelType
    name: str


class Overwrite(RawBaseModel):
    id: Snowflake
    type: OverwriteType
    allow: Permission
    deny: Permission


class ThreadMetadata(RawBaseModel):
    ...


class ThreadMember(RawBaseModel):
    ...


class ForumTag(RawBaseModel):
    id: Snowflake
    name: str
    moderated: bool
    emoji_id: Snowflake | None = None
    emoji_name: str | None = None


class DefaultReaction(RawBaseModel):
    emoji_id: Snowflake | None = None
    emoji_name: str | None = None


class Channel(RawBaseModel):
    id: Snowflake
    type: ChannelType | None = None
    guild_id: Snowflake | None = None
    position: int | None = None
    permission_overwrites: list[Overwrite] | None = None
    name: str | None = None
    topic: str | None = None
    nsfw: bool | None = None
    last_message_id: Snowflake | None = None
    bitrate: int | None = None
    user_limit: int | None = None
    rate_limit_per_user: int | None = None
    recipients: list[User] | None = None
    icon: str | None = None
    owner_id: Snowflake | None = None
    application_id: Snowflake | None = None
    managed: bool | None = None
    parent_id: Snowflake | None = None
    last_pin_timestamp: datetime | None = None
    rtc_region: str | None = None
    video_quality_mode: VideoQualityMode | None = None
    message_count: int | None = None
    member_count: int | None = None
    thread_metadata: ThreadMetadata | None = None
    member: ThreadMember | None = None
    default_auto_archive_duration: int | None = None
    permissions: Permission | None = None
    flags: ChannelFlag | None = None
    total_message_sent: int | None = None
    available_tags: list[ForumTag] | None = None
    applied_tags: list[Snowflake] | None = None
    default_reaction_emoji: DefaultReaction | None = None
    default_thread_rate_limit_per_user: int | None = None
    default_sort_order: int | None = None
    default_forum_layout: int | None = None

    @classmethod
    async def fetch(cls, channel_id: Snowflake | int) -> Channel:
        return cls(
            **await request(
                Route(
                    'GET',
                    '/channels/{channel_id}',
                    channel_id=channel_id
                )
            )
        )

    @property
    def is_thread(self) -> bool:
        return self.type in {ChannelType.PUBLIC_THREAD, ChannelType.PRIVATE_THREAD}

    @property
    def mention(self) -> str:
        return f'<#{self.id}>'

    async def fetch_permissions_for(
        self,
        user_id: Snowflake | int,
    ) -> Permission:
        from .member import Member

        if self.guild_id is None:
            raise ValueError('Guild not found')

        member = await Member.fetch(self.guild_id, user_id)

        return await member.fetch_permissions_for(self.guild_id, self.id)

    async def send(
        self,
        content: str | None = None,
        *,
        tts: bool = False,
        embeds: list[Embed] | None = None,
        attachments: list[File] | None = None,
        components: list[Component] | None = None,
        sticker_ids: list[Snowflake] | None = None,
        reference: Message | MessageReference | None = None,
        allowed_mentions: AllowedMentions | None = None,
        poll: Poll | None = None,
        delete_after: float | None = None,
        token: str | None = project.bot_token
    ) -> Message:
        from .message import Message
        return await Message.send(
            self.id,
            content,
            tts=tts,
            embeds=embeds,
            attachments=attachments,
            components=components,
            sticker_ids=sticker_ids,
            reference=reference,
            allowed_mentions=allowed_mentions,
            poll=poll,
            delete_after=delete_after,
            token=token
        )

    async def fetch_message(self, message_id: Snowflake | int) -> Message:
        from .message import Message

        return await Message.fetch(self.id, message_id)

    async def fetch_webhooks(self, use_cache: bool = True) -> list[Webhook]:
        from .webhook import Webhook

        return [
            Webhook(**webhook)
            for webhook in
            await request(
                Route(
                    'GET',
                    '/channels/{channel_id}/webhooks',
                    channel_id=self.id
                ),
                ignore_cache=not use_cache
            )
        ]

    async def create_webhook(
        self,
        name: str,
        avatar: str | None = None,
        reason: str | None = None
    ) -> Webhook:
        from .webhook import Webhook

        return Webhook(
            **await request(
                Route(
                    'POST',
                    '/channels/{channel_id}/webhooks',
                    channel_id=self.id
                ),
                json={
                    'name': name,
                    'avatar': avatar
                },
                reason=reason
            )
        )

    async def fetch_messages(
        self,
        limit: int = 50,
        before: Snowflake | None = None,
        after: Snowflake | None = None,
        around: Snowflake | None = None,
    ) -> list[Message]:
        from .message import Message

        params = {
            'limit': limit
        }

        if before is not None:
            params['before'] = before

        if after is not None:
            params['after'] = after

        if around is not None:
            params['around'] = around

        return [
            Message(**message)
            for message in
            await request(
                Route(
                    'GET',
                    '/channels/{channel_id}/messages',
                    channel_id=self.id
                ),
                params=params,
                ignore_cache=True
            )
        ]
