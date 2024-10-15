from hikari import RESTApp, Snowflake, PermissionOverwrite, Permissions, Member, Role, Guild
from src.helpers import merge_dicts, TTLSet, TTLDict
from hikari.channels import PermissibleGuildChannel
from collections.abc import Mapping, Sequence
from hikari.impl.rest import RESTClientImpl
from hikari.errors import HikariError
from fastapi import HTTPException
from src.models import project
from asyncio import gather


drest_app = RESTApp()
drest_client: RESTClientImpl
CACHE_TTL = 60

perm_cache = TTLDict[str, bool](ttl=CACHE_TTL)
guild_cache = TTLDict[int, Guild](ttl=CACHE_TTL)
member_cache = TTLDict[str, Member](ttl=CACHE_TTL)
role_cache = TTLDict[int, Sequence[Role]](ttl=CACHE_TTL)
channel_cache = TTLDict[int, PermissibleGuildChannel](ttl=CACHE_TTL)

REQUIRED_PERMISSIONS = (
    Permissions.VIEW_CHANNEL |
    Permissions.SEND_MESSAGES
)


async def start_drest() -> None:
    global drest_client
    await drest_app.start()

    drest_client = drest_app.acquire(project.bot_token, 'Bot')

    drest_client.start()


async def _get_member(guild_id: int, user_id: int) -> Member:
    if (cache_hash := f'{guild_id}::{user_id}') in member_cache:
        return member_cache[cache_hash]

    try:
        member = await drest_client.fetch_member(guild_id, user_id)
    except HikariError:
        raise HTTPException(404, 'channel not found')

    member_cache[cache_hash] = member

    return member


async def _get_roles(guild_id: int) -> Sequence[Role]:
    if guild_id in role_cache:
        return role_cache[guild_id]

    roles = await drest_client.fetch_roles(guild_id)

    role_cache[guild_id] = roles

    return roles


async def _get_guild(guild_id: int) -> Guild:
    if guild_id in guild_cache:
        return guild_cache[guild_id]

    try:
        guild = await drest_client.fetch_guild(guild_id)
    except HikariError:
        raise HTTPException(404, 'channel not found')

    guild_cache[guild_id] = guild

    return guild


async def _get_permissible_channel(channel_id: int) -> PermissibleGuildChannel:
    if channel_id in channel_cache:
        return channel_cache[channel_id]

    try:
        channel = await drest_client.fetch_channel(channel_id)
    except HikariError:
        raise HTTPException(404, 'channel not found')

    if not isinstance(channel, PermissibleGuildChannel):
        raise HTTPException(404, 'channel not found')

    channel_cache[channel_id] = channel

    return channel


async def _get_channel_permission_overwrites(channel: PermissibleGuildChannel) -> Mapping[Snowflake, PermissionOverwrite]:
    if channel.parent_id is None:
        return channel.permission_overwrites

    return merge_dicts(
        channel.permission_overwrites,
        await _get_channel_permission_overwrites(
            await _get_permissible_channel(channel.parent_id)
        )
    )

# ? stole the permission checking code from https://discord.com/developers/docs/topics/permissions#permission-hierarchy


async def _compute_base_permissions(member: Member) -> Permissions:
    guild = await _get_guild(member.guild_id)

    if guild.owner_id == member.id:
        return Permissions.all_permissions()

    permissions = Permissions.NONE

    guild_roles = await _get_roles(guild.id)
    member_roles = set(member.role_ids)

    for role in [role for role in guild_roles if role.id in member_roles]:
        if role.id in member_roles:
            print(role)
            permissions |= role.permissions

    if permissions & Permissions.ADMINISTRATOR:
        return Permissions.all_permissions()

    return permissions


async def _compute_overwrites(
    base_permissions: Permissions,
    member: Member,
    channel: PermissibleGuildChannel
) -> Permissions:
    if base_permissions & Permissions.ADMINISTRATOR:
        return Permissions.all_permissions()

    overwrites = dict(await _get_channel_permission_overwrites(channel))

    permissions = base_permissions
    overwrite_everyone = overwrites.pop(channel.guild_id, None)
    if overwrite_everyone is not None:
        permissions &= ~overwrite_everyone.deny
        permissions |= overwrite_everyone.allow

    allow = Permissions.NONE
    deny = Permissions.NONE

    for role_id in member.role_ids:
        overwrite = overwrites.get(role_id)
        if overwrite is not None:
            allow |= overwrite.allow
            deny |= overwrite.deny

    permissions &= ~deny
    permissions |= allow

    overwrite_member = overwrites.get(member.id)
    if overwrite_member is not None:
        permissions &= ~overwrite_member.deny
        permissions |= overwrite_member.allow

    if member.communication_disabled_until():
        permissions &= (
            Permissions.VIEW_CHANNEL |
            Permissions.READ_MESSAGE_HISTORY)

    return permissions


async def compute_permissions(member: Member, channel: PermissibleGuildChannel) -> Permissions:
    return await _compute_overwrites(
        await _compute_base_permissions(member),
        member,
        channel
    )


async def user_can_send(user_id: int, channel_id: int, guild_id: int) -> bool:
    cache_hash = f'{user_id}::{channel_id}'

    if cache_hash in perm_cache:
        return perm_cache[cache_hash]

    # ? getting guild and roles here so it's cached for later
    member, channel, _, _ = await gather(
        _get_member(guild_id, user_id),
        _get_permissible_channel(channel_id),
        _get_roles(guild_id),
        _get_guild(guild_id)
    )

    member_permissions = await compute_permissions(member, channel)

    if member_permissions & REQUIRED_PERMISSIONS == REQUIRED_PERMISSIONS:
        perm_cache[cache_hash] = True
        return True

    perm_cache[cache_hash] = False
    return False
