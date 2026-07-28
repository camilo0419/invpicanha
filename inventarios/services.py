from django.db import transaction
from django.utils import timezone
from .models import Inventory, InventoryItem, Alert, Product, AppSetting

def create_inventory(user, inventory_type):
    point=getattr(user.profile,'point_name','La Central')
    inv=Inventory.objects.filter(point_name=point,inventory_date=timezone.localdate(),inventory_type=inventory_type).exclude(state=Inventory.CANCELLED).first()
    if inv: return inv,False
    products=Product.objects.filter(active=True)
    products=products.filter(include_daily=True) if inventory_type==Inventory.DAILY else products.filter(include_general=True)
    with transaction.atomic():
        inv=Inventory.objects.create(inventory_type=inventory_type,point_name=point,created_by=user,total_expected=products.count())
        InventoryItem.objects.bulk_create([InventoryItem(inventory=inv,product=p,product_code=p.code,product_name=p.name,category=p.category,unit=p.unit,critical_applied=p.critical_qty,minimum_applied=p.minimum_qty,maximum_applied=p.maximum_qty) for p in products])
    return inv,True

def finalize_inventory(inv):
    settings=AppSetting.get_solo(); items=list(inv.items.select_related('product'))
    if any(i.quantity is None for i in items): raise ValueError('Debes diligenciar todos los productos antes de finalizar.')
    if settings.require_observation_on_alert and any(i.result in [InventoryItem.CRITICAL,InventoryItem.LOW,InventoryItem.HIGH] and not i.observation.strip() for i in items): raise ValueError('Los productos con alerta deben tener observación.')
    counts={k:0 for k in [InventoryItem.CRITICAL,InventoryItem.LOW,InventoryItem.NORMAL,InventoryItem.HIGH]}
    for i in items:
        i.result=i.product.classify(i.quantity); i.save(update_fields=['result','updated_at'])
        if i.result in counts: counts[i.result]+=1
    has_alert=counts[InventoryItem.CRITICAL]+counts[InventoryItem.LOW]+counts[InventoryItem.HIGH]>0
    inv.total_counted=len(items); inv.total_critical=counts[InventoryItem.CRITICAL]; inv.total_low=counts[InventoryItem.LOW]; inv.total_normal=counts[InventoryItem.NORMAL]; inv.total_high=counts[InventoryItem.HIGH]
    inv.state=Inventory.FINAL_ALERT if has_alert else Inventory.FINAL; inv.finalized_at=timezone.now(); inv.save()
    inv.alerts.all().delete()
    if has_alert:
        Alert.objects.create(inventory=inv,alert_date=inv.inventory_date,title=f'{inv.get_inventory_type_display()} con novedades',message=f'Críticos: {inv.total_critical}; bajos: {inv.total_low}; altos: {inv.total_high}.',level=Alert.CRITICAL if inv.total_critical else Alert.HIGH)
    return inv
