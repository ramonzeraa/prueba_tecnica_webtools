from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Membership, Organization, Response, Survey


class SurveyApiTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Northwind")
        self.user = get_user_model().objects.create_user("ana", password="ana123")
        Membership.objects.create(user=self.user, organization=self.organization)
        self.survey = Survey.objects.create(
            organization=self.organization,
            title="Customer satisfaction",
            external_key="northwind-csat",
        )
        Response.objects.create(
            survey=self.survey,
            external_id="evt-001",
            status="complete",
            answers={"nps": 9},
            submitted_at=timezone.now() - timedelta(days=1),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_authorized_user_can_list_results(self):
        response = self.client.get(f"/api/surveys/{self.survey.id}/results/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_user_cannot_access_survey_from_another_organization(self):
        other_org = Organization.objects.create(name="Contoso")
        other_survey = Survey.objects.create(
            organization=other_org,
            title="Employee NPS",
            external_key="contoso-enps",
        )

        response = self.client.get(f"/api/surveys/{other_survey.id}/results/")

        self.assertEqual(response.status_code, 404)

    def test_webhook_rejects_invalid_token(self):
        response = self.client.post(
            "/api/webhooks/responses/",
            {
                "survey_key": self.survey.external_key,
                "event_id": "evt-002",
                "status": "complete",
                "answers": {"nps": 8},
                "submitted_at": timezone.now().isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_webhook_is_idempotent_on_duplicate_event(self):
        payload = {
            "survey_key": self.survey.external_key,
            "event_id": "evt-002",
            "status": "complete",
            "answers": {"nps": 8},
            "submitted_at": timezone.now().isoformat(),
        }

        first = self.client.post(
            "/api/webhooks/responses/",
            payload,
            format="json",
            headers={"X-Webhook-Token": settings.WEBHOOK_TOKEN},
        )
        second = self.client.post(
            "/api/webhooks/responses/",
            payload,
            format="json",
            headers={"X-Webhook-Token": settings.WEBHOOK_TOKEN},
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(
            Response.objects.filter(survey=self.survey, external_id="evt-002").count(), 1
        )

    def test_webhook_creates_separate_response_for_different_event_id(self):
        headers = {"X-Webhook-Token": settings.WEBHOOK_TOKEN}
        self.client.post(
            "/api/webhooks/responses/",
            {
                "survey_key": self.survey.external_key,
                "event_id": "evt-003",
                "status": "complete",
                "answers": {"nps": 6},
                "submitted_at": timezone.now().isoformat(),
            },
            format="json",
            headers=headers,
        )
        response = self.client.post(
            "/api/webhooks/responses/",
            {
                "survey_key": self.survey.external_key,
                "event_id": "evt-004",
                "status": "complete",
                "answers": {"nps": 5},
                "submitted_at": timezone.now().isoformat(),
            },
            format="json",
            headers=headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            Response.objects.filter(survey=self.survey, external_id__in=["evt-003", "evt-004"]).count(),
            2,
        )

    def test_filter_by_from_date_only(self):
        Response.objects.create(
            survey=self.survey,
            external_id="evt-old",
            status="complete",
            answers={},
            submitted_at=timezone.now() - timedelta(days=30),
        )
        cutoff = (timezone.now() - timedelta(days=5)).date().isoformat()

        response = self.client.get(f"/api/surveys/{self.survey.id}/results/?from={cutoff}")

        self.assertEqual(response.status_code, 200)
        ids = [item["external_id"] for item in response.data["results"]]
        self.assertEqual(ids, ["evt-001"])

    def test_filter_by_to_date_only(self):
        cutoff = (timezone.now() - timedelta(days=5)).date().isoformat()

        response = self.client.get(f"/api/surveys/{self.survey.id}/results/?to={cutoff}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

    def test_filter_by_from_and_to_together(self):
        Response.objects.create(
            survey=self.survey,
            external_id="evt-old",
            status="complete",
            answers={},
            submitted_at=timezone.now() - timedelta(days=30),
        )
        date_from = (timezone.now() - timedelta(days=5)).date().isoformat()
        date_to = timezone.now().date().isoformat()

        response = self.client.get(
            f"/api/surveys/{self.survey.id}/results/?from={date_from}&to={date_to}"
        )

        self.assertEqual(response.status_code, 200)
        ids = [item["external_id"] for item in response.data["results"]]
        self.assertEqual(ids, ["evt-001"])

    def test_filter_with_invalid_date_returns_400(self):
        response = self.client.get(f"/api/surveys/{self.survey.id}/results/?from=not-a-date")

        self.assertEqual(response.status_code, 400)

    def test_filter_with_from_after_to_returns_400(self):
        response = self.client.get(
            f"/api/surveys/{self.survey.id}/results/?from=2026-09-20&to=2026-09-01"
        )

        self.assertEqual(response.status_code, 400)

