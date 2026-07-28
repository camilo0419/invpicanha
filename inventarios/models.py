from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class PointOfSale(models.Model):
    DAILY = "DIARIO"
    GENERAL = "GENERAL"
    FREQUENCIES = [
        (DAILY, "Diaria"),
        ("SEMANAL", "Semanal"),
        ("QUINCENAL", "Quincenal"),
        ("MENSUAL", "Mensual"),
    ]

    name = models.CharField("nombre", max_length=100)
    code = models.CharField("código", max_length=30, unique=True)
    active = models.BooleanField("activo", default=True)
    daily_deadline = models.TimeField("hora límite inventario diario", default="21:00")
    general_deadline = models.TimeField("hora límite inventario general", default="21:00")
    general_frequency = models.CharField(
        "frecuencia inventario general",
        max_length=15,
        choices=FREQUENCIES,
        default="SEMANAL",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "punto de venta"
        verbose_name_plural = "puntos de venta"

    def __str__(self):
        return self.name


class Profile(models.Model):
    ADMIN = "ADMIN"
    POS = "PUNTO_VENTA"
    ROLES = [(ADMIN, "Administrador"), (POS, "Punto de venta")]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    role = models.CharField("rol", max_length=20, choices=ROLES)
    point = models.ForeignKey(
        PointOfSale,
        on_delete=models.PROTECT,
        related_name="profiles",
        null=True,
        blank=True,
        verbose_name="punto de venta",
    )
    active = models.BooleanField("activo", default=True)

    def clean(self):
        if self.role == self.POS and not self.point_id:
            raise ValidationError({"point": "El punto de venta es obligatorio para este rol."})

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


class AppSetting(models.Model):
    require_observation_on_alert = models.BooleanField(
        "exigir observación según la regla del producto", default=True
    )
    generate_product_alerts = models.BooleanField(
        "generar alertas por producto", default=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Product(models.Model):
    name = models.CharField("nombre", max_length=120)
    code = models.CharField("código", max_length=30, unique=True)
    category = models.CharField("categoría", max_length=80, blank=True)
    unit = models.CharField("unidad de medida", max_length=30)
    active = models.BooleanField("activo", default=True)
    display_order = models.PositiveIntegerField("orden visual", default=100)
    allows_decimals = models.BooleanField("permite decimales", default=True)
    include_daily = models.BooleanField("incluir en inventario diario", default=False)
    include_general = models.BooleanField("incluir en inventario general", default=True)
    critical_qty = models.DecimalField(
        "cantidad crítica",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    minimum_qty = models.DecimalField(
        "cantidad mínima",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    maximum_qty = models.DecimalField(
        "cantidad máxima",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    require_observation_low = models.BooleanField(
        "exigir observación en crítico o bajo", default=True
    )
    require_observation_high = models.BooleanField(
        "exigir observación en alto", default=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "category", "name"]

    def clean(self):
        errors = {}
        if (
            self.critical_qty is not None
            and self.minimum_qty is not None
            and self.critical_qty > self.minimum_qty
        ):
            errors["critical_qty"] = "Debe ser menor o igual a la cantidad mínima."
        if (
            self.minimum_qty is not None
            and self.maximum_qty is not None
            and self.minimum_qty > self.maximum_qty
        ):
            errors["maximum_qty"] = "Debe ser mayor o igual a la cantidad mínima."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name


class Inventory(models.Model):
    DAILY = "DIARIO"
    GENERAL = "GENERAL"
    TYPES = [(DAILY, "Inventario diario"), (GENERAL, "Inventario general")]

    DRAFT = "BORRADOR"
    IN_PROGRESS = "EN_PROGRESO"
    FINAL = "FINALIZADO"
    FINAL_ALERT = "FINALIZADO_CON_ALERTAS"
    REOPENED = "REABIERTO"
    CANCELLED = "ANULADO"
    STATES = [
        (DRAFT, "Borrador"),
        (IN_PROGRESS, "En progreso"),
        (FINAL, "Finalizado"),
        (FINAL_ALERT, "Finalizado con alertas"),
        (REOPENED, "Reabierto"),
        (CANCELLED, "Anulado"),
    ]
    ACTIVE_STATES = [DRAFT, IN_PROGRESS, FINAL, FINAL_ALERT, REOPENED]

    point = models.ForeignKey(
        PointOfSale, on_delete=models.PROTECT, related_name="inventories", null=True, blank=True
    )
    inventory_date = models.DateField("fecha de inventario", default=timezone.localdate)
    inventory_type = models.CharField("tipo", max_length=15, choices=TYPES)
    state = models.CharField("estado", max_length=30, choices=STATES, default=DRAFT)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inventories_responsible",
        null=True,
        blank=True,
    )
    started_at = models.DateTimeField("inicio", default=timezone.now)
    finalized_at = models.DateTimeField("finalización", null=True, blank=True)
    total_expected = models.PositiveIntegerField(default=0)
    total_counted = models.PositiveIntegerField(default=0)
    total_critical = models.PositiveIntegerField(default=0)
    total_low = models.PositiveIntegerField(default=0)
    total_normal = models.PositiveIntegerField(default=0)
    total_high = models.PositiveIntegerField(default=0)
    general_observation = models.TextField("observación general", blank=True)
    locked = models.BooleanField("bloqueado", default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inventories_created",
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inventories_modified",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    modified_at = models.DateTimeField(auto_now=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inventories_reopened",
        null=True,
        blank=True,
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inventories_cancelled",
        null=True,
        blank=True,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-inventory_date", "-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["point", "inventory_date", "inventory_type"],
                condition=~Q(state="ANULADO"),
                name="unique_active_inventory_per_point_date_type",
            )
        ]

    @property
    def is_final(self):
        return self.state in [self.FINAL, self.FINAL_ALERT]

    @property
    def can_edit(self):
        return not self.locked and self.state in [
            self.DRAFT,
            self.IN_PROGRESS,
            self.REOPENED,
        ]

    def __str__(self):
        return f"{self.get_inventory_type_display()} {self.inventory_date}"


class InventoryItem(models.Model):
    CRITICAL = "CRITICO"
    LOW = "BAJO"
    NORMAL = "NORMAL"
    HIGH = "ALTO"
    NO_RULE = "SIN_REGLA"
    NOT_COUNTED = "NO_CONTADO"
    RESULTS = [
        (CRITICAL, "Crítico"),
        (LOW, "Bajo"),
        (NORMAL, "Normal"),
        (HIGH, "Alto"),
        (NO_RULE, "Sin regla"),
        (NOT_COUNTED, "No contado"),
    ]

    inventory = models.ForeignKey(
        Inventory, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_code = models.CharField("código snapshot", max_length=30)
    product_name = models.CharField("nombre snapshot", max_length=120)
    category = models.CharField("categoría snapshot", max_length=80, blank=True)
    unit = models.CharField("unidad snapshot", max_length=30)
    quantity = models.DecimalField(
        "cantidad contada",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    critical_applied = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    minimum_applied = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    maximum_applied = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    require_observation_low_applied = models.BooleanField(default=True)
    require_observation_high_applied = models.BooleanField(default=True)
    result = models.CharField(max_length=20, choices=RESULTS, default=NOT_COUNTED)
    observation = models.TextField(blank=True)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inventory_items_registered",
        null=True,
        blank=True,
    )
    registered_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__display_order", "product_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["inventory", "product"], name="unique_product_per_inventory"
            )
        ]


class Alert(models.Model):
    PRODUCT_CRITICAL = "PRODUCTO_CRITICO"
    PRODUCT_LOW = "PRODUCTO_BAJO"
    PRODUCT_HIGH = "PRODUCTO_ALTO"
    INVENTORY_INCOMPLETE = "INVENTARIO_INCOMPLETO"
    INVENTORY_REOPENED = "INVENTARIO_REABIERTO"
    INVENTORY_CANCELLED = "INVENTARIO_ANULADO"
    TYPES = [
        (PRODUCT_CRITICAL, "Producto crítico"),
        (PRODUCT_LOW, "Producto bajo"),
        (PRODUCT_HIGH, "Producto alto"),
        ("INVENTARIO_NO_REALIZADO", "Inventario no realizado"),
        (INVENTORY_INCOMPLETE, "Inventario incompleto"),
        ("INVENTARIO_SIN_FINALIZAR", "Inventario sin finalizar"),
        (INVENTORY_REOPENED, "Inventario reabierto"),
        (INVENTORY_CANCELLED, "Inventario anulado"),
    ]
    INFO = "INFORMATIVA"
    LOW = "BAJA"
    MEDIUM = "MEDIA"
    HIGH = "ALTA"
    CRITICAL = "CRITICA"
    LEVELS = [
        (INFO, "Informativa"),
        (LOW, "Baja"),
        (MEDIUM, "Media"),
        (HIGH, "Alta"),
        (CRITICAL, "Crítica"),
    ]
    PENDING = "PENDIENTE"
    RESOLVED = "ATENDIDA"
    STATES = [(PENDING, "Pendiente"), (RESOLVED, "Atendida")]

    inventory = models.ForeignKey(
        Inventory, on_delete=models.CASCADE, related_name="alerts", null=True, blank=True
    )
    item = models.ForeignKey(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name="alerts",
        null=True,
        blank=True,
    )
    point = models.ForeignKey(
        PointOfSale, on_delete=models.PROTECT, related_name="alerts", null=True, blank=True
    )
    alert_type = models.CharField(
        max_length=35, choices=TYPES, default=INVENTORY_INCOMPLETE
    )
    level = models.CharField(max_length=15, choices=LEVELS)
    title = models.CharField(max_length=160)
    message = models.TextField()
    state = models.CharField(max_length=12, choices=STATES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    attended = models.BooleanField(default=False)
    attended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts_attended",
    )
    attended_at = models.DateTimeField(null=True, blank=True)
    attendance_comment = models.TextField(blank=True)

    class Meta:
        ordering = ["attended", "-created_at"]


class AuditLog(models.Model):
    ACTIONS = [
        (action, label)
        for action, label in [
            ("LOGIN", "Inicio de sesión"),
            ("LOGOUT", "Cierre de sesión"),
            ("CREAR_INVENTARIO", "Crear inventario"),
            ("GUARDAR_BORRADOR", "Guardar borrador"),
            ("FINALIZAR_INVENTARIO", "Finalizar inventario"),
            ("REABRIR_INVENTARIO", "Reabrir inventario"),
            ("EDITAR_INVENTARIO", "Editar inventario"),
            ("ANULAR_INVENTARIO", "Anular inventario"),
            ("CREAR_PRODUCTO", "Crear producto"),
            ("EDITAR_PRODUCTO", "Editar producto"),
            ("ACTIVAR_PRODUCTO", "Activar producto"),
            ("DESACTIVAR_PRODUCTO", "Desactivar producto"),
            ("CAMBIAR_REGLAS", "Cambiar reglas"),
            ("ATENDER_ALERTA", "Atender alerta"),
            ("CAMBIAR_CONFIGURACION", "Cambiar configuración"),
        ]
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=30, choices=ACTIONS)
    model = models.CharField(max_length=80)
    object_id = models.CharField(max_length=50, blank=True)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
