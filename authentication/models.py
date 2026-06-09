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

    def is_face_match(self, encoding, tolerance=1000):
        """Compare a captured face image (bytes) with stored encoding using OpenCV.
        The `encoding` argument is a NumPy array representing the captured image.
        Returns True if mean squared error is below tolerance.
        """
        if not self.face_encoding:
            return False
        try:
            import cv2, numpy as np
        except ImportError:
            return False
        # Convert stored bytes to image
        stored_arr = np.frombuffer(self.face_encoding, dtype=np.uint8)
        stored_img = cv2.imdecode(stored_arr, cv2.IMREAD_COLOR)
        if stored_img is None:
            return False
        # Resize both images to same size for comparison
        target_size = (150, 150)
        stored_resized = cv2.resize(stored_img, target_size)
        # `encoding` is expected to be a NumPy array (BGR)
        captured_resized = cv2.resize(encoding, target_size)
        # Compute mean squared error
        mse = np.mean((stored_resized.astype('float') - captured_resized.astype('float')) ** 2)
        return mse <= tolerance


