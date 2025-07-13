import abc
import base64
import logging
import zlib

from django import http, shortcuts, urls, views
from django.db import models as dm
from django.views.generic import edit

from . import forms, models

MASK_VIEW = "mask"
SPATIAL_NORMALIZATION_VIEW = "spatial_normalization"
SURFACE_LOCALIZATION_VIEW = "surface_localization"
FMAP_COREGISTRATION_VIEW = "fmap_coregistration"
DTIFIT_VIEW = "dtifit"


def is_likely_zlib_compressed(data: bytes) -> bool:
    """
    Checks if the given bytes data *likely* starts with a zlib header.
    This is a heuristic and not 100% foolproof for all deflate variants,
    but covers common zlib and gzip streams.
    """
    if len(data) < 2:
        return False  # Zlib and Gzip headers are at least 2 bytes

    # Common zlib header bytes (CMF and FLG)
    # CMF: Compression Method and FLaGs.
    # CM = 8 (DEFLATE), CINFO = 7 (32KB window size) -> CMF = 0x78
    # FLG: FLaGs (FCHECK, FDICT, FLEVEL)
    # Common FLaG values (e.g., 0x01, 0x9C, 0xDA, etc. where FCHECK is divisible by 31)
    # The combination 0x78 0xDA is very common (CM=8, CINFO=7, FCHECK=21, FDICT=0, FLEVEL=2)
    # Other common: 0x78 0x01, 0x78 0x9C, 0x78 0xBB etc.
    # The decompressor handles the full range, but we can check for common starting bytes.
    if data[0] == 0x78 and data[1] in {0x01, 0x9C, 0xDA, 0xBB}:
        return True

    # Gzip header (ID1, ID2)
    # Gzip starts with 0x1F 0x8B
    if data[0] == 0x1F and data[1] == 0x8B:
        return True

    return False


def decompress_if_needed(data: bytes) -> bytes:
    """
    Decompresses the data if it's likely zlib/gzip compressed based on header check,
    otherwise returns the original data. If a decompression error occurs after
    a header check, it falls back to returning the original data.
    """
    if is_likely_zlib_compressed(data):
        try:
            # Attempt to decompress. Duck typing will handle zlib/gzip based on headers.
            # windowBits=32+15 for auto-detection of zlib and gzip headers.
            # Using wbits=MAX_WBITS will auto-detect gzip or zlib header.
            return zlib.decompress(data, wbits=zlib.MAX_WBITS)
        except zlib.error as e:
            # If it looked like zlib but decompression failed, it might be corrupted
            # or a very unusual deflate stream without a standard header that zlib can't immediately handle.
            print(f"Decompression failed even though header suggested zlib/gzip: {e}")
            return data  # Fallback to original data
    return data


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
        logging.info("setting next")
        img = await _get_mask_with_fewest_ratings(
            self.step, related=self.related, key=self.key
        )
        await request.session.aset("image_id", img.pk)  # type: ignore
        logging.info("rendering")
        logging.info(img.pk)
        data = decompress_if_needed(img.img)
        return shortcuts.render(
            request,
            template,
            {
                "form": self.form_class(),
                "image": f"data:image/{self.img_type};base64,{base64.b64encode(data).decode()}",
            },
        )

    async def get_main(self, request: http.HttpRequest) -> http.HttpResponse:
        return await self._get(request=request, template=self.main_template)

    async def get(self, request: http.HttpRequest) -> http.HttpResponse:
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


async def _get_mask_with_fewest_ratings(
    step: models.Step, related: str, key: str
) -> models.Image:
    masks_in_layout = await (
        models.Image.objects.filter(step=step.value)
        .select_related(related)
        .values("id")
        .annotate(n_ratings=dm.Count(f"{related}__{key}"))
        .order_by("n_ratings")
        .afirst()
    )
    if masks_in_layout is None:
        raise http.Http404("No masks in layout")

    return await models.Image.objects.aget(pk=masks_in_layout.get("id"))
