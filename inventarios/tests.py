from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Alert, AuditLog, Inventory, InventoryItem, PointOfSale, Product, Profile
from .services import classify_quantity, create_inventory, finalize_inventory


class InventoryTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.central, _ = PointOfSale.objects.update_or_create(
            code="CENTRAL", defaults={"name": "La Central"}
        )
        cls.other_point = PointOfSale.objects.create(name="Otro punto", code="OTRO")
        cls.pos = user_model.objects.create_user(
            "lacentral@picanhaparrilla.com", password="TestPass123!"
        )
        cls.admin = user_model.objects.create_user(
            "contacto@picanhaparrilla.com", password="TestPass123!"
        )
        cls.other_pos = user_model.objects.create_user("otro@example.com", password="TestPass123!")
        Profile.objects.create(user=cls.pos, role=Profile.POS, point=cls.central)
        Profile.objects.create(user=cls.admin, role=Profile.ADMIN, point=cls.central)
        Profile.objects.create(user=cls.other_pos, role=Profile.POS, point=cls.other_point)
        cls.daily_product = Product.objects.create(
            code="D-001",
            name="Producto diario",
            category="Pruebas",
            unit="Unidad",
            include_daily=True,
            include_general=True,
            allows_decimals=False,
            critical_qty=2,
            minimum_qty=5,
            maximum_qty=10,
            require_observation_low=True,
            require_observation_high=True,
        )
        cls.general_product = Product.objects.create(
            code="G-001",
            name="Producto general",
            category="Pruebas",
            unit="Kg",
            include_daily=False,
            include_general=True,
            critical_qty=1,
            minimum_qty=3,
            maximum_qty=8,
            require_observation_low=False,
            require_observation_high=False,
        )

    def login_pos(self):
        self.client.login(username=self.pos.username, password="TestPass123!")

    def login_admin(self):
        self.client.login(username=self.admin.username, password="TestPass123!")

    def inventory_post(self, inventory, quantities, action="save", observations=None):
        observations = observations or {}
        data = {"action": action, "general_observation": "Conteo de prueba"}
        for item in inventory.items.all():
            value = quantities.get(item.product_code)
            data[f"qty_{item.pk}"] = "" if value is None else str(value)
            data[f"obs_{item.pk}"] = observations.get(item.product_code, "")
        return self.client.post(reverse("inventory_fill", args=[inventory.pk]), data)


class AuthenticationAndPermissionTests(InventoryTestBase):
    def test_login_pos_and_admin(self):
        for user in (self.pos, self.admin):
            response = self.client.post(
                reverse("login"),
                {"username": user.username, "password": "TestPass123!"},
            )
            self.assertRedirects(response, reverse("dashboard"))
            self.client.logout()

    def test_users_are_not_staff_or_superusers(self):
        self.assertFalse(self.pos.is_staff)
        self.assertFalse(self.pos.is_superuser)
        self.assertFalse(self.admin.is_staff)
        self.assertFalse(self.admin.is_superuser)

    def test_pos_cannot_access_admin_sections(self):
        self.login_pos()
        for url in [reverse("products"), reverse("alerts"), reverse("audit"), reverse("settings")]:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_admin_can_access_admin_sections(self):
        self.login_admin()
        for url in [reverse("products"), reverse("alerts"), reverse("audit"), reverse("settings")]:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_idor_protection_between_points(self):
        inventory, _ = create_inventory(self.other_pos, Inventory.DAILY)
        self.login_pos()
        self.assertEqual(
            self.client.get(reverse("inventory_detail", args=[inventory.pk])).status_code, 404
        )
        self.assertEqual(
            self.client.get(reverse("inventory_fill", args=[inventory.pk])).status_code, 404
        )

    def test_logout_requires_post(self):
        self.login_pos()
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))

    def test_open_redirect_is_rejected(self):
        response = self.client.post(
            reverse("login") + "?next=https://evil.example/",
            {"username": self.pos.username, "password": "TestPass123!"},
        )
        self.assertRedirects(response, reverse("dashboard"))


class ClassificationTests(InventoryTestBase):
    def test_all_classifications_and_zero(self):
        values = [
            (None, InventoryItem.NOT_COUNTED),
            (Decimal("0"), InventoryItem.CRITICAL),
            (Decimal("2"), InventoryItem.CRITICAL),
            (Decimal("3"), InventoryItem.LOW),
            (Decimal("5"), InventoryItem.NORMAL),
            (Decimal("11"), InventoryItem.HIGH),
        ]
        for quantity, expected in values:
            with self.subTest(quantity=quantity):
                self.assertEqual(classify_quantity(quantity, 2, 5, 10), expected)

    def test_incomplete_rules_are_no_rule(self):
        self.assertEqual(classify_quantity(5, None, 5, 10), InventoryItem.NO_RULE)
        self.assertEqual(classify_quantity(5, 2, None, 10), InventoryItem.NO_RULE)

    def test_product_rejects_inconsistent_limits(self):
        product = Product(
            code="BAD", name="Inválido", unit="Unidad", critical_qty=6, minimum_qty=5
        )
        with self.assertRaises(ValidationError):
            product.full_clean()


