from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
  email = serializers.EmailField()
  password = serializers.CharField(trim_whitespace=False)


class RegisterSerializer(serializers.Serializer):
  email = serializers.EmailField()
  password = serializers.CharField(min_length=8, trim_whitespace=False)


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=10)
    new_password = serializers.CharField(min_length=8, trim_whitespace=False)


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=10)
