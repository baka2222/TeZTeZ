from django.contrib import admin
from .models import (
    Client, Shop, Product, Service, Order, OrderItem,
    PricingRule, TimeSurcharge, CourierOrder
)
from client.models import Category

# ─── Inlines for Products and Services in Shop ─────────────────────────────────

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)

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
    list_display    = ("name", "owner", "address", "created_at", 'category', 'point_a_lat', 'point_a_lng')
    search_fields   = ("name", "owner__name")
    list_filter     = ("owner", "category", )
    readonly_fields = ("created_at",)
    inlines         = [ProductInline, ServiceInline]
    fieldsets = (
        (None, {
            "fields": ("name", "category", "owner", "address", "description", "point_a_lat", "point_a_lng"),
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
        return qs.filter(owner__phone=str(request.user.last_name))

# ─── Admin for Client ──────────────────────────────────────────────────────────

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display    = (
        "name", "username", "phone", "tg_code", "is_banned",
        "next_ability", "next_ability_beauty", "next_ability_automoto",
        "next_ability_techno", "next_ability_housing", "next_ability_job",
        "created_at", "updated_at",
    )
    search_fields   = ("name", "username", "phone", "tg_code",)
    list_filter     = ("is_banned",)
    list_editable   = ("is_banned",)
    readonly_fields = ("created_at", "updated_at",)
    fieldsets = (
        (None, {
            "fields": (
                "name", "username", "phone", "tg_code", "is_banned",
                "next_ability", "next_ability_beauty", "next_ability_automoto",
                "next_ability_techno", "next_ability_housing", "next_ability_job",
            ),
        }),
        ("Даты", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

# ─── Admin for Product ─────────────────────────────────────────────────────────

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display    = ("name", "shop", "price", "created_at")
    search_fields   = ("name", "shop__name")
    list_filter     = ("shop",)
    readonly_fields = ("created_at",)
    fieldsets = (
        (None, {"fields": ("shop", "name", "price", "description"),}),
        ("Дополнительно", {"fields": ("created_at",), "classes": ("collapse",),}),
    )
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(shop__owner__phone=str(request.user.last_name))

# ─── Admin for Service ─────────────────────────────────────────────────────────

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display    = ("name", "shop", "price", "created_at")
    search_fields   = ("name", "shop__name")
    list_filter     = ("shop",)
    readonly_fields = ("created_at",)
    fieldsets = (
        (None, {"fields": ("shop", "name", "price", "description"),}),
        ("Дополнительно", {"fields": ("created_at",), "classes": ("collapse",),}),
    )
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(shop__owner__phone=str(request.user.last_name))

# ─── Inline for OrderItem ───────────────────────────────────────────────────────

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product", "service", "quantity")
    show_change_link = False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display    = ("id", "shop", "client", "total_price", "created_at")
    search_fields   = ("shop__name", "client__name")
    list_filter     = ("shop", "client")
    readonly_fields = ("total_price", "created_at")
    fieldsets = (
        (None, {"fields": ("shop", "client"),}),
        ("Дополнительно", {"fields": ("total_price", "created_at"), "classes": ("collapse",),}),
    )
    inlines = [OrderItemInline]
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(shop__owner__phone=str(request.user.last_name))

# ─── Admin for CourierOrder and Pricing ────────────────────────────────────────

@admin.register(PricingRule)
class PricingRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "min_distance", "max_distance", "base_price", "per_km_price", "multiplier")
    list_editable = ("min_distance", "max_distance", "base_price", "per_km_price", "multiplier")
    ordering = ("min_distance",)

@admin.register(TimeSurcharge)
class TimeSurchargeAdmin(admin.ModelAdmin):
    list_display = ("name", "start_time", "end_time", "multiplier")
    ordering = ("start_time",)

@admin.register(CourierOrder)
class CourierOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "client", "courier", "distance_km", "price", "created_at", 'status')
    list_filter = ("courier",)
    search_fields = ("client__name", "courier__name")
    readonly_fields = ("distance_km", "price", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("client", "courier", "point_a_lat", "point_a_lng", "point_b_lat", "point_b_lng", "comment",  'status'),}),
        ("Результаты расчётов", {"fields": ("distance_km", "price", "created_at", "updated_at"), "classes": ("collapse",),}),
    )
