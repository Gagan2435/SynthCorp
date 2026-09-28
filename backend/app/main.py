from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings

app = FastAPI(title="SynthCorp", version="1.0.0", description="Describe a company. Get its data.")
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
