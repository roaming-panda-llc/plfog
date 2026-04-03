from django.urls import path

from . import views

urlpatterns = [
    path("payment-method/setup/", views.setup_payment_method, name="billing_setup_payment_method"),
    path("api/setup-intent/", views.create_setup_intent_api, name="billing_create_setup_intent"),
    path("payment-method/confirm/", views.confirm_setup, name="billing_confirm_setup"),
    path("payment-method/remove/", views.remove_payment_method, name="billing_remove_payment_method"),
    path("webhooks/stripe/", views.stripe_webhook, name="billing_stripe_webhook"),
    path("admin/dashboard/", views.admin_tab_dashboard, name="billing_admin_dashboard"),
    path("admin/add-entry/", views.admin_add_tab_entry, name="billing_admin_add_entry"),
    path("admin/save-settings/", views.billing_admin_save_settings, name="billing_admin_save_settings"),
    path("connect/initiate/<int:guild_id>/", views.initiate_connect, name="billing_initiate_connect"),
    path("connect/callback/", views.connect_callback, name="billing_connect_callback"),
]
