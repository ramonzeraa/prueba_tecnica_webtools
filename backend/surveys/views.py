from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response as ApiResponse
from rest_framework.views import APIView

from django.db import IntegrityError, transaction

from .models import Response, Survey
from .serializers import ResponseSerializer, WebhookSerializer


class SurveyResultsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, survey_id):
        survey = get_object_or_404(Survey.objects.for_user(request.user), pk=survey_id)
        responses = Response.objects.filter(survey=survey)

        return ApiResponse(
            {
                "survey": {"id": survey.id, "title": survey.title},
                "count": responses.count(),
                "results": ResponseSerializer(responses, many=True).data,
            }
        )


class ResponseWebhookView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if request.headers.get("X-Webhook-Token") != settings.WEBHOOK_TOKEN:
            return ApiResponse({"detail": "Invalid token"}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = WebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        survey = get_object_or_404(Survey, external_key=payload["survey_key"])
        
        #añadido transaction.atomic() para asegurar que la creación de la respuesta sea atómica y evitar duplicados
        try:    
            with transaction.atomic():
                response = Response.objects.create(
                survey=survey,
                external_id=payload["event_id"],
                status=payload["status"],
                answers=payload["answers"],
                submitted_at=payload["submitted_at"],
                )
            response_status = status.HTTP_201_CREATED
        except IntegrityError:
            response = Response.objects.get(survey=survey, external_id=payload["event_id"])
            response_status = status.HTTP_200_OK
        return ApiResponse(ResponseSerializer(response).data, status=response_status)    
        

