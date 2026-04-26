"""Views for the Classes app — admin tabs, public portal, instructor profile pages."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Min, Q
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from classes.forms import (
    CategoryForm,
    ClassOfferingForm,
    ClassSessionFormSet,
    ClassSettingsForm,
    DiscountCodeForm,
    InstructorClassOfferingForm,
    InstructorProfileForm,
    PromoteUserToInstructorForm,
)
from classes.models import Category, ClassOffering, ClassSettings, DiscountCode, Instructor, Registration
from core.models import SiteConfiguration

_ViewFunc = Callable[..., HttpResponse]


def _browsable_classes() -> Any:
    """Published, non-private classes annotated with first upcoming session date.

    Classes without any upcoming sessions are hidden unless they use flexible
    scheduling. Ordered by category sort, then soonest upcoming session.
    """
    now = timezone.now()
    return (
        ClassOffering.objects.public()
        .select_related("category", "instructor")
        .prefetch_related("sessions")
        .annotate(first_session_at=Min("sessions__starts_at", filter=Q(sessions__starts_at__gte=now)))
        .filter(Q(first_session_at__isnull=False) | Q(scheduling_model=ClassOffering.SchedulingModel.FLEXIBLE))
        .order_by("category__sort_order", "category__name", "first_session_at", "title")
    )


def public_list(request: HttpRequest) -> HttpResponse:
    """Public portal — hero + sticky category filter + grouped class cards."""
    settings_obj = ClassSettings.load()
    selected_category_slug = request.GET.get("category", "").strip()
    classes_qs = _browsable_classes()
    if selected_category_slug:
        classes_qs = classes_qs.filter(category__slug=selected_category_slug)
    classes = list(classes_qs)
    # Category chips show only categories with at least one browsable class.
    category_counts: dict[int, int] = {}
    for offering in _browsable_classes():
        category_counts[offering.category_id] = category_counts.get(offering.category_id, 0) + 1
    categories = [cat for cat in Category.objects.all() if category_counts.get(cat.id)]
    for cat in categories:
        cat.class_count = category_counts[cat.id]  # type: ignore[attr-defined]
    # Group classes by category for the rendered sections.
    grouped: dict[int, dict[str, Any]] = {}
    for offering in classes:
        bucket = grouped.setdefault(offering.category_id, {"category": offering.category, "classes": []})
        bucket["classes"].append(offering)
    category_sections = [grouped[cat.id] for cat in categories if cat.id in grouped]
    distinct_instructor_ids = {offering.instructor_id for offering in classes}
    return render(
        request,
        "classes/public/list.html",
        {
            "settings_obj": settings_obj,
            "site_config": SiteConfiguration.load(),
            "categories": categories,
            "selected_category_slug": selected_category_slug,
            "category_sections": category_sections,
            "total_classes": len(classes),
            "total_instructors": len(distinct_instructor_ids),
            "total_categories": len(categories),
        },
    )


def public_category(request: HttpRequest, slug: str) -> HttpResponse:
    """Public category landing — same layout as list, pre-filtered."""
    category = get_object_or_404(Category, slug=slug)
    request.GET = request.GET.copy()
    request.GET["category"] = category.slug
    return public_list(request)


def public_class_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """Full class detail page — schedule, info grid, (future: registration form)."""
    offering = get_object_or_404(
        ClassOffering.objects.public().select_related("category", "instructor").prefetch_related("sessions"),
        slug=slug,
    )
    settings_obj = ClassSettings.load()
    member_price_cents = None
    if offering.member_discount_pct:
        member_price_cents = int(offering.price_cents * (100 - offering.member_discount_pct) / 100)
    upcoming_sessions = list(offering.sessions.filter(starts_at__gte=timezone.now()).order_by("starts_at"))
    return render(
        request,
        "classes/public/detail.html",
        {
            "offering": offering,
            "settings_obj": settings_obj,
            "site_config": SiteConfiguration.load(),
            "upcoming_sessions": upcoming_sessions,
            "member_price_cents": member_price_cents,
            "spots_remaining": offering.spots_remaining,
        },
    )


def public_instructor(request: HttpRequest, slug: str) -> HttpResponse:
    """Public instructor profile — bio, photo, current + past classes."""
    instructor = get_object_or_404(Instructor, slug=slug, is_active=True)
    now = timezone.now()
    current_classes = (
        ClassOffering.objects.public()
        .filter(instructor=instructor)
        .prefetch_related("sessions")
        .annotate(first_session_at=Min("sessions__starts_at", filter=Q(sessions__starts_at__gte=now)))
        .filter(Q(first_session_at__isnull=False) | Q(scheduling_model=ClassOffering.SchedulingModel.FLEXIBLE))
        .order_by("first_session_at", "title")
    )
    past_classes = (
        ClassOffering.objects.filter(instructor=instructor, status=ClassOffering.Status.ARCHIVED)
        .select_related("category")
        .order_by("-updated_at")
    )
    return render(
        request,
        "classes/public/instructor.html",
        {
            "instructor": instructor,
            "current_classes": current_classes,
            "past_classes": past_classes,
            "settings_obj": ClassSettings.load(),
            "site_config": SiteConfiguration.load(),
        },
    )


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


def instructor_required(view_func: _ViewFunc) -> _ViewFunc:
    """Decorator: Teaching portal access.

    Active instructors pass through. Admins without an Instructor record get
    bounced to the Classes admin Instructors tab — they have a superset view
    over there, and the Teaching portal is per-instructor so there's no
    meaningful admin-scoped equivalent.
    """

    @wraps(view_func)
    @login_required
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        instructor = Instructor.objects.filter(user=request.user, is_active=True).first()
        if instructor is None:
            view_as = getattr(request, "view_as", None)
            if view_as is not None and view_as.has_actual("admin"):
                messages.info(
                    request,
                    "You don't have an Instructor profile — manage instructors here instead.",
                )
                return redirect("classes:admin_instructors")
            return HttpResponseForbidden("Instructor access required.")
        request.instructor = instructor  # type: ignore[attr-defined]
        return view_func(request, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def classes_admin_access_required(view_func: _ViewFunc) -> _ViewFunc:
    """Decorator: Classes admin tabs are admin-only.

    Authorization checks the user's *actual* admin role (not the view-as
    preview) so an admin previewing as Instructor/Guest still reaches the
    admin pages when they navigate back. Instructors manage their own
    discount codes and registrations from the Teaching portal instead.
    """

    @wraps(view_func)
    @login_required
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        view_as = getattr(request, "view_as", None)
        if view_as is None or not view_as.has_actual("admin"):
            return HttpResponseForbidden("Classes admin access requires admin privileges.")
        return view_func(request, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


@instructor_required
def instructor_dashboard(request: HttpRequest) -> HttpResponse:
    """My classes — list view for the logged-in instructor."""
    instructor: Instructor = request.instructor  # type: ignore[attr-defined]
    classes = (
        ClassOffering.objects.for_instructor(instructor)
        .select_related("category")
        .annotate(registration_count=Count("registrations"))
        .order_by("-created_at")
    )
    return render(
        request,
        "classes/instructor/classes_list.html",
        {
            "active_tab": "classes",
            "instructor": instructor,
            "classes": classes,
        },
    )


def _render_instructor_class_form(
    request: HttpRequest,
    *,
    form: InstructorClassOfferingForm,
    formset: Any,
    instructor: Instructor,
    mode: str,
    offering: ClassOffering | None = None,
) -> HttpResponse:
    return render(
        request,
        "classes/instructor/class_form.html",
        {
            "active_tab": "classes",
            "instructor": instructor,
            "form": form,
            "formset": formset,
            "mode": mode,
            "offering": offering,
        },
    )


@instructor_required
def instructor_class_create(request: HttpRequest) -> HttpResponse:
    instructor: Instructor = request.instructor  # type: ignore[attr-defined]
    form = InstructorClassOfferingForm(request.POST or None, request.FILES or None, instructor=instructor)
    formset = ClassSessionFormSet(request.POST or None, prefix="sessions")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        offering = form.save()
        formset.instance = offering
        formset.save()
        submit_now = request.POST.get("action") == "submit"
        if submit_now:
            offering.submit_for_review()
            messages.success(request, f"Submitted “{offering.title}” for admin review.")
        else:
            messages.success(request, f"Saved draft “{offering.title}”.")
        return redirect("classes:instructor_class_edit", pk=offering.pk)
    return _render_instructor_class_form(request, form=form, formset=formset, instructor=instructor, mode="create")


@instructor_required
def instructor_class_edit(request: HttpRequest, pk: int) -> HttpResponse:
    instructor: Instructor = request.instructor  # type: ignore[attr-defined]
    offering = get_object_or_404(
        ClassOffering.objects.filter(instructor=instructor),
        pk=pk,
    )
    if offering.status in {ClassOffering.Status.PUBLISHED, ClassOffering.Status.ARCHIVED}:
        messages.info(request, "Published and archived classes can only be edited by an admin.")
        return redirect("classes:instructor_dashboard")
    form = InstructorClassOfferingForm(
        request.POST or None, request.FILES or None, instance=offering, instructor=instructor
    )
    formset = ClassSessionFormSet(request.POST or None, instance=offering, prefix="sessions")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        offering = form.save()
        formset.save()
        submit_now = request.POST.get("action") == "submit"
        if submit_now and offering.status == ClassOffering.Status.DRAFT:
            offering.submit_for_review()
            messages.success(request, f"Submitted “{offering.title}” for admin review.")
        else:
            messages.success(request, "Class updated.")
        return redirect("classes:instructor_class_edit", pk=offering.pk)
    return _render_instructor_class_form(
        request, form=form, formset=formset, instructor=instructor, mode="edit", offering=offering
    )


@instructor_required
def instructor_class_submit(request: HttpRequest, pk: int) -> HttpResponse:
    """Transition a draft to 'pending review'."""
    instructor: Instructor = request.instructor  # type: ignore[attr-defined]
    offering = get_object_or_404(ClassOffering.objects.filter(instructor=instructor), pk=pk)
    if request.method == "POST" and offering.status == ClassOffering.Status.DRAFT:
        offering.submit_for_review()
        messages.success(request, f"Submitted “{offering.title}” for admin review.")
    return redirect("classes:instructor_dashboard")


@instructor_required
def instructor_registrations(request: HttpRequest) -> HttpResponse:
    instructor: Instructor = request.instructor  # type: ignore[attr-defined]
    registrations = (
        Registration.objects.filter(class_offering__instructor=instructor)
        .select_related("class_offering", "member")
        .order_by("-registered_at")
    )
    return render(
        request,
        "classes/instructor/registrations.html",
        {
            "active_tab": "registrations",
            "instructor": instructor,
            "registrations": registrations,
        },
    )


@instructor_required
def instructor_discount_codes(request: HttpRequest) -> HttpResponse:
    """Discount codes — managed by instructors from the Teaching portal.

    Codes are currently shared across all classes (no per-instructor
    ownership on the DiscountCode model), so any instructor sees every code.
    If that becomes a problem, add an ``owner`` FK and filter here.
    """
    instructor: Instructor = request.instructor  # type: ignore[attr-defined]
    codes = DiscountCode.objects.all()
    return render(
        request,
        "classes/instructor/discount_codes.html",
        {
            "active_tab": "discount_codes",
            "instructor": instructor,
            "codes": codes,
        },
    )


@instructor_required
def instructor_discount_code_create(request: HttpRequest) -> HttpResponse:
    instructor: Instructor = request.instructor  # type: ignore[attr-defined]
    form = DiscountCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Discount code created.")
        return redirect("classes:instructor_discount_codes")
    return render(
        request,
        "classes/instructor/discount_code_form.html",
        {"active_tab": "discount_codes", "instructor": instructor, "form": form, "mode": "create"},
    )


@instructor_required
def instructor_discount_code_edit(request: HttpRequest, pk: int) -> HttpResponse:
    instructor: Instructor = request.instructor  # type: ignore[attr-defined]
    code = get_object_or_404(DiscountCode, pk=pk)
    form = DiscountCodeForm(request.POST or None, instance=code)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Discount code updated.")
        return redirect("classes:instructor_discount_codes")
    return render(
        request,
        "classes/instructor/discount_code_form.html",
        {"active_tab": "discount_codes", "instructor": instructor, "form": form, "code": code, "mode": "edit"},
    )


@instructor_required
def instructor_discount_code_delete(request: HttpRequest, pk: int) -> HttpResponse:
    code = get_object_or_404(DiscountCode, pk=pk)
    if request.method == "POST":
        code.delete()
        messages.success(request, "Discount code deleted.")
    return redirect("classes:instructor_discount_codes")


@instructor_required
def instructor_profile(request: HttpRequest) -> HttpResponse:
    instructor: Instructor = request.instructor  # type: ignore[attr-defined]
    form = InstructorProfileForm(request.POST or None, request.FILES or None, instance=instructor)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("classes:instructor_profile")
    return render(
        request,
        "classes/instructor/profile.html",
        {"active_tab": "profile", "instructor": instructor, "form": form},
    )


@classes_admin_access_required
def admin_classes(request: HttpRequest) -> HttpResponse:
    valid_statuses = {choice.value for choice in ClassOffering.Status}
    status_filter = request.GET.get("status", "").strip()
    if status_filter not in valid_statuses:
        status_filter = ""
    base = ClassOffering.objects.select_related("instructor", "category").annotate(
        registration_count=Count("registrations")
    )
    classes = base.filter(status=status_filter) if status_filter else base
    classes = classes.order_by("-created_at")
    status_counts = {row["status"]: row["count"] for row in base.values("status").annotate(count=Count("pk"))}
    filters = [("", "All", base.count())] + [
        (choice.value, choice.label, status_counts.get(choice.value, 0)) for choice in ClassOffering.Status
    ]
    return render(
        request,
        "classes/admin/classes_list.html",
        {
            "active_tab": "classes",
            "classes": classes,
            "pending_count": ClassOffering.objects.pending_review().count(),
            "status_filters": filters,
            "selected_status": status_filter,
        },
    )


@classes_admin_access_required
def admin_class_create(request: HttpRequest) -> HttpResponse:
    form = ClassOfferingForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        offering = form.save(commit=False)
        offering.status = ClassOffering.Status.PUBLISHED
        offering.save()
        messages.success(request, f"{offering.title} is published.")
        return redirect("classes:admin_classes")
    return render(
        request,
        "classes/admin/class_form.html",
        {"active_tab": "classes", "form": form, "mode": "create"},
    )


@classes_admin_access_required
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


@classes_admin_access_required
def admin_class_detail(request: HttpRequest, pk: int) -> HttpResponse:
    offering = get_object_or_404(ClassOffering, pk=pk)
    return render(
        request,
        "classes/admin/class_detail.html",
        {"active_tab": "classes", "offering": offering},
    )


@classes_admin_access_required
def admin_class_approve(request: HttpRequest, pk: int) -> HttpResponse:
    offering = get_object_or_404(ClassOffering, pk=pk)
    if request.method == "POST":
        offering.approve(request.user)
        messages.success(request, f"{offering.title} is published.")
    return redirect("classes:admin_class_detail", pk=offering.pk)


@classes_admin_access_required
def admin_class_archive(request: HttpRequest, pk: int) -> HttpResponse:
    offering = get_object_or_404(ClassOffering, pk=pk)
    if request.method == "POST":
        offering.archive()
        messages.success(request, f"{offering.title} archived.")
        return redirect("classes:admin_classes")
    return redirect("classes:admin_class_detail", pk=offering.pk)


@classes_admin_access_required
def admin_class_duplicate(request: HttpRequest, pk: int) -> HttpResponse:
    offering = get_object_or_404(ClassOffering, pk=pk)
    if request.method == "POST":
        copy = offering.duplicate()
        messages.success(request, "Class duplicated.")
        return redirect("classes:admin_class_edit", pk=copy.pk)
    return redirect("classes:admin_class_detail", pk=offering.pk)


@classes_admin_access_required
def admin_class_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Hard-delete a class — only when it has no registrations.

    Classes with any registration history (even cancelled) are refused to
    preserve the audit record; use Archive instead in that case.
    """
    offering = get_object_or_404(ClassOffering, pk=pk)
    if request.method == "POST":
        if offering.registrations.exists():
            messages.error(request, "Can't delete — this class has registrations. Archive it instead.")
            return redirect("classes:admin_class_detail", pk=offering.pk)
        title = offering.title
        offering.delete()
        messages.success(request, f"Deleted “{title}”.")
        return redirect("classes:admin_classes")
    return redirect("classes:admin_class_detail", pk=offering.pk)


