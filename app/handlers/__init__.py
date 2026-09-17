from aiogram import Router

from app.handlers.user_start import router as start_router
from app.handlers.user_profile import router as profile_router
from app.handlers.user_top import router as top_router
from app.handlers.user_referrals import router as referrals_router
from app.handlers.user_market import router as market_router
from app.handlers.user_giveaways import router as gaw_user_router
from app.handlers.user_finance import router as finance_router
from app.handlers.admin_levels import router as admin_levels_router
from app.handlers.admin_giveaways import router as admin_gaw_router
from app.handlers.admin_requests import router as admin_req_router
from app.handlers.admin_stats import router as admin_stats_router


def register_routers(root: Router) -> None:
    root.include_router(start_router)
    root.include_router(profile_router)
    root.include_router(top_router)
    root.include_router(referrals_router)
    root.include_router(market_router)
    root.include_router(gaw_user_router)
    root.include_router(finance_router)
    root.include_router(admin_levels_router)
    root.include_router(admin_gaw_router)
    root.include_router(admin_req_router)
    root.include_router(admin_stats_router)
