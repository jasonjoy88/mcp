"""Domain models and DTOs for multica-mcp.

Mirrors the Go version's ``internal/domain/models.go``.
Uses Pydantic v2 for validation and JSON serialization.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TaskStatus(StrEnum):
    """Task status values accepted by the Multica API."""

    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


VALID_TASK_STATUSES = [s.value for s in TaskStatus]


class Priority(StrEnum):
    """Task priority values."""

    NONE = "none"
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


VALID_PRIORITIES = [p.value for p in Priority]


class ProjectStatus(StrEnum):
    """Project status values accepted by the Multica API."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


VALID_PROJECT_STATUSES = [s.value for s in ProjectStatus]


class AssigneeType(StrEnum):
    """Assignee type: member, agent, or squad."""

    MEMBER = "member"
    AGENT = "agent"
    SQUAD = "squad"


VALID_ASSIGNEE_TYPES = [t.value for t in AssigneeType]


# ---------------------------------------------------------------------------
# Entity models (mirror Go structs with json tags)
# ---------------------------------------------------------------------------


class Project(BaseModel):
    """A Multica project."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    workspace_id: str = Field(alias="workspace_id")
    title: str
    description: str | None = None
    icon: str | None = None
    status: str
    priority: str
    lead_type: str | None = Field(default=None, alias="lead_type")
    lead_id: str | None = Field(default=None, alias="lead_id")
    issue_count: int = Field(default=0, alias="issue_count")
    done_count: int = Field(default=0, alias="done_count")
    created_at: str = Field(alias="created_at")
    updated_at: str = Field(alias="updated_at")


class Task(BaseModel):
    """A Multica task / issue."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    workspace_id: str = Field(alias="workspace_id")
    number: int
    identifier: str
    title: str
    description: str | None = None
    status: str
    priority: str
    assignee_type: str | None = Field(default=None, alias="assignee_type")
    assignee_id: str | None = Field(default=None, alias="assignee_id")
    creator_type: str = Field(alias="creator_type")
    creator_id: str = Field(alias="creator_id")
    parent_issue_id: str | None = Field(default=None, alias="parent_issue_id")
    project_id: str | None = Field(default=None, alias="project_id")
    position: float = 0.0
    stage: int | None = None
    start_date: str | None = Field(default=None, alias="start_date")
    due_date: str | None = Field(default=None, alias="due_date")
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(alias="created_at")
    updated_at: str = Field(alias="updated_at")
    reactions: list[Any] = Field(default_factory=list)
    attachments: list[Any] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)
    subtasks: list[Task] = Field(default_factory=list)


class Comment(BaseModel):
    """A comment on a task / issue."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    issue_id: str = Field(alias="issue_id")
    author_type: str = Field(alias="author_type")
    author_id: str = Field(alias="author_id")
    content: str
    type: str
    parent_id: str | None = Field(default=None, alias="parent_id")
    resolved_at: str | None = Field(default=None, alias="resolved_at")
    resolved_by_type: str | None = Field(default=None, alias="resolved_by_type")
    resolved_by_id: str | None = Field(default=None, alias="resolved_by_id")
    reply_count: int | None = Field(default=None, alias="reply_count")
    last_activity_at: str | None = Field(default=None, alias="last_activity_at")
    source_task_id: str | None = Field(default=None, alias="source_task_id")
    created_at: str = Field(alias="created_at")
    updated_at: str = Field(alias="updated_at")


class Agent(BaseModel):
    """A Multica agent definition."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    workspace_id: str = Field(alias="workspace_id")
    runtime_id: str = Field(alias="runtime_id")
    name: str
    description: str
    instructions: str
    avatar_url: str | None = Field(default=None, alias="avatar_url")
    runtime_mode: str = Field(alias="runtime_mode")
    visibility: str
    status: str
    max_concurrent_tasks: int = Field(alias="max_concurrent_tasks")
    model: str
    owner_id: str | None = Field(default=None, alias="owner_id")
    created_at: str = Field(alias="created_at")
    updated_at: str = Field(alias="updated_at")
    archived_at: str | None = Field(default=None, alias="archived_at")


