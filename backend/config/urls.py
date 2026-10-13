from django.urls import path, re_path

from config.views import spa
from trips.api import api

urlpatterns = [
    path("api/", api.urls),
    re_path(r"^(?!api/)(?P<path>.*)$", spa),
]
