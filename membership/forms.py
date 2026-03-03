from __future__ import annotations

from django import forms

from .models import Buyable, Order


class BuyableForm(forms.ModelForm):
    class Meta:
        model = Buyable
        fields = ["name", "description", "image", "unit_price", "is_active"]


class OrderNoteForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}
