"""Tests for the use case layer."""

from types import SimpleNamespace

import pytest

from multica_mcp.app import UseCase
from multica_mcp.app.assignee import resolve_assignee_type
from multica_mcp.domain import (
    AddCommentInput,
    AssignTaskInput,
    CreateProjectInput,
    CreateSubtaskInput,
    CreateTaskInput,
    CreateTaskWithSubtasksInput,
    GetTaskInput,
    ListProjectsInput,
    ListTasksInput,
    PlanTaskBreakdownInput,
    SearchTasksInput,
    SubtaskDef,
    Task,
    UpdateTaskInput,
)


# A mock client that returns canned responses
class MockClient:
    def __init__(self):
        self.projects = []
        self.tasks = []
        self.agents = []
        self.created_projects = []
        self.created_tasks = []
        self.updated_tasks = []
        self.comments = []

    async def list_projects(self):
        return self.projects

    async def search_projects(self, query):
        return [p for p in self.projects if query.lower() in p.title.lower()]

    async def get_project(self, pid):
        for p in self.projects:
            if p.id == pid:
                return p
        raise ValueError("not found")

    async def create_project(self, input):
        from multica_mcp.domain import Project

        self.created_projects.append(input)
        return Project(
            id=f"p-{len(self.created_projects)}",
            workspace_id="ws-1",
            title=input.title,
            description=input.description or None,
            status=input.status or "planned",
            priority=input.priority or "none",
            lead_type=input.lead_type,
            lead_id=input.lead_id,
            issue_count=0,
            done_count=0,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

    async def list_tasks(self, opts):
        return self.tasks

    async def get_task(self, tid):
        for t in self.tasks:
            if t.id == tid:
                return t
        raise ValueError("not found")

    async def list_child_issues(self, parent_id):
        return [t for t in self.tasks if getattr(t, "parent_issue_id", None) == parent_id]

    async def list_comments(self, issue_id):
        return self.comments

    async def create_task(self, input):
        task = SimpleNamespace(
            id=f"task-{len(self.created_tasks)+1}",
            identifier=f"MUL-{len(self.created_tasks)+1}",
            title=input.title,
            status="todo",
        )
        self.created_tasks.append(input)
        return task

    async def update_task(self, task_id, input):
        self.updated_tasks.append((task_id, input))
        return SimpleNamespace(
            id=task_id,
            identifier="MUL-1",
            title=input.title or "updated",
            status=input.status or "todo",
        )

    async def create_comment(self, input):
        self.comments.append(input)
        return SimpleNamespace(
            id=f"c-{len(self.comments)}",
            issue_id=input.task_id,
            content=input.comment,
        )

    async def list_agents(self):
        return self.agents

    async def search_issues(self, query, project_id=None, status=None, limit=None):
        return self.tasks

    async def preview_comment_triggers(self, input):
        return SimpleNamespace(agents=[])

    async def preview_issue_triggers(self, input):
        return SimpleNamespace(triggers=[], total_count=0)


def _make_task(tid, title, status="todo"):
    return Task(
        id=tid,
        workspace_id="ws-1",
        number=1,
        identifier="MUL-1",
        title=title,
        status=status,
        priority="medium",
        creator_type="member",
        creator_id="u-1",
        position=0.0,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )


def _make_project(pid, title):
    from multica_mcp.domain import Project
    return Project(
        id=pid,
        workspace_id="ws-1",
        title=title,
        status="active",
        priority="high",
        issue_count=0,
        done_count=0,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )


def _make_agent(aid, name):
    from multica_mcp.domain import Agent
    return Agent(
        id=aid,
        workspace_id="ws-1",
        runtime_id=f"rt-{aid}",
        name=name,
        description="",
        instructions="",
        runtime_mode="auto",
        visibility="workspace",
        status="active",
        max_concurrent_tasks=3,
        model="gpt-4",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )


class TestReadOnly:
    @pytest.mark.asyncio
    async def test_write_ops_blocked(self):
        client = MockClient()
        uc = UseCase(client, read_only=True)

        with pytest.raises(RuntimeError, match="read-only"):
            await uc.create_project(CreateProjectInput(title="x"))

        with pytest.raises(RuntimeError, match="read-only"):
            await uc.create_task(CreateTaskInput(project_id="p-1", title="x", description="y"))

        with pytest.raises(RuntimeError, match="read-only"):
            await uc.create_subtask(CreateSubtaskInput(parent_task_id="t-1", title="x", description="y"))

        with pytest.raises(RuntimeError, match="read-only"):
            await uc.update_task(UpdateTaskInput(task_id="t-1", status="done"))

        with pytest.raises(RuntimeError, match="read-only"):
            await uc.add_comment(AddCommentInput(task_id="t-1", comment="hi"))

        with pytest.raises(RuntimeError, match="read-only"):
            await uc.assign_task(AssignTaskInput(task_id="t-1", assignee_id="u-1"))

        with pytest.raises(RuntimeError, match="read-only"):
            await uc.create_task_with_subtasks(
                CreateTaskWithSubtasksInput(project_id="p-1", title="x", description="y")
            )

    @pytest.mark.asyncio
    async def test_read_ops_allowed(self):
        client = MockClient()
        uc = UseCase(client, read_only=True)

        # These should not raise
        await uc.list_projects(ListProjectsInput())
        await uc.list_tasks(ListTasksInput())
        await uc.search_tasks(SearchTasksInput(query="x"))
        await uc.plan_task_breakdown(PlanTaskBreakdownInput(title="x", description="y"))


class TestListProjects:
    @pytest.mark.asyncio
    async def test_no_query(self):
        client = MockClient()
        client.projects = [_make_project("p-1", "Alpha"), _make_project("p-2", "Beta")]
        uc = UseCase(client)
        result = await uc.list_projects(ListProjectsInput())
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_with_query(self):
        client = MockClient()
        client.projects = [_make_project("p-1", "Alpha"), _make_project("p-2", "Beta")]
        uc = UseCase(client)
        result = await uc.list_projects(ListProjectsInput(query="beta"))
        assert len(result) == 1
        assert result[0].title == "Beta"


class TestCreateProject:
    @pytest.mark.asyncio
    async def test_create_project(self):
        client = MockClient()
        uc = UseCase(client)
        result = await uc.create_project(
            CreateProjectInput(title="采购平台监控指标开发", description="tapd link")
        )
        assert result.id == "p-1"
        assert result.title == "采购平台监控指标开发"
        assert len(client.created_projects) == 1

    @pytest.mark.asyncio
    async def test_dry_run(self):
        client = MockClient()
        uc = UseCase(client)
        result = await uc.create_project(CreateProjectInput(title="x", dry_run=True))
        assert result.id == "(dry run)"
        assert client.created_projects == []

    @pytest.mark.asyncio
    async def test_invalid_status(self):
        client = MockClient()
        uc = UseCase(client)
        with pytest.raises(ValueError, match="invalid project status"):
            await uc.create_project(CreateProjectInput(title="x", status="active"))

    @pytest.mark.asyncio
    async def test_default_lead_type(self):
        client = MockClient()
        uc = UseCase(client)
        await uc.create_project(CreateProjectInput(title="x", lead_id="u-1"))
        assert client.created_projects[0].lead_type == "member"


class TestGetTask:
    @pytest.mark.asyncio
    async def test_aggregates_comments_and_subtasks(self):
        client = MockClient()
        client.tasks = [_make_task("t-1", "Parent")]
        client.comments = []
        uc = UseCase(client)

        result = await uc.get_task(GetTaskInput(task_id="t-1"))
        assert result.id == "t-1"
        # Should have comments and subtasks fields (empty lists)
        assert isinstance(result.comments, list)
        assert isinstance(result.subtasks, list)


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_dry_run(self):
        client = MockClient()
        uc = UseCase(client)
        result = await uc.create_task(
            CreateTaskInput(project_id="p-1", title="Dry", description="", dry_run=True)
        )
        assert result.title == "Dry"
        assert result.identifier == "(dry run)"
        assert len(client.created_tasks) == 0  # no actual API call

    @pytest.mark.asyncio
    async def test_creates_task(self):
        client = MockClient()
        uc = UseCase(client)
        result = await uc.create_task(
            CreateTaskInput(project_id="p-1", title="Real", description="desc")
        )
        assert result.title == "Real"
        assert len(client.created_tasks) == 1


class TestUpdateTask:
    @pytest.mark.asyncio
    async def test_invalid_status(self):
        client = MockClient()
        uc = UseCase(client)
        with pytest.raises(ValueError, match="invalid status"):
            await uc.update_task(UpdateTaskInput(task_id="t-1", status="invalid_status"))

    @pytest.mark.asyncio
    async def test_dry_run(self):
        client = MockClient()
        uc = UseCase(client)
        result = await uc.update_task(
            UpdateTaskInput(task_id="t-1", status="done", dry_run=True)
        )
        assert result.status == "done"
        assert len(client.updated_tasks) == 0  # no actual API call

    @pytest.mark.asyncio
    async def test_valid_update(self):
        client = MockClient()
        uc = UseCase(client)
        result = await uc.update_task(
            UpdateTaskInput(task_id="t-1", status="done")
        )
        assert result.status == "done"
        assert len(client.updated_tasks) == 1


class TestPlanTaskBreakdown:
    @pytest.mark.asyncio
    async def test_returns_four_subtasks(self):
        uc = UseCase(MockClient())
        result = await uc.plan_task_breakdown(
            PlanTaskBreakdownInput(title="Feature X", description="Build it")
        )
        assert len(result.subtasks) == 4
        assert result.subtasks[0].title == "Analysis and requirements"
        assert result.subtasks[1].title == "Implementation"
        assert result.subtasks[2].title == "Testing"
        assert result.subtasks[3].title == "Documentation and cleanup"


class TestCreateTaskWithSubtasks:
    @pytest.mark.asyncio
    async def test_dry_run(self):
        client = MockClient()
        uc = UseCase(client)
        result = await uc.create_task_with_subtasks(
            CreateTaskWithSubtasksInput(
                project_id="p-1",
                title="Parent",
                description="desc",
                subtasks=[
                    SubtaskDef(title="s1", description="d1"),
                    SubtaskDef(title="s2", description="d2"),
                ],
                dry_run=True,
            )
        )
        assert result.parent.title == "Parent"
        assert len(result.subtasks) == 2
        assert result.parent.identifier == "(dry run)"
        assert len(client.created_tasks) == 0

    @pytest.mark.asyncio
    async def test_creates_parent_and_subtasks(self):
        client = MockClient()
        uc = UseCase(client)
        result = await uc.create_task_with_subtasks(
            CreateTaskWithSubtasksInput(
                project_id="p-1",
                title="Parent",
                description="desc",
                subtasks=[
                    SubtaskDef(title="s1", description="d1"),
                    SubtaskDef(title="s2", description="d2"),
                ],
            )
        )
        assert result.parent.id.startswith("task-")
        assert len(result.subtasks) == 2
        assert len(client.created_tasks) == 3  # 1 parent + 2 subtasks


class TestResolveProjectReference:
    @pytest.mark.asyncio
    async def test_by_id(self):
        client = MockClient()
        client.projects = [_make_project("p-1", "Alpha")]
        uc = UseCase(client)
        result = await uc.resolve_project_reference("p-1")
        assert result == "p-1"

    @pytest.mark.asyncio
    async def test_by_exact_title(self):
        client = MockClient()
        client.projects = [_make_project("p-1", "Alpha")]
        uc = UseCase(client)
        result = await uc.resolve_project_reference("Alpha")
        assert result == "p-1"

    @pytest.mark.asyncio
    async def test_by_fuzzy_title(self):
        client = MockClient()
        client.projects = [_make_project("p-1", "Hello World Project")]
        uc = UseCase(client)
        result = await uc.resolve_project_reference("world")
        assert result == "p-1"

    @pytest.mark.asyncio
    async def test_not_found(self):
        client = MockClient()
        client.projects = []
        uc = UseCase(client)
        with pytest.raises(ValueError, match="not found"):
            await uc.resolve_project_reference("nope")


class TestAssigneeResolution:
    @pytest.mark.asyncio
    async def test_explicit_valid(self):
        client = MockClient()
        result = await resolve_assignee_type(client, "u-1", explicit="agent")
        assert result == "agent"

    @pytest.mark.asyncio
    async def test_explicit_invalid(self):
        client = MockClient()
        with pytest.raises(ValueError, match="invalid assignee_type"):
            await resolve_assignee_type(client, "u-1", explicit="invalid")

    @pytest.mark.asyncio
    async def test_empty_assignee(self):
        client = MockClient()
        result = await resolve_assignee_type(client, "")
        assert result is None

    @pytest.mark.asyncio
    async def test_infers_agent(self):
        client = MockClient()
        client.agents = [_make_agent("a-1", "My Agent")]
        result = await resolve_assignee_type(client, "a-1")
        assert result == "agent"

    @pytest.mark.asyncio
    async def test_falls_back_to_member(self):
        client = MockClient()
        client.agents = [_make_agent("a-1", "My Agent")]
        result = await resolve_assignee_type(client, "user-999")
        assert result == "member"
