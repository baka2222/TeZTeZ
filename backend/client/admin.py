# backend/client/admin.py

from django.contrib import admin
from .models import Client, Shop, Product, Service, Order, OrderItem

# ─── Inline для Product и Service в админке Shop ─────────────────────────────────

class ProductInline(admin.TabularInline):
    model = Product
    extra = 1
    fields = ("name", "price")
    show_change_link = True

class ServiceInline(admin.TabularInline):
    model = Service
    extra = 1
    fields = ("name", "price")
    show_change_link = True

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display   = ("name", "owner", "address", "created_at")
    search_fields  = ("name", "owner__name")
    list_filter    = ("owner",)
    readonly_fields= ("created_at",)
    inlines        = [ProductInline, ServiceInline]
    fieldsets = (
        (None, {
            "fields": ("name", "owner", "address", "description"),
        }),
        ("Дополнительно", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Считаем, что request.user.id = tg_code владельца
        return qs.filter(owner__tg_code=str(request.user.id))


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display   = ("name", "phone", "tg_code", "created_at", "updated_at")
    search_fields  = ("name", "phone", "tg_code")
    readonly_fields= ("created_at", "updated_at")
    fieldsets = (
        (None, {
            "fields": ("name", "phone", "tg_code"),
        }),
        ("Даты", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display   = ("name", "shop", "price", "created_at")
    search_fields  = ("name", "shop__name")
    list_filter    = ("shop",)
    readonly_fields= ("created_at",)
    fieldsets = (
        (None, {
            "fields": ("shop", "name", "price", "description"),
        }),
        ("Дополнительно", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(shop__owner__tg_code=str(request.user.id))


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display   = ("name", "shop", "price", "created_at")
    search_fields  = ("name", "shop__name")
    list_filter    = ("shop",)
    readonly_fields= ("created_at",)
    fieldsets = (
        (None, {
            "fields": ("shop", "name", "price", "description"),
        }),
        ("Дополнительно", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(shop__owner__tg_code=str(request.user.id))


# ─── Inline для позиций заказа (OrderItem) ────────────────────────────────────────

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    fields = ("product", "quantity")
    readonly_fields = ()
    # Если нужно запретить редактирование конкретных полей, укажите их здесь


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display   = ("id", "shop", "client", "total_price", "created_at")
    search_fields  = ("shop__name", "client__name")
    list_filter    = ("shop", "client")
    readonly_fields= ("created_at", "total_price")
    fieldsets = (
        (None, {
            "fields": ("shop", "client"),
        }),
        ("Позиции заказа", {
            "fields": (),  # сами позиции редактируются через inline
            "classes": ("collapse",),
        }),
        ("Дополнительно", {
            "fields": ("total_price", "created_at"),
            "classes": ("collapse",),
        }),
    )
    inlines = [OrderItemInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(shop__owner__tg_code=str(request.user.id))
