import os, uuid, time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.config import settings
from app.core.db import engine
from app.core.logging import configure_logging
from app.api import auth, organizations, domain, integrations, experience
configure_logging()
app=FastAPI(title=settings.app_name,version="1.4.0-experience-alpha",docs_url="/api/docs",openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware,allow_origins=settings.origins,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors=[]
    for item in exc.errors():
        location=".".join(str(part) for part in item.get("loc",[]) if part!="body") or "pedido"
        message=item.get("msg","Valor inválido")
        errors.append({"field":location,"message":message,"type":item.get("type")})
    return JSONResponse(
        status_code=422,
        content={
            "detail":"O pedido contém campos inválidos ou incompletos.",
            "errors":errors,
            "request_id":getattr(request.state,"request_id",None),
        },
    )
@app.middleware("http")
async def headers(request:Request,call_next):
    request.state.request_id=request.headers.get("x-request-id") or str(uuid.uuid4())
    started=time.perf_counter();response=await call_next(request)
    response.headers["X-Request-ID"]=request.state.request_id
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Referrer-Policy"]="strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]="camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"]="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:"
    if settings.environment=="production": response.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
    return response
app.include_router(auth.router,prefix="/api")
app.include_router(organizations.router,prefix="/api")
app.include_router(domain.router,prefix="/api")
app.include_router(integrations.router,prefix="/api")
app.include_router(experience.router,prefix="/api")
@app.get("/health/live")
def live(): return {"status":"alive"}
@app.get("/health/ready")
def ready():
    try:
        with engine.connect() as c:c.execute(text("select 1"))
        return {"status":"ready","database":"ok"}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(503,"Database unavailable")
frontend=Path(__file__).resolve().parents[2]/"frontend"
app.mount("/assets",StaticFiles(directory=frontend/"assets"),name="assets")
@app.get("/{path:path}")
def spa(path:str):
    candidate=frontend/path
    if path and candidate.exists() and candidate.is_file(): return FileResponse(candidate)
    return FileResponse(frontend/"index.html")
