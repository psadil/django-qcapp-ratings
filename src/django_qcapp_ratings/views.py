import abc
import base64
import logging
import typing

from celery import result
from celery.exceptions import TimeoutError
from django import http, shortcuts, urls, views
from django.views.generic import edit

from django_qcapp_ratings import forms, models, tasks

MASK_VIEW = "mask"
SPATIAL_NORMALIZATION_VIEW = "spatial_normalization"
SURFACE_LOCALIZATION_VIEW = "surface_localization"
FMAP_COREGISTRATION_VIEW = "fmap_coregistration"
DTIFIT_VIEW = "dtifit"

IMG_TASK = "img_task"
TASK_TIMEOUT_SEC = 20


# note: not a FormView because the (dynamic) image cannot be placed in form
class RateView(abc.ABC, views.View):
    template_name = "rate_image.html"
    form_class = forms.RatingForm
    main_template = "main.html"
    related = "rating"
    key = "source_data_issue"
    img_type = "png"

    @property
    @abc.abstractmethod
    def step(self) -> models.Step:
        raise NotImplementedError

    async def _get(self, request: http.HttpRequest, template: str) -> http.HttpResponse:
        logging.info("looking for img task")
        img_task = await request.session.aget(IMG_TASK)  # type: ignore
        if img_task is None:
            raise http.Http404("no img_task found")
        res = result.AsyncResult(img_task)
        logging.info(f"{res=}")

        logging.info("getting results of img task")
        try:
            img: dict[str, typing.Any] = res.get(timeout=TASK_TIMEOUT_SEC)  # type: ignore
        except TimeoutError:
            raise http.Http404(
                "There has been an issue. Please return to the homepage."
            )

        img_id = img.get("id")
        if img_id is None:
            raise http.Http404("task seems to have failed")

        logging.info("starting img_next task")
        img_task = tasks.run_db_query_async.delay(  # type: ignore
            step=self.step, related=self.related, key=self.key, last_pk=img_id
        )
        await request.session.aset(IMG_TASK, img_task.id)  # type: ignore

        await request.session.aset("image_id", img_id)  # type: ignore
        logging.info(f"rendering {img_id}")
        return shortcuts.render(
            request,
            template,
            {
                "form": self.form_class(),
                "image": f"data:image/{self.img_type};base64,{base64.b64encode(img.get("img", "")).decode()}",
            },
        )

    async def get_main(self, request: http.HttpRequest) -> http.HttpResponse:
        return await self._get(request=request, template=self.main_template)

    async def get(self, request: http.HttpRequest) -> http.HttpResponse:
        logging.info("getting first img")
        img_task = tasks.run_db_query_async.delay(  # type: ignore
            step=self.step, related=self.related, key=self.key
        )

        logging.info("updating session")
        await request.session.aset(IMG_TASK, img_task.id)  # type: ignore

        return await self._get(request=request, template=self.template_name)

    async def post(self, request: http.HttpRequest) -> http.HttpResponse:
        form = self.form_class(request.POST)
        if form.is_valid():
            logging.info("saving rating")

            # rating = sync.sync_to_async(form.save)()

            await self.form_class.Meta.model.from_request_form(
                request=request, form=form
            )

            return await self.get_main(request)

        raise http.Http404("Submitted invalid rating")


class ClickView(RateView):
    template_name = "click.html"
    main_template = "click_canvas.html"
    form_class = forms.ClickForm
    related = "clickedcoordinate"


class RateMask(ClickView):
    @property
    def step(self) -> models.Step:
        return models.Step.MASK


class RateSpatialNormalization(ClickView):
    @property
    def step(self) -> models.Step:
        return models.Step.SPATIAL_NORMALIZATION


class RateSurfaceLocalization(ClickView):
    @property
    def step(self) -> models.Step:
        return models.Step.SURFACE_LOCALIZATION


class RateFMapCoregistration(RateView):
    img_type = "gif"

    @property
    def step(self) -> models.Step:
        return models.Step.FMAP_COREGISTRATION


class RateDTIFIT(RateView):
    img_type = "gif"

    @property
    def step(self) -> models.Step:
        return models.Step.DTIFIT


class LayoutView(edit.FormView):
    template_name = "index.html"
    form_class = forms.IndexForm

    def get_success_url(self):
        match self.request.session.get("step"):
            case models.Step.MASK:
                return urls.reverse(f"{MASK_VIEW}")
            case models.Step.SPATIAL_NORMALIZATION:
                return urls.reverse(f"{SPATIAL_NORMALIZATION_VIEW}")
            case models.Step.SURFACE_LOCALIZATION:
                return urls.reverse(f"{SURFACE_LOCALIZATION_VIEW}")
            case models.Step.FMAP_COREGISTRATION:
                return urls.reverse(f"{FMAP_COREGISTRATION_VIEW}")
            case models.Step.DTIFIT:
                return urls.reverse(f"{DTIFIT_VIEW}")
            case _:
                raise http.Http404("Unknown step")

    def form_valid(self, form: forms.IndexForm):
        form.instance.user = self.request.COOKIES.get("X-Tapis-Username")
        session = form.save()
        self.request.session["session_id"] = session.pk
        self.request.session["step"] = session.step
        return super().form_valid(form)
