"""
Content-Security-Policy-Report-Only middleware for Django API responses.

Adds a conservative CSP in report-only mode so violations are observable
in the browser console without blocking anything.  This covers the DRF
browsable API and Django Admin; the main UI is covered by the Next.js
middleware.

Phase 2C — observation only.  Switch to ``Content-Security-Policy`` (enforce)
once violations have been triaged.
"""
from django.http import HttpRequest, HttpResponse


# The API mostly returns JSON, but DRF browsable API and Django admin serve HTML.
# Keep directives lenient; this is report-only.
_CSP_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])


class CSPReportOnlyMiddleware:
    """Append Content-Security-Policy-Report-Only to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response['Content-Security-Policy-Report-Only'] = _CSP_POLICY
        return response
