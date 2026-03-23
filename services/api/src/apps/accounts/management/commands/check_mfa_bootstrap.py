"""
Management command: check_mfa_bootstrap

Reports MFA enrollment status for all platform staff and advises whether
MFA_BOOTSTRAP_ENABLED should be set to false.

Usage:
    python manage.py check_mfa_bootstrap          # human-readable report
    python manage.py check_mfa_bootstrap --json    # machine-readable

Exit codes:
    0 — bootstrap can stay enabled (some admins still need enrollment)
    1 — all admins enrolled → disable bootstrap NOW
"""
import json as json_mod
import sys

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.models import AccountProfile


class Command(BaseCommand):
    help = 'Check MFA enrollment status and advise on MFA_BOOTSTRAP_ENABLED'

    def add_arguments(self, parser):
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output machine-readable JSON',
        )

    def handle(self, *args, **options):
        staff = AccountProfile.objects.filter(is_platform_staff=True).select_related('user')
        total = staff.count()
        enrolled = staff.filter(mfa_enabled=True).count()
        not_enrolled = total - enrolled

        bootstrap_env = getattr(settings, 'MFA_BOOTSTRAP_ENABLED', False)
        should_disable = (total > 0 and not_enrolled == 0)

        if options['json']:
            self.stdout.write(json_mod.dumps({
                'total_admins': total,
                'mfa_enrolled': enrolled,
                'mfa_pending': not_enrolled,
                'bootstrap_enabled': bootstrap_env,
                'should_disable_bootstrap': should_disable,
                'pending_users': [
                    p.user.email
                    for p in staff.filter(mfa_enabled=False)
                ],
            }, indent=2))
        else:
            self.stdout.write(f'\n  Platform staff total:   {total}')
            self.stdout.write(f'  MFA enrolled:           {enrolled}')
            self.stdout.write(f'  MFA pending:            {not_enrolled}')
            self.stdout.write(f'  MFA_BOOTSTRAP_ENABLED:  {bootstrap_env}')
            self.stdout.write('')

            if not_enrolled > 0:
                self.stdout.write(self.style.WARNING(
                    '  Pending enrollment:'
                ))
                for p in staff.filter(mfa_enabled=False):
                    self.stdout.write(f'    - {p.user.email} ({p.internal_role})')
                self.stdout.write('')

            if should_disable:
                self.stdout.write(self.style.SUCCESS(
                    '  ✓ All admins have MFA enrolled.'
                ))
                if bootstrap_env:
                    self.stderr.write(self.style.ERROR(
                        '  ✗ MFA_BOOTSTRAP_ENABLED is still true!'
                        '  → Set MFA_BOOTSTRAP_ENABLED=false in your environment NOW.\n'
                    ))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        '  ✓ MFA_BOOTSTRAP_ENABLED is already false. All good.\n'
                    ))
            else:
                self.stdout.write(self.style.WARNING(
                    '  Bootstrap must stay enabled until all admins enroll MFA.\n'
                ))

        if should_disable and bootstrap_env:
            sys.exit(1)
