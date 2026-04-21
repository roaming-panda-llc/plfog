"""Admin-facing views for the Classes app. Public + instructor views land in Plan 2/3."""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Any, Callable

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render

if TYPE_CHECKING:
    pass

_ViewFunc = Callable[..., HttpResponse]


def admin_required(view_func: _ViewFunc) -> _ViewFunc:
    """Decorator: only admins (via request.view_as) may access."""

    @wraps(view_func)
    @login_required
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        view_as = getattr(request, "view_as", None)
        if view_as is None or not view_as.is_admin:
            return HttpResponseForbidden("Admin access required.")
        return view_func(request, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


@admin_required
def admin_root(request: HttpRequest) -> HttpResponse:
    return redirect("classes:admin_classes")


@admin_required
def admin_classes(request: HttpRequest) -> HttpResponse:
    return render(request, "classes/admin/classes_list.html", {"active_tab": "classes"})


@admin_required
def admin_categories(request: HttpRequest) -> HttpResponse:
    return render(request, "classes/admin/categories.html", {"active_tab": "categories"})


@admin_required
def admin_instructors(request: HttpRequest) -> HttpResponse:
    return render(request, "classes/admin/instructors.html", {"active_tab": "instructors"})


@admin_required
def admin_registrations(request: HttpRequest) -> HttpResponse:
    return render(request, "classes/admin/registrations.html", {"active_tab": "registrations"})


@admin_required
def admin_discount_codes(request: HttpRequest) -> HttpResponse:
    return render(request, "classes/admin/discount_codes.html", {"active_tab": "discount_codes"})


@admin_required
def admin_settings(request: HttpRequest) -> HttpResponse:
    return render(request, "classes/admin/settings.html", {"active_tab": "settings"})
