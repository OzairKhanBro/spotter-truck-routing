import uuid

from django.db import models


class ForecastCache(models.Model):
    """Hourly forecast for one 0.1° cell, reused for an hour."""

    lat_key = models.FloatField()
    lon_key = models.FloatField()
    fetched_at = models.DateTimeField()
    payload = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["lat_key", "lon_key"], name="forecast_cell_unique")
        ]


class Trip(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    load_lb = models.PositiveIntegerField()
    result = models.JSONField()  # the planned trip, shaped as the API returns it
    corridor = models.JSONField(null=True, blank=True)  # filled on first corridor request

    def as_json(self) -> dict:
        return {"id": str(self.id), "created_at": self.created_at.isoformat(), **self.result}
