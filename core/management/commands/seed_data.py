from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from billing.models import (
    Invoice,
    MemberSubscription,
    Order,
    Payout,
    RevenueSplit,
    SubscriptionPlan,
)
from core.models import Setting
from education.models import (
    ClassDiscountCode,
    ClassSession,
    MakerClass,
    Orientation,
    ScheduledOrientation,
    Student,
)
from membership.models import (
    Guild,
    GuildDocument,
    GuildMembership,
    GuildVote,
    GuildWishlistItem,
    Lease,
    Member,
    MemberSchedule,
    MembershipPlan,
    ScheduleBlock,
    Space,
)
from outreach.models import (
    Buyable,
    BuyablePurchase,
    Event,
    Lead,
    Tour,
)
from tools.models import Document, Rentable, Rental, Tool, ToolReservation

User = get_user_model()

TODAY = timezone.now().date()


class Command(BaseCommand):
    help = "Seed the database with realistic demo data for Past Lives Makerspace"

    def add_arguments(self, parser):  # type: ignore[override]
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all existing data before seeding",
        )

    def handle(self, *args: object, **options: object) -> None:
        if options["flush"]:
            self._flush_data()

        self._seed_settings()
        users = self._seed_users()
        plans = self._seed_membership_plans()
        members = self._seed_members(users, plans)
        guilds = self._seed_guilds(members)
        self._seed_guild_memberships(guilds, users)
        self._seed_guild_votes(members, guilds)
        self._seed_guild_documents(guilds, users)
        self._seed_guild_wishlist(guilds, users)
        spaces = self._seed_spaces(guilds)
        self._seed_leases(members, guilds, spaces)
        tools = self._seed_tools(guilds)
        self._seed_tool_reservations(tools, users)
        splits = self._seed_revenue_splits()
        rentables = self._seed_rentables(tools, splits)
        orders = self._seed_orders(users, splits)
        self._seed_rentals(rentables, users, orders)
        self._seed_invoices(users)
        self._seed_payouts(users, guilds)
        sub_plans = self._seed_subscription_plans()
        self._seed_member_subscriptions(users, sub_plans)
        discount_codes = self._seed_discount_codes()
        self._seed_maker_classes(guilds, users, splits, discount_codes)
        self._seed_orientations(guilds, tools, users, splits, orders)
        self._seed_leads()
        self._seed_tours()
        self._seed_events(guilds, users)
        buyables = self._seed_buyables(guilds, splits)
        self._seed_buyable_purchases(buyables, users, orders)
        self._seed_member_schedules(users)
        self._seed_tool_documents(tools, users)

        self.stdout.write(self.style.SUCCESS("\nSeed complete."))

    # -------------------------------------------------------------------------
    # Flush
    # -------------------------------------------------------------------------

    def _flush_data(self) -> None:
        self.stdout.write("Flushing existing data...")
        BuyablePurchase.objects.all().delete()
        Buyable.objects.all().delete()
        Tour.objects.all().delete()
        Lead.objects.all().delete()
        Event.objects.all().delete()
        ScheduledOrientation.objects.all().delete()
        Student.objects.all().delete()
        ClassSession.objects.all().delete()
        MakerClass.objects.all().delete()
        Orientation.objects.all().delete()
        ClassDiscountCode.objects.all().delete()
        Document.objects.all().delete()
        Rental.objects.all().delete()
        Rentable.objects.all().delete()
        ToolReservation.objects.all().delete()
        Tool.objects.all().delete()
        Lease.objects.all().delete()
        Space.objects.all().delete()
        ScheduleBlock.objects.all().delete()
        MemberSchedule.objects.all().delete()
        GuildWishlistItem.objects.all().delete()
        GuildDocument.objects.all().delete()
        GuildVote.objects.all().delete()
        GuildMembership.objects.all().delete()
        Guild.objects.all().delete()
        Member.objects.all().delete()
        MembershipPlan.objects.all().delete()
        MemberSubscription.objects.all().delete()
        Order.objects.all().delete()
        Invoice.objects.all().delete()
        Payout.objects.all().delete()
        RevenueSplit.objects.all().delete()
        SubscriptionPlan.objects.all().delete()
        Setting.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        self.stdout.write(self.style.SUCCESS("Flush complete."))

    # -------------------------------------------------------------------------
    # Settings
    # -------------------------------------------------------------------------

    def _seed_settings(self) -> None:
        settings_data: list[dict[str, Any]] = [
            {"key": "makerspace_name", "value": "Past Lives Makerspace", "type": "text"},
            {"key": "makerspace_address", "value": "123 SE Industrial Way, Portland, OR 97214", "type": "text"},
            {"key": "max_guild_votes", "value": 3, "type": "number"},
            {"key": "allow_self_registration", "value": True, "type": "boolean"},
        ]
        for item in settings_data:
            Setting.objects.update_or_create(
                key=item["key"],
                defaults={"value": item["value"], "type": item["type"]},
            )
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(settings_data)} settings"))

    # -------------------------------------------------------------------------
    # Users
    # -------------------------------------------------------------------------

    def _seed_users(self) -> list:
        admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@pastlives.org",
                "is_staff": True,
                "is_superuser": True,
                "first_name": "Admin",
                "last_name": "User",
            },
        )
        admin.set_password("admin")
        admin.save()

        demo_user_data = [
            ("mia.chen", "Mia", "Chen", "mia.chen@example.com"),
            ("jordan.walsh", "Jordan", "Walsh", "jordan.walsh@example.com"),
            ("sam.okafor", "Sam", "Okafor", "sam.okafor@example.com"),
            ("priya.nair", "Priya", "Nair", "priya.nair@example.com"),
            ("eli.reyes", "Eli", "Reyes", "eli.reyes@example.com"),
            ("casey.burke", "Casey", "Burke", "casey.burke@example.com"),
            ("devon.huang", "Devon", "Huang", "devon.huang@example.com"),
            ("anya.petrov", "Anya", "Petrov", "anya.petrov@example.com"),
            ("marcos.silva", "Marcos", "Silva", "marcos.silva@example.com"),
            ("riley.nguyen", "Riley", "Nguyen", "riley.nguyen@example.com"),
            ("alex.kim", "Alex", "Kim", "alex.kim@example.com"),
            ("nadia.foster", "Nadia", "Foster", "nadia.foster@example.com"),
            ("tobias.grant", "Tobias", "Grant", "tobias.grant@example.com"),
            ("luna.martinez", "Luna", "Martinez", "luna.martinez@example.com"),
            ("felix.weber", "Felix", "Weber", "felix.weber@example.com"),
            ("imani.brooks", "Imani", "Brooks", "imani.brooks@example.com"),
            ("quinn.harris", "Quinn", "Harris", "quinn.harris@example.com"),
            ("zoe.yamamoto", "Zoe", "Yamamoto", "zoe.yamamoto@example.com"),
            ("raj.patel", "Raj", "Patel", "raj.patel@example.com"),
            ("claire.dubois", "Claire", "Dubois", "claire.dubois@example.com"),
        ]

        users = []
        for username, first, last, email in demo_user_data:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={"email": email, "first_name": first, "last_name": last},
            )
            user.set_password("demo")
            user.save()
            users.append(user)

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(users)} demo users + admin"))
        return users

    # -------------------------------------------------------------------------
    # Membership Plans
    # -------------------------------------------------------------------------

    def _seed_membership_plans(self) -> list:
        plans_data = [
            {"name": "Drop-In", "monthly_price": Decimal("50.00"), "deposit_required": None},
            {"name": "Part-Time", "monthly_price": Decimal("150.00"), "deposit_required": Decimal("200.00")},
            {"name": "Full-Time", "monthly_price": Decimal("300.00"), "deposit_required": Decimal("400.00")},
            {"name": "Studio", "monthly_price": Decimal("500.00"), "deposit_required": Decimal("600.00")},
        ]
        plans = []
        for item in plans_data:
            plan, _ = MembershipPlan.objects.get_or_create(
                name=item["name"],
                defaults={
                    "monthly_price": item["monthly_price"],
                    "deposit_required": item["deposit_required"],
                },
            )
            plans.append(plan)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(plans)} membership plans"))
        return plans

    # -------------------------------------------------------------------------
    # Members
    # -------------------------------------------------------------------------

    def _seed_members(self, users: list, plans: list) -> list:
        drop_in, part_time, full_time, studio = plans

        member_data = [
            # (user_idx, full_legal_name, preferred_name, phone, status, role, plan, join_offset_days)
            (0, "Mia Chen", "Mia", "503-555-0101", Member.Status.ACTIVE, Member.Role.STANDARD, full_time, 400),
            (1, "Jordan Walsh", "Jordan", "503-555-0102", Member.Status.ACTIVE, Member.Role.GUILD_LEAD, studio, 600),
            (2, "Samuel Okafor", "Sam", "503-555-0103", Member.Status.ACTIVE, Member.Role.STANDARD, part_time, 300),
            (3, "Priya Nair", "Priya", "503-555-0104", Member.Status.ACTIVE, Member.Role.WORK_TRADE, part_time, 500),
            (4, "Eli Reyes", "Eli", "503-555-0105", Member.Status.ACTIVE, Member.Role.STANDARD, full_time, 250),
            (5, "Casey Burke", "Casey", "503-555-0106", Member.Status.ACTIVE, Member.Role.VOLUNTEER, drop_in, 180),
            (6, "Devon Huang", "Devon", "503-555-0107", Member.Status.ACTIVE, Member.Role.STANDARD, full_time, 450),
            (7, "Anya Petrov", "Anya", "503-555-0108", Member.Status.ACTIVE, Member.Role.GUILD_LEAD, studio, 700),
            (8, "Marcos Silva", "Marcos", "503-555-0109", Member.Status.ACTIVE, Member.Role.STANDARD, part_time, 320),
            (9, "Riley Nguyen", "Riley", "503-555-0110", Member.Status.ACTIVE, Member.Role.EMPLOYEE, full_time, 550),
            (10, "Alex Kim", "Alex", "503-555-0111", Member.Status.ACTIVE, Member.Role.STANDARD, drop_in, 90),
            (11, "Nadia Foster", "Nadia", "503-555-0112", Member.Status.ACTIVE, Member.Role.CONTRACTOR, full_time, 200),
            (12, "Tobias Grant", "Tobias", "503-555-0113", Member.Status.ACTIVE, Member.Role.STANDARD, part_time, 380),
            (13, "Luna Martinez", "Luna", "503-555-0114", Member.Status.ACTIVE, Member.Role.GUILD_LEAD, studio, 620),
            (14, "Felix Weber", "Felix", "503-555-0115", Member.Status.ACTIVE, Member.Role.STANDARD, full_time, 280),
            (15, "Imani Brooks", "Imani", "503-555-0116", Member.Status.FORMER, Member.Role.STANDARD, part_time, 800),
            (16, "Quinn Harris", "Quinn", "503-555-0117", Member.Status.FORMER, Member.Role.STANDARD, drop_in, 730),
            (17, "Zoe Yamamoto", "Zoe", "503-555-0118", Member.Status.FORMER, Member.Role.WORK_TRADE, part_time, 900),
            (18, "Raj Patel", "Raj", "503-555-0119", Member.Status.SUSPENDED, Member.Role.STANDARD, full_time, 150),
            (
                19,
                "Claire Dubois",
                "Claire",
                "503-555-0120",
                Member.Status.SUSPENDED,
                Member.Role.STANDARD,
                drop_in,
                120,
            ),
        ]

        members = []
        for row in member_data:
            idx, legal, preferred, phone, status, role, plan, offset = row
            user = users[idx]
            join_date = TODAY - timedelta(days=offset)
            defaults = {
                "full_legal_name": legal,
                "preferred_name": preferred,
                "email": user.email,
                "phone": phone,
                "billing_name": legal,
                "emergency_contact_name": f"{preferred} Emergency Contact",
                "emergency_contact_phone": "503-555-9999",
                "emergency_contact_relationship": "Partner",
                "membership_plan": plan,
                "status": status,
                "role": role,
                "join_date": join_date,
            }
            if status == Member.Status.FORMER:
                defaults["cancellation_date"] = join_date + timedelta(days=365)
            member, _ = Member.objects.get_or_create(user=user, defaults=defaults)
            members.append(member)

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(members)} members"))
        return members

    # -------------------------------------------------------------------------
    # Guilds
    # -------------------------------------------------------------------------

    def _seed_guilds(self, members: list) -> list:
        guilds_data = [
            {
                "name": "Woodworking",
                "intro": "Crafting functional art from raw timber.",
                "description": (
                    "The Woodworking Guild is home to cabinet makers, furniture builders, and sculptors. "
                    "We maintain a fully equipped shop with table saws, planers, jointers, and a CNC router."
                ),
                "icon": "handyman",
                "guild_lead": members[1],
            },
            {
                "name": "Metalworking",
                "intro": "Forging ideas in steel and aluminum.",
                "description": (
                    "Our Metalworking Guild covers welding (MIG, TIG, stick), plasma cutting, metal lathe, "
                    "and metal casting. We work with steel, aluminum, brass, and copper."
                ),
                "icon": "precision_manufacturing",
                "guild_lead": members[7],
            },
            {
                "name": "Ceramics",
                "intro": "Shaping earth into lasting forms.",
                "description": (
                    "The Ceramics Guild features electric and kick wheels, slab rollers, extruders, "
                    "and two kilns. We fire earthenware, stoneware, and porcelain."
                ),
                "icon": "emoji_objects",
                "guild_lead": members[13],
            },
            {
                "name": "Textiles",
                "intro": "Weaving community through fiber arts.",
                "description": (
                    "From spinning and weaving to sewing and embroidery, the Textiles Guild supports "
                    "all fiber arts. We have industrial sewing machines, sergers, and a floor loom."
                ),
                "icon": "checkroom",
                "guild_lead": members[3],
            },
            {
                "name": "Electronics",
                "intro": "Bridging the physical and digital worlds.",
                "description": (
                    "The Electronics Guild specializes in microcontrollers, PCB design, soldering, "
                    "and embedded systems. We host Arduino and Raspberry Pi workshops regularly."
                ),
                "icon": "memory",
                "guild_lead": members[9],
            },
            {
                "name": "3D Printing",
                "intro": "Turning digital designs into physical reality.",
                "description": (
                    "Our 3D Printing Guild operates FDM, resin, and SLS printers. We cover Fusion 360, "
                    "Blender, and print farm management."
                ),
                "icon": "view_in_ar",
                "guild_lead": members[4],
            },
            {
                "name": "Jewelry",
                "intro": "Crafting wearable art from precious metals and stones.",
                "description": (
                    "The Jewelry Guild provides jewelers benches, flex shafts, rolling mills, a kiln, "
                    "and lapidary equipment. We work in silver, gold, bronze, and gemstones."
                ),
                "icon": "diamond",
                "guild_lead": members[0],
            },
            {
                "name": "Screen Printing",
                "intro": "Pressing color onto fabric and paper.",
                "description": (
                    "The Screen Printing Guild maintains a four-color press, exposure unit, and drying "
                    "rack. We print on t-shirts, tote bags, posters, and more."
                ),
                "icon": "print",
                "guild_lead": members[2],
            },
        ]

        guilds = []
        for item in guilds_data:
            guild, _ = Guild.objects.get_or_create(
                name=item["name"],
                defaults={
                    "intro": item["intro"],
                    "description": item["description"],
                    "icon": item["icon"],
                    "guild_lead": item["guild_lead"],
                    "is_active": True,
                },
            )
            guilds.append(guild)

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(guilds)} guilds"))
        return guilds

    # -------------------------------------------------------------------------
    # Guild Memberships
    # -------------------------------------------------------------------------

    def _seed_guild_memberships(self, guilds: list, users: list) -> None:
        memberships = [
            # (guild_idx, user_idx, is_lead)
            (0, 1, True),
            (0, 0, False),
            (0, 4, False),
            (0, 6, False),
            (1, 7, True),
            (1, 8, False),
            (1, 11, False),
            (1, 14, False),
            (2, 13, True),
            (2, 2, False),
            (2, 5, False),
            (2, 12, False),
            (3, 3, True),
            (3, 10, False),
            (3, 16, False),
            (4, 9, True),
            (4, 18, False),
            (4, 19, False),
            (5, 4, True),
            (5, 6, False),
            (5, 15, False),
            (6, 0, True),
            (6, 17, False),
            (6, 12, False),
            (7, 2, True),
            (7, 8, False),
            (7, 5, False),
        ]
        count = 0
        for guild_idx, user_idx, is_lead in memberships:
            GuildMembership.objects.get_or_create(
                guild=guilds[guild_idx],
                user=users[user_idx],
                defaults={"is_lead": is_lead},
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} guild memberships"))

    # -------------------------------------------------------------------------
    # Guild Votes
    # -------------------------------------------------------------------------

    def _seed_guild_votes(self, members: list, guilds: list) -> None:
        votes_data = [
            (0, [(1, guilds[0]), (2, guilds[6]), (3, guilds[3])]),
            (2, [(1, guilds[7]), (2, guilds[2]), (3, guilds[4])]),
            (4, [(1, guilds[5]), (2, guilds[0]), (3, guilds[1])]),
            (5, [(1, guilds[3]), (2, guilds[7]), (3, guilds[2])]),
            (8, [(1, guilds[1]), (2, guilds[0]), (3, guilds[5])]),
            (10, [(1, guilds[4]), (2, guilds[5]), (3, guilds[6])]),
        ]
        count = 0
        for member_idx, priority_guilds in votes_data:
            member = members[member_idx]
            for priority, guild in priority_guilds:
                GuildVote.objects.get_or_create(
                    member=member,
                    priority=priority,
                    defaults={"guild": guild},
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} guild votes"))

    # -------------------------------------------------------------------------
    # Guild Documents
    # -------------------------------------------------------------------------

    def _seed_guild_documents(self, guilds: list, users: list) -> None:
        docs_data = [
            (0, "Woodworking Safety Handbook", users[1]),
            (0, "Table Saw Operation Guide", users[1]),
            (1, "Welding Safety Manual", users[7]),
            (2, "Kiln Temperature Schedules", users[13]),
            (4, "Electronics Lab Rules", users[9]),
            (5, "3D Printer Maintenance Log", users[4]),
        ]
        count = 0
        for guild_idx, name, uploader in docs_data:
            doc, created = GuildDocument.objects.get_or_create(
                guild=guilds[guild_idx],
                name=name,
                defaults={"uploaded_by": uploader},
            )
            if created:
                doc.file_path.save(
                    f"{name.lower().replace(' ', '_')}.pdf",
                    ContentFile(b"placeholder"),
                    save=True,
                )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} guild documents"))

    # -------------------------------------------------------------------------
    # Guild Wishlist Items
    # -------------------------------------------------------------------------

    def _seed_guild_wishlist(self, guilds: list, users: list) -> None:
        wishlist_data = [
            (
                0,
                "Festool Track Saw",
                "Precision track saw for sheet goods",
                "https://festool.com",
                Decimal("800.00"),
                False,
            ),
            (0, "Drum Sander", "Wide drum sander for flattening slabs", "", Decimal("1200.00"), False),
            (0, "Wood Moisture Meter", "Digital moisture meter for kiln-dried lumber", "", Decimal("60.00"), True),
            (1, "TIG Welder", "Lincoln Electric TIG welder for aluminum work", "", Decimal("2500.00"), False),
            (1, "Metal Bandsaw", "Horizontal/vertical metal cutting bandsaw", "", Decimal("900.00"), False),
            (2, "Raku Kiln", "Propane-fired raku kiln for outdoor firings", "", Decimal("600.00"), False),
            (2, "Slab Roller Replacement Canvas", "Replacement canvas set for slab roller", "", Decimal("80.00"), True),
            (3, "Serger Machine", "Industrial serger for production sewing", "", Decimal("400.00"), False),
            (3, "Dress Form Set", "Adjustable dress forms in multiple sizes", "", Decimal("350.00"), False),
            (4, "Oscilloscope", "Four-channel digital oscilloscope", "", Decimal("500.00"), False),
            (4, "SMD Rework Station", "Hot air rework station for SMD components", "", Decimal("150.00"), True),
            (5, "Resin Printer", "High-resolution MSLA resin printer", "", Decimal("700.00"), False),
            (5, "Filament Dryer", "Multi-spool filament drying cabinet", "", Decimal("200.00"), False),
            (6, "Rolling Mill", "Electric rolling mill for metal sheet work", "", Decimal("1800.00"), False),
            (6, "Hydraulic Press", "20-ton hydraulic press for metal forming", "", Decimal("3000.00"), False),
            (7, "Exposure Unit", "UV exposure unit for screen burning", "", Decimal("800.00"), True),
            (7, "Flash Dryer", "Infrared flash dryer for multi-color printing", "", Decimal("600.00"), False),
        ]
        count = 0
        for guild_idx, name, desc, link, cost, fulfilled in wishlist_data:
            GuildWishlistItem.objects.get_or_create(
                guild=guilds[guild_idx],
                name=name,
                defaults={
                    "description": desc,
                    "link": link,
                    "estimated_cost": cost,
                    "is_fulfilled": fulfilled,
                    "created_by": users[guild_idx % len(users)],
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} guild wishlist items"))

    # -------------------------------------------------------------------------
    # Spaces
    # -------------------------------------------------------------------------

    def _seed_spaces(self, guilds: list) -> list:
        spaces: list = []

        # Studios S-101 to S-112
        studio_configs = [
            ("S-101", "Woodworking Studio A", 400, Decimal("3.75"), Space.Status.OCCUPIED, guilds[0]),
            ("S-102", "Woodworking Studio B", 350, Decimal("3.75"), Space.Status.OCCUPIED, guilds[0]),
            ("S-103", "Metalworking Studio", 500, Decimal("3.50"), Space.Status.OCCUPIED, guilds[1]),
            ("S-104", "Ceramics Studio", 380, Decimal("3.75"), Space.Status.OCCUPIED, guilds[2]),
            ("S-105", "Textiles Studio", 320, Decimal("3.75"), Space.Status.OCCUPIED, guilds[3]),
            ("S-106", "Electronics Lab", 280, Decimal("4.00"), Space.Status.OCCUPIED, guilds[4]),
            ("S-107", "3D Printing Lab", 260, Decimal("4.00"), Space.Status.OCCUPIED, guilds[5]),
            ("S-108", "Jewelry Studio", 240, Decimal("4.25"), Space.Status.OCCUPIED, guilds[6]),
            ("S-109", "Screen Print Studio", 360, Decimal("3.50"), Space.Status.OCCUPIED, guilds[7]),
            ("S-110", "Private Studio A", 200, Decimal("4.50"), Space.Status.OCCUPIED, None),
            ("S-111", "Private Studio B", 180, Decimal("4.50"), Space.Status.AVAILABLE, None),
            ("S-112", "Large Open Studio", 600, Decimal("3.25"), Space.Status.AVAILABLE, None),
        ]
        for sid, name, sqft, rate, status, guild in studio_configs:
            space, _ = Space.objects.get_or_create(
                space_id=sid,
                defaults={
                    "name": name,
                    "space_type": Space.SpaceType.STUDIO,
                    "size_sqft": Decimal(str(sqft)),
                    "rate_per_sqft": rate,
                    "status": status,
                    "is_rentable": True,
                    "sublet_guild": guild,
                },
            )
            spaces.append(space)

        # Storage ST-201 to ST-208
        storage_configs = [
            ("ST-201", "Storage Unit A", 50, Space.Status.OCCUPIED),
            ("ST-202", "Storage Unit B", 50, Space.Status.OCCUPIED),
            ("ST-203", "Storage Unit C", 75, Space.Status.OCCUPIED),
            ("ST-204", "Storage Unit D", 75, Space.Status.AVAILABLE),
            ("ST-205", "Storage Unit E", 100, Space.Status.OCCUPIED),
            ("ST-206", "Storage Unit F", 100, Space.Status.AVAILABLE),
            ("ST-207", "Storage Unit G", 40, Space.Status.AVAILABLE),
            ("ST-208", "Storage Unit H", 40, Space.Status.OCCUPIED),
        ]
        for sid, name, sqft, status in storage_configs:
            space, _ = Space.objects.get_or_create(
                space_id=sid,
                defaults={
                    "name": name,
                    "space_type": Space.SpaceType.STORAGE,
                    "size_sqft": Decimal(str(sqft)),
                    "rate_per_sqft": Decimal("2.50"),
                    "status": status,
                    "is_rentable": True,
                },
            )
            spaces.append(space)

        # Parking P-301 to P-308
        for i in range(1, 9):
            sid = f"P-3{i:02d}"
            status = Space.Status.OCCUPIED if i <= 5 else Space.Status.AVAILABLE
            space, _ = Space.objects.get_or_create(
                space_id=sid,
                defaults={
                    "name": f"Parking Space {i}",
                    "space_type": Space.SpaceType.PARKING,
                    "manual_price": Decimal("50.00"),
                    "status": status,
                    "is_rentable": True,
                },
            )
            spaces.append(space)

        # Desks D-401 to D-408
        for i in range(1, 9):
            sid = f"D-4{i:02d}"
            status = Space.Status.OCCUPIED if i <= 6 else Space.Status.AVAILABLE
            space, _ = Space.objects.get_or_create(
                space_id=sid,
                defaults={
                    "name": f"Dedicated Desk {i}",
                    "space_type": Space.SpaceType.DESK,
                    "manual_price": Decimal("150.00"),
                    "status": status,
                    "is_rentable": True,
                },
            )
            spaces.append(space)

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(spaces)} spaces"))
        return spaces

    # -------------------------------------------------------------------------
    # Leases
    # -------------------------------------------------------------------------

    def _seed_leases(self, members: list, guilds: list, spaces: list) -> None:
        member_ct = ContentType.objects.get_for_model(Member)
        guild_ct = ContentType.objects.get_for_model(Guild)

        start = TODAY - timedelta(days=365)

        lease_data = [
            # Studios sublet to guilds
            (guild_ct, guilds[0].pk, spaces[0], Lease.LeaseType.ANNUAL, Decimal("1500.00"), Decimal("1500.00")),
            (guild_ct, guilds[0].pk, spaces[1], Lease.LeaseType.ANNUAL, Decimal("1312.50"), Decimal("1312.50")),
            (guild_ct, guilds[1].pk, spaces[2], Lease.LeaseType.ANNUAL, Decimal("1750.00"), Decimal("1750.00")),
            (guild_ct, guilds[2].pk, spaces[3], Lease.LeaseType.ANNUAL, Decimal("1425.00"), Decimal("1425.00")),
            (guild_ct, guilds[3].pk, spaces[4], Lease.LeaseType.ANNUAL, Decimal("1200.00"), Decimal("1200.00")),
            (guild_ct, guilds[4].pk, spaces[5], Lease.LeaseType.ANNUAL, Decimal("1120.00"), Decimal("1120.00")),
            (guild_ct, guilds[5].pk, spaces[6], Lease.LeaseType.ANNUAL, Decimal("1040.00"), Decimal("1040.00")),
            (guild_ct, guilds[6].pk, spaces[7], Lease.LeaseType.ANNUAL, Decimal("1020.00"), Decimal("1020.00")),
            (guild_ct, guilds[7].pk, spaces[8], Lease.LeaseType.ANNUAL, Decimal("1260.00"), Decimal("1260.00")),
            # Private studios to members
            (member_ct, members[0].pk, spaces[9], Lease.LeaseType.MONTH_TO_MONTH, Decimal("900.00"), Decimal("875.00")),
            # Storage units to members
            (
                member_ct,
                members[2].pk,
                spaces[12],
                Lease.LeaseType.MONTH_TO_MONTH,
                Decimal("125.00"),
                Decimal("125.00"),
            ),
            (
                member_ct,
                members[4].pk,
                spaces[13],
                Lease.LeaseType.MONTH_TO_MONTH,
                Decimal("125.00"),
                Decimal("125.00"),
            ),
            (
                member_ct,
                members[6].pk,
                spaces[14],
                Lease.LeaseType.MONTH_TO_MONTH,
                Decimal("187.50"),
                Decimal("187.50"),
            ),
            # Parking to members
            (member_ct, members[1].pk, spaces[20], Lease.LeaseType.MONTH_TO_MONTH, Decimal("50.00"), Decimal("50.00")),
            (member_ct, members[3].pk, spaces[21], Lease.LeaseType.MONTH_TO_MONTH, Decimal("50.00"), Decimal("50.00")),
            # Desks to members
            (
                member_ct,
                members[8].pk,
                spaces[28],
                Lease.LeaseType.MONTH_TO_MONTH,
                Decimal("150.00"),
                Decimal("150.00"),
            ),
            (
                member_ct,
                members[9].pk,
                spaces[29],
                Lease.LeaseType.MONTH_TO_MONTH,
                Decimal("150.00"),
                Decimal("150.00"),
            ),
            (
                member_ct,
                members[10].pk,
                spaces[30],
                Lease.LeaseType.MONTH_TO_MONTH,
                Decimal("150.00"),
                Decimal("150.00"),
            ),
        ]

        count = 0
        for ct, obj_id, space, lease_type, base_price, monthly_rent in lease_data:
            Lease.objects.get_or_create(
                content_type=ct,
                object_id=obj_id,
                space=space,
                defaults={
                    "lease_type": lease_type,
                    "base_price": base_price,
                    "monthly_rent": monthly_rent,
                    "start_date": start,
                    "deposit_required": base_price,
                    "deposit_paid_amount": base_price,
                    "deposit_paid_date": start,
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} leases"))

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    def _seed_tools(self, guilds: list) -> list:
        tools_data = [
            # Woodworking tools (guild_idx=0)
            (0, "Table Saw", "SawStop 10-inch contractor table saw", Decimal("3500.00"), True, True),
            (0, "Bandsaw", "14-inch bandsaw for curves and resawing", Decimal("800.00"), True, False),
            (0, "Drill Press", "Floor-standing drill press", Decimal("600.00"), True, False),
            (0, "Jointer", "6-inch benchtop jointer for edge work", Decimal("700.00"), True, False),
            (0, "Thickness Planer", "13-inch thickness planer", Decimal("500.00"), True, False),
            (0, "CNC Router", "ShapeOko 4 CNC router", Decimal("2000.00"), True, True),
            # Metalworking tools (guild_idx=1)
            (1, "MIG Welder", "Miller Millermatic 211 MIG welder", Decimal("1200.00"), True, True),
            (1, "TIG Welder", "Lincoln Electric Square Wave TIG 200", Decimal("2200.00"), True, True),
            (1, "Angle Grinder", "4.5-inch angle grinder", Decimal("150.00"), True, False),
            (1, "Metal Lathe", "12x36 metal lathe", Decimal("4000.00"), True, True),
            (1, "Plasma Cutter", "Hypertherm Powermax 45 plasma cutter", Decimal("2800.00"), True, True),
            (1, "Metal Bandsaw", "Horizontal/vertical metal cutting bandsaw", Decimal("1100.00"), True, False),
            # Ceramics tools (guild_idx=2)
            (2, "Pottery Wheel", "Brent electric pottery wheel", Decimal("1200.00"), True, True),
            (2, "Slab Roller", "North Star 26-inch slab roller", Decimal("800.00"), True, False),
            (2, "Electric Kiln", "L&L Easy-Fire electric kiln", Decimal("3000.00"), True, True),
            (2, "Clay Extruder", "Scott Creek horizontal extruder", Decimal("400.00"), True, False),
            # Textiles tools (guild_idx=3)
            (3, "Industrial Sewing Machine", "Juki DDL-8700 industrial sewing machine", Decimal("900.00"), True, True),
            (3, "Serger Machine", "Juki MO-654DE serger", Decimal("500.00"), True, True),
            (3, "Floor Loom", "Schacht 8-shaft floor loom", Decimal("3500.00"), True, False),
            (3, "Embroidery Machine", "Brother PE800 embroidery machine", Decimal("600.00"), True, True),
            # Electronics tools (guild_idx=4)
            (4, "Soldering Station", "Hakko FX-888D soldering station", Decimal("120.00"), True, False),
            (4, "Oscilloscope", "Rigol DS1054Z four-channel oscilloscope", Decimal("400.00"), True, False),
            (4, "3D Printer (Electronics)", "Bambu Lab P1S for enclosures", Decimal("700.00"), True, True),
            (4, "Laser Cutter", "xTool D1 Pro laser engraver/cutter", Decimal("800.00"), True, True),
            # 3D Printing tools (guild_idx=5)
            (5, "FDM Printer - Large", "Creality CR-10 Max large format printer", Decimal("600.00"), True, True),
            (5, "Resin Printer", "Elegoo Saturn 4 Ultra resin printer", Decimal("700.00"), True, True),
            (5, "FDM Printer - Standard", "Prusa MK4S standard printer", Decimal("800.00"), True, True),
            (5, "Post-Cure Station", "Elegoo Mercury Plus wash and cure station", Decimal("80.00"), False, False),
            # Jewelry tools (guild_idx=6)
            (6, "Flex Shaft", "Foredom flex shaft with handpiece", Decimal("450.00"), True, False),
            (6, "Rolling Mill", "Durston 110mm rolling mill", Decimal("1800.00"), True, False),
            (6, "Jewelers Torch", "Little Torch propane/oxygen system", Decimal("300.00"), True, False),
            (6, "Pickle Pot", "Presto pot with safety pickle", Decimal("50.00"), False, False),
            # Screen Printing tools (guild_idx=7)
            (7, "Screen Print Press", "Vastex V-1000 4-station press", Decimal("2500.00"), True, True),
            (7, "Exposure Unit", "Vastex EXP-2040 UV exposure unit", Decimal("800.00"), True, False),
            (7, "Flash Dryer", "Vastex D-100 infrared flash dryer", Decimal("600.00"), True, False),
            (7, "Heat Gun", "Wagner Spraytech heat gun", Decimal("60.00"), False, False),
            # Org-owned shared tools
            (None, "Shop Vac - Large", "Craftsman 16-gallon wet/dry vacuum", Decimal("150.00"), False, False),
            (None, "Air Compressor", "Ingersoll Rand 60-gallon air compressor", Decimal("800.00"), False, False),
            (None, "Forklift", "Toyota 5000 lb electric forklift", Decimal("12000.00"), False, False),
            (None, "Pressure Washer", "Sun Joe SPX4001 electric pressure washer", Decimal("200.00"), False, False),
            (None, "Bench Grinder", "Dewalt 8-inch bench grinder", Decimal("180.00"), True, False),
            (None, "Belt Sander", "JET 1x42 belt/disc combo sander", Decimal("300.00"), True, False),
            (None, "Core Drill", "Milwaukee M18 FUEL core drill", Decimal("450.00"), True, False),
            (None, "Impact Driver Set", "Milwaukee M18 impact driver kit", Decimal("280.00"), True, True),
            (None, "Paint Sprayer", "Fuji Semi-Pro 2 HVLP sprayer", Decimal("340.00"), True, True),
        ]

        tools = []
        for item in tools_data:
            guild_idx, name, desc, value, reservable, rentable = item
            guild = guilds[guild_idx] if guild_idx is not None else None
            owner_type = Tool.OwnerType.GUILD if guild else Tool.OwnerType.ORG
            tool, _ = Tool.objects.get_or_create(
                name=name,
                defaults={
                    "description": desc,
                    "estimated_value": value,
                    "guild": guild,
                    "owner_type": owner_type,
                    "is_reservable": reservable,
                    "is_rentable": rentable,
                },
            )
            tools.append(tool)

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(tools)} tools"))
        return tools

    # -------------------------------------------------------------------------
    # Tool Reservations
    # -------------------------------------------------------------------------

    def _seed_tool_reservations(self, tools: list, users: list) -> None:
        now = timezone.now()
        reservations = [
            (
                tools[0],
                users[0],
                now + timedelta(days=1),
                now + timedelta(days=1, hours=3),
                ToolReservation.Status.ACTIVE,
            ),
            (
                tools[6],
                users[7],
                now + timedelta(days=2),
                now + timedelta(days=2, hours=4),
                ToolReservation.Status.ACTIVE,
            ),
            (
                tools[12],
                users[13],
                now + timedelta(days=1),
                now + timedelta(days=1, hours=2),
                ToolReservation.Status.ACTIVE,
            ),
            (tools[16], users[3], now - timedelta(days=1), now - timedelta(hours=21), ToolReservation.Status.COMPLETED),
            (
                tools[23],
                users[9],
                now - timedelta(days=2),
                now - timedelta(days=2) + timedelta(hours=3),
                ToolReservation.Status.COMPLETED,
            ),
            (
                tools[24],
                users[4],
                now + timedelta(days=3),
                now + timedelta(days=3, hours=2),
                ToolReservation.Status.ACTIVE,
            ),
            (tools[32], users[2], now - timedelta(days=1), now - timedelta(hours=20), ToolReservation.Status.CANCELLED),
        ]
        count = 0
        for tool, user, starts, ends, status in reservations:
            ToolReservation.objects.get_or_create(
                tool=tool,
                user=user,
                defaults={"starts_at": starts, "ends_at": ends, "status": status},
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} tool reservations"))

    # -------------------------------------------------------------------------
    # Revenue Splits
    # -------------------------------------------------------------------------

    def _seed_revenue_splits(self) -> list:
        splits_data = [
            {
                "name": "Guild Workshop 70/30",
                "splits": [
                    {"entity_type": "guild", "entity_id": 1, "percentage": 70},
                    {"entity_type": "org", "entity_id": 0, "percentage": 30},
                ],
                "notes": "70% to hosting guild, 30% to organization",
            },
            {
                "name": "Class Revenue 60/40",
                "splits": [
                    {"entity_type": "user", "entity_id": 1, "percentage": 60},
                    {"entity_type": "org", "entity_id": 0, "percentage": 40},
                ],
                "notes": "60% to instructor, 40% to organization",
            },
            {
                "name": "Orientation Revenue 50/50",
                "splits": [
                    {"entity_type": "user", "entity_id": 1, "percentage": 50},
                    {"entity_type": "org", "entity_id": 0, "percentage": 50},
                ],
                "notes": "50% to orienter, 50% to organization",
            },
        ]
        splits = []
        for item in splits_data:
            split, _ = RevenueSplit.objects.get_or_create(
                name=item["name"],
                defaults={"splits": item["splits"], "notes": item["notes"]},
            )
            splits.append(split)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(splits)} revenue splits"))
        return splits

    # -------------------------------------------------------------------------
    # Rentables
    # -------------------------------------------------------------------------

    def _seed_rentables(self, tools: list, splits: list) -> list:
        rental_split = splits[0]
        rentables_data = [
            (tools[5], Rentable.RentalPeriod.DAYS, Decimal("75.00"), rental_split),  # CNC Router
            (tools[23], Rentable.RentalPeriod.DAYS, Decimal("50.00"), rental_split),  # Laser Cutter
            (tools[43], Rentable.RentalPeriod.DAYS, Decimal("40.00"), None),  # Paint Sprayer
            (tools[44], Rentable.RentalPeriod.DAYS, Decimal("25.00"), None),  # Impact Driver Set
            (tools[12], Rentable.RentalPeriod.HOURS, Decimal("15.00"), rental_split),  # Pottery Wheel
        ]
        rentables = []
        for tool, period, cost, split in rentables_data:
            rentable, _ = Rentable.objects.get_or_create(
                tool=tool,
                rental_period=period,
                defaults={"cost_per_period": cost, "revenue_split": split, "is_active": True},
            )
            rentables.append(rentable)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(rentables)} rentables"))
        return rentables

    # -------------------------------------------------------------------------
    # Orders
    # -------------------------------------------------------------------------

    def _seed_orders(self, users: list, splits: list) -> list:
        now = timezone.now()
        class_split = splits[1]
        orders_data = [
            (users[0], "Monthly membership dues", 30000, Order.Status.PAID, now - timedelta(days=30)),
            (users[1], "Studio rental - March", 150000, Order.Status.PAID, now - timedelta(days=30)),
            (users[2], "Storage unit rental", 12500, Order.Status.PAID, now - timedelta(days=30)),
            (users[3], "Monthly membership dues", 15000, Order.Status.PAID, now - timedelta(days=30)),
            (users[4], "Intro to Woodworking class", 7500, Order.Status.PAID, now - timedelta(days=20)),
            (users[5], "CNC Router rental - 2 days", 15000, Order.Status.BILLED, now - timedelta(days=10)),
            (users[6], "Monthly membership dues", 30000, Order.Status.ON_TAB, now - timedelta(days=5)),
            (users[7], "3D printing orientation", 2500, Order.Status.PAID, now - timedelta(days=15)),
            (users[8], "Desk rental - March", 15000, Order.Status.PAID, now - timedelta(days=30)),
            (users[9], "Pottery wheel rental - 3 hours", 4500, Order.Status.PAID, now - timedelta(days=7)),
            (users[10], "Day pass", 5000, Order.Status.PAID, now - timedelta(days=2)),
            (users[11], "Welding 101 class", 9500, Order.Status.BILLED, now - timedelta(days=3)),
            (users[12], "Monthly membership dues", 15000, Order.Status.ON_TAB, now - timedelta(days=1)),
            (users[13], "Ceramics orientation", 2500, Order.Status.PAID, now - timedelta(days=12)),
            (users[14], "T-Shirt purchase x2", 5000, Order.Status.FAILED, now - timedelta(days=4)),
        ]
        orders = []
        for user, desc, amount, status, issued_at in orders_data:
            order, _ = Order.objects.get_or_create(
                user=user,
                description=desc,
                defaults={
                    "amount": amount,
                    "status": status,
                    "issued_at": issued_at,
                    "revenue_split": class_split if "class" in desc.lower() else None,
                },
            )
            orders.append(order)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(orders)} orders"))
        return orders

    # -------------------------------------------------------------------------
    # Rentals
    # -------------------------------------------------------------------------

    def _seed_rentals(self, rentables: list, users: list, orders: list) -> None:
        now = timezone.now()
        rentals_data = [
            (
                rentables[0],
                users[4],
                now - timedelta(days=3),
                now - timedelta(days=1),
                Rental.Status.RETURNED,
                orders[4],
            ),
            (rentables[1], users[11], now - timedelta(days=2), now + timedelta(days=0), Rental.Status.ACTIVE, None),
            (rentables[2], users[6], now - timedelta(hours=5), now + timedelta(hours=19), Rental.Status.ACTIVE, None),
            (rentables[3], users[9], now - timedelta(days=1), now + timedelta(days=1), Rental.Status.ACTIVE, None),
            (
                rentables[4],
                users[13],
                now - timedelta(hours=4),
                now - timedelta(hours=1),
                Rental.Status.RETURNED,
                orders[13],
            ),
        ]
        count = 0
        for rentable, user, checked_out, due, status, order in rentals_data:
            Rental.objects.get_or_create(
                rentable=rentable,
                user=user,
                defaults={"checked_out_at": checked_out, "due_at": due, "status": status, "order": order},
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} rentals"))

    # -------------------------------------------------------------------------
    # Invoices
    # -------------------------------------------------------------------------

    def _seed_invoices(self, users: list) -> None:
        now = timezone.now()
        invoices_data = [
            (
                users[0],
                "in_0001",
                30000,
                30000,
                Invoice.Status.PAID,
                now - timedelta(days=30),
                now - timedelta(days=28),
            ),
            (
                users[1],
                "in_0002",
                150000,
                150000,
                Invoice.Status.PAID,
                now - timedelta(days=30),
                now - timedelta(days=27),
            ),
            (
                users[2],
                "in_0003",
                12500,
                12500,
                Invoice.Status.PAID,
                now - timedelta(days=30),
                now - timedelta(days=29),
            ),
            (
                users[3],
                "in_0004",
                15000,
                15000,
                Invoice.Status.PAID,
                now - timedelta(days=30),
                now - timedelta(days=28),
            ),
            (users[4], "in_0005", 30000, 0, Invoice.Status.OPEN, now - timedelta(days=5), None),
            (users[5], "in_0006", 15000, 0, Invoice.Status.OPEN, now - timedelta(days=10), None),
            (users[6], "in_0007", 30000, 0, Invoice.Status.DRAFT, now - timedelta(days=2), None),
            (
                users[7],
                "in_0008",
                37500,
                37500,
                Invoice.Status.PAID,
                now - timedelta(days=60),
                now - timedelta(days=58),
            ),
            (users[8], "in_0009", 15000, 0, Invoice.Status.VOID, now - timedelta(days=90), None),
            (users[9], "in_0010", 30000, 0, Invoice.Status.UNCOLLECTIBLE, now - timedelta(days=45), None),
        ]
        count = 0
        for user, stripe_id, amount_due, amount_paid, status, issued_at, paid_at in invoices_data:
            Invoice.objects.get_or_create(
                stripe_invoice_id=stripe_id,
                defaults={
                    "user": user,
                    "amount_due": amount_due,
                    "amount_paid": amount_paid,
                    "status": status,
                    "issued_at": issued_at,
                    "paid_at": paid_at,
                    "line_items": [{"description": "Monthly dues", "amount": amount_due}],
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} invoices"))

    # -------------------------------------------------------------------------
    # Payouts
    # -------------------------------------------------------------------------

    def _seed_payouts(self, users: list, guilds: list) -> None:
        period_start = date(2026, 1, 1)
        period_end = date(2026, 1, 31)

        payouts_data = [
            (Payout.PayeeType.USER, users[1].pk, 45000, Payout.Status.DISTRIBUTED),
            (Payout.PayeeType.USER, users[9].pk, 22000, Payout.Status.DISTRIBUTED),
            (Payout.PayeeType.GUILD, guilds[0].pk, 105000, Payout.Status.PENDING),
            (Payout.PayeeType.GUILD, guilds[1].pk, 87500, Payout.Status.PENDING),
            (Payout.PayeeType.USER, users[4].pk, 15000, Payout.Status.DISTRIBUTED),
        ]
        count = 0
        for payee_type, payee_id, amount, status in payouts_data:
            distributed_at = timezone.now() - timedelta(days=15) if status == Payout.Status.DISTRIBUTED else None
            Payout.objects.get_or_create(
                payee_type=payee_type,
                payee_id=payee_id,
                period_start=period_start,
                period_end=period_end,
                defaults={
                    "amount": amount,
                    "invoice_ids": [],
                    "status": status,
                    "distributed_at": distributed_at,
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} payouts"))

    # -------------------------------------------------------------------------
    # Subscription Plans
    # -------------------------------------------------------------------------

    def _seed_subscription_plans(self) -> list:
        plans_data = [
            {
                "name": "Monthly Membership",
                "description": "Standard monthly membership subscription",
                "price": Decimal("300.00"),
                "interval": SubscriptionPlan.Interval.MONTHLY,
                "plan_type": "membership",
            },
            {
                "name": "Annual Membership",
                "description": "Annual membership with two months free",
                "price": Decimal("3000.00"),
                "interval": SubscriptionPlan.Interval.YEARLY,
                "plan_type": "membership",
            },
            {
                "name": "Guild Access",
                "description": "Add-on subscription for dedicated guild access",
                "price": Decimal("50.00"),
                "interval": SubscriptionPlan.Interval.MONTHLY,
                "plan_type": "guild_access",
            },
        ]
        plans = []
        for item in plans_data:
            plan, _ = SubscriptionPlan.objects.get_or_create(
                name=item["name"],
                defaults={
                    "description": item["description"],
                    "price": item["price"],
                    "interval": item["interval"],
                    "plan_type": item["plan_type"],
                    "is_active": True,
                },
            )
            plans.append(plan)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(plans)} subscription plans"))
        return plans

    # -------------------------------------------------------------------------
    # Member Subscriptions
    # -------------------------------------------------------------------------

    def _seed_member_subscriptions(self, users: list, plans: list) -> None:
        monthly, annual, guild_access = plans
        now = timezone.now()
        subs_data = [
            (users[0], monthly, MemberSubscription.Status.ACTIVE, now - timedelta(days=400), None, None),
            (users[1], annual, MemberSubscription.Status.ACTIVE, now - timedelta(days=300), None, None),
            (users[2], monthly, MemberSubscription.Status.ACTIVE, now - timedelta(days=200), None, None),
            (users[3], monthly, MemberSubscription.Status.ACTIVE, now - timedelta(days=500), None, None),
            (users[4], monthly, MemberSubscription.Status.ACTIVE, now - timedelta(days=150), None, None),
            (users[5], guild_access, MemberSubscription.Status.ACTIVE, now - timedelta(days=80), None, None),
            (users[6], monthly, MemberSubscription.Status.PAST_DUE, now - timedelta(days=45), None, None),
            (users[7], annual, MemberSubscription.Status.ACTIVE, now - timedelta(days=600), None, None),
            (users[8], monthly, MemberSubscription.Status.ACTIVE, now - timedelta(days=320), None, None),
            (users[9], monthly, MemberSubscription.Status.ACTIVE, now - timedelta(days=550), None, None),
            (
                users[15],
                monthly,
                MemberSubscription.Status.CANCELLED,
                now - timedelta(days=800),
                now - timedelta(days=400),
                now - timedelta(days=400),
            ),
            (
                users[16],
                guild_access,
                MemberSubscription.Status.CANCELLED,
                now - timedelta(days=730),
                now - timedelta(days=365),
                now - timedelta(days=365),
            ),
        ]
        count = 0
        for user, plan, status, starts, ends, cancelled in subs_data:
            MemberSubscription.objects.get_or_create(
                user=user,
                subscription_plan=plan,
                defaults={
                    "starts_at": starts,
                    "status": status,
                    "ends_at": ends,
                    "cancelled_at": cancelled,
                    "next_billing_at": now + timedelta(days=30) if status == MemberSubscription.Status.ACTIVE else None,
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} member subscriptions"))

    # -------------------------------------------------------------------------
    # Discount Codes
    # -------------------------------------------------------------------------

    def _seed_discount_codes(self) -> list:
        codes_data = [
            ("WELCOME10", ClassDiscountCode.DiscountType.PERCENTAGE, Decimal("10.00"), True),
            ("MEMBER20", ClassDiscountCode.DiscountType.PERCENTAGE, Decimal("20.00"), True),
            ("HALFOFF", ClassDiscountCode.DiscountType.PERCENTAGE, Decimal("50.00"), True),
            ("FREE100", ClassDiscountCode.DiscountType.FIXED, Decimal("100.00"), True),
        ]
        codes = []
        for code, discount_type, value, is_active in codes_data:
            dc, _ = ClassDiscountCode.objects.get_or_create(
                code=code,
                defaults={"discount_type": discount_type, "discount_value": value, "is_active": is_active},
            )
            codes.append(dc)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(codes)} discount codes"))
        return codes

    # -------------------------------------------------------------------------
    # Maker Classes
    # -------------------------------------------------------------------------

    def _seed_maker_classes(
        self,
        guilds: list,
        users: list,
        splits: list,
        discount_codes: list,
    ) -> None:
        class_split = splits[1]
        now = timezone.now()

        classes_data: list[dict[str, Any]] = [
            {
                "name": "Intro to Woodworking",
                "description": "Learn the fundamentals of woodworking including tool safety, wood selection, and basic joinery.",
                "location": "Woodworking Studio A",
                "price": Decimal("75.00"),
                "max_students": 8,
                "guild_idx": 0,
                "instructor_idx": 1,
                "status": MakerClass.Status.PUBLISHED,
                "session_offset": 7,
            },
            {
                "name": "Welding 101",
                "description": "Introduction to MIG welding covering safety, equipment setup, and basic weld techniques.",
                "location": "Metalworking Studio",
                "price": Decimal("95.00"),
                "max_students": 6,
                "guild_idx": 1,
                "instructor_idx": 7,
                "status": MakerClass.Status.PUBLISHED,
                "session_offset": 14,
            },
            {
                "name": "Pottery Basics",
                "description": "An introductory wheel throwing class covering centering, opening, and pulling walls.",
                "location": "Ceramics Studio",
                "price": Decimal("65.00"),
                "max_students": 6,
                "guild_idx": 2,
                "instructor_idx": 13,
                "status": MakerClass.Status.PUBLISHED,
                "session_offset": 10,
            },
            {
                "name": "Sewing Machine Basics",
                "description": "Get comfortable with an industrial sewing machine. Cover threading, tension, and basic stitches.",
                "location": "Textiles Studio",
                "price": Decimal("45.00"),
                "max_students": 10,
                "guild_idx": 3,
                "instructor_idx": 3,
                "status": MakerClass.Status.PUBLISHED,
                "session_offset": 5,
            },
            {
                "name": "Arduino Workshop",
                "description": "Build your first microcontroller project using Arduino. No coding experience required.",
                "location": "Electronics Lab",
                "price": Decimal("55.00"),
                "max_students": 12,
                "guild_idx": 4,
                "instructor_idx": 9,
                "status": MakerClass.Status.PUBLISHED,
                "session_offset": 21,
            },
            {
                "name": "3D Printing Fundamentals",
                "description": "Learn to design, slice, and print your first 3D object. Covers FDM and basic resin printing.",
                "location": "3D Printing Lab",
                "price": Decimal("50.00"),
                "max_students": 8,
                "guild_idx": 5,
                "instructor_idx": 4,
                "status": MakerClass.Status.PUBLISHED,
                "session_offset": 12,
            },
            {
                "name": "Ring Making",
                "description": "Create a sterling silver ring from scratch using sawing, filing, soldering, and polishing.",
                "location": "Jewelry Studio",
                "price": Decimal("120.00"),
                "max_students": 6,
                "guild_idx": 6,
                "instructor_idx": 0,
                "status": MakerClass.Status.DRAFT,
                "session_offset": 30,
            },
            {
                "name": "Screen Printing T-Shirts",
                "description": "Design and print your own t-shirt using the single-color screen printing process.",
                "location": "Screen Print Studio",
                "price": Decimal("60.00"),
                "max_students": 8,
                "guild_idx": 7,
                "instructor_idx": 2,
                "status": MakerClass.Status.PUBLISHED,
                "session_offset": 9,
            },
        ]

        for item in classes_data:
            maker_class, created = MakerClass.objects.get_or_create(
                name=item["name"],
                defaults={
                    "description": item["description"],
                    "location": item["location"],
                    "price": item["price"],
                    "max_students": item["max_students"],
                    "guild": guilds[item["guild_idx"]],
                    "revenue_split": class_split,
                    "status": item["status"],
                    "created_by": users[item["instructor_idx"]],
                    "published_at": now - timedelta(days=30) if item["status"] == MakerClass.Status.PUBLISHED else None,
                },
            )
            if created:
                maker_class.instructors.add(users[item["instructor_idx"]])
                maker_class.discount_codes.add(discount_codes[0], discount_codes[1])

                session_date = now + timedelta(days=item["session_offset"])
                ClassSession.objects.create(
                    maker_class=maker_class,
                    starts_at=session_date.replace(hour=10, minute=0),
                    ends_at=session_date.replace(hour=14, minute=0),
                )

                # Seed 2-3 students per published class
                if item["status"] == MakerClass.Status.PUBLISHED:
                    student_indices = [i % len(users) for i in range(2, 5)]
                    for si in student_indices:
                        Student.objects.get_or_create(
                            maker_class=maker_class,
                            email=users[si].email,
                            defaults={
                                "user": users[si],
                                "name": f"{users[si].first_name} {users[si].last_name}",
                                "amount_paid": item["price"],
                            },
                        )

        self.stdout.write(self.style.SUCCESS("Seeded 8 maker classes"))

    # -------------------------------------------------------------------------
    # Orientations
    # -------------------------------------------------------------------------

    def _seed_orientations(
        self,
        guilds: list,
        tools: list,
        users: list,
        splits: list,
        orders: list,
    ) -> None:
        orientation_split = splits[2]
        now = timezone.now()

        # Map guild index to primary tool index and orienter user index
        orientation_data = [
            (
                0,
                "Woodworking Orientation",
                "Required orientation for all woodworking equipment.",
                60,
                Decimal("25.00"),
                [tools[0], tools[1]],
                users[1],
            ),
            (
                1,
                "Metalworking Orientation",
                "Required orientation for all welding and metal equipment.",
                90,
                Decimal("35.00"),
                [tools[6], tools[10]],
                users[7],
            ),
            (
                2,
                "Ceramics Orientation",
                "Required orientation for pottery wheels and kilns.",
                45,
                Decimal("20.00"),
                [tools[12], tools[14]],
                users[13],
            ),
            (
                3,
                "Textiles Orientation",
                "Required orientation for industrial sewing machines.",
                30,
                Decimal("15.00"),
                [tools[16], tools[17]],
                users[3],
            ),
            (
                4,
                "Electronics Orientation",
                "Required orientation for electronics lab equipment.",
                60,
                Decimal("25.00"),
                [tools[20], tools[23]],
                users[9],
            ),
            (
                5,
                "3D Printing Orientation",
                "Required orientation for FDM and resin printers.",
                60,
                Decimal("25.00"),
                [tools[24], tools[25]],
                users[4],
            ),
            (
                6,
                "Jewelry Orientation",
                "Required orientation for torch and rolling mill.",
                45,
                Decimal("20.00"),
                [tools[28], tools[29]],
                users[0],
            ),
            (
                7,
                "Screen Printing Orientation",
                "Required orientation for the screen print press.",
                45,
                Decimal("20.00"),
                [tools[32], tools[33]],
                users[2],
            ),
        ]

        count = 0
        for guild_idx, name, desc, duration, price, orient_tools, orienter in orientation_data:
            orientation, created = Orientation.objects.get_or_create(
                name=name,
                defaults={
                    "guild": guilds[guild_idx],
                    "description": desc,
                    "duration_minutes": duration,
                    "price": price,
                    "revenue_split": orientation_split,
                    "is_active": True,
                },
            )
            if created:
                orientation.tools.set(orient_tools)
                orientation.orienters.add(orienter)

                # Create 2 scheduled orientations per orientation
                for day_offset in [3, 10]:
                    scheduled_at = now + timedelta(days=day_offset)
                    user = users[(guild_idx * 2 + day_offset) % len(users)]
                    ScheduledOrientation.objects.get_or_create(
                        orientation=orientation,
                        user=user,
                        defaults={"scheduled_at": scheduled_at, "status": ScheduledOrientation.Status.PENDING},
                    )
            count += 1

        self.stdout.write(self.style.SUCCESS(f"Seeded {count} orientations with scheduled sessions"))

    # -------------------------------------------------------------------------
    # Leads
    # -------------------------------------------------------------------------

    def _seed_leads(self) -> None:
        leads_data = [
            (
                "Marcus Thompson",
                "marcus.t@email.com",
                "503-555-1001",
                Lead.Status.NEW,
                "Instagram",
                "Interested in woodworking and metalworking",
            ),
            (
                "Sofia Andersen",
                "sofia.a@email.com",
                "503-555-1002",
                Lead.Status.CONTACTED,
                "Website",
                "Looking for ceramics studio space",
            ),
            (
                "Yusuf Ibrahim",
                "yusuf.i@email.com",
                "503-555-1003",
                Lead.Status.TOURED,
                "Referral",
                "Jewelry maker seeking dedicated bench",
            ),
            (
                "Hana Takahashi",
                "hana.t@email.com",
                "503-555-1004",
                Lead.Status.CONVERTED,
                "Open House",
                "Converted - now a full-time member",
            ),
            (
                "Bryce Coleman",
                "bryce.c@email.com",
                "503-555-1005",
                Lead.Status.LOST,
                "Google",
                "Looking for cheaper option",
            ),
            (
                "Fatima Al-Rashid",
                "fatima.ar@email.com",
                "503-555-1006",
                Lead.Status.NEW,
                "Facebook",
                "Interested in screen printing",
            ),
            (
                "Diego Vargas",
                "diego.v@email.com",
                "503-555-1007",
                Lead.Status.CONTACTED,
                "Word of Mouth",
                "Electronics hobbyist",
            ),
            ("Amara Osei", "amara.o@email.com", "503-555-1008", Lead.Status.TOURED, "Meetup", "3D printing enthusiast"),
            ("Lars Eriksson", "lars.e@email.com", "503-555-1009", Lead.Status.NEW, "Website", "Textile artist"),
            (
                "Mei-Ling Wu",
                "meiling.w@email.com",
                "503-555-1010",
                Lead.Status.CONTACTED,
                "Instagram",
                "Wants studio space for ceramics",
            ),
            (
                "Kwame Asante",
                "kwame.a@email.com",
                "503-555-1011",
                Lead.Status.CONVERTED,
                "Referral",
                "Converted - part-time member",
            ),
            (
                "Ingrid Sorensen",
                "ingrid.s@email.com",
                "503-555-1012",
                Lead.Status.LOST,
                "Cold Email",
                "Budget constraints",
            ),
        ]
        count = 0
        for name, email, phone, status, source, interests in leads_data:
            Lead.objects.get_or_create(
                email=email,
                defaults={
                    "name": name,
                    "phone": phone,
                    "status": status,
                    "source": source,
                    "interests": interests,
                    "greenlighted_for_membership": status == Lead.Status.CONVERTED,
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} leads"))

    # -------------------------------------------------------------------------
    # Tours
    # -------------------------------------------------------------------------

    def _seed_tours(self) -> None:
        now = timezone.now()
        leads = list(Lead.objects.all())
        if not leads:  # pragma: no cover
            self.stdout.write(self.style.SUCCESS("Seeded 0 tours (no leads found)"))
            return

        tours_data = [
            (leads[1], now - timedelta(days=5), Tour.Status.COMPLETED, "Great tour, very interested in ceramics"),
            (leads[2], now - timedelta(days=3), Tour.Status.COMPLETED, "Toured jewelry studio, loved it"),
            (leads[3], now - timedelta(days=30), Tour.Status.COMPLETED, "Converted to member after tour"),
            (leads[0], now + timedelta(days=2), Tour.Status.SCHEDULED, ""),
            (leads[5], now + timedelta(days=4), Tour.Status.SCHEDULED, ""),
            (leads[7], now - timedelta(days=1), Tour.Status.CLAIMED, ""),
            (leads[8], now - timedelta(days=10), Tour.Status.CANCELLED, "Lead cancelled last minute"),
            (leads[10], now - timedelta(days=45), Tour.Status.COMPLETED, "Converted to part-time member"),
        ]
        count = 0
        for lead, scheduled_at, status, notes in tours_data:
            completed_at = scheduled_at if status == Tour.Status.COMPLETED else None
            Tour.objects.get_or_create(
                lead=lead,
                defaults={
                    "scheduled_at": scheduled_at,
                    "status": status,
                    "completion_notes": notes,
                    "completed_at": completed_at,
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} tours"))

    # -------------------------------------------------------------------------
    # Events
    # -------------------------------------------------------------------------

    def _seed_events(self, guilds: list, users: list) -> None:
        now = timezone.now()
        events_data = [
            {
                "name": "Open House",
                "description": "Monthly open house event for prospective members to tour the space and meet our community.",
                "starts_at": now + timedelta(days=15),
                "ends_at": now + timedelta(days=15, hours=3),
                "location": "Past Lives Makerspace - Main Hall",
                "is_recurring": True,
                "recurrence_rule": "FREQ=MONTHLY;BYDAY=3SA",
                "is_published": True,
                "guild": None,
                "creator": users[0],
            },
            {
                "name": "Gallery Night",
                "description": "Show off your projects and creations at our quarterly gallery night. Food and drinks provided.",
                "starts_at": now + timedelta(days=30),
                "ends_at": now + timedelta(days=30, hours=4),
                "location": "Past Lives Makerspace - All Studios",
                "is_recurring": False,
                "recurrence_rule": "",
                "is_published": True,
                "guild": None,
                "creator": users[1],
            },
            {
                "name": "Maker Faire Prep Workshop",
                "description": "Workshop to help members prepare projects for the Portland Mini Maker Faire.",
                "starts_at": now + timedelta(days=45),
                "ends_at": now + timedelta(days=45, hours=5),
                "location": "Woodworking Studio A",
                "is_recurring": False,
                "recurrence_rule": "",
                "is_published": True,
                "guild": guilds[0],
                "creator": users[1],
            },
            {
                "name": "Workshop Weekend",
                "description": "Two-day intensive workshop weekend featuring multiple classes and hands-on sessions.",
                "starts_at": now + timedelta(days=60),
                "ends_at": now + timedelta(days=62),
                "location": "Past Lives Makerspace",
                "is_recurring": False,
                "recurrence_rule": "",
                "is_published": False,
                "guild": None,
                "creator": users[9],
            },
        ]
        count = 0
        for item in events_data:
            Event.objects.get_or_create(
                name=item["name"],
                defaults={
                    "starts_at": item["starts_at"],
                    "description": item["description"],
                    "ends_at": item["ends_at"],
                    "location": item["location"],
                    "is_recurring": item["is_recurring"],
                    "recurrence_rule": item["recurrence_rule"],
                    "is_published": item["is_published"],
                    "guild": item["guild"],
                    "created_by": item["creator"],
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} events"))

    # -------------------------------------------------------------------------
    # Buyables
    # -------------------------------------------------------------------------

    def _seed_buyables(self, guilds: list, splits: list) -> list:
        guild_split = splits[0]
        buyables_data = [
            (
                "Day Pass",
                "Single-day access to the makerspace and all common areas.",
                Decimal("25.00"),
                True,
                None,
                None,
            ),
            ("Guest Pass", "Bring a guest for a day with your active membership.", Decimal("15.00"), True, None, None),
            ("Locker Rental (Monthly)", "Secure locker rental for one month.", Decimal("20.00"), True, None, None),
            (
                "Past Lives T-Shirt",
                "Official Past Lives Makerspace t-shirt, unisex fit.",
                Decimal("25.00"),
                True,
                None,
                guild_split,
            ),
            ("Sticker Pack", "Set of 5 Past Lives Makerspace stickers.", Decimal("8.00"), True, None, None),
        ]
        buyables = []
        for name, desc, price, is_active, guild, split in buyables_data:
            buyable, _ = Buyable.objects.get_or_create(
                name=name,
                defaults={
                    "description": desc,
                    "unit_price": price,
                    "is_active": is_active,
                    "guild": guild,
                    "revenue_split": split,
                },
            )
            buyables.append(buyable)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(buyables)} buyables"))
        return buyables

    # -------------------------------------------------------------------------
    # Buyable Purchases
    # -------------------------------------------------------------------------

    def _seed_buyable_purchases(self, buyables: list, users: list, orders: list) -> None:
        now = timezone.now()
        purchases_data = [
            (buyables[0], users[10], 1, now - timedelta(days=2), orders[10]),
            (buyables[0], users[5], 1, now - timedelta(days=5), None),
            (buyables[0], users[15], 1, now - timedelta(days=10), None),
            (buyables[0], users[16], 1, now - timedelta(days=8), None),
            (buyables[1], users[0], 1, now - timedelta(days=3), None),
            (buyables[1], users[2], 1, now - timedelta(days=7), None),
            (buyables[2], users[4], 1, now - timedelta(days=30), None),
            (buyables[2], users[8], 1, now - timedelta(days=25), None),
            (buyables[2], users[11], 1, now - timedelta(days=20), None),
            (buyables[3], users[0], 1, now - timedelta(days=15), None),
            (buyables[3], users[6], 2, now - timedelta(days=4), orders[14]),
            (buyables[3], users[9], 1, now - timedelta(days=12), None),
            (buyables[3], users[12], 1, now - timedelta(days=20), None),
            (buyables[4], users[1], 2, now - timedelta(days=18), None),
            (buyables[4], users[3], 1, now - timedelta(days=9), None),
            (buyables[4], users[5], 1, now - timedelta(days=6), None),
            (buyables[4], users[7], 3, now - timedelta(days=22), None),
            (buyables[4], users[13], 2, now - timedelta(days=14), None),
            (buyables[0], users[18], 1, now - timedelta(days=1), None),
            (buyables[3], users[19], 1, now - timedelta(days=3), None),
        ]
        count = 0
        for buyable, user, qty, purchased_at, order in purchases_data:
            BuyablePurchase.objects.get_or_create(
                buyable=buyable,
                user=user,
                defaults={"purchased_at": purchased_at, "quantity": qty, "order": order},
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} buyable purchases"))

    # -------------------------------------------------------------------------
    # Member Schedules
    # -------------------------------------------------------------------------

    def _seed_member_schedules(self, users: list) -> None:
        schedule_data = [
            (users[0], [(1, time(9, 0), time(17, 0)), (3, time(9, 0), time(17, 0)), (5, time(10, 0), time(14, 0))]),
            (users[1], [(2, time(8, 0), time(16, 0)), (4, time(8, 0), time(16, 0))]),
            (users[2], [(1, time(18, 0), time(21, 0)), (3, time(18, 0), time(21, 0)), (6, time(10, 0), time(15, 0))]),
            (users[3], [(0, time(14, 0), time(18, 0)), (2, time(14, 0), time(18, 0)), (4, time(14, 0), time(18, 0))]),
            (users[4], [(1, time(7, 0), time(9, 0)), (2, time(7, 0), time(9, 0)), (5, time(9, 0), time(17, 0))]),
            (users[5], [(6, time(11, 0), time(17, 0)), (0, time(12, 0), time(17, 0))]),
            (users[6], [(3, time(19, 0), time(22, 0)), (4, time(19, 0), time(22, 0)), (5, time(15, 0), time(20, 0))]),
            (users[7], [(1, time(10, 0), time(18, 0)), (2, time(10, 0), time(18, 0)), (3, time(10, 0), time(18, 0))]),
            (users[8], [(2, time(9, 0), time(12, 0)), (4, time(9, 0), time(12, 0)), (6, time(9, 0), time(14, 0))]),
            (users[9], [(1, time(8, 0), time(17, 0)), (2, time(8, 0), time(17, 0)), (4, time(8, 0), time(17, 0))]),
        ]
        count = 0
        for user, blocks in schedule_data:
            schedule, _ = MemberSchedule.objects.get_or_create(user=user)
            for day, start, end in blocks:
                ScheduleBlock.objects.get_or_create(
                    member_schedule=schedule,
                    day_of_week=day,
                    start_time=start,
                    defaults={"end_time": end, "is_recurring": True},
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded 10 member schedules with {count} schedule blocks"))

    # -------------------------------------------------------------------------
    # Tool Documents
    # -------------------------------------------------------------------------

    def _seed_tool_documents(self, tools: list, users: list) -> None:
        tool_ct = ContentType.objects.get_for_model(Tool)
        docs_data = [
            (tools[0], "Table Saw Safety Manual", users[1]),
            (tools[6], "MIG Welder Operation Guide", users[7]),
            (tools[10], "Plasma Cutter Safety Guide", users[7]),
            (tools[14], "Kiln Safety and Operation", users[13]),
            (tools[23], "Laser Cutter Material Guidelines", users[9]),
        ]
        count = 0
        for tool, name, uploader in docs_data:
            doc, created = Document.objects.get_or_create(
                content_type=tool_ct,
                object_id=tool.pk,
                name=name,
                defaults={"uploaded_by": uploader},
            )
            if created:
                doc.file_path.save(
                    f"{name.lower().replace(' ', '_')}.pdf",
                    ContentFile(b"placeholder"),
                    save=True,
                )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} tool documents"))
