"""Tests for the Multica REST client."""

import pytest

from multica_mcp.domain import (
    AddCommentInput,
    CreateProjectInput,
    CreateTaskInput,
    ListTasksInput,
    PreviewCommentTriggersInput,
    PreviewIssueTriggersInput,
    UpdateTaskInput,
)
from multica_mcp.multica import MulticaAPIError, MulticaClient

BASE_URL = "https://multica.example.com"
TOKEN = "mul_test123"


def make_client() -> MulticaClient:
    client = MulticaClient(BASE_URL, TOKEN, client_version="0.2.0")
    client.set_workspace_scope(workspace_id="ws-1")
    return client


class TestClientBasics:
    def test_init(self):
        client = MulticaClient(BASE_URL, TOKEN, client_version="0.2.0")
        assert client._base_url == BASE_URL
        assert client._token == TOKEN

    def test_set_workspace_scope_by_id(self):
        client = MulticaClient(BASE_URL, TOKEN)
        client.set_workspace_scope(workspace_id="ws-1")
        assert client._workspace_id == "ws-1"
        assert client._workspace_slug == ""

    def test_set_workspace_scope_by_slug(self):
        client = MulticaClient(BASE_URL, TOKEN)
        client.set_workspace_scope(slug="my-ws")
        assert client._workspace_slug == "my-ws"

    def test_base_url_trailing_slash_stripped(self):
        client = MulticaClient("https://example.com/", TOKEN)
        assert client._base_url == "https://example.com"


class TestWorkspaces:
    @pytest.mark.asyncio
    async def test_list_workspaces(self, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/workspaces",
            json={
                "workspaces": [
                    {
                        "id": "ws-1",
                        "slug": "ws-1",
                        "name": "WS 1",
                        "issue_prefix": "WS1",
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z",
                    }
                ]
            },
        )
        client = MulticaClient(BASE_URL, TOKEN)
        workspaces = await client.list_workspaces()
        assert len(workspaces) == 1
        assert workspaces[0].id == "ws-1"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_list_workspaces_bare_array(self, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/workspaces",
            json=[
                {
                    "id": "ws-2",
                    "slug": "ws-2",
                    "name": "WS 2",
                    "issue_prefix": "WS2",
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                }
            ],
        )
        client = MulticaClient(BASE_URL, TOKEN)
        workspaces = await client.list_workspaces()
        assert len(workspaces) == 1
        assert workspaces[0].id == "ws-2"
        await client.aclose()


