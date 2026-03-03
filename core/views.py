from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render


def health_check(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "home.html")


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "membership/dashboard.html")
