from typing import Any


def response(
    status: int,
    description: str,
    example: Any
) -> dict[str | int, dict]:
    return {
        status:
        {
            'description': description,
            'content':
            {
                'application/json':
                {
                    'example': example
                }
            }
        }
    }


def multi_response(
    status: int,
    description: str,
    examples: dict[str, Any]
) -> dict[str | int, dict]:
    """examples is a dictionary of example names and their values"""
    try:
        return {
            status:
            {
                'description': description,
                'content':
                {
                    'application/json':
                    {
                        'examples':
                        {
                            name:
                            {
                                'value': value
                            }
                            for name, value in examples.items()
                        }
                    }
                }
            }
        }
    except ValueError:
        print(examples)
        exit()


def file_response(
    content_type: str
) -> dict[str | int, dict]:
    return {
        content_type:
        {
            'schema':
            {
                'type': 'string',
                'format': 'binary',
                'example': 'binary file'
            }
        }
    }


def multi_file_response(
    status: int,
    description: str,
    content_types: list[str]
) -> dict[str | int, dict]:
    return {
        status:
        {
            'description': description,
            'content':
            {
                content_type:
                {
                    'schema':
                    {
                        'type': 'string',
                        'format': 'binary',
                        'example': 'binary file'
                    }
                }
                for content_type in content_types
            }
        }
    }
