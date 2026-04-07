"""App version and changelog."""

from __future__ import annotations

VERSION = "1.3.2"

CHANGELOG: list[dict[str, str | list[str]]] = [
    {
        "version": "1.3.2",
        "date": "2026-04-07",
        "title": "Pay-as-you-go Tabs, Guild Product Cards & Stripe in Settings",
        "changes": [
            "You no longer need to save a card before adding things to your tab — just add the item and pay later",
            "When you have charges ready to pay, a 'Pay Now' button appears on your Tab page that opens Stripe's secure checkout",
            "Money goes directly to the guild that owns the items you bought",
            "Guild pages now show products as cards instead of a table — easier to scan",
            "All Stripe configuration now lives in the admin Payments → Settings page — no more editing server environment variables",
            "Stripe Connect platform billing can now be enabled with a single toggle in Settings (for future membership and space-lease billing)",
        ],
    },
    {
        "version": "1.3.1",
        "date": "2026-04-07",
        "title": "Pay Guilds Directly for Consumables",
        "changes": [
            "Guilds can now connect their own Stripe account by pasting their API keys — no platform setup required",
            "Money for consumables (clay, materials, etc.) goes straight to the guild that owns the items",
            "Admins can test a guild's Stripe keys before saving to make sure everything is connected",
        ],
    },
    {
        "version": "1.3.0",
        "date": "2026-04-02",
        "title": "Tab Billing System",
        "changes": [
            "New tab system — charges accumulate on your tab and get billed on a schedule, just like a bar tab",
            "See your tab balance at a glance with the new balance pill in the top bar",
            "My Tab page shows your pending charges, tab limit, and remaining balance",
            "Tab History page shows all past charges with itemized details you can expand",
            "Add items to your own tab with the self-service form",
            "Set up a payment method securely through Stripe — your card info never touches our server",
            "Automated billing engine charges tabs on a configurable schedule (daily, weekly, or monthly)",
            "Failed charges automatically retry up to 3 times before locking the tab",
            "Email receipts after every successful charge with an itemized breakdown",
            "Guild Stripe accounts can be connected via Stripe Connect — each guild receives their share of charges directly",
            "Members can pick products when adding to their tab — price and description are filled in automatically",
            "Unified Payments admin — one page for outstanding tabs, charge history, billing settings, and Stripe accounts",
            "All financial records are preserved forever — entries are voided, never deleted",
            "Guild pages — each guild now has its own page with an about section and a list of products",
            "Guild leads can edit their guild's about text and manage their product listings directly from the guild page",
        ],
    },
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
