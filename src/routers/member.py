from src.core.models.member import MemberModel, MemberUpdateModel
from src.core.auth import api_key_validator, TokenData
from fastapi import HTTPException, Security, APIRouter
from fastapi.responses import JSONResponse
from src.db import ProxyMember, Group, Image
from src.docs import member as docs
from beanie import PydanticObjectId
from asyncio import gather

router = APIRouter(prefix='/member', tags=['Member'])


@router.get(
    '/{member_id}',
    response_model=MemberModel,
    responses=docs.get__member)
async def get__member(
    member_id: PydanticObjectId,
    token: TokenData = Security(api_key_validator)
) -> JSONResponse:
    member = await ProxyMember.find_one({'_id': member_id})

    if member is None or token.user_id not in (await member.get_group()).accounts:
        raise HTTPException(404, 'member not found')

    return JSONResponse(
        content=member.model_dump_json()
    )


@router.patch(
    '/{member_id}',
    response_model=MemberModel,
    responses=docs.patch__member)
async def patch__member(
    member_id: PydanticObjectId,
    patch: MemberUpdateModel,
    token: TokenData = Security(api_key_validator)
) -> JSONResponse:
    member = await ProxyMember.find_one({'_id': member_id})
    tasks = []

    if member is None or token.user_id not in (await member.get_group()).accounts:
        raise HTTPException(404, 'member not found')

    for field in patch.model_fields_set:
        match field:
            case 'name':
                group = await member.get_group()
                if await group.get_member_by_name(patch.name) is not None:
                    raise HTTPException(
                        400, f'member {patch.name} already exists')

                if group.tag and (len_sum := len(patch.name+group.tag)) > 80:
                    raise HTTPException(
                        400, f'name and group tag combined must be less than 80 characters ({len_sum}/80)')

                member.name = patch.name
            case 'avatar':
                image = await Image.find_one({'_id': patch.avatar})

                if image is None:
                    raise HTTPException(404, 'avatar not found')

                member.avatar = patch.avatar
            case 'group':
                current_group = await member.get_group()
                new_group = await Group.find_one({'_id': patch.group})

                if new_group is None or token.user_id not in new_group.accounts:
                    raise HTTPException(404, 'group not found')

                if current_group.id != new_group.id:
                    current_group.members.remove(member.id)
                    new_group.members.add(member.id)

                    tasks.append(current_group.save_changes())
                    tasks.append(new_group.save_changes())
            case 'proxy_tags':
                member.proxy_tags = patch.proxy_tags
            case _:
                raise HTTPException(400, f'invalid field: {field}')

    tasks.append(member.save_changes())

    await gather(*tasks)

    return JSONResponse(
        content=member.model_dump_json()
    )


@router.delete(
    '/{member_id}',
    responses=docs.delete__member)
async def delete__member(
    member_id: PydanticObjectId,
    token: TokenData = Security(api_key_validator)
) -> JSONResponse:
    member = await ProxyMember.find_one({'_id': member_id})

    if member is None or token.user_id not in (group := await member.get_group()).accounts:
        raise HTTPException(404, 'member not found')

    group.members.discard(member.id)

    await gather(
        member.delete(),
        group.save_changes()
    )

    return JSONResponse(
        content={
            'message': f'member {member.name} of group {group.name} successfully deleted'
        }
    )
