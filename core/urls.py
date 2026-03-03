from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health_check, name="health_check"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("", views.home, name="home"),
]
