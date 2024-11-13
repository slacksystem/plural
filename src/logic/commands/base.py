from src.discord import slash_command, Interaction, message_command, InteractionContextType, Message, ApplicationCommandOption, ApplicationCommandOptionType, Embed, Permission, ApplicationIntegrationType, ApplicationCommandOptionChoice, Attachment
from src.db import Message as DBMessage, ProxyMember, Latch, UserProxyInteraction
from src.logic.proxy import get_proxy_webhook, process_proxy
from src.logic.modals import modal_plural_edit, umodal_edit
from src.errors import InteractionError
from src.models import DebugMessage
from asyncio import gather
from time import time


@slash_command(
    name='ping', description='check the bot\'s latency',
    contexts=InteractionContextType.ALL(),
    integration_types=ApplicationIntegrationType.ALL())
async def slash_ping(interaction: Interaction) -> None:
    timestamp = (interaction.id >> 22) + 1420070400000

    await interaction.response.send_message(
        f'pong! ({round((time()*1000-timestamp))}ms)'
    )


async def _userproxy_edit(interaction: Interaction, message: Message) -> bool:
    if message.interaction_metadata is None:
        return False

    if message.interaction_metadata.user.id != interaction.author_id:
        raise InteractionError('message is not a proxied message!')

    if message.interaction_metadata.user.id != interaction.author_id:
        raise InteractionError('you can only edit your own messages!')

    if (
        message.webhook_id is None or
        not await UserProxyInteraction.find_one({'message_id': message.id}) or
        not await ProxyMember.find_one({'userproxy.bot_id': message.webhook_id})
    ):
        raise InteractionError('message is not a proxied message!')

    await interaction.response.send_modal(
        modal=umodal_edit.with_title(
            'edit message'
        ).with_text_value(
            0, message.content
        ).with_extra(
            message.id
        ))
    return True


@message_command(
    name='/plu/ral edit',
    contexts=InteractionContextType.ALL(),
    integration_types=ApplicationIntegrationType.ALL())
async def message_plural_edit(interaction: Interaction, message: Message) -> None:
    assert interaction.channel is not None
    assert interaction.guild is not None

    if await _userproxy_edit(interaction, message):
        return

    if message.webhook_id is None:
        raise InteractionError('message is not a proxied message!')

    webhook = await get_proxy_webhook(interaction.channel)

    if message.webhook_id != webhook.id:
        raise InteractionError(
            'due to discord limitations, you can\'t edit userproxy messages older than 15 minutes')

    db_message = await DBMessage.find_one({'proxy_id': message.id})

    if db_message is None:
        raise InteractionError(
            'message could not be found, is it more than a day old?')

    if interaction.author_id != db_message.author_id:
        raise InteractionError('you can only edit your own messages!')

    await interaction.response.send_modal(
        modal_plural_edit.with_extra(
            message
        )
    )


@slash_command(
    name='autoproxy',
    description='automatically proxy messages. leave empty to toggle',
    options=[
        ApplicationCommandOption(
            type=ApplicationCommandOptionType.BOOLEAN,
            name='enabled',
            description='enable or disable auto proxying',
            required=False
        ),
        ApplicationCommandOption(
            type=ApplicationCommandOptionType.STRING,
            name='member',
            description='set to a specific member immediately',
            required=False,
            autocomplete=True
        ),
        ApplicationCommandOption(
            type=ApplicationCommandOptionType.BOOLEAN,
            name='server_only',
            description='whether to enable/disable in every server or just this one',
            required=False)],
    contexts=[InteractionContextType.GUILD],
    integration_types=[ApplicationIntegrationType.GUILD_INSTALL])
async def slash_autoproxy(
    interaction: Interaction,
    enabled: bool | None = None,
    member: ProxyMember | None = None,
    server_only: bool = True
) -> None:
    if interaction.guild is None and server_only:
        raise InteractionError(
            'you must use this command in a server when the `server_only` option is enabled')

    latch = (
        await Latch.find_one(
            {
                'user': interaction.author_id,
                'guild': interaction.guild_id if server_only else None
            }
        ) or await Latch(
            user=interaction.author_id,
            guild=interaction.guild_id if server_only else None,
            enabled=False,
            member=None
        ).save()
    )

    latch.enabled = bool(
        enabled
        if enabled is not None else
        member or not latch.enabled
    )

    if member is not None:
        latch.member = member.id

    if not latch.enabled:
        latch.member = None

    message = (
        f'autoproxying in `{interaction.guild.name}` is now '
        if server_only and interaction.guild is not None else
        'global autoproxy is now '
    ) + (
        'enabled' if latch.enabled else 'disabled'
    )

    if latch.enabled:
        message += ' and set to ' + (
            f'member `{member.name}`'
            if member else
            'the next member to send a message'
        )

    await gather(
        latch.save(),
        interaction.response.send_message(
            embeds=[Embed.success(message)]
        )
    )


@slash_command(
    name='switch',
    description='quickly switch global autoproxy',
    options=[
        ApplicationCommandOption(
            type=ApplicationCommandOptionType.STRING,
            name='member',
            description='member to switch to',
            required=True,
            autocomplete=True),
        ApplicationCommandOption(
            type=ApplicationCommandOptionType.BOOLEAN,
            name='enabled',
            description='enable or disable auto proxying',
            required=False)],
    contexts=[InteractionContextType.GUILD],
    integration_types=[ApplicationIntegrationType.GUILD_INSTALL])
async def slash_switch(
    interaction: Interaction,
    member: ProxyMember,
    enabled: bool | None = None
) -> None:
    assert slash_autoproxy.callback is not None
    await slash_autoproxy.callback(
        interaction,
        enabled=enabled,
        member=member,
        server_only=False
    )


