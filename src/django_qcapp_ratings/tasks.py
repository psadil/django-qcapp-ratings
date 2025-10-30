import typing

import celery
from asgiref import sync

from django_qcapp_ratings import models, selectors


@celery.shared_task
def run_db_query_async(step: int, last_pk: int | None = None) -> dict[str, typing.Any]:
    image = sync.async_to_sync(selectors.get_image_with_fewest_ratings)(
        step=models.Step(step), last_pk=last_pk
    )

    return image.to_dict()
