from src.discord import Emoji, MessageCreateEvent, Message, Permission, Channel, Snowflake, Webhook, ChannelType, AllowedMentions, StickerFormatType
from src.db import Member as ProxyMember, Latch, Group, Webhook as DBWebhook, Message as DBMessage
from regex import finditer, Match, escape, match, IGNORECASE, sub
from src.discord.http import get_from_cdn
from src.models import DebugMessage
from dataclasses import dataclass
from asyncio import gather
from random import randint


_emoji_index = randint(0, 999)


def emoji_index() -> str:
    global _emoji_index
    if _emoji_index == 999:
        _emoji_index = -1
    _emoji_index += 1
    return f'{_emoji_index:03}'


@dataclass(frozen=True)
class ProbableEmoji:
    name: str
    id: int
    animated: bool

    def __str__(self) -> str:
        return f'<{"a" if self.animated else ""}:{self.name}:{self.id}>'

    async def read(self) -> bytes:
        return await get_from_cdn(
            f'https://cdn.discordapp.com/emojis/{self.id}.{"gif" if self.animated else "png"}')


async def process_emoji(message: str) -> tuple[list[Emoji], str]:
    guild_emojis = {
        ProbableEmoji(
            name=str(match.group(2)),
            id=int(match.group(3)),
            animated=match.group(1) is not None
        )
        for match in finditer(r'<(a)?:(\w{2,32}):(\d+)>', message)
    }

    app_emojis = {}

    async def _create_emoji(emoji: ProbableEmoji) -> None:
        app_emojis.update({
            emoji.id: await Emoji.create_application_emoji(
                name=f'{emoji.name[:28]}_{emoji_index()}',
                image=await emoji.read(),
            )
        })

    await gather(*[_create_emoji(emoji) for emoji in guild_emojis])

    for guild_emoji in guild_emojis:
        message = message.replace(
            str(guild_emoji), str(app_emojis.get(guild_emoji.id))
        )

    return list(app_emojis.values()), message


def _ensure_proxy_preserves_mentions(check: Match) -> bool:
    for safety_match in finditer(
        r'<(?:(?:[@#]|sound:|:[\S_]+|\/(?:\w+ ?){1,3}:)\d+|https?:\/\/[^\s]+)>',
        check.string
    ):
        if (
            (
                # ? if the prefix is present
                check.end(1) and
                safety_match.start() < check.end(1)
            ) or
            (
                # ? if the suffix is present
                (check.start(3)-len(check.string)) and
                safety_match.end() > check.start(3)
            )
        ):
            return False

    return True


async def get_proxy_for_message(
    message: MessageCreateEvent,
    debug_log: list[DebugMessage | str] | None = None
) -> tuple[ProxyMember, str, Latch | None] | tuple[None, None, None]:
    assert message.author is not None
    assert message.channel is not None
    assert message.guild is not None
    if debug_log is None:
        debug_log = []

    groups = await Group.find_many({'accounts': message.author.id}).to_list()

    channel_ids: set[Snowflake | None] = {
        message.channel.id,
    }
    channel = message.channel

    while channel.parent_id is not None:
        channel_ids.add(channel.parent_id)
        channel = await Channel.fetch(channel.parent_id)

    channel_ids.discard(None)

    # ? get global latch if it exists
    latch = await Latch.find_one({'user': message.author.id, 'guild': 0})

    if latch is None or latch.enabled is False:
        # ? if it doesn't exist or is disabled, get the guild latch
        latch = await Latch.find_one({'user': message.author.id, 'guild': message.guild.id})

    latch_return: tuple[ProxyMember, str, Latch] | None = None

    for group in groups.copy():
        if (  # ? this is a mess, if the system restricts channels and the message isn't in one of them, skip
            group.channels and
            not any(
                channel_id in group.channels
                for channel_id in channel_ids
            )
        ):
            if debug_log:
                debug_log.append(
                    DebugMessage.GROUP_CHANNEL_RESTRICTED.format(group.name))
            continue

        for member_id in group.members.copy():
            member = await ProxyMember.get(member_id)

            if member is None:
                continue

            if latch and latch.enabled and latch.member == member.id:
                # ? putting this here, if there are proxy tags given, prioritize them
                # ? also having this check here ensures that channels are still checked
                latch_return = member, message.content, latch

            for proxy_tag in member.proxy_tags:
                if not proxy_tag.prefix and not proxy_tag.suffix:
                    continue

                prefix, suffix = (
                    (escape(proxy_tag.prefix), escape(proxy_tag.suffix))
                    if not proxy_tag.regex else
                    (proxy_tag.prefix, proxy_tag.suffix)
                )

                check = match(
                    f'^({prefix})([\\s\\S]+)({suffix})$',
                    message.content,
                    IGNORECASE if not proxy_tag.case_sensitive else 0
                )

                if check is not None:
                    if not _ensure_proxy_preserves_mentions(check):
                        continue

                    if latch is not None and latch.enabled:
                        latch.member = member.id
                        await latch.save_changes()

                    return member, check.group(2), latch

    if latch is None:
        debug_log.append(DebugMessage.AUTHOR_NO_TAGS)

        return None, None, None

    if latch_return is not None:
        return latch_return

    if debug_log:
        debug_log.append(DebugMessage.AUTHOR_NO_TAGS_NO_LATCH)

    return None, None, None


