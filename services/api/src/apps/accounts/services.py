from django.db import transaction
from django.core.exceptions import ValidationError
from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

class MembershipService:
    @staticmethod
    def create_membership_safely(user, business, role):
        """
        Creates a membership ensuring seat limits are respected with row locking.
        """
        with transaction.atomic():
            # Resolve HQ and lock specific tables or rows if possible
            # We lock the HQ business to serialize additions to the family
            hq = business.parent if business.parent else business
            
            # Select for update to prevent concurrent reads of seat counts
            # We lock the HQ subscription since the limit is there
            try:
                sub = Subscription.objects.select_for_update().get(business=hq)
            except Subscription.DoesNotExist:
                # If no subscription, maybe we don't enforce? Or fail?
                # Default logic usually implies open or starter. 
                # Assuming check_seat_limit signal default behavior: if no sub, no limit.
                sub = None

            if sub and sub.max_seats > 0:
                family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))
                current_count = Membership.objects.filter(business__id__in=family_ids).count()
                
                if current_count >= sub.max_seats:
                    raise ValidationError(f"Límite de usuarios ({sub.max_seats}) alcanzado para la cuenta {hq.name}.")

            # Proceed to create
            return Membership.objects.create(user=user, business=business, role=role)