@classes_admin_access_required
def admin_categories(request: HttpRequest) -> HttpResponse:
    categories = Category.objects.all()
    return render(
        request,
        "classes/admin/categories.html",
        {"active_tab": "categories", "categories": categories},
    )


@classes_admin_access_required
def admin_category_create(request: HttpRequest) -> HttpResponse:
    form = CategoryForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category created.")
        return redirect("classes:admin_categories")
    return render(
        request,
        "classes/admin/category_form.html",
        {"active_tab": "categories", "form": form, "mode": "create"},
    )


@classes_admin_access_required
def admin_category_edit(request: HttpRequest, pk: int) -> HttpResponse:
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, request.FILES or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category updated.")
        return redirect("classes:admin_categories")
    return render(
        request,
        "classes/admin/category_form.html",
        {"active_tab": "categories", "form": form, "category": category, "mode": "edit"},
    )


@classes_admin_access_required
def admin_category_delete(request: HttpRequest, pk: int) -> HttpResponse:
    category = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        category.delete()
        messages.success(request, "Category deleted.")
    return redirect("classes:admin_categories")


@classes_admin_access_required
def admin_instructors(request: HttpRequest) -> HttpResponse:
    instructors = Instructor.objects.select_related("user").annotate(class_count=Count("classes"))
    return render(
        request,
        "classes/admin/instructors.html",
        {"active_tab": "instructors", "instructors": instructors},
    )


