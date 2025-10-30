import base64
import dataclasses
import logging
import typing

from celery import result
from django import http
from django.db import models as dm

from django_qcapp_ratings import models

TASK_TIMEOUT_SEC = 30


@dataclasses.dataclass
class ImageResult:
    id: int
    step: models.Step
    img: bytes

    @property
    def img_type(self) -> str:
        match self.step:
            case (
                models.Step.MASK
                | models.Step.SPATIAL_NORMALIZATION
                | models.Step.SURFACE_LOCALIZATION
            ):
                related = "png"
            case models.Step.FMAP_COREGISTRATION | models.Step.DTIFIT:
                related = "gif"
            case _:
                raise AssertionError("Unknown step")
        return related

    @property
    def img_decoded(self) -> str:
        return base64.b64encode(self.img).decode()


def get_related_from_step(step: models.Step) -> str:
    match step:
        case (
            models.Step.MASK
            | models.Step.SPATIAL_NORMALIZATION
            | models.Step.SURFACE_LOCALIZATION
        ):
            related = "clickedcoordinate"
        case _:
            related = "rating"
    return related


async def get_img_id(request: http.HttpRequest) -> ImageResult:
    logging.info("looking for img task")
    img_task = await request.session.aget("img_task")
    if img_task is None:
        raise http.Http404("no img_task found")
    res = result.AsyncResult(img_task)

    logging.info(f"getting results of {res=}")
    img: dict[str, typing.Any] = res.get(timeout=TASK_TIMEOUT_SEC)

    return ImageResult(**img)


async def get_image_with_fewest_ratings(
    step: models.Step, last_pk: int | None = None, key: str = "source_data_issue"
) -> models.Image:
    related = get_related_from_step(step)

    # select scan with fewest ratings
    scan_query = models.Image.objects.filter(step=step.value)
    if last_pk is not None:
        # get file1 from previous image
        last_img_q = (
            await models.Image.objects.filter(pk=last_pk).values("file1").afirst()
        )
        if last_img_q is None:
            raise ValueError("Unable to find file1 of last img")
        scan_query = scan_query.exclude(file1__in=[last_img_q.get("file1")])
    file1 = await (
        scan_query.values("file1")
        .annotate(n_ratings=dm.Count(f"{related}__{key}"))
        .order_by("n_ratings")
        .afirst()
    )
    if file1 is None:
        raise ValueError("No scan found")

    # select image from scan with fewest ratings
    image_query = models.Image.objects.filter(file1=file1.get("file1"))
    if last_pk is not None:
        image_query = image_query.exclude(id__in=[last_pk])

    image = await (
        image_query.values("id")
        .annotate(n_ratings=dm.Count(f"{related}__{key}"))
        .order_by("n_ratings")
        .afirst()
    )
    if image is None:
        raise ValueError("No image found")

    return await models.Image.objects.aget(pk=image.get("id"))
