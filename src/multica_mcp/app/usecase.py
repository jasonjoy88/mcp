"""Business use case layer.

Mirrors the Go version's ``internal/app/usecase.go``.
All public methods are async.
"""

from __future__ import annotations

import logging

from ..domain import (
    VALID_PRIORITIES,
    VALID_PROJECT_STATUSES,
    VALID_TASK_STATUSES,
    AddCommentInput,
    Agent,
    AssignTaskInput,
    Comment,
    CommentTriggerPreview,
    CreateProjectInput,
    CreateSubtaskInput,
    CreateTaskInput,
    CreateTaskResult,
    CreateTaskWithSubtasksInput,
    CreateTaskWithSubtasksResult,
    GetProjectInput,
    GetTaskInput,
    IssueTriggerPreview,
    ListAgentsInput,
    ListProjectsInput,
    ListTasksInput,
    PlannedSubtask,
    PlanTaskBreakdownInput,
    PlanTaskBreakdownOutput,
    PreviewCommentTriggersInput,
    PreviewIssueTriggersInput,
    Project,
    SearchTasksInput,
    Task,
    UpdateTaskInput,
)
from ..multica import MulticaClient
from .assignee import resolve_assignee_type

logger = logging.getLogger(__name__)


class UseCase:
    """Application-level use cases wrapping the Multica client.

    Responsibilities:
    * read-only guard
    * state / enum validation
    * assignee type inference
    * aggregating multiple API calls (e.g. task + comments + subtasks)
    * dry-run response construction
    * parent/child task orchestration
    """

    def __init__(self, client: MulticaClient, read_only: bool = False) -> None:
        self._client = client
        self._read_only = read_only

    def _check_read_only(self) -> None:
        if self._read_only:
            raise RuntimeError("server is in read-only mode: write operations are disabled")

    # -- projects ----------------------------------------------------------

    async def list_projects(self, input: ListProjectsInput) -> list[Project]:
        if input.query:
            return await self._client.search_projects(input.query)
        return await self._client.list_projects()

    async def get_project(self, input: GetProjectInput) -> Project:
        return await self._client.get_project(input.project_id)

    async def create_project(self, input: CreateProjectInput) -> Project:
        self._check_read_only()

        if input.status and input.status not in VALID_PROJECT_STATUSES:
            raise ValueError(
                f"invalid project status {input.status!r}; "
                f"valid values: {', '.join(VALID_PROJECT_STATUSES)}"
            )
        if input.priority and input.priority not in VALID_PRIORITIES:
            raise ValueError(
                f"invalid priority {input.priority!r}; "
                f"valid values: {', '.join(VALID_PRIORITIES)}"
            )

        if input.dry_run:
            return Project(
                id="(dry run)",
                workspace_id="",
                title=input.title,
                description=input.description or None,
                status=input.status or "planned",
                priority=input.priority or "none",
                lead_type=input.lead_type,
                lead_id=input.lead_id,
                issue_count=0,
                done_count=0,
                created_at="",
                updated_at="",
            )

        if input.lead_id and not input.lead_type:
            input = input.model_copy(update={"lead_type": "member"})

        return await self._client.create_project(input)

    # -- tasks -------------------------------------------------------------

    async def list_tasks(self, input: ListTasksInput) -> list[Task]:
        if input.query:
            return await self._client.search_issues(
                input.query,
                project_id=input.project_id or None,
                status=input.status,
                limit=input.limit,
            )
        return await self._client.list_tasks(input)

    async def get_task(self, input: GetTaskInput) -> Task:
        task = await self._client.get_task(input.task_id)

        try:
            task.comments = await self._client.list_comments(input.task_id)
        except Exception as exc:
            logger.warning("failed to load comments for task",
                           extra={"task_id": input.task_id, "error": str(exc)})

        try:
            task.subtasks = await self._client.list_child_issues(input.task_id)
        except Exception as exc:
            logger.warning("failed to load subtasks for task",
                           extra={"task_id": input.task_id, "error": str(exc)})

        return task

    # -- create task -------------------------------------------------------

    async def create_task(self, input: CreateTaskInput) -> CreateTaskResult:
        self._check_read_only()

        if input.dry_run:
            return CreateTaskResult(
                title=input.title,
                status="todo",
                identifier="(dry run)",
            )

        if input.assignee:
            assignee_type = await resolve_assignee_type(
                self._client, input.assignee, input.assignee_type
            )
            input.assignee_type = assignee_type

        task = await self._client.create_task(input)
        return CreateTaskResult(
            id=task.id,
            identifier=task.identifier,
            title=task.title,
            status=task.status,
        )

    # -- create subtask ----------------------------------------------------

    async def create_subtask(self, input: CreateSubtaskInput) -> CreateTaskResult:
        self._check_read_only()

        if input.dry_run:
            return CreateTaskResult(
                title=input.title,
                status="todo",
                identifier="(dry run)",
            )

        parent = await self._client.get_task(input.parent_task_id)
        if not parent:
            raise ValueError(f"parent task not found: {input.parent_task_id}")

        create_input = CreateTaskInput(
            project_id=parent.project_id or "",
            title=input.title,
            description=input.description,
            assignee=input.assignee,
            assignee_type=input.assignee_type,
            stage=input.stage,
            parent_issue_id=parent.id,
        )

        if create_input.assignee:
            assignee_type = await resolve_assignee_type(
                self._client, create_input.assignee, create_input.assignee_type
            )
            create_input.assignee_type = assignee_type

        result = await self._client.create_task(create_input)
        return CreateTaskResult(
            id=result.id,
            identifier=result.identifier,
            title=result.title,
            status=result.status,
        )

    # -- update task -------------------------------------------------------

    async def update_task(self, input: UpdateTaskInput) -> CreateTaskResult:
        self._check_read_only()

        if input.status and input.status not in VALID_TASK_STATUSES:
            raise ValueError(
                f"invalid status {input.status!r}; valid values: {', '.join(VALID_TASK_STATUSES)}"
            )

        if input.dry_run:
            return CreateTaskResult(
                id=input.task_id,
                status=input.status or "(unchanged)",
                title=input.title or "(unchanged)",
            )

        if input.assignee is not None and input.assignee != "":
            assignee_type = await resolve_assignee_type(
                self._client, input.assignee, input.assignee_type
            )
            input.assignee_type = assignee_type

        task = await self._client.update_task(input.task_id, input)
        return CreateTaskResult(
            id=task.id,
            identifier=task.identifier,
            title=task.title,
            status=task.status,
        )

    # -- comment -----------------------------------------------------------

    async def add_comment(self, input: AddCommentInput) -> Comment:
        self._check_read_only()
        return await self._client.create_comment(input)

    # -- trigger previews --------------------------------------------------

    async def preview_comment_triggers(
        self, input: PreviewCommentTriggersInput
    ) -> CommentTriggerPreview:
        return await self._client.preview_comment_triggers(input)

    async def preview_issue_triggers(
        self, input: PreviewIssueTriggersInput
    ) -> IssueTriggerPreview:
        return await self._client.preview_issue_triggers(input)

    # -- agents ------------------------------------------------------------

    async def list_agents(self, input: ListAgentsInput) -> list[Agent]:
        return await self._client.list_agents()

    # -- assign task -------------------------------------------------------

    async def assign_task(self, input: AssignTaskInput) -> CreateTaskResult:
        """Assign a task to a member/agent/squad.

        ``input`` has ``task_id``, ``assignee_id``, and optional ``assignee_type``.
        """
        self._check_read_only()

        assignee_type = await resolve_assignee_type(
            self._client, input.assignee_id, input.assignee_type
        )

        update_input = UpdateTaskInput(
            task_id=input.task_id,
            assignee=input.assignee_id,
            assignee_type=assignee_type,
        )

        task = await self._client.update_task(input.task_id, update_input)
        return CreateTaskResult(
            id=task.id,
            identifier=task.identifier,
            title=task.title,
            status=task.status,
        )

    # -- search tasks ------------------------------------------------------

    async def search_tasks(self, input: SearchTasksInput) -> list[Task]:
        return await self._client.search_issues(
            input.query,
            project_id=input.project_id,
            status=input.status,
            limit=input.limit,
        )

    # -- plan task breakdown (local, no API calls) -------------------------

    async def plan_task_breakdown(
        self, input: PlanTaskBreakdownInput
    ) -> PlanTaskBreakdownOutput:
        subtasks = _plan_subtasks(input.title, input.description)
        return PlanTaskBreakdownOutput(subtasks=subtasks)

    # -- create task with subtasks -----------------------------------------

    async def create_task_with_subtasks(
        self, input: CreateTaskWithSubtasksInput
    ) -> CreateTaskWithSubtasksResult:
        self._check_read_only()

        if input.dry_run:
            parent = CreateTaskResult(
                title=input.title,
                status="todo",
                identifier="(dry run)",
            )
            subs = [
                CreateTaskResult(title=s.title, status="todo", identifier="(dry run)")
                for s in input.subtasks
            ]
            return CreateTaskWithSubtasksResult(parent=parent, subtasks=subs)

        parent_input = CreateTaskInput(
            project_id=input.project_id,
            title=input.title,
            description=input.description,
            assignee=input.assignee,
            assignee_type=input.assignee_type,
        )

        if parent_input.assignee:
            assignee_type = await resolve_assignee_type(
                self._client, parent_input.assignee, parent_input.assignee_type
            )
            parent_input.assignee_type = assignee_type

        parent_task = await self._client.create_task(parent_input)

        result = CreateTaskWithSubtasksResult(
            parent=CreateTaskResult(
                id=parent_task.id,
                identifier=parent_task.identifier,
                title=parent_task.title,
                status=parent_task.status,
            ),
            subtasks=[],
        )

        for sub in input.subtasks:
            sub_input = CreateTaskInput(
                project_id=input.project_id,
                title=sub.title,
                description=sub.description,
                assignee=input.assignee,
                assignee_type=parent_input.assignee_type,
                parent_issue_id=parent_task.id,
            )

            try:
                sub_task = await self._client.create_task(sub_input)
                result.subtasks.append(
                    CreateTaskResult(
                        id=sub_task.id,
                        identifier=sub_task.identifier,
                        title=sub_task.title,
                        status=sub_task.status,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "failed to create subtask",
                    extra={"title": sub.title, "error": str(exc)},
                )
                continue

        return result

    # -- project reference resolution --------------------------------------

    async def resolve_project_reference(self, ref: str) -> str:
        """Resolve a project reference (ID, exact title, or fuzzy title match)."""
        projects = await self._client.list_projects()
        ref_lower = ref.lower()
        for p in projects:
            if p.id.lower() == ref_lower:
                return p.id
        for p in projects:
            if p.title.lower() == ref_lower:
                return p.id
        for p in projects:
            if ref_lower in p.title.lower():
                return p.id
        raise ValueError(f"project {ref!r} not found")


# -- local helpers ---------------------------------------------------------


def _plan_subtasks(title: str, description: str) -> list[PlannedSubtask]:
    """Generate a standard 4-step subtask plan locally (no LLM)."""
    return [
        PlannedSubtask(
            title="Analysis and requirements",
            description=f"Analyze requirements and define acceptance criteria for: {title}",
            dependencies=[],
            acceptance_criteria=[
                "Requirements documented",
                "Acceptance criteria defined",
            ],
        ),
        PlannedSubtask(
            title="Implementation",
            description=f"Implement the core functionality for: {title}",
            dependencies=["Analysis and requirements"],
            acceptance_criteria=[
                "Core functionality implemented",
                "Code follows project conventions",
            ],
        ),
        PlannedSubtask(
            title="Testing",
            description=f"Write and run tests for: {title}",
            dependencies=["Implementation"],
            acceptance_criteria=[
                "Unit tests pass",
                "Integration tests pass",
            ],
        ),
        PlannedSubtask(
            title="Documentation and cleanup",
            description=f"Document changes and clean up for: {title}",
            dependencies=["Testing"],
            acceptance_criteria=[
                "Documentation updated",
                "Code reviewed and cleaned",
            ],
        ),
    ]
