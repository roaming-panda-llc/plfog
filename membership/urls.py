from django.urls import path

from . import views

urlpatterns = [
    path("", views.guild_list, name="guild_list"),
    path("<slug:slug>/", views.guild_detail, name="guild_detail"),
]
