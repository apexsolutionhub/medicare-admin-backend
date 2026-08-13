"""
URL configuration for pharmacy-admin Apex console.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/apex/", include("apex.urls")),
    path("api/tenants/", include("tenants.urls")),
]