class InventoryFlowTests(InventoryTestBase):
    def test_create_daily_and_general_with_correct_products(self):
        daily, created = create_inventory(self.pos, Inventory.DAILY)
        general, general_created = create_inventory(self.pos, Inventory.GENERAL)
        self.assertTrue(created)
        self.assertTrue(general_created)
        self.assertEqual(list(daily.items.values_list("product_code", flat=True)), ["D-001"])
        self.assertEqual(general.items.count(), 2)

    def test_start_is_post_only_and_reuses_same_day_inventory(self):
        self.login_pos()
        url = reverse("inventory_start", args=["diario"])
        self.assertEqual(self.client.get(url).status_code, 405)
        first = self.client.post(url)
        second = self.client.post(url)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(Inventory.objects.filter(inventory_type=Inventory.DAILY).count(), 1)

    def test_save_draft_and_zero_is_counted(self):
        inventory, _ = create_inventory(self.pos, Inventory.DAILY)
        self.login_pos()
        response = self.inventory_post(inventory, {"D-001": 0})
        self.assertRedirects(response, reverse("inventory_fill", args=[inventory.pk]))
        inventory.refresh_from_db()
        item = inventory.items.get()
        self.assertEqual(inventory.total_counted, 1)
        self.assertEqual(item.quantity, 0)
        self.assertEqual(item.result, InventoryItem.CRITICAL)

    def test_empty_is_not_counted_and_cannot_finalize(self):
        inventory, _ = create_inventory(self.pos, Inventory.DAILY)
        self.login_pos()
        response = self.inventory_post(inventory, {"D-001": None}, action="finalize")
        self.assertEqual(response.status_code, 200)
        inventory.refresh_from_db()
        self.assertFalse(inventory.locked)
        self.assertEqual(inventory.total_counted, 0)

    def test_required_observation_blocks_finalization(self):
        inventory, _ = create_inventory(self.pos, Inventory.DAILY)
        self.login_pos()
        response = self.inventory_post(inventory, {"D-001": 1}, action="finalize")
        self.assertEqual(response.status_code, 200)
        inventory.refresh_from_db()
        self.assertFalse(inventory.locked)

    def test_finalize_blocks_inventory_and_creates_alert(self):
        inventory, _ = create_inventory(self.pos, Inventory.DAILY)
        self.login_pos()
        response = self.inventory_post(
            inventory,
            {"D-001": 1},
            action="finalize",
            observations={"D-001": "Compra requerida"},
        )
        self.assertRedirects(response, reverse("inventory_detail", args=[inventory.pk]))
        inventory.refresh_from_db()
        self.assertTrue(inventory.locked)
        self.assertEqual(inventory.state, Inventory.FINAL_ALERT)
        self.assertEqual(inventory.total_critical, 1)
        self.assertEqual(inventory.alerts.filter(alert_type=Alert.PRODUCT_CRITICAL).count(), 1)

    def test_pos_cannot_modify_finalized_inventory(self):
        inventory, _ = create_inventory(self.pos, Inventory.DAILY)
        item = inventory.items.get()
        item.quantity = 5
        item.save()
        finalize_inventory(inventory, self.pos)
        self.login_pos()
        response = self.client.post(
            reverse("inventory_fill", args=[inventory.pk]),
            {f"qty_{item.pk}": "9", "action": "save"},
        )
        self.assertRedirects(response, reverse("inventory_detail", args=[inventory.pk]))
        item.refresh_from_db()
        self.assertEqual(item.quantity, 5)

    def test_admin_reopens_edits_and_refinalizes_without_duplicate_product_alerts(self):
        inventory, _ = create_inventory(self.pos, Inventory.DAILY)
        item = inventory.items.get()
        item.quantity = 1
        item.observation = "Inicial"
        item.save()
        finalize_inventory(inventory, self.pos)
        self.login_admin()
        response = self.client.post(reverse("inventory_reopen", args=[inventory.pk]))
        self.assertRedirects(response, reverse("inventory_detail", args=[inventory.pk]))
        inventory.refresh_from_db()
        self.assertEqual(inventory.state, Inventory.REOPENED)
        self.assertFalse(inventory.locked)
        self.inventory_post(
            inventory,
            {"D-001": 11},
            action="finalize",
            observations={"D-001": "Exceso revisado"},
        )
        inventory.refresh_from_db()
        self.assertTrue(inventory.locked)
        self.assertEqual(inventory.alerts.filter(alert_type=Alert.PRODUCT_HIGH).count(), 1)
        self.assertEqual(inventory.alerts.filter(alert_type=Alert.PRODUCT_CRITICAL).count(), 0)
        self.assertEqual(inventory.alerts.filter(alert_type=Alert.INVENTORY_REOPENED).count(), 1)

    def test_pos_cannot_reopen(self):
        inventory, _ = create_inventory(self.pos, Inventory.DAILY)
        item = inventory.items.get()
        item.quantity = 5
        item.save()
        finalize_inventory(inventory, self.pos)
        self.login_pos()
        self.assertEqual(
            self.client.post(reverse("inventory_reopen", args=[inventory.pk])).status_code, 403
        )

    def test_admin_can_cancel_with_reason(self):
        inventory, _ = create_inventory(self.pos, Inventory.DAILY)
        self.login_admin()
        response = self.client.post(
            reverse("inventory_cancel", args=[inventory.pk]), {"reason": "Conteo duplicado"}
        )
        self.assertRedirects(response, reverse("inventory_detail", args=[inventory.pk]))
        inventory.refresh_from_db()
        self.assertEqual(inventory.state, Inventory.CANCELLED)
        self.assertTrue(inventory.locked)
        self.assertEqual(inventory.cancellation_reason, "Conteo duplicado")
        self.assertTrue(inventory.alerts.filter(alert_type=Alert.INVENTORY_CANCELLED).exists())

    def test_history_visible_by_point_and_all_for_admin(self):
        own, _ = create_inventory(self.pos, Inventory.DAILY)
        other, _ = create_inventory(self.other_pos, Inventory.DAILY)
        self.login_pos()
        response = self.client.get(reverse("inventory_list"))
        self.assertContains(response, own.point.name)
        self.assertNotContains(response, other.point.name)
        self.client.logout()
        self.login_admin()
        response = self.client.get(reverse("inventory_list"))
        self.assertContains(response, own.point.name)
        self.assertContains(response, other.point.name)


