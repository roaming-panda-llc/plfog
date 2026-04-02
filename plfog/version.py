"""App version and changelog."""

from __future__ import annotations

VERSION = "1.2.1"

CHANGELOG: list[dict[str, str | list[str]]] = [
    {
        "version": "1.2.1",
        "date": "2026-04-01",
        "title": "Mobile Sidebar Fix",
        "changes": [
            "Fixed the sidebar on mobile — it now slides open as a drawer with a dark backdrop you can tap to close",
            "Sidebar starts closed on mobile so you get the full screen for content",
            "Tapping a nav link on mobile automatically closes the sidebar",
        ],
    },
    {
        "version": "1.2.0",
        "date": "2026-03-30",
        "title": "Member Management Redesign",
        "changes": [
            "Admin Members page now lets you create users with a login right from the add form",
            "Added email aliases — members can have multiple email addresses and log in with any of them",
            "New 'Users' filter on the Members page to see who has logged into the app",
            "Search now finds members by their alias emails too",
            "Removed the separate User admin page — everything is managed through Members now",
        ],
    },
    {
        "version": "1.1.2",
        "date": "2026-03-30",
        "title": "Mobile Sidebar Fix",
        "changes": [
            "Fixed the sidebar menu button not working on Android phones — the side menu now opens and closes properly on mobile",
        ],
    },
    {
        "version": "1.1.1",
        "date": "2026-03-28",
        "title": "Better Discord Announcements",
        "changes": [
            "Discord now gets a friendly release announcement when updates go live — with version and what changed",
            "Removed noisy PR-opened notifications so the channel stays clean",
        ],
    },
    {
        "version": "1.1.0",
        "date": "2026-03-28",
        "title": "Vote Standings & Discord Notifications",
        "changes": [
            "Live vote standings with bar charts on the guild voting page — see who's leading in real time",
            "Admin voting dashboard now shows visual bar charts for vote leaders",
            "Discord notifications — the team gets pinged when PRs are opened or code is merged to main",
        ],
    },
    {
        "version": "1.0.3",
        "date": "2026-03-28",
        "title": "Login & Email Fixes",
        "changes": [
            "Members synced from Airtable can now log in immediately — no signup step needed",
            "All emails from Past Lives are now properly branded (no more 'example.com')",
            "Table columns in the admin panel are now left-aligned for easier reading",
        ],
    },
    {
        "version": "1.0.2",
        "date": "2026-03-28",
        "title": "Admin Fixes",
        "changes": [
            "Role management moved out of the member directory — it now lives in the admin panel only",
            "Login code entry allows up to 5 attempts before locking out (was 3)",
        ],
    },
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
