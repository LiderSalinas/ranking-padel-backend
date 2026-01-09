from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from routers import parejas, desafios, jugadores, auth, ranking, push
from database import init_db


app = FastAPI(title="Ranking Pádel Backend")
@app.on_event("startup")
def on_startup():
    init_db()


# ✅ CORS (Local + Vercel + Ngrok)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ranking-padel-6oi72la0a-lidersalinas.vercel.app",
        "https://ranking-padel-web.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ FIX: Forzar que los HTTPException salgan SIEMPRE como JSON (no HTML)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

# ✅ FIX (extra recomendado): Capturar errores inesperados y devolver JSON
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"},
    )

# Routers
app.include_router(parejas.router, prefix="/parejas")
app.include_router(desafios.router, prefix="/desafios")
app.include_router(jugadores.router, prefix="/jugadores")
app.include_router(ranking.router)
app.include_router(auth.router)  # /auth/...
app.include_router(push.router)
