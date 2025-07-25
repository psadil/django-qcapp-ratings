from django import forms

from django_qcapp_ratings import models


class RatingForm(forms.ModelForm):
    class Meta:
        model = models.Rating
        fields = ["rating", "source_data_issue", "comments"]
        widgets = {"rating": forms.RadioSelect}


class IndexForm(forms.ModelForm):
    class Meta:
        model = models.Session
        fields = ["step"]


class ClickForm(forms.ModelForm):
    class Meta:
        model = models.ClickedCoordinate
        fields = ["source_data_issue", "comments"]
