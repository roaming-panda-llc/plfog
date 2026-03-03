from django.conf import settings as django_settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("core.urls")),
]

try:
    urlpatterns += [path("stripe/", include("djstripe.urls", namespace="djstripe"))]
except Exception:  # pragma: no cover
    pass

if django_settings.DEBUG:  # pragma: no cover
    urlpatterns += static(django_settings.MEDIA_URL, document_root=django_settings.MEDIA_ROOT)  # type: ignore[arg-type]
