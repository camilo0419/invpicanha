from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from inventarios.models import AppSetting, PointOfSale, Product, Profile


class Command(BaseCommand):
    help = "Crea o actualiza los datos iniciales sin duplicarlos."

    @transaction.atomic
    def handle(self, *args, **options):
        point, _ = PointOfSale.objects.update_or_create(
            code="CENTRAL",
            defaults={
                "name": "La Central",
                "active": True,
                "general_frequency": "SEMANAL",
            },
        )
        user_model = get_user_model()
        users = [
            (
                "lacentral@picanhaparrilla.com",
                "PicanhaCentral2026!",
                Profile.POS,
            ),
            (
                "contacto@picanhaparrilla.com",
                "PicanhaAdmin2026!",
                Profile.ADMIN,
            ),
        ]
        for username, password, role in users:
            user, created = user_model.objects.get_or_create(
                username=username,
                defaults={"email": username},
            )
            user.email = username
            user.is_staff = False
            user.is_superuser = False
            user.is_active = True
            if created or not user.has_usable_password():
                user.set_password(password)
            user.save()
            Profile.objects.update_or_create(
                user=user,
                defaults={"role": role, "point": point, "active": True},
            )

        AppSetting.get_solo()
        products = [
            ("CAR-001", "Picanha", "Carnes", "Kg", True, 5, 12, 45),
            ("CAR-002", "Punta de anca", "Carnes", "Kg", True, 4, 10, 35),
            ("LAC-001", "Leche", "Lácteos", "Litro", True, 2, 6, 30),
            ("LAC-002", "Queso parmesano", "Lácteos", "Kg", True, 1, 3, 12),
            ("BEB-001", "Pilsen", "Cervezas", "Unidad", True, 6, 18, 100),
            ("BEB-002", "Gaseosa", "Bebidas", "Unidad", True, 8, 20, 120),
            ("INS-001", "Pasta de tomate", "Insumos", "Kg", True, 2, 5, 25),
            ("EMP-001", "Servilletas", "Empaques", "Paquete", False, 2, 5, 30),
            ("ASE-001", "Detergente", "Aseo", "Litro", False, 1, 3, 15),
        ]
        for order, (code, name, category, unit, daily, critical, minimum, maximum) in enumerate(
            products, 10
        ):
            Product.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "category": category,
                    "unit": unit,
                    "active": True,
                    "include_daily": daily,
                    "include_general": True,
                    "critical_qty": critical,
                    "minimum_qty": minimum,
                    "maximum_qty": maximum,
                    "display_order": order,
                    "allows_decimals": unit in ["Kg", "Litro"],
                },
            )
        self.stdout.write(self.style.SUCCESS("Datos iniciales creados o actualizados."))
        self.stdout.write("Punto de venta: lacentral@picanhaparrilla.com / PicanhaCentral2026!")
        self.stdout.write("Administrador: contacto@picanhaparrilla.com / PicanhaAdmin2026!")
        self.stdout.write(self.style.WARNING("Cambia ambas contraseñas antes de usar en producción."))
