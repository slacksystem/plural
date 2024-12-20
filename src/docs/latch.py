from src.docs.responses import response, multi_response


get__latch = {
    **response(
        status=200,
        description='latch found',
        example={
            'user': 250797109022818305,
            'guild': 844127424526680084,
            'enabled': True,
            'member': '67018b8f74900a4cd323555a'
        }
    ),
    **response(
        status=404,
        description='latch not found',
        example={
            'detail': 'latch not found'
        }
    )
}

patch__latch = {
    **response(
        status=200,
        description='latch updated, returns updated latch',
        example={
            'user': 250797109022818305,
            'guild': 844127424526680084,
            'enabled': True,
            'member': '67018b8f74900a4cd323555a'
        }
    ),
    **multi_response(
        status=404,
        description='latch or member not found',
        examples={
            'latch': {
                'detail': 'latch not found'
            },
            'member': {
                'detail': 'member not found'
            }
        }
    ),
    **response(
        status=400,
        description='invalid field',
        example={
            'detail': 'invalid field: invalid_field'
        }
    )
}


post__latch = {
    **response(
        status=200,
        description='latch created, returns created latch',
        example={
            'user': 250797109022818305,
            'guild': 844127424526680084,
            'enabled': True,
            'member': '67018b8f74900a4cd323555a'
        }
    ),
    **response(
        status=400,
        description='latch already exists',
        example={
            'detail': 'latch already exists'
        }
    ),
    **response(
        status=404,
        description='member not found',
        example={
            'detail': 'member not found'
        }
    )
}


put__latch = {
    **response(
        status=200,
        description='latch updated / created, returns latch',
        example={
            'user': 250797109022818305,
            'guild': 844127424526680084,
            'enabled': True,
            'member': '67018b8f74900a4cd323555a'
        }
    ),
    **response(
        status=404,
        description='member not found',
        example={
            'detail': 'member not found'
        }
    )
}
