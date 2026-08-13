from app.routers import users
from app.routers.admin import router as admin_router

# Mount the Roof Admin Bot under the already included users router so the
# application entrypoint does not need any special-case wiring.
users.router.include_router(admin_router)
