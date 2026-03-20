from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import delete, select

from src.models.alchemy import ProblemType, ProblemTypePrerequisite
from src.models.pydantic import (
    ProblemTypeCreate,
    ProblemTypeGraphNodeResponse,
    ProblemTypeGraphResponse,
    ProblemTypeResponse,
    ProblemTypeUpdate,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase


class ProblemTypeService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db


    async def list_problem_types(self) -> list[ProblemTypeResponse]:
        async with self.db.session_ctx() as session:
            problem_types_by_id = await self._load_problem_types_by_id(session)
            prerequisite_ids_by_problem_type = await self._load_prerequisite_ids_by_problem_type(session)
        return self._build_problem_type_responses(
            problem_types_by_id,
            prerequisite_ids_by_problem_type,
        )


    async def get_problem_type(self, problem_type_id: uuid.UUID) -> ProblemTypeResponse:
        async with self.db.session_ctx() as session:
            problem_type = await self._get_problem_type_or_404(session, problem_type_id)
            prerequisite_ids_by_problem_type = await self._load_prerequisite_ids_by_problem_type(session)
        return ProblemTypeResponse(
            id=problem_type.id,
            name=problem_type.name,
            prerequisite_ids=prerequisite_ids_by_problem_type.get(problem_type.id, []),
        )


    async def create_problem_type(self, data: ProblemTypeCreate) -> ProblemTypeResponse:
        async with self.db.session_ctx() as session:
            await self._ensure_problem_type_name_is_unique(session, data.name)
            await self._ensure_problem_types_exist(session, data.prerequisite_ids)

            problem_type = ProblemType(name=data.name)
            session.add(problem_type)
            await session.flush()

            await self._replace_prerequisites(
                session=session,
                problem_type_id=problem_type.id,
                prerequisite_ids=data.prerequisite_ids,
            )

            return ProblemTypeResponse(
                id=problem_type.id,
                name=problem_type.name,
                prerequisite_ids=sorted(data.prerequisite_ids, key=str),
            )


    async def update_problem_type(
        self,
        problem_type_id: uuid.UUID,
        data: ProblemTypeUpdate,
    ) -> ProblemTypeResponse:
        async with self.db.session_ctx() as session:
            problem_type = await self._get_problem_type_or_404(session, problem_type_id)

            if data.name is not None:
                await self._ensure_problem_type_name_is_unique(
                    session,
                    data.name,
                    current_id=problem_type.id,
                )
                problem_type.name = data.name

            if data.prerequisite_ids is not None:
                await self._ensure_problem_types_exist(session, data.prerequisite_ids)
                await self._replace_prerequisites(
                    session=session,
                    problem_type_id=problem_type.id,
                    prerequisite_ids=data.prerequisite_ids,
                )

            prerequisite_ids_by_problem_type = await self._load_prerequisite_ids_by_problem_type(session)
            return ProblemTypeResponse(
                id=problem_type.id,
                name=problem_type.name,
                prerequisite_ids=prerequisite_ids_by_problem_type.get(problem_type.id, []),
            )


    async def delete_problem_type(self, problem_type_id: uuid.UUID) -> None:
        async with self.db.session_ctx() as session:
            problem_type = await self._get_problem_type_or_404(session, problem_type_id)
            await session.delete(problem_type)


    async def get_problem_type_graph(self) -> ProblemTypeGraphResponse:
        async with self.db.session_ctx() as session:
            problem_types_by_id = await self._load_problem_types_by_id(session)
            prerequisite_ids_by_problem_type = await self._load_prerequisite_ids_by_problem_type(session)

        all_prerequisite_ids = {
            prerequisite_id
            for prerequisite_ids in prerequisite_ids_by_problem_type.values()
            for prerequisite_id in prerequisite_ids
        }
        root_ids = [
            problem_type_id
            for problem_type_id in problem_types_by_id
            if problem_type_id not in all_prerequisite_ids
        ]

        return ProblemTypeGraphResponse(
            roots=[
                self._build_graph_node(
                    problem_type_id=problem_type_id,
                    problem_types_by_id=problem_types_by_id,
                    prerequisite_ids_by_problem_type=prerequisite_ids_by_problem_type,
                )
                for problem_type_id in self._sort_problem_type_ids(root_ids, problem_types_by_id)
            ]
        )


    async def _replace_prerequisites(
        self,
        session: "AsyncSession",
        problem_type_id: uuid.UUID,
        prerequisite_ids: list[uuid.UUID],
    ) -> None:
        if problem_type_id in prerequisite_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Problem type cannot depend on itself",
            )

        await self._validate_prerequisite_graph(
            session=session,
            problem_type_id=problem_type_id,
            prerequisite_ids=prerequisite_ids,
        )

        await session.execute(
            delete(ProblemTypePrerequisite).where(
                ProblemTypePrerequisite.problem_type_id == problem_type_id
            )
        )

        for prerequisite_id in prerequisite_ids:
            session.add(
                ProblemTypePrerequisite(
                    problem_type_id=problem_type_id,
                    prerequisite_problem_type_id=prerequisite_id,
                )
            )


    async def _validate_prerequisite_graph(
        self,
        session: "AsyncSession",
        problem_type_id: uuid.UUID,
        prerequisite_ids: list[uuid.UUID],
    ) -> None:
        prerequisites_by_problem_type = await self._load_prerequisite_ids_by_problem_type(session)
        prerequisites_by_problem_type[problem_type_id] = sorted(prerequisite_ids, key=str)
        self._ensure_graph_is_acyclic(prerequisites_by_problem_type)


    def _ensure_graph_is_acyclic(
        self,
        prerequisites_by_problem_type: dict[uuid.UUID, list[uuid.UUID]],
    ) -> None:
        active_ids: set[uuid.UUID] = set()
        visited_ids: set[uuid.UUID] = set()

        def visit(problem_type_id: uuid.UUID) -> None:
            if problem_type_id in active_ids:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Problem type prerequisites must not contain cycles",
                )

            if problem_type_id in visited_ids:
                return

            active_ids.add(problem_type_id)
            for prerequisite_id in prerequisites_by_problem_type.get(problem_type_id, []):
                visit(prerequisite_id)
            active_ids.remove(problem_type_id)
            visited_ids.add(problem_type_id)

        for problem_type_id in prerequisites_by_problem_type:
            visit(problem_type_id)


    async def _load_problem_types_by_id(
        self,
        session: "AsyncSession",
    ) -> dict[uuid.UUID, ProblemType]:
        result = await session.execute(select(ProblemType))
        problem_types = result.scalars().all()
        return {
            problem_type.id: problem_type
            for problem_type in problem_types
        }


    async def _load_prerequisite_ids_by_problem_type(
        self,
        session: "AsyncSession",
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        result = await session.execute(
            select(
                ProblemTypePrerequisite.problem_type_id,
                ProblemTypePrerequisite.prerequisite_problem_type_id,
            )
        )
        prerequisite_ids_by_problem_type: dict[uuid.UUID, list[uuid.UUID]] = {}
        for problem_type_id, prerequisite_id in result.all():
            prerequisite_ids_by_problem_type.setdefault(problem_type_id, []).append(prerequisite_id)

        return {
            problem_type_id: sorted(prerequisite_ids, key=str)
            for problem_type_id, prerequisite_ids in prerequisite_ids_by_problem_type.items()
        }


    def _build_problem_type_responses(
        self,
        problem_types_by_id: dict[uuid.UUID, ProblemType],
        prerequisite_ids_by_problem_type: dict[uuid.UUID, list[uuid.UUID]],
    ) -> list[ProblemTypeResponse]:
        return [
            ProblemTypeResponse(
                id=problem_type.id,
                name=problem_type.name,
                prerequisite_ids=prerequisite_ids_by_problem_type.get(problem_type.id, []),
            )
            for problem_type in self._sort_problem_types(problem_types_by_id.values())
        ]


    def _build_graph_node(
        self,
        problem_type_id: uuid.UUID,
        problem_types_by_id: dict[uuid.UUID, ProblemType],
        prerequisite_ids_by_problem_type: dict[uuid.UUID, list[uuid.UUID]],
    ) -> ProblemTypeGraphNodeResponse:
        problem_type = problem_types_by_id[problem_type_id]
        prerequisite_ids = prerequisite_ids_by_problem_type.get(problem_type_id, [])
        return ProblemTypeGraphNodeResponse(
            id=problem_type.id,
            name=problem_type.name,
            prerequisites=[
                self._build_graph_node(
                    problem_type_id=prerequisite_id,
                    problem_types_by_id=problem_types_by_id,
                    prerequisite_ids_by_problem_type=prerequisite_ids_by_problem_type,
                )
                for prerequisite_id in self._sort_problem_type_ids(
                    prerequisite_ids,
                    problem_types_by_id,
                )
            ],
        )


    def _sort_problem_types(
        self,
        problem_types: Iterable[ProblemType],
    ) -> list[ProblemType]:
        return sorted(problem_types, key=lambda item: item.name)


    def _sort_problem_type_ids(
        self,
        problem_type_ids: list[uuid.UUID],
        problem_types_by_id: dict[uuid.UUID, ProblemType],
    ) -> list[uuid.UUID]:
        return sorted(
            problem_type_ids,
            key=lambda item: problem_types_by_id[item].name,
        )


    async def _get_problem_type_or_404(
        self,
        session: "AsyncSession",
        problem_type_id: uuid.UUID,
    ) -> ProblemType:
        result = await session.execute(select(ProblemType).where(ProblemType.id == problem_type_id))
        problem_type = result.scalar_one_or_none()
        if problem_type is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Problem type not found",
            )
        return problem_type


    async def _ensure_problem_type_name_is_unique(
        self,
        session: "AsyncSession",
        name: str,
        current_id: uuid.UUID | None = None,
    ) -> None:
        result = await session.execute(select(ProblemType).where(ProblemType.name == name))
        problem_type = result.scalar_one_or_none()
        if problem_type is not None and problem_type.id != current_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Problem type name must be unique",
            )


    async def _ensure_problem_types_exist(
        self,
        session: "AsyncSession",
        problem_type_ids: list[uuid.UUID],
    ) -> None:
        if not problem_type_ids:
            return

        result = await session.execute(select(ProblemType.id).where(ProblemType.id.in_(problem_type_ids)))
        existing_ids = set(result.scalars().all())
        missing_ids = [
            problem_type_id
            for problem_type_id in problem_type_ids
            if problem_type_id not in existing_ids
        ]
        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Problem types not found: {', '.join(str(item) for item in missing_ids)}",
            )
