from fastapi import FastAPI

from .router import router


app = FastAPI(
    title="API"
)

app.include_router(router)