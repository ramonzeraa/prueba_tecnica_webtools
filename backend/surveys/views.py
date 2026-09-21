from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response as ApiResponse
from rest_framework.views import APIView

from django.db import IntegrityError, transaction

from .models import Response, Survey
from .serializers import DateRangeFilterSerializer, ResponseSerializer, WebhookSerializer


class SurveyResultsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = LimitOffsetPagination

    def get(self, request, survey_id):
        survey = get_object_or_404(Survey.objects.for_user(request.user), pk=survey_id)

        filters = DateRangeFilterSerializer(
            data={
                "date_from": request.query_params.get("from"),
                "date_to": request.query_params.get("to"),
            }
        )
        filters.is_valid(raise_exception=True)
        date_from = filters.validated_data.get("date_from")
        date_to = filters.validated_data.get("date_to")

        responses = Response.objects.filter(survey=survey)
        if date_from:
            responses = responses.filter(submitted_at__date__gte=date_from)
        if date_to:
            responses = responses.filter(submitted_at__date__lte=date_to)

        total_count = responses.count()

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(responses, request, view=self)

        payload = {
            "survey": {"id": survey.id, "title": survey.title},
            "count": total_count,
            "results": ResponseSerializer(page if page is not None else responses, many=True).data,
        }
        if page is not None:
            payload["next"] = paginator.get_next_link()
            payload["previous"] = paginator.get_previous_link()

        return ApiResponse(payload)


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
        