@slash_command(
    name='delete_all_data',
    description='delete all of your data',
    contexts=InteractionContextType.ALL(),
    integration_types=ApplicationIntegrationType.ALL())
async def slash_delete_all_data(interaction: Interaction) -> None:
    await interaction.response.send_message(
        embeds=[Embed(  # ! implement components, probably make view class
            title='are you sure?',
            description='this will delete all of your data, including groups, members, avatars, latches, and messages\n\nthis action is irreversible',
            color=0xff6969
        )]
    )


@slash_command(
    name='reproxy',
    description='reproxy your last message. must be the last message in the channel',
    options=[
        ApplicationCommandOption(
            type=ApplicationCommandOptionType.STRING,
            name='member',
            description='member to reproxy as',
            required=True,
            autocomplete=True)],
    contexts=[InteractionContextType.GUILD],
    integration_types=[ApplicationIntegrationType.GUILD_INSTALL])
async def slash_reproxy(
    interaction: Interaction,
    member: ProxyMember
) -> None:
    assert interaction.channel is not None
    assert interaction.app_permissions is not None

    if not interaction.app_permissions & Permission.READ_MESSAGE_HISTORY:
        raise InteractionError(
            'bot does not have permission to read message history in this channel')

    messages = await interaction.channel.fetch_messages(limit=1)

    if not messages:
        raise InteractionError('message not found')

    message = messages[0]

    last_proxy_message = await DBMessage.find_one(
        {
            'author_id': interaction.author_id,
            'proxy_id': message.id
        },
        sort=[('ts', -1)]
    )

    if last_proxy_message is None:
        raise InteractionError(
            'no messages found, you cannot reproxy a message that was not the most recent message, or a message older than one day')

    message.author = (
        interaction.member.user
        if interaction.member is not None
        else interaction.user
    )

    message.channel = interaction.channel
    message.guild = interaction.guild

    await gather(
        process_proxy(
            message,
            member=member),
        interaction.response.send_message(
            embeds=[Embed.success(f'message reproxied as {member.name}')]),
        last_proxy_message.delete()
    )


@message_command(
    name='/plu/ral debug',
    contexts=[InteractionContextType.GUILD],
    integration_types=[ApplicationIntegrationType.GUILD_INSTALL])
async def message_plural_debug(interaction: Interaction, message: Message) -> None:
    debug_log: list[DebugMessage | str] = [DebugMessage.ENABLER]

    await process_proxy(message, debug_log)

    debug_log.remove(DebugMessage.ENABLER)

    await interaction.response.send_message(
        embeds=[Embed(
            title='debug log',
            description=f'```{'\n'.join(debug_log)}```',
            color=(
                0x69ff69
                if DebugMessage.SUCCESS in debug_log else
                0xff6969
            )
        )]
    )


@message_command(
    name='/plu/ral proxy info',
    contexts=[InteractionContextType.GUILD],
    integration_types=[ApplicationIntegrationType.GUILD_INSTALL])
async def message_plural_proxy_info(interaction: Interaction, message: Message) -> None:
    if message.webhook_id is None:
        raise InteractionError('message is not a proxied message!')

    assert message.author is not None

    db_message = await DBMessage.find_one({'proxy_id': message.id})

    if db_message is None:
        raise InteractionError(
            'message could not be found, is it more than a day old?')

    embed = Embed(
        title='proxy info',
        color=0x69ff69
    )

    embed.add_field(
        name='author',
        value=db_message.author_name,
        inline=False
    )

    embed.set_footer(
        text=f'original message id: {db_message.original_id or 'sent through / plu/ral api'}'
    )

    embed.set_thumbnail(
        url=message.author.avatar_url
    )

    await interaction.response.send_message(
        embeds=[embed]
    )


@slash_command(
    name='api',
    description='get or refresh an api key',
    contexts=InteractionContextType.ALL(),
    integration_types=ApplicationIntegrationType.ALL())
async def slash_api(interaction: Interaction) -> None:
    ...


# ! implement cooldowns
@slash_command(
    name='export',
    description='export your data',
    options=[
        ApplicationCommandOption(
            type=ApplicationCommandOptionType.STRING,
            name='format',
            description='export format; default: importable',
            required=False,
            choices=[
                ApplicationCommandOptionChoice(
                    name='importable; contains minimum data required for import, relatively safe to share',
                    value='importable'
                ),
                ApplicationCommandOptionChoice(
                    name='full; contains complete data package, DO NOT SHARE',
                    value='full'
                )])],
    contexts=InteractionContextType.ALL(),
    integration_types=ApplicationIntegrationType.ALL())
async def slash_export(
    interaction: Interaction,
    format: str = 'importable'
) -> None:
    ...


@slash_command(
    name='help',
    description='get started with the bot',
    contexts=InteractionContextType.ALL(),
    integration_types=ApplicationIntegrationType.ALL())
async def slash_help(interaction: Interaction) -> None:
    ...


@slash_command(
    name='import',
    description='import data from /plu/ral, pluralkit, or tupperbox',
    options=[
        ApplicationCommandOption(
            type=ApplicationCommandOptionType.ATTACHMENT,
            name='file',
            description='file to import. 4MB max',
            required=False),
        ApplicationCommandOption(
            type=ApplicationCommandOptionType.STRING,
            name='file_url',
            description='url of your exported file. 4MB max',
            required=False)],
    contexts=InteractionContextType.ALL(),
    integration_types=ApplicationIntegrationType.ALL())
async def slash_import(
    interaction: Interaction,
    file: Attachment | None = None,
    file_url: str | None = None
) -> None:
    ...
