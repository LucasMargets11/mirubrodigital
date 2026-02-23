from decimal import Decimal
from typing import List, Optional, Dict, Any
from django.utils import timezone
from django.db import models
from .models import Module, Bundle, Promotion, Subscription
from apps.business.models import Business

class PricingService:
    @staticmethod
    def calculate_quote(
        vertical: str,
        billing_period: str,
        plan_type: str,
        selected_module_codes: List[str] = None,
        bundle_code: str = None
    ) -> Dict[str, Any]:
        
        modules = []
        bundle = None
        
        # 1. Resolve Modules and Validation
        if plan_type == 'bundle':
            if not bundle_code:
                raise ValueError("Bundle code is required for bundle plan type")
            try:
                bundle = Bundle.objects.get(code=bundle_code, is_active=True)
                modules = list(bundle.modules.filter(is_active=True))
                # Validate vertical (optional strict check)
                # if bundle.vertical != vertical: ...
            except Bundle.DoesNotExist:
                raise ValueError("Invalid bundle code")
                
        elif plan_type == 'custom':
            if selected_module_codes is None:
                selected_module_codes = []
            
            # Auto-include core modules for vertical
            core_modules = Module.objects.filter(is_active=True, is_core=True).filter(
                models.Q(vertical=vertical) | models.Q(vertical='both')
            )
            
            # Get selected
            selected_modules_qs = Module.objects.filter(code__in=selected_module_codes, is_active=True)
            modules = list(selected_modules_qs)
            
            # Add missing cores
            selected_ids = {m.id for m in modules}
            for core in core_modules:
                if core.id not in selected_ids:
                    modules.append(core)
            
            # Check dependencies
            module_map = {m.code: m for m in modules}
            for m in modules:
                for req in m.requires.all():
                    if req.code not in module_map:
                        raise ValueError(f"Module {m.name} requires {req.name}")

        else:
             raise ValueError("Invalid plan type")

        # 2. Base Calculation
        subtotal = 0
        module_details = []
        
        price_field = 'price_monthly' if billing_period == 'monthly' else 'price_yearly'
        
        for m in modules:
            price = getattr(m, price_field)
            if price is None and billing_period == 'yearly':
                price = m.price_monthly * 12
                
            module_details.append({
                'code': m.code,
                'name': m.name,
                'price': price
            })
            subtotal += price

        # 3. Apply Bundle Pricing / Discount
        discount_amount = 0
        final_total = subtotal
        
        if plan_type == 'bundle' and bundle:
            bundle_price = None
            
            if bundle.pricing_mode == 'fixed_price':
                bundle_price = getattr(bundle, f'fixed_price_{billing_period}')
                if bundle_price is None and billing_period == 'yearly':
                     bundle_price = (bundle.fixed_price_monthly or 0) * 12
            
            elif bundle.pricing_mode == 'discount_percent':
                 if bundle.discount_percent:
                     discount = Decimal(subtotal) * (bundle.discount_percent / 100)
                     discount_val = int(discount)
                     bundle_price = subtotal - discount_val

            if bundle_price is not None:
                final_total = bundle_price
                discount_amount = subtotal - final_total

        # 4. Suggestions (if Custom)
        suggestion = None
        if plan_type == 'custom':
            bundle_candidates = Bundle.objects.filter(vertical=vertical, is_active=True)
            selected_ids = set(m.id for m in modules)
            
            for b in bundle_candidates:
                b_module_ids = set(b.modules.values_list('id', flat=True))
                # Logic: Is the bundle exactly what was selected?
                if b_module_ids == selected_ids:
                    # Calculate bundle price
                    b_price = 0
                    if b.pricing_mode == 'fixed_price':
                         b_price = getattr(b, f'fixed_price_{billing_period}')
                         if b_price is None and billing_period == 'yearly':
                             b_price = (b.fixed_price_monthly or 0) * 12
                    elif b.pricing_mode == 'discount_percent':
                         b_subtotal = subtotal # Matches exactly
                         if b.discount_percent:
                            discount = Decimal(b_subtotal) * (b.discount_percent / 100)
                            b_price = b_subtotal - int(discount)
                         else:
                            b_price = b_subtotal
                    
                    savings = final_total - b_price
                    if savings > 0:
                        suggestion = {
                            'bundle_code': b.code,
                            'bundle_name': b.name,
                            'bundle_total': b_price,
                            'savings_amount': savings,
                            'savings_percent': round((savings / final_total) * 100, 1)
                        }
                    break

        # 5. Apply Promotions
        promo_discount = 0
        applied_promo = None
        
        now = timezone.now()
        
        if plan_type == 'bundle' and bundle:
             active_promo = Promotion.objects.filter(
                 applies_to='bundle',
                 target_bundle=bundle,
                 is_active=True,
                 starts_at__lte=now
             ).filter(models.Q(ends_at__gte=now) | models.Q(ends_at__isnull=True)).first()
             
             if active_promo:
                 # Prefer discount percent logic for transparency
                 if active_promo.discount_percent:
                     d_amt = Decimal(final_total) * (active_promo.discount_percent / 100)
                     promo_discount = int(d_amt)
                     final_total -= promo_discount
                     applied_promo = {
                         'code': active_promo.code,
                         'name': active_promo.name,
                         'amount': promo_discount
                     }
                 elif active_promo.fixed_override_price is not None:
                     # Simplified handling
                     pass

        return {
            'subtotal': subtotal,
            'bundle_discount': discount_amount,
            'promo_discount': promo_discount,
            'total': final_total,
            'modules': module_details,
            'suggestion': suggestion,
            'applied_promo': applied_promo,
            'currency': 'ARS'
        }

    @staticmethod
    def tenant_has_feature(business_id: int, feature_code: str) -> bool:
        try:
            sub = Subscription.objects.get(business_id=business_id)
        except Subscription.DoesNotExist:
            return False
            
        if sub.status not in ['active', 'trial']:
            return False
        
        if sub.plan_type == 'bundle':
            if sub.bundle:
                return sub.bundle.modules.filter(code=feature_code).exists()
        else:
            return sub.selected_modules.filter(code=feature_code).exists()
        
        return False
