from django.urls import path

from .views import ApexLoginView, ApexMeView

urlpatterns = [
    path("auth/login/", ApexLoginView.as_view(), name="apex-login"),
    path("me/", ApexMeView.as_view(), name="apex-me"),
]
