from __future__ import annotations
from pydantic import GetJsonSchemaHandler, GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from pydantic.json_schema import JsonSchemaValue
from typing import TypeVar, Union, Any, Literal
from enum import StrEnum


__all__ = (
    'Snowflake',
    'MISSING',
)


class _MissingType:
    def __bool__(self) -> Literal[False]:
        return False

    def __repr__(self) -> str:
        return "MISSING"

    def __copy__(self) -> _MissingType:
        return self

    def __deepcopy__(self, _: Any) -> _MissingType:
        return self

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.none_schema(),
            python_schema=core_schema.is_instance_schema(cls),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        _core_schema: CoreSchema,
        _handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        return {"type": "null"}


MISSING = _MissingType()

T = TypeVar('T')
MissingOr = Union[T, _MissingType]
MissingNoneOr = Union[T, None, _MissingType]


class Snowflake(int):
    # ? i stole this from the internet
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: type["Snowflake"] | None,
        _handler: GetJsonSchemaHandler,
    ) -> CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.int_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x),
                return_schema=core_schema.str_schema(),
            )
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        _core_schema: CoreSchema,
        _handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        return {'type': 'string', 'format': 'snowflake'}


class ListenerType(StrEnum):
    INTERACTION = 'INTERACTION'
    MESSAGE_CREATE = 'MESSAGE_CREATE'
    MESSAGE_UPDATE = 'MESSAGE_UPDATE'
    MESSAGE_REACTION_ADD = 'MESSAGE_REACTION_ADD'
