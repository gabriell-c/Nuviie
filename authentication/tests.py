import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from authentication import face_store

User = get_user_model()

SAMPLES = [[0.1] * 512, [0.2] * 512]


class FaceProfilePortabilityTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir_patch = patch.object(face_store, 'PROFILE_DIR', Path(self.tmp.name))
        self.dir_patch.start()
        self.addCleanup(self.dir_patch.stop)

    def _make_user(self, email='me@example.com', with_face=True):
        user = User.objects.create_user(
            username=email.split('@')[0], email=email, password='x',
        )
        if with_face:
            user.face_encoding = face_store.encode_samples_to_bytes(SAMPLES)
            user.face_login_enabled = True
            user.save()
        return user

    def test_export_creates_file(self):
        user = self._make_user()
        self.assertTrue(face_store.export_profile(user))
        files = list(Path(self.tmp.name).glob('*.json'))
        self.assertEqual(len(files), 1)

    def test_import_restores_into_empty_user(self):
        """Simula outro PC: usuário existe mas sem encoding; arquivo restaura."""
        user = self._make_user()
        face_store.export_profile(user)

        # Simula máquina nova: zera o encoding no banco.
        user.face_encoding = None
        user.face_login_enabled = False
        user.save()

        restored, files = face_store.import_profiles()
        self.assertEqual(restored, 1)
        self.assertEqual(files, 1)

        user.refresh_from_db()
        self.assertTrue(user.face_login_enabled)
        self.assertEqual(face_store.decode_samples_from_bytes(user.face_encoding), SAMPLES)

    def test_import_does_not_overwrite_by_default(self):
        user = self._make_user()
        face_store.export_profile(user)
        # Usuário já tem encoding → import padrão não mexe.
        restored, _ = face_store.import_profiles()
        self.assertEqual(restored, 0)

    def test_import_overwrite(self):
        user = self._make_user()
        face_store.export_profile(user)
        user.face_encoding = face_store.encode_samples_to_bytes([[0.9] * 512])
        user.save()
        restored, _ = face_store.import_profiles(overwrite=True)
        self.assertEqual(restored, 1)
        user.refresh_from_db()
        self.assertEqual(face_store.decode_samples_from_bytes(user.face_encoding), SAMPLES)

    def test_import_matches_by_email_case_insensitive(self):
        user = self._make_user(email='Me@Example.com')
        face_store.export_profile(user)
        user.face_encoding = None
        user.save()
        restored, _ = face_store.import_profiles()
        self.assertEqual(restored, 1)

    def test_remove_profile(self):
        user = self._make_user()
        face_store.export_profile(user)
        face_store.remove_profile(user.email)
        self.assertEqual(list(Path(self.tmp.name).glob('*.json')), [])