class AdministrationTests(InventoryTestBase):
    def test_product_crud_and_toggle_are_admin_only(self):
        self.login_admin()
        response = self.client.post(
            reverse("product_create"),
            {
                "code": "NEW",
                "name": "Nuevo",
                "category": "Cat",
                "unit": "Unidad",
                "display_order": 5,
                "critical_qty": 1,
                "minimum_qty": 2,
                "maximum_qty": 3,
                "active": "on",
                "include_general": "on",
            },
        )
        self.assertRedirects(response, reverse("products"))
        product = Product.objects.get(code="NEW")
        self.client.post(reverse("product_toggle", args=[product.pk]))
        product.refresh_from_db()
        self.assertFalse(product.active)
        self.assertTrue(AuditLog.objects.filter(action="DESACTIVAR_PRODUCTO").exists())

    def test_alert_attention_requires_comment_and_is_audited(self):
        inventory, _ = create_inventory(self.pos, Inventory.DAILY)
        item = inventory.items.get()
        item.quantity = 1
        item.observation = "Bajo"
        item.save()
        finalize_inventory(inventory, self.pos)
        alert = inventory.alerts.get()
        self.login_admin()
        response = self.client.post(reverse("alert_resolve", args=[alert.pk]), {"attendance_comment": ""})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("alert_resolve", args=[alert.pk]),
            {"attendance_comment": "Se solicitó reposición."},
        )
        self.assertRedirects(response, reverse("alerts"))
        alert.refresh_from_db()
        self.assertTrue(alert.attended)
        self.assertEqual(alert.attended_by, self.admin)
        self.assertTrue(AuditLog.objects.filter(action="ATENDER_ALERTA").exists())

    def test_inventory_actions_are_audited(self):
        self.login_pos()
        self.client.post(reverse("inventory_start", args=["diario"]))
        inventory = Inventory.objects.get()
        self.inventory_post(inventory, {"D-001": 5}, action="save")
        self.inventory_post(inventory, {"D-001": 5}, action="finalize")
        actions = set(AuditLog.objects.values_list("action", flat=True))
        self.assertTrue({"CREAR_INVENTARIO", "GUARDAR_BORRADOR", "FINALIZAR_INVENTARIO"} <= actions)

    def test_seed_command_is_idempotent(self):
        from django.core.management import call_command

        call_command("seed_initial_data", verbosity=0)
        call_command("seed_initial_data", verbosity=0)
        self.assertEqual(PointOfSale.objects.filter(code="CENTRAL").count(), 1)
        self.assertEqual(get_user_model().objects.filter(username="contacto@picanhaparrilla.com").count(), 1)
