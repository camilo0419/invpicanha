from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Alert, AppSetting, AuditLog, Inventory, InventoryItem, Product


def classify_quantity(quantity, critical, minimum, maximum):
    """Única fuente de verdad para clasificar cantidades."""
    if quantity is None:
        return InventoryItem.NOT_COUNTED
    if critical is None or minimum is None:
        return InventoryItem.NO_RULE
    if quantity <= critical:
        return InventoryItem.CRITICAL
    if quantity < minimum:
        return InventoryItem.LOW
    if maximum is not None and quantity > maximum:
        return InventoryItem.HIGH
    return InventoryItem.NORMAL


def classify_item(item):
    return classify_quantity(
        item.quantity,
        item.critical_applied,
        item.minimum_applied,
        item.maximum_applied,
    )


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None


def audit(request, action, obj=None, description=""):
    AuditLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        model=obj.__class__.__name__ if obj else "",
        object_id=str(obj.pk) if obj and obj.pk else "",
        description=description,
        ip=client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
    )


def create_inventory(user, inventory_type):
    point = user.profile.point
    if not point or not point.active:
        raise ValueError("El usuario no tiene un punto de venta activo asignado.")
    existing = (
        Inventory.objects.filter(
            point=point,
            inventory_date=timezone.localdate(),
            inventory_type=inventory_type,
        )
        .exclude(state=Inventory.CANCELLED)
        .first()
    )
    if existing:
        return existing, False
    products = Product.objects.filter(activo=True)
    products = (
        products.filter(incluir_inventario_diario=True)
        if inventory_type == Inventory.DAILY
        else products.filter(incluir_inventario_general=True)
    )
    try:
        with transaction.atomic():
            inventory = Inventory.objects.create(
                inventory_type=inventory_type,
                point=point,
                responsible=user,
                created_by=user,
                modified_by=user,
                total_expected=products.count(),
            )
            InventoryItem.objects.bulk_create(
                [
                    InventoryItem(
                        inventory=inventory,
                        product=product,
                        product_code=product.code,
                        product_name=product.name,
                        category=product.category,
                        unit=product.unidad_medida,
                        critical_applied=product.critical_qty,
                        minimum_applied=product.minimum_qty,
                        maximum_applied=product.maximum_qty,
                        require_observation_low_applied=product.require_observation_low,
                        require_observation_high_applied=product.require_observation_high,
                    )
                    for product in products
                ]
            )
    except IntegrityError:
        inventory = Inventory.objects.get(
            point=point,
            inventory_date=timezone.localdate(),
            inventory_type=inventory_type,
        )
        return inventory, False
    return inventory, True


def validate_finalization(items):
    errors = []
    app_settings = AppSetting.get_solo()
    for item in items:
        item.result = classify_item(item)
        if item.quantity is None:
            errors.append(f"{item.product_name}: falta diligenciar la cantidad.")
            continue
        requires_note = (
            item.result in [InventoryItem.CRITICAL, InventoryItem.LOW]
            and item.require_observation_low_applied
        ) or (
            item.result == InventoryItem.HIGH
            and item.require_observation_high_applied
        )
        if app_settings.require_observation_on_alert and requires_note and not item.observation.strip():
            errors.append(f"{item.product_name}: la observación es obligatoria para este resultado.")
    return errors


def _create_product_alerts(inventory, items):
    if not AppSetting.get_solo().generate_product_alerts:
        return
    mapping = {
        InventoryItem.CRITICAL: (
            Alert.PRODUCT_CRITICAL,
            Alert.CRITICAL,
            "Producto en nivel crítico",
        ),
        InventoryItem.LOW: (Alert.PRODUCT_LOW, Alert.HIGH, "Producto bajo mínimo"),
        InventoryItem.HIGH: (Alert.PRODUCT_HIGH, Alert.MEDIUM, "Producto sobre máximo"),
    }
    alerts = []
    for item in items:
        if item.result not in mapping:
            continue
        alert_type, level, title = mapping[item.result]
        limits = (
            f"crítico {item.critical_applied if item.critical_applied is not None else '—'}, "
            f"mínimo {item.minimum_applied if item.minimum_applied is not None else '—'}, "
            f"máximo {item.maximum_applied if item.maximum_applied is not None else '—'}"
        )
        alerts.append(
            Alert(
                inventory=inventory,
                item=item,
                point=inventory.point,
                alert_type=alert_type,
                level=level,
                title=f"{title}: {item.product_name}",
                message=f"Cantidad {item.quantity} {item.unit}; reglas aplicadas: {limits}.",
            )
        )
    Alert.objects.bulk_create(alerts)


