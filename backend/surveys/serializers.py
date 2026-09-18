from rest_framework import serializers

from .models import Response


class ResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Response
        fields = ["id", "external_id", "status", "answers", "submitted_at"]


class WebhookSerializer(serializers.Serializer):
    survey_key = serializers.CharField()
    event_id = serializers.CharField()
    status = serializers.ChoiceField(choices=["partial", "complete"])
    answers = serializers.JSONField()
    submitted_at = serializers.DateTimeField()


class DateRangeFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                {"detail": "'from' no puede ser posterior a 'to'."}
            )
        return attrs