class TestProjects:
    @pytest.mark.asyncio
    async def test_list_projects(self, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/projects",
            json={
                "projects": [
                    {
                        "id": "p-1",
                        "workspace_id": "ws-1",
                        "title": "Project 1",
                        "status": "active",
                        "priority": "high",
                        "issue_count": 0,
                        "done_count": 0,
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z",
                    }
                ],
                "total": 1,
            },
        )
        client = make_client()
        projects = await client.list_projects()
        assert len(projects) == 1
        assert projects[0].title == "Project 1"

        # Check headers
        request = httpx_mock.get_request()
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert request.headers["X-Client-Platform"] == "mcp"
        assert request.headers["X-Client-Version"] == "0.2.0"
        assert request.headers["X-Workspace-ID"] == "ws-1"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_search_projects(self, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/projects/search?q=test",
            json={"projects": [], "total": 0},
        )
        client = make_client()
        result = await client.search_projects("test")
        assert result == []
        await client.aclose()

    @pytest.mark.asyncio
    async def test_create_project(self, httpx_mock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/projects",
            json={
                "id": "p-new",
                "workspace_id": "ws-1",
                "title": "New Project",
                "description": "desc",
                "status": "planned",
                "priority": "none",
                "issue_count": 0,
                "done_count": 0,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        )
        client = make_client()
        from multica_mcp.domain import ProjectResourceDef

        inp = CreateProjectInput(
            title="New Project",
            description="desc",
            status="planned",
            start_date="2026-10-13",
            due_date="2026-10-31",
            resources=[
                ProjectResourceDef(
                    url="git@remote.ysbang.cn:oms-pms/pms-out.git",
                    label="pms-out",
                    ref="feat-addGrafanaQuota",
                )
            ],
        )
        result = await client.create_project(inp)
        assert result.id == "p-new"
        assert result.title == "New Project"

        request = httpx_mock.get_request()
        body = request.content.decode()
        assert "New Project" in body
        assert "2026-10-13" in body
        assert "2026-10-31" in body
        assert "feat-addGrafanaQuota" in body
        assert "pms-out" in body
        await client.aclose()


class TestTasks:
    @pytest.mark.asyncio
    async def test_list_tasks_with_filters(self, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/issues?project_id=p-1&status=todo&assignee_id=user-1&limit=10",
            json={"issues": [], "total": 0},
        )
        client = make_client()
        opts = ListTasksInput(
            project_id="p-1",
            status="todo",
            assignee="user-1",
            limit=10,
        )
        tasks = await client.list_tasks(opts)
        assert tasks == []

        request = httpx_mock.get_request()
        url = str(request.url)
        assert "project_id=p-1" in url
        assert "status=todo" in url
        assert "assignee_id=user-1" in url
        assert "limit=10" in url
        await client.aclose()

    @pytest.mark.asyncio
    async def test_get_task(self, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/issues/t-1",
            json={
                "id": "t-1",
                "workspace_id": "ws-1",
                "number": 1,
                "identifier": "MUL-1",
                "title": "Task 1",
                "status": "todo",
                "priority": "medium",
                "creator_type": "member",
                "creator_id": "u-1",
                "position": 0.0,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        )
        client = make_client()
        task = await client.get_task("t-1")
        assert task.id == "t-1"
        assert task.identifier == "MUL-1"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_create_task(self, httpx_mock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/issues",
            json={
                "id": "t-1",
                "workspace_id": "ws-1",
                "number": 1,
                "identifier": "MUL-1",
                "title": "New Task",
                "status": "todo",
                "priority": "medium",
                "creator_type": "member",
                "creator_id": "u-1",
                "position": 0.0,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        )
        client = make_client()
        inp = CreateTaskInput(project_id="p-1", title="New Task", description="desc")
        result = await client.create_task(inp)
        assert result.title == "New Task"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_update_task(self, httpx_mock):
        httpx_mock.add_response(
            method="PUT",
            url=f"{BASE_URL}/api/issues/t-1",
            json={
                "id": "t-1",
                "workspace_id": "ws-1",
                "number": 1,
                "identifier": "MUL-1",
                "title": "Updated",
                "status": "done",
                "priority": "medium",
                "creator_type": "member",
                "creator_id": "u-1",
                "position": 0.0,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
            },
        )
        client = make_client()
        inp = UpdateTaskInput(task_id="t-1", status="done", suppress_run=True)
        result = await client.update_task("t-1", inp)
        assert result.status == "done"
        await client.aclose()


class TestComments:
    @pytest.mark.asyncio
    async def test_create_comment(self, httpx_mock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/issues/t-1/comments",
            json={
                "id": "c-1",
                "issue_id": "t-1",
                "author_type": "member",
                "author_id": "u-1",
                "content": "Hello",
                "type": "comment",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        )
        client = make_client()
        inp = AddCommentInput(task_id="t-1", comment="Hello")
        result = await client.create_comment(inp)
        assert result.content == "Hello"
        await client.aclose()


class TestPreviews:
    @pytest.mark.asyncio
    async def test_preview_comment_triggers(self, httpx_mock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/issues/t-1/comments/trigger-preview",
            json={"agents": []},
        )
        client = make_client()
        inp = PreviewCommentTriggersInput(task_id="t-1", content="test")
        result = await client.preview_comment_triggers(inp)
        assert result.agents == []
        await client.aclose()

    @pytest.mark.asyncio
    async def test_preview_issue_triggers(self, httpx_mock):
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE_URL}/api/issues/preview-trigger",
            json={"triggers": [], "total_count": 0},
        )
        client = make_client()
        inp = PreviewIssueTriggersInput(is_create=True, assignee_id="agent-1")
        result = await client.preview_issue_triggers(inp)
        assert result.total_count == 0
        await client.aclose()


class TestAgents:
    @pytest.mark.asyncio
    async def test_list_agents(self, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/agents",
            json=[],
        )
        client = make_client()
        agents = await client.list_agents()
        assert agents == []
        await client.aclose()


class TestSearchIssues:
    @pytest.mark.asyncio
    async def test_search_issues(self, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/issues/search?q=test&project_id=p-1&status=todo&limit=5",
            json={"issues": [], "total": 0},
        )
        client = make_client()
        result = await client.search_issues("test", project_id="p-1", status="todo", limit=5)
        assert result == []
        await client.aclose()


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_api_error_with_error_field(self, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/projects",
            json={"error": "not found"},
            status_code=404,
        )
        client = make_client()
        with pytest.raises(MulticaAPIError) as exc_info:
            await client.list_projects()
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message
        await client.aclose()

    @pytest.mark.asyncio
    async def test_api_error_raw_body(self, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/projects",
            text="internal server error",
            status_code=500,
        )
        client = make_client()
        with pytest.raises(MulticaAPIError) as exc_info:
            await client.list_projects()
        assert exc_info.value.status_code == 500
        await client.aclose()
