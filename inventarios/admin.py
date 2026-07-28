from django.contrib import admin

from .models import (
    Alert,
    AppSetting,
    AuditLog,
    Inventory,
    InventoryItem,
    PointOfSale,
    Product,
    Profile,
)


@admin.register(PointOfSale)
class PointOfSaleAdmin(admin.ModelAdmin):
    list_display = ("id", "__str__")
    search_fields = ("=id", "name", "code")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "__str__")
    search_fields = ("=id", "name", "code", "category")


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("id", "__str__")
    search_fields = ("=id",)


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ("id", "__str__")
    search_fields = ("=id",)


admin.site.register(Profile)
admin.site.register(AppSetting)
admin.site.register(Alert)
admin.site.register(AuditLog)