from fastapi import APIRouter, HTTPException, Response


router = APIRouter()


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    try:
        from agent_service.app.infrastructure.observability.prometheus_metrics_recorder import (
            render_prometheus_metrics,
        )
    except ImportError as e:
        raise HTTPException(status_code=503, detail="prometheus_client is not installed") from e

    content, content_type = render_prometheus_metrics()
    return Response(content=content, media_type=content_type)