@classes_admin_access_required
def admin_instructor_promote(request: HttpRequest) -> HttpResponse:
    """Add an existing User as an Instructor — grants the role to a member account."""
    form = PromoteUserToInstructorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        instructor = form.save()
        messages.success(request, f"{instructor.display_name} is now an instructor.")
        return redirect("classes:admin_instructors")
    return render(
        request,
        "classes/admin/instructor_promote.html",
        {"active_tab": "instructors", "form": form},
    )


@classes_admin_access_required
def admin_registrations(request: HttpRequest) -> HttpResponse:
    registrations = Registration.objects.select_related("class_offering", "member").order_by("-registered_at")
    return render(
        request,
        "classes/admin/registrations.html",
        {"active_tab": "registrations", "registrations": registrations},
    )


@classes_admin_access_required
def admin_registration_detail(request: HttpRequest, pk: int) -> HttpResponse:
    registration = get_object_or_404(
        Registration.objects.select_related("class_offering", "member").prefetch_related("waivers"),
        pk=pk,
    )
    return render(
        request,
        "classes/admin/registration_detail.html",
        {"active_tab": "registrations", "registration": registration},
    )


@classes_admin_access_required
def admin_registration_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    registration = get_object_or_404(Registration, pk=pk)
    if request.method == "POST":
        registration.cancel(reason=request.POST.get("reason", ""))
        messages.success(request, "Registration cancelled.")
    return redirect("classes:admin_registration_detail", pk=pk)