class Workspace(BaseModel):
    """A Multica workspace."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    slug: str
    name: str
    description: str | None = None
    issue_prefix: str = Field(alias="issue_prefix")
    created_at: str = Field(alias="created_at")
    updated_at: str = Field(alias="updated_at")


# ---------------------------------------------------------------------------
# Trigger preview models
# ---------------------------------------------------------------------------


class CommentTriggerAgent(BaseModel):
    """An agent that would be triggered by a comment."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    avatar_url: str | None = Field(default=None, alias="avatar_url")
    source: str
    reason: str


class CommentTriggerPreview(BaseModel):
    """Result of a comment trigger preview."""

    agents: list[CommentTriggerAgent] = Field(default_factory=list)


class IssueTriggerPreviewItem(BaseModel):
    """A single trigger entry for issue create/update preview."""

    model_config = ConfigDict(populate_by_name=True)

    issue_id: str = Field(alias="issue_id")
    agent_id: str = Field(alias="agent_id")
    source: str
    handoff_supported: bool = Field(alias="handoff_supported")


class IssueTriggerPreview(BaseModel):
    """Result of an issue trigger preview."""

    triggers: list[IssueTriggerPreviewItem] = Field(default_factory=list)
    total_count: int = Field(default=0, alias="total_count")


# ---------------------------------------------------------------------------
# Input DTOs
# ---------------------------------------------------------------------------


class ListProjectsInput(BaseModel):
    """Input for listing projects."""

    query: str = ""


class GetProjectInput(BaseModel):
    """Input for getting a project by ID."""

    project_id: str = Field(alias="project_id")


class ProjectResourceDef(BaseModel):
    """Git (or other) resource attached when creating a project."""

    model_config = ConfigDict(populate_by_name=True)

    url: str
    label: str | None = None
    ref: str | None = None
    default_branch_hint: str | None = Field(default=None, alias="default_branch_hint")


class CreateProjectInput(BaseModel):
    """Input for creating a new project."""

    model_config = ConfigDict(populate_by_name=True)

    title: str
    description: str = ""
    status: str | None = None
    priority: str | None = None
    lead_type: str | None = Field(default=None, alias="lead_type")
    lead_id: str | None = Field(default=None, alias="lead_id")
    start_date: str | None = Field(default=None, alias="start_date")
    due_date: str | None = Field(default=None, alias="due_date")
    resources: list[ProjectResourceDef] = Field(default_factory=list)
    dry_run: bool = Field(default=False, alias="dry_run")


class ListTasksInput(BaseModel):
    """Input for listing tasks with optional filters."""

    model_config = ConfigDict(populate_by_name=True)

    project_id: str = Field(default="", alias="project_id")
    status: str | None = None
    assignee: str | None = None
    query: str | None = None
    limit: int | None = None


class GetTaskInput(BaseModel):
    """Input for getting a single task."""

    task_id: str = Field(alias="task_id")


class CreateTaskInput(BaseModel):
    """Input for creating a new task."""

    model_config = ConfigDict(populate_by_name=True)

    project_id: str = Field(alias="project_id")
    title: str
    description: str = ""
    priority: str | None = None
    labels: list[str] = Field(default_factory=list)
    assignee: str | None = None
    assignee_type: str | None = Field(default=None, alias="assignee_type")
    stage: int | None = None
    parent_issue_id: str | None = Field(default=None, alias="parent_issue_id")
    idempotency_key: str | None = Field(default=None, alias="idempotency_key")
    dry_run: bool = Field(default=False, alias="dry_run")


class CreateSubtaskInput(BaseModel):
    """Input for creating a subtask."""

    model_config = ConfigDict(populate_by_name=True)

    parent_task_id: str = Field(alias="parent_task_id")
    title: str
    description: str = ""
    assignee: str | None = None
    assignee_type: str | None = Field(default=None, alias="assignee_type")
    stage: int | None = None
    dry_run: bool = Field(default=False, alias="dry_run")


