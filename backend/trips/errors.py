class TripError(Exception):
    """A problem the person planning the trip can act on. `message` is shown to them."""

    status = 422

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NoRouteError(TripError):
    status = 422


class ProviderError(TripError):
    status = 502
