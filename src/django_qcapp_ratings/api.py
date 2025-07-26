import base64

import orjson
from django import http, shortcuts
from ninja import FilterSchema, ModelSchema, NinjaAPI, Query, Schema, parser, renderers

from django_qcapp_ratings import models


class ORJSONParser(parser.Parser):
    def parse_body(self, request):
        return orjson.loads(request.body)


class ORJSONRenderer(renderers.BaseRenderer):
    media_type = "application/json"

    def render(self, request, data, *, response_status):
        return orjson.dumps(data)


# API instance
api = NinjaAPI(
    title="QC App Ratings API",
    version="1.0.0",
    renderer=ORJSONRenderer(),
    parser=ORJSONParser(),
)


class ImageSchema(ModelSchema):
    img: str

    class Meta:
        model = models.Image
        fields = ["id", "slice", "file1", "file2", "display", "step", "created", "img"]
        fields_optional = ["created", "slice", "file2", "display", "step"]


class ImageResponseSchema(ModelSchema):
    img: str

    class Meta:
        model = models.Image
        fields = ["id", "created"]


class DeleteResponseSchema(Schema):
    success: bool
    message: str


class StepFilter(FilterSchema):
    name: models.Step | None = None


# Endpoints
@api.post("/image/", response=ImageResponseSchema)
def create_image(request: http.HttpRequest, payload: ImageSchema):
    """Create a single image"""
    image = models.Image.objects.create(**payload.dict())
    return {"id": image.pk, "created": image.created}


@api.delete("/image/{image_id}/", response=DeleteResponseSchema)
def delete_image(request: http.HttpRequest, image_id: int):
    """Delete a single image by ID"""
    image = shortcuts.get_object_or_404(models.Image, id=image_id)
    image.delete()
    return {"success": True, "message": f"Image {image_id} deleted successfully"}


@api.get("/images/", response=list[ImageSchema])
def list_images(
    request: http.HttpRequest,
    filters: StepFilter = Query(...),  # type: ignore
    limit: int = 100,
):
    """List images with optional filtering by step"""
    images = filters.filter(models.Image.objects.all())[:limit]

    return [
        {
            "id": image.pk,
            "slice": image.slice,
            "file1": image.file1,
            "file2": image.file2,
            "display": image.display,
            "step": image.step,
            "created": image.created,
            "img": base64.b64encode(image.img).decode(),
        }
        for image in images
    ]


@api.get("/image/{image_id}/", response=ImageSchema)
def get_image(request: http.HttpRequest, image_id: int):
    """Get a single image by ID"""
    image = shortcuts.get_object_or_404(models.Image, id=image_id)
    return {
        "id": image.pk,
        "slice": image.slice,
        "file1": image.file1,
        "file2": image.file2,
        "display": image.display,
        "step": image.step,
        "created": image.created,
        "img": base64.b64encode(image.img).decode(),
    }
