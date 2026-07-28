from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import (
    AlertResolveForm,
    CancellationForm,
    PointOfSaleForm,
    ProductForm,
    SettingForm,
)
from .models import Alert, AppSetting, AuditLog, Inventory, InventoryItem, PointOfSale, Product, Profile
from .services import (
    audit,
    cancel_inventory,
    classify_item,
    create_inventory,
    finalize_inventory,
    reopen_inventory,
)


def _profile(user):
    profile = getattr(user, "profile", None)
    if not profile or not profile.active:
        raise PermissionDenied("Usuario sin perfil funcional activo.")
    return profile


def _visible_inventory(request, pk):
    queryset = Inventory.objects.select_related(
        "point", "created_by", "responsible", "modified_by", "reopened_by", "cancelled_by"
    )
    profile = _profile(request.user)
    if profile.role == Profile.POS:
        queryset = queryset.filter(point=profile.point)
    return get_object_or_404(queryset, pk=pk)


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        profile = getattr(user, "profile", None)
        if not profile or not profile.active:
            form.add_error(None, "Tu cuenta no tiene acceso funcional activo.")
        else:
            login(request, user)
            audit(request, "LOGIN", user, "Inicio de sesión correcto.")
            next_url = request.POST.get("next") or request.GET.get("next")
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                return redirect(next_url)
            return redirect("dashboard")
    return render(request, "registration/login.html", {"form": form})


@require_POST
@login_required
def logout_view(request):
    audit(request, "LOGOUT", request.user, "Cierre de sesión.")
    logout(request)
    return redirect("login")


@login_required
def dashboard(request):
    profile = _profile(request.user)
    today = timezone.localdate()
    if profile.role == Profile.ADMIN:
        inventories = Inventory.objects.select_related("point", "responsible")
        alerts = Alert.objects.filter(attended=False).select_related("point", "inventory", "item")[:8]
        context = {
            "recent": inventories[:8],
            "alerts": alerts,
            "inventories_today": inventories.filter(inventory_date=today).exclude(state=Inventory.CANCELLED).count(),
            "drafts": inventories.filter(state__in=[Inventory.DRAFT, Inventory.IN_PROGRESS, Inventory.REOPENED]).count(),
            "critical_alerts": Alert.objects.filter(attended=False, level=Alert.CRITICAL).count(),
            "high_alerts": Alert.objects.filter(attended=False, alert_type=Alert.PRODUCT_HIGH).count(),
            "low_alerts": Alert.objects.filter(attended=False, alert_type=Alert.PRODUCT_LOW).count(),
            "productos_activos": Product.objects.filter(activo=True).count(),
            "daily_pending": PointOfSale.objects.filter(active=True).exclude(
                inventories__inventory_date=today,
                inventories__inventory_type=Inventory.DAILY,
                inventories__state__in=[Inventory.FINAL, Inventory.FINAL_ALERT],
            ).count(),
            "general_pending": PointOfSale.objects.filter(active=True).exclude(
                inventories__inventory_date=today,
                inventories__inventory_type=Inventory.GENERAL,
                inventories__state__in=[Inventory.FINAL, Inventory.FINAL_ALERT],
            ).count(),
        }
        return render(request, "inventarios/admin_dashboard.html", context)

    point_inventories = Inventory.objects.filter(point=profile.point).select_related("responsible")
    daily_today = point_inventories.filter(
        inventory_date=today, inventory_type=Inventory.DAILY
    ).exclude(state=Inventory.CANCELLED).first()
    latest_general = point_inventories.filter(inventory_type=Inventory.GENERAL).exclude(
        state=Inventory.CANCELLED
    ).first()
    context = {
        "point": profile.point,
        "today": today,
        "daily_today": daily_today,
        "latest_general": latest_general,
        "drafts": point_inventories.filter(
            state__in=[Inventory.DRAFT, Inventory.IN_PROGRESS, Inventory.REOPENED]
        ),
        "recent": point_inventories[:6],
        "related_alerts": Alert.objects.filter(point=profile.point).select_related(
            "inventory", "item"
        )[:5],
    }
    return render(request, "inventarios/pos_dashboard.html", context)


