from PIL.Image import Image, Resampling, open as pil_open
from warnings import catch_warnings, simplefilter
from .enums import StickerType, StickerFormatType
from src.discord.http import get_from_cdn, File
from src.discord.types import Snowflake
from src.models import project
from .base import RawBaseModel
from asyncio import to_thread
from logfire import span
from io import BytesIO
from .user import User


__all__ = (
    'StickerItem',
    'Sticker',
)


class StickerItem(RawBaseModel):
    id: Snowflake
    name: str
    format_type: StickerFormatType

    @property  # ! reconsider this
    def filename(self) -> str:
        ext = self.format_type.file_extension if self.format_type != StickerFormatType.APNG else 'gif'
        return f'{self.name}.{ext}'

    def _apng_to_gif(self, data: bytes) -> bytes:
        output = BytesIO()

        with pil_open(BytesIO(data)) as img:
            resized_frames: list[Image] = []

            for frame in range(getattr(img, 'n_frames', 1)):
                img.seek(frame)
                resized_frames.append(
                    img.convert('RGB').resize(
                        (160, 160),
                        resample=Resampling.LANCZOS
                    )
                )
            with catch_warnings():
                # ? because of palleting nonsense, PIL warns "Couldn't allocate palette entry for transparency"
                simplefilter('ignore')
                resized_frames[0].save(
                    fp=output,
                    format='gif',
                    save_all=True,
                    append_images=resized_frames[1:],
                    disposal=2
                )

        return output.getvalue()

    async def read(self) -> bytes:
        if self.format_type == StickerFormatType.LOTTIE:
            raise ValueError('Lottie stickers are not supported')

        data = await get_from_cdn(
            f'https://cdn.discordapp.com/stickers/{self.id}.{self.format_type.file_extension}')

        if self.format_type != StickerFormatType.APNG:
            return data

        if project.logfire_token:
            with span('Converting apng to gif', token=project.logfire_token):
                return await to_thread(self._apng_to_gif, data)

        return await to_thread(self._apng_to_gif, data)

    async def as_file(self) -> File:
        return File(
            BytesIO(await self.read()),
            filename=self.filename,
            description=getattr(self, 'description', None),
            spoiler=False
        )


class Sticker(StickerItem):
    id: Snowflake
    pack_id: Snowflake | None = None
    name: str
    description: str | None = None
    tags: str | None = None
    type: StickerType
    format_type: StickerFormatType
    available: bool | None = None
    guild_id: Snowflake | None = None
    user: User | None = None
    sort_value: int | None = None