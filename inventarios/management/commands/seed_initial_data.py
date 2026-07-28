from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from inventarios.models import AppSetting, PointOfSale, Profile


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
        call_command("cargar_catalogo_picanha", stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Datos iniciales creados o actualizados."))
        self.stdout.write("Punto de venta: lacentral@picanhaparrilla.com / PicanhaCentral2026!")
        self.stdout.write("Administrador: contacto@picanhaparrilla.com / PicanhaAdmin2026!")
        self.stdout.write(self.style.WARNING("Cambia ambas contraseñas antes de usar en producción."))
