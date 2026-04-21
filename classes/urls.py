from django.urls import path

from classes import views

app_name = "classes"

urlpatterns = [
    path("admin/", views.admin_root, name="admin_root"),
    path("admin/classes/", views.admin_classes, name="admin_classes"),
    path("admin/classes/new/", views.admin_class_create, name="admin_class_create"),
    path("admin/classes/<int:pk>/", views.admin_class_detail, name="admin_class_detail"),
    path("admin/classes/<int:pk>/edit/", views.admin_class_edit, name="admin_class_edit"),
    path("admin/classes/<int:pk>/approve/", views.admin_class_approve, name="admin_class_approve"),
    path("admin/classes/<int:pk>/archive/", views.admin_class_archive, name="admin_class_archive"),
    path("admin/classes/<int:pk>/duplicate/", views.admin_class_duplicate, name="admin_class_duplicate"),
    path("admin/categories/", views.admin_categories, name="admin_categories"),
    path("admin/categories/new/", views.admin_category_create, name="admin_category_create"),
    path("admin/categories/<int:pk>/edit/", views.admin_category_edit, name="admin_category_edit"),
    path("admin/categories/<int:pk>/delete/", views.admin_category_delete, name="admin_category_delete"),
    path("admin/instructors/", views.admin_instructors, name="admin_instructors"),
    path("admin/instructors/new/", views.admin_instructor_invite, name="admin_instructor_invite"),
    path("admin/registrations/", views.admin_registrations, name="admin_registrations"),
    path("admin/discount-codes/", views.admin_discount_codes, name="admin_discount_codes"),
    path("admin/settings/", views.admin_settings, name="admin_settings"),
]
