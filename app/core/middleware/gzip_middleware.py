from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware

def add(app: FastAPI):
    app.add_middleware(GZipMiddleware, minimum_size=1000)