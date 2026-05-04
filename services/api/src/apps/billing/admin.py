from django.contrib import admin

from .models import (
    Plan,
    PromoCode,
    PromoCodeRedemption,
)


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'name', 'discount_type', 'discount_value',
        'duration_cycles', 'active', 'starts_at', 'ends_at',
        'max_redemptions', 'max_redemptions_per_business', 'created_at',
    ]
    list_filter = ['active', 'discount_type']
    search_fields = ['code', 'name']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    fieldsets = [
        ('Código', {
            'fields': ['code', 'name', 'description', 'active', 'created_by'],
        }),
        ('Descuento', {
            'fields': ['discount_type', 'discount_value', 'duration_cycles'],
        }),
        ('Vigencia', {
            'fields': ['starts_at', 'ends_at'],
        }),
        ('Límites de uso', {
            'fields': ['max_redemptions', 'max_redemptions_per_business'],
        }),
        ('Restricciones', {
            'fields': [
                'applies_to_plan_codes',
                'applies_to_service',
                'applies_to_billing_periods',
            ],
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse'],
        }),
    ]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PromoCodeRedemption)
class PromoCodeRedemptionAdmin(admin.ModelAdmin):
    list_display = [
        'promo_code', 'business', 'status',
        'original_amount', 'discounted_amount',
        'cycles_used', 'cycles_total',
        'price_restored', 'created_at',
    ]
    list_filter = ['status', 'price_restored']
    search_fields = ['promo_code__code', 'business__name']
    readonly_fields = [
        'promo_code', 'business', 'user', 'subscription', 'checkout_session',
        'original_amount', 'discounted_amount', 'cycles_total',
        'last_applied_payment_id', 'created_at', 'updated_at',
    ]
    raw_id_fields = ['subscription', 'checkout_session']
