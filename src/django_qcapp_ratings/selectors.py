from django import http
from django.db import models as dm

from django_qcapp_ratings import models


async def get_image_with_fewest_ratings(
    step: models.Step, related: str, key: str
) -> models.Image:
    image = await (
        models.Image.objects.filter(step=step.value)
        .select_related(related)
        .values("id")
        .annotate(n_ratings=dm.Count(f"{related}__{key}"))
        .order_by("n_ratings")
        .afirst()
    )
    if image is None:
        raise http.Http404("No image found.")

    return await models.Image.objects.aget(pk=image.get("id"))
