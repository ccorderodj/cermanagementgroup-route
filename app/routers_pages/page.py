from fastapi import APIRouter

from app.routers_pages.auth.router import router as router_auth
from app.routers_pages.admin.router import router as router_admin
from app.routers_pages.route.router import router as router_route
from app.core.utils.web_routers import CheckNameRoute

page_router = APIRouter(
    route_class=CheckNameRoute,
)

page_router.include_router(router_auth)
page_router.include_router(router_admin)
page_router.include_router(router_route)
