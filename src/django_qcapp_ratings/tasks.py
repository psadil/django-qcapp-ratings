import typing

from asgiref.sync import async_to_sync
from celery import shared_task

from django_qcapp_ratings import models, selectors


@shared_task
def run_db_query_async(
    step: int, related: str, key: str, last_pk: int | None = None
) -> dict[str, typing.Any]:
    if last_pk is None:
        image = async_to_sync(selectors.get_image_with_fewest_ratings)(
            step=models.Step(step), related=related, key=key
        )
    else:
        image = async_to_sync(selectors.get_image_pk_with_fewest_ratings)(
            step=models.Step(step), related=related, key=key, last_pk=last_pk
        )

    return image.to_dict()
