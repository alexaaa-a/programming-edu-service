from fastapi import APIRouter, HTTPException, Response

from agent_service.app.infrastructure.observability.prometheus_metrics_recorder import render_prometheus_metrics


router = APIRouter()


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    content, content_type = render_prometheus_metrics()
    return Response(content=content, media_type=content_type)
