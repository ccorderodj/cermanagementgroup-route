from fastapi import APIRouter

from app.core.utils.web_routers import CheckNameRoute

from app.routers_pages.admin.locations.router import router as locations_page
from app.routers_pages.admin.companies.router import router as company_page
from app.routers_pages.admin.profile.router import router as profile_page
from app.routers_pages.admin.platform.router import router as platform_page
from app.routers_pages.admin.route.router import router as route_config_page
from app.routers_pages.admin.security.router import router as security_page

router = APIRouter(
    prefix="/admin",
    route_class=CheckNameRoute,
    tags=["Frontend"],
)

router.include_router(locations_page)
router.include_router(company_page)
router.include_router(profile_page)
router.include_router(security_page)
router.include_router(platform_page)
router.include_router(route_config_page)
