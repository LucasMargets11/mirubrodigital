from typing import Optional

from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
  """Allow JWT authentication via Authorization header or httpOnly cookies."""

  def authenticate(self, request):  # type: ignore[override]
    header = self.get_header(request)
    if header is not None:
      raw_token = self.get_raw_token(header)
    else:
      raw_token = request.COOKIES.get('access_token')

    if raw_token is None:
      return None

    validated_token = self.get_validated_token(raw_token)
    return self.get_user(validated_token), validated_token