@classes_admin_access_required
def admin_discount_codes(request: HttpRequest) -> HttpResponse:
    codes = DiscountCode.objects.all()
    return render(
        request,
        "classes/admin/discount_codes.html",
        {"active_tab": "discount_codes", "codes": codes},
    )


@classes_admin_access_required
def admin_discount_code_create(request: HttpRequest) -> HttpResponse:
    form = DiscountCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Discount code created.")
        return redirect("classes:admin_discount_codes")
    return render(
        request,
        "classes/admin/discount_code_form.html",
        {"active_tab": "discount_codes", "form": form, "mode": "create"},
    )


@classes_admin_access_required
def admin_discount_code_edit(request: HttpRequest, pk: int) -> HttpResponse:
    code = get_object_or_404(DiscountCode, pk=pk)
    form = DiscountCodeForm(request.POST or None, instance=code)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Discount code updated.")
        return redirect("classes:admin_discount_codes")
    return render(
        request,
        "classes/admin/discount_code_form.html",
        {"active_tab": "discount_codes", "form": form, "code": code, "mode": "edit"},
    )


@classes_admin_access_required
def admin_discount_code_delete(request: HttpRequest, pk: int) -> HttpResponse:
    code = get_object_or_404(DiscountCode, pk=pk)
    if request.method == "POST":
        code.delete()
        messages.success(request, "Discount code deleted.")
    return redirect("classes:admin_discount_codes")


@admin_required
def admin_settings(request: HttpRequest) -> HttpResponse:
    settings_obj = ClassSettings.load()
    form = ClassSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Settings saved.")
        return redirect("classes:admin_settings")
    return render(
        request,
        "classes/admin/settings.html",
        {"active_tab": "settings", "form": form},
    )