@require_POST
@role_required(Profile.POS, Profile.ADMIN)
def inventory_start(request, kind):
    if kind not in {"diario", "general"}:
        raise Http404
    profile = _profile(request.user)
    if profile.role == Profile.ADMIN and not profile.point:
        point = PointOfSale.objects.filter(active=True).first()
        if not point:
            messages.error(request, "No existe un punto de venta activo.")
            return redirect("dashboard")
        profile.point = point
    inventory_type = Inventory.DAILY if kind == "diario" else Inventory.GENERAL
    try:
        inventory, created = create_inventory(request.user, inventory_type)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard")
    if created:
        audit(request, "CREAR_INVENTARIO", inventory, f"Creó {inventory.get_inventory_type_display()}.")
        messages.success(request, "Inventario creado.")
    else:
        messages.info(request, "Ya existe un inventario de este tipo para hoy.")
    target = "inventory_detail" if inventory.locked else "inventory_fill"
    return redirect(target, pk=inventory.pk)


def _parse_items(request, inventory, items):
    errors = []
    now = timezone.now()
    for item in items:
        raw = request.POST.get(f"qty_{item.id}", "").strip().replace(",", ".")
        observation = request.POST.get(f"obs_{item.id}", "").strip()
        try:
            quantity = None if raw == "" else Decimal(raw)
        except InvalidOperation:
            errors.append(f"{item.product_name}: cantidad inválida.")
            continue
        if quantity is not None and quantity < 0:
            errors.append(f"{item.product_name}: la cantidad no puede ser negativa.")
            continue
        if (
            quantity is not None
            and not item.product.permite_decimales
            and quantity != quantity.to_integral_value()
        ):
            errors.append(f"{item.product_name}: solo admite cantidades enteras.")
            continue
        item.quantity = quantity
        item.observation = observation
        item.result = classify_item(item)
        if quantity is not None:
            item.registered_by = request.user
            item.registered_at = now
    InventoryItem.objects.bulk_update(
        items,
        ["quantity", "observation", "result", "registered_by", "registered_at", "updated_at"],
    )
    inventory.general_observation = request.POST.get("general_observation", "").strip()
    inventory.total_counted = sum(item.quantity is not None for item in items)
    inventory.state = Inventory.IN_PROGRESS if inventory.total_counted else Inventory.DRAFT
    inventory.modified_by = request.user
    inventory.save()
    return errors


@role_required(Profile.POS, Profile.ADMIN)
def inventory_fill(request, pk):
    inventory = _visible_inventory(request, pk)
    profile = _profile(request.user)
    if profile.role == Profile.POS and inventory.state == Inventory.REOPENED:
        raise PermissionDenied("Solo el administrador puede editar un inventario reabierto.")
    if not inventory.can_edit:
        return redirect("inventory_detail", pk=inventory.pk)
    items = list(inventory.items.select_related("product"))
    if request.method == "POST":
        action = request.POST.get("action", "save")
        with transaction.atomic():
            errors = _parse_items(request, inventory, items)
        if errors:
            for error in errors:
                messages.error(request, error)
        elif action == "finalize":
            try:
                finalize_inventory(inventory, request.user)
            except ValueError as exc:
                for error in str(exc).splitlines():
                    messages.error(request, error)
            else:
                audit(request, "FINALIZAR_INVENTARIO", inventory, "Finalizó y bloqueó el inventario.")
                messages.success(request, "Inventario finalizado y bloqueado correctamente.")
                return redirect("inventory_detail", pk=inventory.pk)
        else:
            action_name = "EDITAR_INVENTARIO" if inventory.state == Inventory.REOPENED else "GUARDAR_BORRADOR"
            audit(request, action_name, inventory, "Guardó cambios del inventario.")
            messages.success(request, "Borrador guardado.")
            return redirect("inventory_fill", pk=inventory.pk)
    categories = sorted({item.category or "Sin categoría" for item in items})
    return render(
        request,
        "inventarios/inventory_fill.html",
        {"inv": inventory, "items": items, "categories": categories},
    )


