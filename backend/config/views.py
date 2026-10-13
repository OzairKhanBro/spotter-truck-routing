from django.conf import settings
from django.http import FileResponse, Http404


def spa(request, path=""):
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        raise Http404("Frontend not built. Run `bun run build` in frontend/.")
    return FileResponse(index.open("rb"), content_type="text/html")
