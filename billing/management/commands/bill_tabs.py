from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from billing.models import Order
from billing.stripe_utils import create_invoice_for_user

User = get_user_model()


class Command(BaseCommand):
    help = "Bill all members with outstanding tab balances"

    def handle(self, *args: object, **options: object) -> None:
        users_with_tabs = User.objects.filter(orders__status=Order.Status.ON_TAB).distinct()

        if not users_with_tabs.exists():
            self.stdout.write(self.style.WARNING("No outstanding tabs to bill"))
            return

        billed_count = 0
        for user in users_with_tabs:
            tab_orders = Order.objects.filter(user=user, status=Order.Status.ON_TAB)
            if not tab_orders.exists():
                continue

            invoice = create_invoice_for_user(user, tab_orders)
            if invoice:
                order_count = tab_orders.count()
                tab_orders.update(status=Order.Status.BILLED, billed_at=timezone.now())
                billed_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Billed {user.username}: {order_count} orders, total ${invoice.amount_due / 100:.2f}"
                    )
                )
            else:
                self.stdout.write(self.style.ERROR(f"Failed to bill {user.username}"))

        self.stdout.write(self.style.SUCCESS(f"\nBilled {billed_count} users total"))
