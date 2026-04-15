from django.urls import path

from . import views

urlpatterns = [
    path("guilds/voting/", views.guild_voting, name="hub_guild_voting"),
    path("guilds/voting/history/", views.snapshot_history, name="hub_snapshot_history"),
    path("guilds/voting/history/<int:pk>/", views.snapshot_detail, name="hub_snapshot_detail"),
    path("members/", views.member_directory, name="hub_member_directory"),
    path("guilds/<int:pk>/", views.guild_detail, name="hub_guild_detail"),
    path("guilds/<int:pk>/edit/", views.guild_edit, name="hub_guild_edit"),
    path("guilds/<int:pk>/cart/confirm/", views.guild_cart_confirm, name="hub_guild_cart_confirm"),
    path("guilds/<int:pk>/eyop-form/", views.guild_eyop_form, name="hub_guild_eyop_form"),
    path(
        "guilds/<int:pk>/products/add/",
        views.guild_product_create,
        name="hub_guild_product_create",
    ),
    path(
        "guilds/<int:pk>/products/<int:product_pk>/edit/",
        views.guild_product_update,
        name="hub_guild_product_update",
    ),
    path(
        "guilds/<int:pk>/products/<int:product_pk>/delete/",
        views.guild_product_delete,
        name="hub_guild_product_delete",
    ),
    path("settings/profile/", views.profile_settings, name="hub_profile_settings"),
    path("settings/emails/", views.email_preferences, name="hub_email_preferences"),
    path("feedback/", views.beta_feedback, name="hub_beta_feedback"),
    path("tab/", views.tab_detail, name="hub_tab_detail"),
    path("tab/history/", views.tab_history, name="hub_tab_history"),
    path("tab/void/<int:entry_pk>/", views.void_tab_entry, name="hub_void_tab_entry"),
]
