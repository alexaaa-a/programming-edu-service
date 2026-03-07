from dishka import AsyncContainer, make_async_container
from dishka.integrations.fastapi import FastapiProvider

from task_service.app.config import Settings

from .providers import all_providers


def create_container(settings: Settings) -> AsyncContainer:
    return make_async_container(
        FastapiProvider(), *all_providers, context={Settings: settings}
    )
