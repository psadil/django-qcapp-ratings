from django.contrib import admin

from . import models

# @admin.register(models.Rating)
# class RatingAdmin(admin.ModelAdmin):
#     @admin.action(description="Download all ratings")
#     def download_view(self, request):
#         """Redirects to the API endpoint for downloading ratings"""
#         # The default name for the NinjaAPI instance is "api-1.0.0"
#         api_url = urls.reverse("api-1.0.0:list_ratings")
#         return shortcuts.redirect(api_url)


admin.site.register(
    [models.Image, models.Rating, models.Session, models.ClickedCoordinate]
)
