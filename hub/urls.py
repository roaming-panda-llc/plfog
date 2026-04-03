from django.urls import path

from . import views

urlpatterns = [
    path("guilds/voting/", views.guild_voting, name="hub_guild_voting"),
    path("guilds/voting/history/", views.snapshot_history, name="hub_snapshot_history"),
    path("guilds/voting/history/<int:pk>/", views.snapshot_detail, name="hub_snapshot_detail"),
    path("members/", views.member_directory, name="hub_member_directory"),
    path("guilds/<int:pk>/", views.guild_detail, name="hub_guild_detail"),
    path("guilds/<int:pk>/edit/", views.guild_edit, name="hub_guild_edit"),
    path("guilds/<int:pk>/products/<int:product_pk>/edit/", views.guild_product_edit, name="hub_guild_product_edit"),
    path("guilds/<int:pk>/products/<int:product_pk>/remove/", views.guild_product_remove, name="hub_guild_product_remove"),
    path("settings/profile/", views.profile_settings, name="hub_profile_settings"),
    path("settings/emails/", views.email_preferences, name="hub_email_preferences"),
    path("feedback/", views.beta_feedback, name="hub_beta_feedback"),
    path("tab/", views.tab_detail, name="hub_tab_detail"),
    path("tab/history/", views.tab_history, name="hub_tab_history"),
]
