import uuid

from django.shortcuts import get_object_or_404
from ninja import NinjaAPI

from .errors import TripError
from .models import Trip
from .providers.photon import search_places
from .schemas import TripIn
from .services import Place, TripRequest, build_corridor, plan_trip

api = NinjaAPI(title="Weather-Aware Truck Routing")


@api.exception_handler(TripError)
def trip_error(request, exc: TripError):
    return api.create_response(request, {"detail": exc.message}, status=exc.status)


@api.get("/health")
def health(request):
    return {"ok": True}


@api.get("/geocode")
def geocode(request, q: str = ""):
    return search_places(q)


@api.post("/trips")
def create_trip(request, payload: TripIn):
    req = TripRequest(
        origin=Place(**payload.origin.model_dump()),
        destination=Place(**payload.destination.model_dump()),
        departure=payload.departure,
        load_lb=payload.load_lb,
        interval_mi=payload.interval_mi,
    )
    trip = Trip.objects.create(load_lb=payload.load_lb, result=plan_trip(req))
    return api.create_response(request, trip.as_json(), status=201)


@api.get("/trips/{trip_id}")
def get_trip(request, trip_id: uuid.UUID):
    return get_object_or_404(Trip, id=trip_id).as_json()


@api.get("/trips/{trip_id}/corridor")
def get_corridor(request, trip_id: uuid.UUID):
    return build_corridor(get_object_or_404(Trip, id=trip_id))
