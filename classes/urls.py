from django.urls import path

from classes import views

app_name = "classes"

urlpatterns = [
    path("admin/", views.admin_root, name="admin_root"),
    path("admin/classes/", views.admin_classes, name="admin_classes"),
    path("admin/categories/", views.admin_categories, name="admin_categories"),
    path("admin/instructors/", views.admin_instructors, name="admin_instructors"),
    path("admin/registrations/", views.admin_registrations, name="admin_registrations"),
    path("admin/discount-codes/", views.admin_discount_codes, name="admin_discount_codes"),
    path("admin/settings/", views.admin_settings, name="admin_settings"),
]