async def permission_check(
    message: MessageCreateEvent,
    debug_log: list[DebugMessage | str] | None = None,
    channel_permissions: Permission | None = None
) -> bool:
    assert message.author is not None
    assert message.channel is not None

    # ? mypy stupid
    self_permissions = channel_permissions or await message.channel.fetch_permissions_for(
        message.author.id)

    if not isinstance(self_permissions, Permission):
        return False  # ? mypy stupid

    if not self_permissions & Permission.SEND_MESSAGES:
        if debug_log:
            debug_log.append(DebugMessage.PERM_SEND_MESSAGES)

        return False

    if not self_permissions & Permission.MANAGE_WEBHOOKS:
        if debug_log:
            debug_log.append(DebugMessage.PERM_MANAGE_WEBHOOKS)

        return False

    if not self_permissions & Permission.MANAGE_MESSAGES:
        if debug_log:
            debug_log.append(DebugMessage.PERM_MANAGE_MESSAGES)

        return False

    return True


async def get_proxy_webhook(channel: Channel) -> Webhook:

    if channel.type in {ChannelType.PUBLIC_THREAD, ChannelType.PRIVATE_THREAD}:
        if channel.parent_id is None:
            raise ValueError('thread channel has no parent')

        channel = await channel.fetch(channel.parent_id)

    if channel.guild_id is None:
        raise ValueError('resolved channel is not a guild channel')

    webhook = await DBWebhook.get(channel.id)

    if webhook is not None:
        return await Webhook.from_url(
            webhook.url
        )

    for webhook in await channel.fetch_webhooks():
        if webhook.name == '/plu/ral proxy':
            assert webhook.url is not None  # ? will always exist after fetching it
            await DBWebhook(
                id=channel.id,
                guild=channel.guild_id,
                url=webhook.url
            ).save()
            return webhook

    webhook = await channel.create_webhook(
        name='/plu/ral proxy',
        reason='required for /plu/ral to function'
    )

    assert webhook.url is not None  # ? will always exist after creating it

    await DBWebhook(
        id=channel.id,
        guild=channel.guild_id,
        url=webhook.url
    ).save()

    return webhook


def handle_discord_markdown(text: str) -> str:
    markdown_patterns = {
        '*':   r'\*([^*]+)\*',
        '_':   r'_([^_]+)_',
        '**':  r'\*\*([^*]+)\*\*',
        '__':  r'__([^_]+)__',
        '~~':  r'~~([^~]+)~~',
        '`':   r'`([^`]+)`',
        '```': r'```[\s\S]+?```'
    }

    for pattern in markdown_patterns.values():
        text = sub(pattern, r'\1', text)

    for char in [
        '*', '_',
        '~', '`'
    ]:
        text = sub(
            r'(?<!\\)' + escape(char),
            r'\\\1',
            text
        )

    return text


def format_reply(
    content: str,
    reference: Message,
    guild_id: int | None = None
) -> str:  # | ReplyEmbed:
    assert reference.author is not None

    refcontent = reference.content or ''
    refattachments = reference.attachments
    mention = (
        reference.author.mention
        if reference.webhook_id is None else
        f'`@{reference.author.display_name}`'
    )

    base_reply = f'-# [↪](<{reference.jump_url}>) {mention}'

    if (
        match(
            r'^-# \[↪\]\(<https:\/\/discord\.com\/channels\/\d+\/\d+\/\d+>\)',
            refcontent
        )
    ):
        refcontent = '\n'.join(refcontent.split('\n')[1:])

    refcontent = handle_discord_markdown(refcontent).replace('\n', ' ')

    formatted_refcontent = (
        refcontent
        if len(refcontent) <= 75 else
        f'{refcontent[:75].strip()}…'
    ).replace('://', ':/​/')  # ? add zero-width space to prevent link previews

    reply_content = (
        formatted_refcontent
        if formatted_refcontent else
        f'[*Click to see attachment*](<{reference.jump_url}>)'
        if refattachments else
        f'[*Click to see message*](<{reference.jump_url}>)'
    )

    total_content = f'{base_reply} {reply_content}\n{content}'
    if len(total_content) <= 2000:
        return total_content

    return total_content

    # return ReplyEmbed(reference, reference.jump_url)


