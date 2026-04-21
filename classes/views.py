"""Admin-facing views for the Classes app. Public + instructor views land in Plan 2/3."""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Any, Callable

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from classes.forms import ClassOfferingForm
from classes.models import ClassOffering

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
    classes = ClassOffering.objects.select_related("instructor", "category").order_by("-created_at")
    return render(
        request,
        "classes/admin/classes_list.html",
        {
            "active_tab": "classes",
            "classes": classes,
            "pending_count": ClassOffering.objects.pending_review().count(),
        },
    )


@admin_required
def admin_class_create(request: HttpRequest) -> HttpResponse:
    form = ClassOfferingForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Class created.")
        return redirect("classes:admin_classes")
    return render(
        request,
        "classes/admin/class_form.html",
        {"active_tab": "classes", "form": form, "mode": "create"},
    )


@admin_required
def admin_class_edit(request: HttpRequest, pk: int) -> HttpResponse:
    offering = get_object_or_404(ClassOffering, pk=pk)
    form = ClassOfferingForm(request.POST or None, request.FILES or None, instance=offering)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Class updated.")
        return redirect("classes:admin_class_detail", pk=offering.pk)
    return render(
        request,
        "classes/admin/class_form.html",
        {"active_tab": "classes", "form": form, "offering": offering, "mode": "edit"},
    )


@admin_required
def admin_class_detail(request: HttpRequest, pk: int) -> HttpResponse:
    offering = get_object_or_404(ClassOffering, pk=pk)
    return render(
        request,
        "classes/admin/class_detail.html",
        {"active_tab": "classes", "offering": offering},
    )


@admin_required
def admin_class_approve(request: HttpRequest, pk: int) -> HttpResponse:
    offering = get_object_or_404(ClassOffering, pk=pk)
    offering.approve(request.user)
    messages.success(request, f"{offering.title} is published.")
    return redirect("classes:admin_class_detail", pk=offering.pk)


@admin_required
def admin_class_archive(request: HttpRequest, pk: int) -> HttpResponse:
    offering = get_object_or_404(ClassOffering, pk=pk)
    offering.archive()
    messages.success(request, f"{offering.title} archived.")
    return redirect("classes:admin_classes")


@admin_required
def admin_class_duplicate(request: HttpRequest, pk: int) -> HttpResponse:
    src = get_object_or_404(ClassOffering, pk=pk)
    src.pk = None
    src.slug = f"{src.slug}-copy"
    src.status = ClassOffering.Status.DRAFT
    src.published_at = None
    src.approved_by = None
    src.title = f"{src.title} (copy)"
    src.save()
    messages.success(request, "Class duplicated.")
    return redirect("classes:admin_class_edit", pk=src.pk)


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