@login_required
def inventory_list(request):
    profile = _profile(request.user)
    queryset = Inventory.objects.select_related("point", "responsible")
    if profile.role == Profile.POS:
        queryset = queryset.filter(point=profile.point)
    filters = {
        "inventory_type": request.GET.get("type"),
        "state": request.GET.get("state"),
        "responsible__username__icontains": request.GET.get("responsible"),
        "inventory_date__gte": request.GET.get("date_from"),
        "inventory_date__lte": request.GET.get("date_to"),
    }
    for key, value in filters.items():
        if value:
            queryset = queryset.filter(**{key: value})
    alert_filter = request.GET.get("alerts")
    if alert_filter == "yes":
        queryset = queryset.filter(alerts__isnull=False).distinct()
    elif alert_filter == "no":
        queryset = queryset.filter(alerts__isnull=True)
    page = Paginator(queryset, 18).get_page(request.GET.get("page"))
    return render(
        request,
        "inventarios/inventory_list.html",
        {"page": page, "types": Inventory.TYPES, "states": Inventory.STATES},
    )


@login_required
def inventory_detail(request, pk):
    inventory = _visible_inventory(request, pk)
    result_filter = request.GET.get("result")
    items = inventory.items.select_related("registered_by")
    if result_filter:
        items = items.filter(result=result_filter)
    return render(
        request,
        "inventarios/inventory_detail.html",
        {"inv": inventory, "items": items, "filt": result_filter},
    )


@require_POST
@role_required(Profile.ADMIN)
def inventory_reopen(request, pk):
    inventory = _visible_inventory(request, pk)
    try:
        reopen_inventory(inventory, request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        audit(request, "REABRIR_INVENTARIO", inventory, "Reabrió el inventario.")
        messages.success(request, "Inventario reabierto. Ya puede editarse.")
    return redirect("inventory_detail", pk=inventory.pk)


@role_required(Profile.ADMIN)
def inventory_cancel(request, pk):
    inventory = _visible_inventory(request, pk)
    form = CancellationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            cancel_inventory(inventory, request.user, form.cleaned_data["reason"])
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            audit(request, "ANULAR_INVENTARIO", inventory, f"Anuló: {form.cleaned_data['reason']}")
            messages.success(request, "Inventario anulado sin eliminar su historial.")
            return redirect("inventory_detail", pk=inventory.pk)
    return render(request, "inventarios/inventory_cancel.html", {"inv": inventory, "form": form})


@role_required(Profile.ADMIN)
def products(request):
    queryset = Product.objects.all()
    query = request.GET.get("q", "")
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query) | Q(code__icontains=query) | Q(category__icontains=query)
        )
    estado = request.GET.get("estado")
    if estado in {"activo", "inactivo"}:
        queryset = queryset.filter(activo=estado == "activo")
    inventory_type = request.GET.get("inventario")
    if inventory_type == "diario":
        queryset = queryset.filter(incluir_inventario_diario=True)
    elif inventory_type == "general":
        queryset = queryset.filter(incluir_inventario_general=True)
    order = request.GET.get("orden", "display_order")
    allowed_orders = {"display_order", "name", "code", "category", "-updated_at"}
    queryset = queryset.order_by(order if order in allowed_orders else "display_order")
    return render(request, "inventarios/products.html", {"products": queryset, "q": query})