async def process_proxy(
    message: MessageCreateEvent,
    debug_log: list[DebugMessage | str] | None = None,
    channel_permissions: Permission | None = None
) -> tuple[bool, list[Emoji] | None]:
    assert message.author is not None
    assert message.channel is not None
    if debug_log is None:
        # ? if debug_log is given by debug command, it will have DebugMessage.ENABLER, being a truthy value
        # ? if it's not given, we set it to an empty list here and never append to it
        debug_log = []

    valid_content = bool(
        message.content or message.attachments or message.sticker_items or message.poll)

    if (
        message.author.bot or
        message.guild is None or
        not valid_content or
        (message.attachments and message.sticker_items)
    ):
        if debug_log:
            if message.author.bot:
                debug_log.append(DebugMessage.AUTHOR_BOT)

            if message.guild is None:
                debug_log.append(DebugMessage.NOT_IN_GUILD)

            if not valid_content:
                debug_log.append(DebugMessage.NO_CONTENT)

            if message.attachments and message.sticker_items:
                debug_log.append(DebugMessage.ATTACHMENTS_AND_STICKERS)

        return False, None

    member, proxy_content, latch = await get_proxy_for_message(message, debug_log)

    if member is None or proxy_content is None:
        return False, None

    if (
        latch is not None and
        latch.enabled and
        message.content.startswith('\\')
    ):
        # ? if latch is enabled and,
        # ? if message starts with single backslash, skip proxying this message,
        # ? if message starts with double backslash, reset member on latch
        if message.content.startswith('\\\\'):
            latch.member = None
            await latch.save_changes()

        if debug_log:
            debug_log.append(DebugMessage.AUTOPROXY_BYPASSED)

        return False, None

    if not await permission_check(message, debug_log, channel_permissions):
        return False, None

    if len(proxy_content) > 1980:
        await message.channel.send(
            'i cannot proxy message over 1980 characters',
            reference=message,
            allowed_mentions=AllowedMentions(
                replied_user=False
            ),
            delete_after=10
        )

        if debug_log:
            debug_log.append(DebugMessage.OVER_TEXT_LIMIT)

        return False, None

    if sum(
        attachment.size
        for attachment in
        message.attachments
    ) > message.guild.filesize_limit:
        await message.channel.send(
            'attachments are above the file size limit',
            reference=message,
            allowed_mentions=AllowedMentions(
                replied_user=False
            ),
            delete_after=10
        )

        if debug_log:
            debug_log.append(DebugMessage.OVER_FILE_LIMIT)

        return False, None

    webhook = await get_proxy_webhook(message.channel)

    # ? don't actually clone emotes if we're debugging
    app_emojis = list()
    if not debug_log:
        app_emojis, proxy_content = await process_emoji(proxy_content)

    if len(proxy_content) > 2000:
        await message.channel.send(
            'this message was over 2000 characters after processing emotes. proxy failed',
            reference=message,
            allowed_mentions=AllowedMentions(
                replied_user=False
            ),
            delete_after=10
        )
        return False, app_emojis

    embed = None
    if message.referenced_message:
        if message.referenced_message.guild is None:
            message.referenced_message.guild = message.guild

        proxy_with_reply = format_reply(
            proxy_content, message.referenced_message)

        if isinstance(proxy_with_reply, str):
            proxy_content = proxy_with_reply
        else:
            embed = proxy_with_reply

    if debug_log:
        debug_log.append(DebugMessage.SUCCESS)
        return True, app_emojis

    attachments = [
        await attachment.as_file()
        for attachment in message.attachments
    ]
    if message.sticker_items and not attachments:
        if any(
            sticker.format_type == StickerFormatType.LOTTIE
            for sticker in message.sticker_items
        ):
            if debug_log:
                debug_log.append(DebugMessage.INCOMPATIBLE_STICKERS)
            return False, app_emojis

        attachments = [
            await sticker.as_file()
            for sticker in message.sticker_items
        ]

    responses = await gather(
        message.delete(reason='/plu/ral proxy'),
        webhook.execute(
            content=proxy_content,
            thread_id=(
                message.channel.id
                if message.channel.type in {ChannelType.PUBLIC_THREAD, ChannelType.PRIVATE_THREAD} else
                None
            ),
            wait=True,
            username=f'{member.name} {((await member.get_group()).tag or "")}',
            avatar_url=await member.get_avatar_url(),
            embeds=[embed] if embed is not None else [],
            attachments=attachments,
            allowed_mentions=AllowedMentions(
                replied_user=(
                    message.referenced_message is not None and
                    message.referenced_message.author in message.mentions
                )
            ),
            poll=message.poll
        )
    )
    # webhook.send(
    #     content=proxy_content,
    #     thread=(
    #         message.channel
    #         if getattr(message.channel, 'parent', None) is not None else
    #         MISSING
    #     ),
    #     wait=True,
    #     username=f'{member.name} {((await member.get_group()).tag or '')}',
    #     avatar_url=await member.get_avatar_url(),
    #     embed=embed,
    #     files=attachments,
    #     allowed_mentions=(
    #         AllowedMentions(
    #             users=(
    #                 [message.reference.resolved.author]
    #                 if message.reference.resolved.author in message.mentions else
    #                 []
    #             )
    #         )
    #     ) if (
    #         not embed == MISSING and
    #         message.reference is not None and
    #         isinstance(message.reference.resolved, Message)
    #     ) else MISSING,
    #     poll=message.poll or MISSING
    # )

    await DBMessage(
        original_id=message.id,
        proxy_id=responses[1].id,
        author_id=message.author.id
    ).save()

    return True, app_emojis