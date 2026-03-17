from src.fast_api.routers.auth_router import get_auth_router
from src.fast_api.routers.difficulty_router import get_difficulty_router
from src.fast_api.routers.health_router import get_health_router
from src.fast_api.routers.problem_router import get_problem_router
from src.fast_api.routers.skill_router import get_skill_router
from src.fast_api.routers.topic_router import get_topic_router

__all__ = [
    "get_auth_router",
    "get_difficulty_router",
    "get_health_router",
    "get_problem_router",
    "get_skill_router",
    "get_topic_router",
]
