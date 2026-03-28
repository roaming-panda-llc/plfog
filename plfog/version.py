"""App version and changelog."""

from __future__ import annotations

VERSION = "1.0.1"

CHANGELOG: list[dict[str, str | list[str]]] = [
    {
        "version": "1.0.1",
        "date": "2026-03-27",
        "title": "Hotfix",
        "changes": [
            "Guild vote history from before launch is now reflected in voting results",
            "Login code emails no longer show [example.com] in the subject line",
            "Login page email field now shows the correct placeholder",
        ],
    },
    {
        "version": "1.0.0",
        "date": "2026-03-27",
        "title": "Launch Day",
        "changes": [
            "Vote for your favorite guilds each month and see how funding gets split",
            "Your own member hub — one place for voting, directory, and settings",
            "Passwordless sign-in — just enter your email and we send you a code",
            "Member directory — find other members, see their bios and contact info",
            "Member roles — admins, guild officers, and regular members each see what they need",
            "Admins can invite new members, manage the roster, and take funding snapshots",
            "Send us feedback anytime from the Feedback button",
            "Works on your phone — install it like an app from your browser",
            "Forgot which email you signed up with? The new account finder has you covered",
        ],
    },
]
