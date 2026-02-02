from rest_framework import serializers
from .models import Module, Bundle, Promotion, Subscription

class ModuleSimpleSerializer(serializers.ModelSerializer):
    # Only expose code for recursive serialization in bundles to avoid infinite depth issues or just self reference
    class Meta:
        model = Module
        fields = ['code']

class ModuleSerializer(serializers.ModelSerializer):
    requires = ModuleSimpleSerializer(many=True, read_only=True)
    
    class Meta:
        model = Module
        fields = [
            'code', 'name', 'description', 'category', 'vertical', 
            'price_monthly', 'price_yearly', 'is_core', 'requires', 'is_active'
        ]

class BundleSerializer(serializers.ModelSerializer):
    modules = ModuleSerializer(many=True, read_only=True)
    
    class Meta:
        model = Bundle
        fields = [
            'code', 'name', 'description', 'vertical', 'badge', 
            'modules', 'pricing_mode', 'fixed_price_monthly', 
            'fixed_price_yearly', 'discount_percent', 'is_default_recommended'
        ]

class PromotionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Promotion
        fields = ['code', 'name', 'discount_percent', 'fixed_override_price', 'ends_at']

class QuoteRequestSerializer(serializers.Serializer):
    vertical = serializers.ChoiceField(choices=['commercial', 'restaurant'])
    billing_period = serializers.ChoiceField(choices=['monthly', 'yearly'])
    plan_type = serializers.ChoiceField(choices=['bundle', 'custom'])
    selected_module_codes = serializers.ListField(child=serializers.CharField(), required=False)
    bundle_code = serializers.CharField(required=False, allow_null=True)

class SubscribeRequestSerializer(serializers.Serializer):
    plan_type = serializers.ChoiceField(choices=['bundle', 'custom'])
    billing_period = serializers.ChoiceField(choices=['monthly', 'yearly'])
    bundle_code = serializers.CharField(required=False, allow_null=True)
    selected_module_codes = serializers.ListField(child=serializers.CharField(), required=False)

class SubscriptionSerializer(serializers.ModelSerializer):
    bundle = BundleSerializer(read_only=True)
    selected_modules = ModuleSerializer(many=True, read_only=True)
    
    class Meta:
        model = Subscription
        fields = [
            'plan_type', 'bundle', 'selected_modules', 'billing_period', 
            'currency', 'price_snapshot', 'status', 'created_at'
        ]
