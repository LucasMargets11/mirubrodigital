
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.exceptions import PermissionDenied

from apps.business.models import Business, Subscription
from apps.accounts.models import Membership
from apps.accounts.services import MembershipService
from apps.accounts.access import resolve_request_membership
from apps.business.scope import get_allowed_business_ids

User = get_user_model()

class TestScopeValidation(TestCase):
    def setUp(self):
        # Setup HQ and Branches
        self.owner = User.objects.create_user(username='hq_owner', email='owner@hq.com', password='password')
        self.manager = User.objects.create_user(username='hq_manager', email='manager@hq.com', password='password')
        self.employee = User.objects.create_user(username='branch_emp', email='emp@branch.com', password='password')

        self.hq = Business.objects.create(name="HQ")
        # Manually create owner membership
        Membership.objects.create(user=self.owner, business=self.hq, role='owner')

        self.branch_a = Business.objects.create(name="Branch A", parent=self.hq)
        # Note: Depending on business logic, owner might NOT be automatically added to branch as member.
        # But for scope='children' to work, we are testing that HQ owner CAN see it.
        
        self.branch_b = Business.objects.create(name="Branch B", parent=self.hq)

        # Create a manager in HQ (admin role)
        Membership.objects.create(user=self.manager, business=self.hq, role='admin')

        # Create an employee in Branch A (waiter role)
        Membership.objects.create(user=self.employee, business=self.branch_a, role='waiter')

    def test_scope_current_always_allowed(self):
        """Scope 'current' should always return just the current business ID."""
        ids = get_allowed_business_ids(self.owner, self.hq, scope='current')
        self.assertEqual(ids, [self.hq.id])

        ids_branch = get_allowed_business_ids(self.employee, self.branch_a, scope='current')
        self.assertEqual(ids_branch, [self.branch_a.id])

    def test_scope_children_allowed_for_hq_owner(self):
        """Owner of HQ should be able to see children scope."""
        ids = get_allowed_business_ids(self.owner, self.hq, scope='children')
        self.assertSetEqual(set(ids), {self.hq.id, self.branch_a.id, self.branch_b.id})

    def test_scope_children_denied_for_branch_context(self):
        """If current business is a branch, cannot request children scope (no grandchildren logic yet)."""
        with self.assertRaises(PermissionDenied):
            get_allowed_business_ids(self.owner, self.branch_a, scope='children')

    def test_scope_children_denied_for_non_admin(self):
        """Regular employee cannot see aggregated scope."""
        # Employee is in Branch A. Even if we added them to HQ as waiter:
        Membership.objects.create(user=self.employee, business=self.hq, role='waiter')
        with self.assertRaises(PermissionDenied):
            get_allowed_business_ids(self.employee, self.hq, scope='children')

    def test_scope_selected_validation(self):
        """Selected scope should filter correct IDs and reject invalid ones."""
        # Select only Branch A
        ids = get_allowed_business_ids(self.owner, self.hq, scope='selected', selection=[self.branch_a.id])
        self.assertEqual(ids, [self.branch_a.id])

        # Try to select a random business not owned
        random_biz = Business.objects.create(name="Random")
        Membership.objects.create(user=self.manager, business=random_biz, role='owner')
        
        with self.assertRaises(PermissionDenied):
            get_allowed_business_ids(self.owner, self.hq, scope='selected', selection=[random_biz.id])

class TestHierarchyAccess(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='hq_owner', email='owner@hq.com', password='password')
        self.hq = Business.objects.create(name="HQ")
        Membership.objects.create(user=self.owner, business=self.hq, role='owner')

        self.branch = Business.objects.create(name="Branch", parent=self.hq)
        
        # CRITICAL: Ensure owner is NOT member of Branch explicitly
        Membership.objects.filter(user=self.owner, business=self.branch).delete()

    def test_owner_implicit_access_to_branch(self):
        """
        HQ Owner should be able to access branch context even without explicit membership.
        """
        factory = RequestFactory()
        # Simulate request to Branch context
        request = factory.get(f'/api/branch/', HTTP_X_BUSINESS_ID=str(self.branch.id))
        request.user = self.owner
        
        # This function is what AuthenticationMiddleware / View uses
        membership = resolve_request_membership(request)
        
        self.assertIsNotNone(membership)
        # The membership returned is still the HQ one (which allows access)
        self.assertEqual(membership.business, self.hq)
        self.assertEqual(membership.user, self.owner)
        
        # BUT the request context should have been switched to the branch
        self.assertEqual(request.business, self.branch)


    def test_unrelated_user_denied(self):
        other_user = User.objects.create_user(username='other', email='other@test.com', password='password')
        factory = RequestFactory()
        request = factory.get(f'/api/branch/', HTTP_X_BUSINESS_ID=str(self.branch.id))
        request.user = other_user

        # resolve_request_membership returns None if denied/not found, it doesn't raise PermissionDenied
        # The view layer handles the 403.
        self.assertIsNone(resolve_request_membership(request))

class TestSeatLimitSafety(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='owner@test.com', password='p')
        self.business = Business.objects.create(name="Biz")
        Membership.objects.create(user=self.owner, business=self.business, role='owner')
        
        # Create Subscription and force a small limit
        self.sub = Subscription.objects.create(business=self.business, max_seats=2)
        
        # Owner takes 1 seat
        self.assertEqual(Membership.objects.filter(business=self.business).count(), 1)

    def test_add_member_within_limit(self):
        """Should succeed if slots open"""
        user2 = User.objects.create_user(username='u2', email='u2@test.com')
        # Pass user object to service (user, business, role)
        mem = MembershipService.create_membership_safely(user2, self.business, 'waiter')
        self.assertIsNotNone(mem)
        self.assertEqual(Membership.objects.filter(business=self.business).count(), 2)

    def test_add_member_exceeding_limit(self):
        """Should fail if limit reached"""
        # Fill the last slot
        user2 = User.objects.create_user(username='u2', email='u2@test.com')
        MembershipService.create_membership_safely(user2, self.business, 'waiter')
        
        # Try one more
        user3 = User.objects.create_user(username='u3', email='u3@test.com')
        with self.assertRaises(ValidationError) as cm:
            MembershipService.create_membership_safely(user3, self.business, 'waiter')
        
        self.assertIn("Límite de usuarios", str(cm.exception))

    def test_removed_member_frees_slot(self):
        """If we remove a member, we can add another."""
        user2 = User.objects.create_user(username='u2', email='u2@test.com')
        mem = MembershipService.create_membership_safely(user2, self.business, 'waiter')
        
        # Use delete() as Membership has no is_active field
        mem.delete()
        
        # Now adding user3 should work
        user3 = User.objects.create_user(username='u3', email='u3@test.com')
        mem3 = MembershipService.create_membership_safely(user3, self.business, 'waiter')
        self.assertIsNotNone(mem3)

