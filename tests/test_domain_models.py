"""Tests for domain models."""



from multica_mcp.domain import (
    VALID_PROJECT_STATUSES,
    VALID_TASK_STATUSES,
    Agent,
    AssigneeType,
    Comment,
    CreateProjectInput,
    CreateTaskInput,
    CreateTaskResult,
    CreateTaskWithSubtasksInput,
    PlannedSubtask,
    PlanTaskBreakdownOutput,
    Priority,
    Project,
    ProjectStatus,
    SubtaskDef,
    Task,
    TaskStatus,
    UpdateTaskInput,
    Workspace,
)


class TestTaskStatus:
    def test_all_values(self):
        assert len(VALID_TASK_STATUSES) == 7
        assert "backlog" in VALID_TASK_STATUSES
        assert "done" in VALID_TASK_STATUSES

    def test_enum_values(self):
        assert TaskStatus.BACKLOG.value == "backlog"
        assert TaskStatus.DONE.value == "done"


class TestPriority:
    def test_enum_values(self):
        assert Priority.URGENT.value == "urgent"
        assert Priority.NONE.value == "none"


class TestAssigneeType:
    def test_enum_values(self):
        assert AssigneeType.MEMBER.value == "member"
        assert AssigneeType.AGENT.value == "agent"
        assert AssigneeType.SQUAD.value == "squad"


class TestProject:
    def test_serialization(self):
        p = Project(
            id="proj-1",
            workspace_id="ws-1",
            title="My Project",
            status="active",
            priority="high",
            issue_count=10,
            done_count=5,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-02T00:00:00Z",
        )
        data = p.model_dump(by_alias=True)
        assert data["id"] == "proj-1"
        assert data["workspace_id"] == "ws-1"
        assert data["title"] == "My Project"
        assert data["issue_count"] == 10

    def test_from_json(self):
        raw = {
            "id": "proj-1",
            "workspace_id": "ws-1",
            "title": "Test",
            "description": None,
            "icon": None,
            "status": "active",
            "priority": "medium",
            "lead_type": None,
            "lead_id": None,
            "issue_count": 0,
            "done_count": 0,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        p = Project(**raw)
        assert p.id == "proj-1"
        assert p.description is None


class TestTask:
    def test_serialization_with_comments_and_subtasks(self):
        comment = Comment(
            id="c-1",
            issue_id="task-1",
            author_type="member",
            author_id="user-1",
            content="hello",
            type="comment",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        subtask = Task(
            id="sub-1",
            workspace_id="ws-1",
            number=2,
            identifier="MUL-2",
            title="sub",
            status="todo",
            priority="medium",
            creator_type="member",
            creator_id="user-1",
            position=0.0,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        task = Task(
            id="task-1",
            workspace_id="ws-1",
            number=1,
            identifier="MUL-1",
            title="Test task",
            status="in_progress",
            priority="high",
            creator_type="member",
            creator_id="user-1",
            position=0.0,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            comments=[comment],
            subtasks=[subtask],
        )
        data = task.model_dump(by_alias=True, mode="json")
        assert data["id"] == "task-1"
        assert len(data["comments"]) == 1
        assert len(data["subtasks"]) == 1
        assert data["comments"][0]["content"] == "hello"
        assert data["subtasks"][0]["identifier"] == "MUL-2"


class TestWorkspace:
    def test_basic(self):
        ws = Workspace(
            id="ws-1",
            slug="my-workspace",
            name="My Workspace",
            issue_prefix="MUL",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        assert ws.slug == "my-workspace"


class TestAgent:
    def test_basic(self):
        a = Agent(
            id="agent-1",
            workspace_id="ws-1",
            runtime_id="rt-1",
            name="Test Agent",
            description="test",
            instructions="do stuff",
            runtime_mode="auto",
            visibility="workspace",
            status="active",
            max_concurrent_tasks=3,
            model="gpt-4",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        assert a.name == "Test Agent"


class TestInputModels:
    def test_create_project_input_defaults(self):
        from multica_mcp.domain import ProjectResourceDef

        inp = CreateProjectInput(title="Hello")
        assert inp.title == "Hello"
        assert inp.description == ""
        assert inp.dry_run is False
        assert inp.status is None
        assert inp.resources == []
        assert ProjectStatus.PLANNED.value in VALID_PROJECT_STATUSES

        with_res = CreateProjectInput(
            title="【PMS组】demo",
            resources=[ProjectResourceDef(url="git@x:y.git", label="svc", ref="feat-x")],
        )
        assert with_res.resources[0].ref == "feat-x"

    def test_create_task_input_defaults(self):
        inp = CreateTaskInput(project_id="p-1", title="Hello", description="desc")
        assert inp.project_id == "p-1"
        assert inp.dry_run is False
        assert inp.priority is None

    def test_update_task_input_optional(self):
        inp = UpdateTaskInput(task_id="t-1", status="done")
        assert inp.task_id == "t-1"
        assert inp.status == "done"
        assert inp.title is None
        assert inp.clear_stage is False

    def test_create_task_with_subtasks(self):
        inp = CreateTaskWithSubtasksInput(
            project_id="p-1",
            title="Parent",
            description="parent desc",
            subtasks=[
                SubtaskDef(title="sub 1", description="d1"),
                SubtaskDef(title="sub 2", description="d2"),
            ],
        )
        assert len(inp.subtasks) == 2
        assert inp.subtasks[0].title == "sub 1"


class TestOutputModels:
    def test_plan_breakdown_output(self):
        out = PlanTaskBreakdownOutput(
            subtasks=[
                PlannedSubtask(
                    title="Analysis",
                    description="analyze",
                    acceptance_criteria=["done"],
                )
            ]
        )
        data = out.model_dump(by_alias=True)
        assert len(data["subtasks"]) == 1
        assert data["subtasks"][0]["acceptance_criteria"] == ["done"]

    def test_create_task_result(self):
        r = CreateTaskResult(id="t-1", identifier="MUL-1", title="x", status="todo")
        data = r.model_dump(by_alias=True)
        assert data["id"] == "t-1"
        assert data["identifier"] == "MUL-1"
