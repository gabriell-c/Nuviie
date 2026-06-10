from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True, unique=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    whatsapp_otp = models.CharField(max_length=6, blank=True, null=True)
    whatsapp_otp_created_at = models.DateTimeField(blank=True, null=True)
    face_encoding = models.BinaryField(null=True, blank=True)
    face_login_enabled = models.BooleanField(default=False)

    # Use email as the primary username field for SaaS-like behavior
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def is_otp_valid(self):
        if not self.whatsapp_otp or not self.whatsapp_otp_created_at:
            return False
        # OTP is valid for 10 minutes
        expiry = self.whatsapp_otp_created_at + timezone.timedelta(minutes=10)
        return timezone.now() <= expiry

