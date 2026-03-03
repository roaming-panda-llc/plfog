from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import ClassDiscountCode, ClassImage, ClassSession, MakerClass, Orientation, ScheduledOrientation, Student


class ClassSessionInline(TabularInline):
    model = ClassSession
    fields = ["starts_at", "ends_at", "notes"]
    extra = 0


class ClassImageInline(TabularInline):
    model = ClassImage
    fields = ["image_path", "sort_order"]
    extra = 0


class StudentInline(TabularInline):
    model = Student
    fields = ["name", "email", "user", "amount_paid", "registered_at"]
    readonly_fields = ["registered_at"]
    extra = 0


@admin.register(MakerClass)
class MakerClassAdmin(ModelAdmin):
    list_display = ["name", "guild", "price", "status", "student_count", "published_at"]
    list_filter = ["status", "guild"]
    search_fields = ["name"]
    inlines = [ClassSessionInline, ClassImageInline, StudentInline]

    @admin.display(description="Students")
    def student_count(self, obj: MakerClass) -> int:
        return obj.students.count()


@admin.register(ClassSession)
class ClassSessionAdmin(ModelAdmin):
    list_display = ["maker_class", "starts_at", "ends_at"]
    list_filter = ["maker_class"]


@admin.register(ClassImage)
class ClassImageAdmin(ModelAdmin):
    list_display = ["maker_class", "sort_order"]


@admin.register(ClassDiscountCode)
class ClassDiscountCodeAdmin(ModelAdmin):
    list_display = ["code", "discount_type", "discount_value", "is_active"]
    list_filter = ["discount_type", "is_active"]
    search_fields = ["code"]


@admin.register(Student)
class StudentAdmin(ModelAdmin):
    list_display = ["name", "email", "maker_class", "amount_paid", "is_member_display", "registered_at"]
    list_filter = ["maker_class"]
    search_fields = ["name", "email"]

    @admin.display(boolean=True, description="Member")
    def is_member_display(self, obj: Student) -> bool:
        return obj.is_member


class ScheduledOrientationInline(TabularInline):
    model = ScheduledOrientation
    fields = ["user", "scheduled_at", "claimed_by", "status"]
    extra = 0


@admin.register(Orientation)
class OrientationAdmin(ModelAdmin):
    list_display = ["name", "guild", "price", "duration_minutes", "is_active"]
    list_filter = ["is_active", "guild"]
    search_fields = ["name"]
    inlines = [ScheduledOrientationInline]


@admin.register(ScheduledOrientation)
class ScheduledOrientationAdmin(ModelAdmin):
    list_display = ["orientation", "user", "scheduled_at", "claimed_by", "status"]
    list_filter = ["status"]
    search_fields = ["orientation__name", "user__username"]