@role_required(Profile.ADMIN)
def product_form(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    old_rules = None
    if product:
        old_rules = (product.critical_qty, product.minimum_qty, product.maximum_qty)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        action = "EDITAR_PRODUCTO" if pk else "CREAR_PRODUCTO"
        audit(request, action, product, f"Guardó el producto {product.code}.")
        new_rules = (product.critical_qty, product.minimum_qty, product.maximum_qty)
        if old_rules is not None and old_rules != new_rules:
            audit(request, "CAMBIAR_REGLAS", product, f"Cambió reglas de {old_rules} a {new_rules}.")
        messages.success(request, "Producto guardado.")
        return redirect("products")
    return render(request, "inventarios/product_form.html", {"form": form, "obj": product})


@require_POST
@role_required(Profile.ADMIN)
def product_toggle(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.activo = not product.activo
    product.save(update_fields=["activo", "updated_at"])
    action = "ACTIVAR_PRODUCTO" if product.activo else "DESACTIVAR_PRODUCTO"
    audit(request, action, product, action)
    messages.success(request, "Estado del producto actualizado.")
    return redirect("products")


@role_required(Profile.ADMIN)
def alerts(request):
    queryset = Alert.objects.select_related("inventory", "item", "point", "attended_by")
    filters = {
        "state": request.GET.get("state"),
        "level": request.GET.get("level"),
        "alert_type": request.GET.get("type"),
        "inventory_id": request.GET.get("inventory"),
        "created_at__date__gte": request.GET.get("date_from"),
        "created_at__date__lte": request.GET.get("date_to"),
    }
    for key, value in filters.items():
        if value:
            queryset = queryset.filter(**{key: value})
    product = request.GET.get("product")
    if product:
        queryset = queryset.filter(item__product_name__icontains=product)
    return render(
        request,
        "inventarios/alerts.html",
        {"alerts": queryset, "levels": Alert.LEVELS, "types": Alert.TYPES},
    )


@role_required(Profile.ADMIN)
def alert_resolve(request, pk):
    alert_obj = get_object_or_404(Alert, pk=pk)
    if alert_obj.attended:
        messages.info(request, "Esta alerta ya fue atendida.")
        return redirect("alerts")
    form = AlertResolveForm(request.POST or None, instance=alert_obj)
    if request.method == "POST" and form.is_valid():
        alert_obj = form.save(commit=False)
        alert_obj.attended = True
        alert_obj.state = Alert.RESOLVED
        alert_obj.attended_by = request.user
        alert_obj.attended_at = timezone.now()
        alert_obj.save()
        audit(request, "ATENDER_ALERTA", alert_obj, "Marcó la alerta como atendida.")
        messages.success(request, "Alerta marcada como atendida.")
        return redirect("alerts")
    return render(request, "inventarios/alert_resolve.html", {"alert": alert_obj, "form": form})


@role_required(Profile.ADMIN)
def settings_view(request):
    app_settings = AppSetting.get_solo()
    point = PointOfSale.objects.filter(code="CENTRAL").first() or PointOfSale.objects.first()
    settings_form = SettingForm(request.POST or None, instance=app_settings, prefix="settings")
    point_form = PointOfSaleForm(request.POST or None, instance=point, prefix="point")
    if request.method == "POST" and settings_form.is_valid() and point_form.is_valid():
        settings_form.save()
        point = point_form.save()
        audit(request, "CAMBIAR_CONFIGURACION", point, "Actualizó configuración operativa.")
        messages.success(request, "Configuración guardada.")
        return redirect("settings")
    return render(
        request,
        "inventarios/settings.html",
        {"settings_form": settings_form, "point_form": point_form},
    )


@role_required(Profile.ADMIN)
def audit_list(request):
    queryset = AuditLog.objects.select_related("user")
    if request.GET.get("action"):
        queryset = queryset.filter(action=request.GET["action"])
    if request.GET.get("user"):
        queryset = queryset.filter(user__username__icontains=request.GET["user"])
    if request.GET.get("date_from"):
        queryset = queryset.filter(created_at__date__gte=request.GET["date_from"])
    if request.GET.get("date_to"):
        queryset = queryset.filter(created_at__date__lte=request.GET["date_to"])
    page = Paginator(queryset, 30).get_page(request.GET.get("page"))
    return render(request, "inventarios/audit.html", {"page": page, "actions": AuditLog.ACTIONS})