@transaction.atomic
def finalize_inventory(inventory, user):
    inventory = Inventory.objects.select_for_update().get(pk=inventory.pk)
    if not inventory.can_edit:
        raise ValueError("Este inventario está bloqueado y no se puede finalizar.")
    items = list(inventory.items.select_related("product"))
    errors = validate_finalization(items)
    if errors:
        raise ValueError("\n".join(errors))
    for item in items:
        item.valor_unitario_aplicado = item.product.valor_unitario_promedio
        item.valor_total_estimado = (
            (item.quantity * item.valor_unitario_aplicado).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if item.quantity is not None and item.valor_unitario_aplicado is not None
            else None
        )
    InventoryItem.objects.bulk_update(
        items,
        ["result", "valor_unitario_aplicado", "valor_total_estimado", "updated_at"],
    )
    counts = {
        result: sum(item.result == result for item in items)
        for result in [
            InventoryItem.CRITICAL,
            InventoryItem.LOW,
            InventoryItem.NORMAL,
            InventoryItem.HIGH,
        ]
    }
    has_alerts = counts[InventoryItem.CRITICAL] + counts[InventoryItem.LOW] + counts[InventoryItem.HIGH] > 0
    inventory.total_counted = len(items)
    inventory.total_critical = counts[InventoryItem.CRITICAL]
    inventory.total_low = counts[InventoryItem.LOW]
    inventory.total_normal = counts[InventoryItem.NORMAL]
    inventory.total_high = counts[InventoryItem.HIGH]
    inventory.state = Inventory.FINAL_ALERT if has_alerts else Inventory.FINAL
    inventory.finalized_at = timezone.now()
    inventory.locked = True
    inventory.modified_by = user
    inventory.save()
    inventory.alerts.filter(
        alert_type__in=[
            Alert.PRODUCT_CRITICAL,
            Alert.PRODUCT_LOW,
            Alert.PRODUCT_HIGH,
        ]
    ).delete()
    _create_product_alerts(inventory, items)
    return inventory


@transaction.atomic
def reopen_inventory(inventory, user):
    inventory = Inventory.objects.select_for_update().get(pk=inventory.pk)
    if not inventory.is_final:
        raise ValueError("Solo se pueden reabrir inventarios finalizados.")
    inventory.state = Inventory.REOPENED
    inventory.locked = False
    inventory.reopened_by = user
    inventory.reopened_at = timezone.now()
    inventory.modified_by = user
    inventory.save()
    Alert.objects.create(
        inventory=inventory,
        point=inventory.point,
        alert_type=Alert.INVENTORY_REOPENED,
        level=Alert.INFO,
        title="Inventario reabierto",
        message=f"El inventario fue reabierto por {user.username}.",
    )
    return inventory


@transaction.atomic
def cancel_inventory(inventory, user, reason):
    inventory = Inventory.objects.select_for_update().get(pk=inventory.pk)
    if inventory.state == Inventory.CANCELLED:
        raise ValueError("El inventario ya está anulado.")
    if not reason.strip():
        raise ValueError("El motivo de anulación es obligatorio.")
    inventory.state = Inventory.CANCELLED
    inventory.locked = True
    inventory.cancelled_by = user
    inventory.cancelled_at = timezone.now()
    inventory.cancellation_reason = reason.strip()
    inventory.modified_by = user
    inventory.save()
    Alert.objects.create(
        inventory=inventory,
        point=inventory.point,
        alert_type=Alert.INVENTORY_CANCELLED,
        level=Alert.MEDIUM,
        title="Inventario anulado",
        message=f"Motivo: {reason.strip()}",
    )
    return inventory
