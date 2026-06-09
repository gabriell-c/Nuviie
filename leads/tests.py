from django.test import TestCase
from django.contrib.auth import get_user_model
from authentication.models import CustomUser
from authentication.whatsapp import clean_phone_number
from leads.models import Lead, LeadNote
from leads.scraper import run_google_maps_scraper, run_instagram_scraper

class NuviieSaaSTestCase(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            username="testuser",
            email="testuser@nuviie.com",
            password="testpassword123",
            first_name="Test",
            last_name="User",
            phone_number="5511999999999"
        )

    def test_user_creation(self):
        """Test user properties and authentication basics"""
        self.assertEqual(self.user.email, "testuser@nuviie.com")
        self.assertEqual(self.user.phone_number, "5511999999999")
        self.assertTrue(self.user.check_password("testpassword123"))

    def test_phone_normalization(self):
        """Test formatting cleans correct digits and drops symbols"""
        raw_phone = "+55 (11) 98888-8888"
        self.assertEqual(clean_phone_number(raw_phone), "5511988888888")
        
        raw_phone_with_spaces = "  55 11 97777 7777  "
        self.assertEqual(clean_phone_number(raw_phone_with_spaces), "5511977777777")

    def test_lead_quality_score(self):
        """Test auto-calculation of lead details quality score"""
        lead = Lead.objects.create(
            user=self.user,
            name="Clínica Odonto Test",
            category="Dentista",
            city="São Paulo",
            phone_number="(11) 99999-9999",
            normalized_phone="5511999999999",
            website="https://odontotest.com",
            instagram="@odontotest",
            source="google_maps",
            status="novo"
        )
        # Check that quality calculation yields maximum score since info is present
        # +20 phone, +20 website, +20 instagram, +20 category = 80 minimum
        self.assertGreaterEqual(lead.quality_score, 80)
        
        # Incomplete lead
        poor_lead = Lead.objects.create(
            user=self.user,
            name="Anon Business",
            source="google_maps",
            status="novo"
        )
        # Rating, phone, socials, categories, website are blank. Quality should be 0.
        self.assertEqual(poor_lead.quality_score, 0)

    def test_google_maps_scraper_deduplication(self):
        """Test lead scraper imports correct counts and drops duplicates"""
        # Run Google Maps scrape once for 5 leads
        saved, skipped = run_google_maps_scraper(
            user=self.user,
            city="São Paulo",
            niche="Dentistas",
            limit=5,
            only_without_website=False,
            seed=42
        )
        self.assertEqual(saved, 5)
        self.assertEqual(skipped, 0)
        self.assertEqual(Lead.objects.filter(user=self.user).count(), 5)
        
        # Run again with same parameters - should identify them as duplicates and save 0
        saved_again, skipped_again = run_google_maps_scraper(
            user=self.user,
            city="São Paulo",
            niche="Dentistas",
            limit=5,
            only_without_website=False,
            seed=42
        )
        self.assertEqual(saved_again, 0)
        self.assertEqual(skipped_again, 5)
        self.assertEqual(Lead.objects.filter(user=self.user).count(), 5)

    def test_instagram_scraper_verified_filter(self):
        """Test Instagram crawler applies query criteria and checks badges"""
        saved, skipped = run_instagram_scraper(
            user=self.user,
            niche="Advogados",
            location="Curitiba",
            limit=3,
            only_verified=True,
            only_with_bio_link=True,
            seed=42
        )
        self.assertEqual(saved, 3)
        
        # All imported leads must be verified and have a website
        for lead in Lead.objects.filter(user=self.user, source='instagram'):
            self.assertTrue(lead.is_verified)
            self.assertIsNotNone(lead.website)
            self.assertTrue(lead.website.startswith("http"))
