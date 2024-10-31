from PIL.Image import Image, Resampling, open as pil_open
from warnings import catch_warnings, simplefilter
from discord import HTTPClient, StickerFormatType
from dataclasses import dataclass
from asyncio import to_thread
from os import mkdir, remove
from os.path import exists
from io import BytesIO


@dataclass(frozen=True)
class ProbableEmoji:
    name: str
    id: int
    animated: bool

    def __str__(self) -> str:
        return f'<{"a" if self.animated else ""}:{self.name}:{self.id}>'

    async def read(self, http: HTTPClient) -> bytes:
        return await http.get_from_cdn(
            f'https://cdn.discordapp.com/emojis/{self.id}.{"gif" if self.animated else "png"}')


@dataclass(frozen=True)
class ProbableSticker:
    name: str
    id: int
    format: StickerFormatType

    @property
    def filename(self) -> str:
        ext = self.format.file_extension if self.format != StickerFormatType.apng else 'gif'
        return f'{self.name}.{ext}'

    def _apng_to_gif(self, data: bytes) -> bytes:
        assert self.format == StickerFormatType.apng
        # ? figure something out to cache this later
        if not exists('.sticker_conversions'):
            mkdir('.sticker_conversions')

        file_path = f'.sticker_conversions/{self.id}'

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
                    fp=f'{file_path}.gif',
                    save_all=True,
                    append_images=resized_frames[1:]
                )

        with open(f'{file_path}.gif', 'rb') as f:
            new_data = f.read()

        remove(f'{file_path}.gif')

        return new_data

    async def read(self, http: HTTPClient) -> bytes:
        if self.format == StickerFormatType.lottie:
            raise ValueError('Lottie stickers are not supported')

        data = await http.get_from_cdn(
            f'https://cdn.discordapp.com/stickers/{self.id}.{self.format.file_extension}')

        if self.format != StickerFormatType.apng:
            return data

        return await to_thread(self._apng_to_gif, data)
