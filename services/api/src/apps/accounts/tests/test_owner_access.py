"""
Tests for Owner Access Management endpoints
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import Membership, AccessAuditLog
from apps.business.models import Business, Subscription

User = get_user_model()


class OwnerAccessEndpointsTestCase(TestCase):
    """Test suite for owner-only access management endpoints."""
    
    def setUp(self):
        """Set up test data."""
        # Create HQ business
        self.business = Business.objects.create(
            name="Test HQ",
            default_service="gestion"
        )
        self.subscription = Subscription.objects.create(
            business=self.business,
            plan="starter",
            status="active"
        )
        
        # Create owner user
        self.owner = User.objects.create_user(
            username="owner@test.com",
            email="owner@test.com",
            password="testpass123"
        )
        self.owner_membership = Membership.objects.create(
            user=self.owner,
            business=self.business,
            role="owner"
        )
        
        # Create staff user
        self.staff = User.objects.create_user(
            username="staff@test.com",
            email="staff@test.com",
            password="testpass123"
        )
        self.staff_membership = Membership.objects.create(
            user=self.staff,
            business=self.business,
            role="staff"
        )
        
        # Create manager user
        self.manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="testpass123"
        )
        self.manager_membership = Membership.objects.create(
            user=self.manager,
            business=self.business,
            role="manager"
        )
        
        self.client = APIClient()
    
    def test_access_summary_authenticated(self):
        """Test that authenticated users can access their summary."""
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/v1/owner/access/summary/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['role'], 'staff')
        self.assertIn('permissions_by_module', response.data)
    
    def test_roles_list_owner_only(self):
        """Test that only owners can list roles."""
        # Staff should get 403
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/v1/owner/access/roles/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Owner should succeed
        self.client.force_authenticate(user=self.owner)
        response = self.client.get('/api/v1/owner/access/roles/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
    
    def test_accounts_list_owner_only(self):
        """Test that only owners can list accounts."""
        # Manager should get 403
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/v1/owner/access/accounts/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Owner should succeed
        self.client.force_authenticate(user=self.owner)
        response = self.client.get('/api/v1/owner/access/accounts/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)  # owner + staff + manager
    
    def test_reset_password_owner_only(self):
        """Test that only owners can reset passwords."""
        # Staff trying to reset manager password should get 403
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(f'/api/v1/owner/access/accounts/{self.manager.id}/reset-password/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Owner should succeed
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(f'/api/v1/owner/access/accounts/{self.staff.id}/reset-password/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('temporary_password', response.data)
        self.assertIn('username', response.data)
    
    def test_reset_password_creates_audit_log(self):
        """Test that password reset creates audit log."""
        self.client.force_authenticate(user=self.owner)
        
        initial_count = AccessAuditLog.objects.count()
        
        response = self.client.post(f'/api/v1/owner/access/accounts/{self.staff.id}/reset-password/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check audit log was created
        self.assertEqual(AccessAuditLog.objects.count(), initial_count + 1)
        
        log = AccessAuditLog.objects.latest('created_at')
        self.assertEqual(log.action, 'PASSWORD_RESET')
        self.assertEqual(log.actor, self.owner)
        self.assertEqual(log.target_user, self.staff)
        self.assertEqual(log.business, self.business)
    
    def test_reset_password_changes_user_password(self):
        """Test that password is actually changed."""
        self.client.force_authenticate(user=self.owner)
        
        old_password = self.staff.password
        
        response = self.client.post(f'/api/v1/owner/access/accounts/{self.staff.id}/reset-password/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Refresh user from DB
        self.staff.refresh_from_db()
        
        # Password hash should have changed
        self.assertNotEqual(self.staff.password, old_password)
        
        # Temporary password should work
        temp_password = response.data['temporary_password']
        self.assertTrue(self.staff.check_password(temp_password))
    
    def test_reset_password_prevents_self_reset(self):
        """Test that owner cannot reset their own password."""
        self.client.force_authenticate(user=self.owner)
        
        response = self.client.post(f'/api/v1/owner/access/accounts/{self.owner.id}/reset-password/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_reset_password_cross_tenant_forbidden(self):
        """Test that owner cannot reset password for user in different business."""
        # Create another business
        other_business = Business.objects.create(name="Other Business")
        other_user = User.objects.create_user(
            username="other@test.com",
            email="other@test.com",
            password="testpass123"
        )
        Membership.objects.create(
            user=other_user,
            business=other_business,
            role="staff"
        )
        
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(f'/api/v1/owner/access/accounts/{other_user.id}/reset-password/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_disable_account_owner_only(self):
        """Test that only owners can disable accounts."""
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(f'/api/v1/owner/access/accounts/{self.manager.id}/disable/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(f'/api/v1/owner/access/accounts/{self.staff.id}/disable/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_disable_account_toggles_status(self):
        """Test that disable toggles is_active status."""
        self.client.force_authenticate(user=self.owner)
        
        # Initially active
        self.assertTrue(self.staff.is_active)
        
        # First call disables
        response = self.client.post(f'/api/v1/owner/access/accounts/{self.staff.id}/disable/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_active'])
        
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)
        
        # Second call re-enables
        response = self.client.post(f'/api/v1/owner/access/accounts/{self.staff.id}/disable/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_active'])
        
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)
    
    def test_audit_logs_owner_only(self):
        """Test that only owners can view audit logs."""
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/v1/owner/access/audit-logs/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        self.client.force_authenticate(user=self.owner)
        response = self.client.get('/api/v1/owner/access/audit-logs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
    
    def test_temporary_password_is_strong(self):
        """Test that generated temporary password meets security requirements."""
        self.client.force_authenticate(user=self.owner)
        
        response = self.client.post(f'/api/v1/owner/access/accounts/{self.staff.id}/reset-password/')
        temp_password = response.data['temporary_password']
        
        # Check length
        self.assertGreaterEqual(len(temp_password), 12)
        
        # Check has uppercase
        self.assertTrue(any(c.isupper() for c in temp_password))
        
        # Check has lowercase
        self.assertTrue(any(c.islower() for c in temp_password))
        
        # Check has digit
        self.assertTrue(any(c.isdigit() for c in temp_password))
