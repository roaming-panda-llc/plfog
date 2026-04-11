from django.contrib import admin
from django.urls import include, path

from plfog.admin_views import (
    invite_member,
    snapshot_delete,
    snapshot_detail,
    snapshot_draft,
    snapshot_take,
)

# Custom admin URLs must be before admin.site.urls
admin_custom_urls = [
    path("admin/membership/member/invite/", invite_member, name="admin_invite_member"),
    path("admin/snapshots/draft/", snapshot_draft, name="admin_snapshot_draft"),
    path("admin/snapshots/take/", snapshot_take, name="admin_snapshot_take"),
    path("admin/snapshots/<int:pk>/", snapshot_detail, name="admin_snapshot_detail"),
    path("admin/snapshots/<int:pk>/delete/", snapshot_delete, name="admin_snapshot_delete"),
]

urlpatterns = admin_custom_urls + [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("billing/", include("billing.urls")),
    # Member hub
    path("", include("hub.urls")),
    path("", include("core.urls")),
]
