from collections.abc import AsyncIterable

import aiohttp
from dishka import Provider, Scope, provide


class AiohttpClientSessionProvider(Provider):
    @provide(scope=Scope.APP)
    async def aiohttp_client_session(self) -> AsyncIterable[aiohttp.ClientSession]:
        session = aiohttp.ClientSession()
        try:
            yield session
        finally:
            await session.close()


HttpProviders = [AiohttpClientSessionProvider()]
