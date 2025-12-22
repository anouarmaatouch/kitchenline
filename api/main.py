from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.config import Config

app = FastAPI(
    title="Restau API",
    version="2.0.0",
    description="FastAPI Backend for Restaurant Voice Agent"
)

# CORS Configuration
origins = ["*"]  # Update this with specific domains in production

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "framework": "FastAPI",
        "environment": "production" if Config.SECRET_KEY != "dev" else "development"
    }

# We will import and include routers here later
from routes import auth_routes, voice_routes, admin_routes

app.include_router(auth_routes.router)
app.include_router(voice_routes.router)
app.include_router(admin_routes.router)

# --- Static Files & SPA ---
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Determine path to frontend dist
# Local: ../web/dist (relative to api folder)
# Docker: /app/web/dist (relative to /app/api which is cwd)
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web", "dist"))

if not os.path.exists(frontend_dist):
    # Fallback for local dev if run from root
    frontend_dist = os.path.join(os.getcwd(), "web", "dist")

if os.path.exists(frontend_dist):
    # Mount assets (CSS, JS, Images)
    assets_path = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    # Serve other static files (favicon, manifest, etc.) or fallback to index.html
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Attempt to serve file directly if it exists
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        
        # Fallback to index.html for React Router
        return FileResponse(os.path.join(frontend_dist, "index.html"))
else:
    print(f"⚠️ Frontend build not found at: {frontend_dist}")
