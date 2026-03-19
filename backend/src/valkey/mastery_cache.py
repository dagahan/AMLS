from __future__ import annotations

from typing import TYPE_CHECKING

from src.models.pydantic.mastery import MasteryOverviewCache
from src.valkey.valkey_client import get_async_valkey_client

if TYPE_CHECKING:
    from valkey.asyncio import Valkey as AsyncValkey


class MasteryCache:
    def __init__(self) -> None:
        self.cache_ttl_seconds = 3600


    async def get_mastery_overview(self, user_id: str) -> MasteryOverviewCache | None:
        cache_key = await self._build_overview_cache_key(user_id)
        cached_value = await self._get_valkey_client().get(cache_key)
        if cached_value is None:
            return None
        return MasteryOverviewCache.model_validate_json(cached_value)


    async def set_mastery_overview(self, user_id: str, overview: MasteryOverviewCache) -> None:
        cache_key = await self._build_overview_cache_key(user_id)
        await self._get_valkey_client().set(
            cache_key,
            overview.model_dump_json(),
            ex=self.cache_ttl_seconds,
        )


    async def get_user_answers_version(self, user_id: str) -> int:
        raw_value = await self._get_valkey_client().get(self._build_user_answers_version_key(user_id))
        if raw_value is None:
            return 0
        return int(raw_value)


    async def get_problem_mapping_version(self) -> int:
        raw_value = await self._get_valkey_client().get(self._build_problem_mapping_version_key())
        if raw_value is None:
            return 0
        return int(raw_value)


    async def get_taxonomy_version(self) -> int:
        raw_value = await self._get_valkey_client().get(self._build_taxonomy_version_key())
        if raw_value is None:
            return 0
        return int(raw_value)


    async def bump_user_answers_version(self, user_id: str) -> int:
        return int(await self._get_valkey_client().incr(self._build_user_answers_version_key(user_id)))


    async def bump_problem_mapping_version(self) -> int:
        return int(await self._get_valkey_client().incr(self._build_problem_mapping_version_key()))


    async def bump_taxonomy_version(self) -> int:
        return int(await self._get_valkey_client().incr(self._build_taxonomy_version_key()))


    async def _build_overview_cache_key(self, user_id: str) -> str:
        user_answers_version = await self.get_user_answers_version(user_id)
        problem_mapping_version = await self.get_problem_mapping_version()
        taxonomy_version = await self.get_taxonomy_version()
        return (
            f"MasteryOverview:{user_id}:"
            f"answers:{user_answers_version}:"
            f"problems:{problem_mapping_version}:"
            f"taxonomy:{taxonomy_version}"
        )


    def _build_user_answers_version_key(self, user_id: str) -> str:
        return f"MasteryUserAnswersVersion:{user_id}"


    def _build_problem_mapping_version_key(self) -> str:
        return "MasteryProblemMappingVersion"


    def _build_taxonomy_version_key(self) -> str:
        return "MasteryTaxonomyVersion"


    def _get_valkey_client(self) -> AsyncValkey:
        return get_async_valkey_client()
