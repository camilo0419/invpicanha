from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone

class Profile(models.Model):
    ADMIN='ADMIN'; POS='POS'; ROLES=[(ADMIN,'Administrador'),(POS,'Punto de venta')]
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='profile')
    role=models.CharField(max_length=10,choices=ROLES)
    point_name=models.CharField(max_length=80,default='La Central')
    active=models.BooleanField(default=True)
    def __str__(self): return f'{self.user.username} - {self.get_role_display()}'

class AppSetting(models.Model):
    daily_deadline=models.TimeField(default='21:00')
    general_frequency_days=models.PositiveIntegerField(default=7)
    general_deadline=models.TimeField(default='21:00')
    require_observation_on_alert=models.BooleanField(default=True)
    updated_at=models.DateTimeField(auto_now=True)
    @classmethod
    def get_solo(cls):
        obj,_=cls.objects.get_or_create(pk=1)
        return obj

class Product(models.Model):
    name=models.CharField(max_length=120,unique=True)
    code=models.CharField(max_length=30,unique=True)
    category=models.CharField(max_length=80,blank=True)
    unit=models.CharField(max_length=30,default='Unidad')
    active=models.BooleanField(default=True)
    include_daily=models.BooleanField(default=False)
    include_general=models.BooleanField(default=True)
    allows_decimals=models.BooleanField(default=True)
    critical_qty=models.DecimalField(max_digits=12,decimal_places=2,null=True,blank=True,validators=[MinValueValidator(0)])
    minimum_qty=models.DecimalField(max_digits=12,decimal_places=2,null=True,blank=True,validators=[MinValueValidator(0)])
    maximum_qty=models.DecimalField(max_digits=12,decimal_places=2,null=True,blank=True,validators=[MinValueValidator(0)])
    display_order=models.PositiveIntegerField(default=100)
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['display_order','category','name']
    def __str__(self): return self.name
    def classify(self,qty):
        if qty is None: return InventoryItem.NOT_COUNTED
        if self.critical_qty is not None and qty <= self.critical_qty: return InventoryItem.CRITICAL
        if self.minimum_qty is not None and qty < self.minimum_qty: return InventoryItem.LOW
        if self.maximum_qty is not None and qty > self.maximum_qty: return InventoryItem.HIGH
        if self.critical_qty is None and self.minimum_qty is None and self.maximum_qty is None: return InventoryItem.NO_RULE
        return InventoryItem.NORMAL

class Inventory(models.Model):
    DAILY='DAILY'; GENERAL='GENERAL'; TYPES=[(DAILY,'Inventario diario'),(GENERAL,'Inventario general')]
    DRAFT='DRAFT'; FINAL='FINAL'; FINAL_ALERT='FINAL_ALERT'; CANCELLED='CANCELLED'
    STATES=[(DRAFT,'Borrador'),(FINAL,'Finalizado'),(FINAL_ALERT,'Finalizado con alertas'),(CANCELLED,'Anulado')]
    inventory_type=models.CharField(max_length=10,choices=TYPES)
    inventory_date=models.DateField(default=timezone.localdate)
    point_name=models.CharField(max_length=80,default='La Central')
    state=models.CharField(max_length=20,choices=STATES,default=DRAFT)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='inventories_created')
    started_at=models.DateTimeField(auto_now_add=True); finalized_at=models.DateTimeField(null=True,blank=True)
    general_observation=models.TextField(blank=True)
    total_expected=models.PositiveIntegerField(default=0); total_counted=models.PositiveIntegerField(default=0)
    total_critical=models.PositiveIntegerField(default=0); total_low=models.PositiveIntegerField(default=0)
    total_normal=models.PositiveIntegerField(default=0); total_high=models.PositiveIntegerField(default=0)
    class Meta:
        ordering=['-inventory_date','-started_at']
        constraints=[models.UniqueConstraint(fields=['point_name','inventory_date','inventory_type'],condition=models.Q(state__in=['DRAFT','FINAL','FINAL_ALERT']),name='unique_active_inventory_per_day_type')]
    def __str__(self): return f'{self.get_inventory_type_display()} {self.inventory_date}'
    @property
    def is_final(self): return self.state in [self.FINAL,self.FINAL_ALERT]

class InventoryItem(models.Model):
    CRITICAL='CRITICAL'; LOW='LOW'; NORMAL='NORMAL'; HIGH='HIGH'; NO_RULE='NO_RULE'; NOT_COUNTED='NOT_COUNTED'
    RESULTS=[(CRITICAL,'Crítico'),(LOW,'Bajo'),(NORMAL,'Normal'),(HIGH,'Alto'),(NO_RULE,'Sin regla'),(NOT_COUNTED,'No contado')]
    inventory=models.ForeignKey(Inventory,on_delete=models.CASCADE,related_name='items')
    product=models.ForeignKey(Product,on_delete=models.PROTECT)
    product_code=models.CharField(max_length=30); product_name=models.CharField(max_length=120)
    category=models.CharField(max_length=80,blank=True); unit=models.CharField(max_length=30)
    quantity=models.DecimalField(max_digits=12,decimal_places=2,null=True,blank=True,validators=[MinValueValidator(0)])
    critical_applied=models.DecimalField(max_digits=12,decimal_places=2,null=True,blank=True)
    minimum_applied=models.DecimalField(max_digits=12,decimal_places=2,null=True,blank=True)
    maximum_applied=models.DecimalField(max_digits=12,decimal_places=2,null=True,blank=True)
    result=models.CharField(max_length=20,choices=RESULTS,default=NOT_COUNTED)
    observation=models.TextField(blank=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['product__display_order','product_name']; unique_together=[('inventory','product')]

class Alert(models.Model):
    INFO='INFO'; MEDIUM='MEDIUM'; HIGH='HIGH'; CRITICAL='CRITICAL'; LEVELS=[(INFO,'Informativa'),(MEDIUM,'Media'),(HIGH,'Alta'),(CRITICAL,'Crítica')]
    inventory=models.ForeignKey(Inventory,on_delete=models.CASCADE,null=True,blank=True,related_name='alerts')
    alert_date=models.DateField(default=timezone.localdate)
    title=models.CharField(max_length=160); message=models.TextField(); level=models.CharField(max_length=10,choices=LEVELS)
    resolved=models.BooleanField(default=False); resolved_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name='alerts_resolved')
    resolved_at=models.DateTimeField(null=True,blank=True); resolution_note=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['resolved','-created_at']