class UpdateTaskInput(BaseModel):
    """Input for updating a task."""

    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(alias="task_id")
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    labels: list[str] = Field(default_factory=list)
    assignee: str | None = None
    assignee_type: str | None = Field(default=None, alias="assignee_type")
    stage: int | None = None
    clear_stage: bool = Field(default=False, alias="clear_stage")
    suppress_run: bool = Field(default=False, alias="suppress_run")
    handoff_note: str = Field(default="", alias="handoff_note")
    dry_run: bool = Field(default=False, alias="dry_run")


class AddCommentInput(BaseModel):
    """Input for adding a comment to a task."""

    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(alias="task_id")
    comment: str
    parent_id: str | None = Field(default=None, alias="parent_id")
    suppress_agent_ids: list[str] = Field(default_factory=list, alias="suppress_agent_ids")


class PreviewCommentTriggersInput(BaseModel):
    """Input for previewing comment triggers."""

    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(alias="task_id")
    content: str
    parent_id: str | None = Field(default=None, alias="parent_id")


class PreviewIssueTriggersInput(BaseModel):
    """Input for previewing issue triggers."""

    model_config = ConfigDict(populate_by_name=True)

    issue_ids: list[str] = Field(default_factory=list, alias="issue_ids")
    is_create: bool = Field(default=False, alias="is_create")
    assignee_type: str | None = Field(default=None, alias="assignee_type")
    assignee_id: str | None = Field(default=None, alias="assignee_id")
    status: str | None = None


class ListAgentsInput(BaseModel):
    """Input for listing agents."""

    model_config = ConfigDict(populate_by_name=True)

    project_id: str | None = Field(default=None, alias="project_id")


class AssignTaskInput(BaseModel):
    """Input for assigning a task."""

    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(alias="task_id")
    assignee_id: str = Field(alias="assignee_id")
    assignee_type: str | None = Field(default=None, alias="assignee_type")


class SearchTasksInput(BaseModel):
    """Input for searching tasks."""

    model_config = ConfigDict(populate_by_name=True)

    query: str
    project_id: str | None = Field(default=None, alias="project_id")
    status: str | None = None
    limit: int | None = None


class PlanTaskBreakdownInput(BaseModel):
    """Input for the local task breakdown planner."""

    model_config = ConfigDict(populate_by_name=True)

    title: str
    description: str = ""
    project_context: str | None = Field(default=None, alias="project_context")


class SubtaskDef(BaseModel):
    """A subtask definition used in batch create."""

    title: str
    description: str = ""


class CreateTaskWithSubtasksInput(BaseModel):
    """Input for creating a parent task with subtasks."""

    model_config = ConfigDict(populate_by_name=True)

    project_id: str = Field(alias="project_id")
    title: str
    description: str = ""
    subtasks: list[SubtaskDef] = Field(default_factory=list)
    assignee: str | None = None
    assignee_type: str | None = Field(default=None, alias="assignee_type")
    idempotency_key: str | None = Field(default=None, alias="idempotency_key")
    dry_run: bool = Field(default=False, alias="dry_run")


# ---------------------------------------------------------------------------
# Output DTOs
# ---------------------------------------------------------------------------


class PlannedSubtask(BaseModel):
    """A planned subtask (from the local breakdown planner)."""

    title: str
    description: str = ""
    dependencies: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list, alias="acceptance_criteria")


class PlanTaskBreakdownOutput(BaseModel):
    """Output of the local task breakdown planner."""

    subtasks: list[PlannedSubtask] = Field(default_factory=list)


class CreateTaskResult(BaseModel):
    """Result of a create/update task operation."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    identifier: str = ""
    title: str = ""
    status: str = ""
    url: str = ""


class CreateTaskWithSubtasksResult(BaseModel):
    """Result of creating a parent task with subtasks."""

    parent: CreateTaskResult
    subtasks: list[CreateTaskResult] = Field(default_factory=list)


# Rebuild models with forward references
Task.model_rebuild()
