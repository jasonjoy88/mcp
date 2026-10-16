"""Tests for the MCP server layer."""

import pytest

from multica_mcp.app import UseCase
from multica_mcp.domain import Project
from multica_mcp.mcp import MCPServer


class MockClient:
    async def list_projects(self):
        return []

    async def search_projects(self, query):
        return []

    async def get_project(self, pid):
        return Project(
            id=pid,
            workspace_id="ws-1",
            title="Test Project",
            status="active",
            priority="high",
            issue_count=0,
            done_count=0,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

    async def list_tasks(self, opts):
        return []

    async def get_task(self, tid):
        from multica_mcp.domain import Task
        return Task(
            id=tid,
            workspace_id="ws-1",
            number=1,
            identifier="MUL-1",
            title="Test",
            status="todo",
            priority="medium",
            creator_type="member",
            creator_id="u-1",
            position=0.0,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

    async def list_child_issues(self, parent_id):
        return []

    async def list_comments(self, issue_id):
        return []

    async def create_project(self, input):
        return Project(
            id="p-new",
            workspace_id="ws-1",
            title=input.title,
            description=input.description or None,
            status=input.status or "planned",
            priority=input.priority or "none",
            issue_count=0,
            done_count=0,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

    async def create_task(self, input):
        from types import SimpleNamespace
        return SimpleNamespace(id="t-1", identifier="MUL-1", title=input.title, status="todo")

    async def update_task(self, task_id, input):
        from types import SimpleNamespace
        return SimpleNamespace(id=task_id, identifier="MUL-1", title="updated", status="todo")

    async def create_comment(self, input):
        from types import SimpleNamespace
        return SimpleNamespace(id="c-1", issue_id=input.task_id, content=input.comment)

    async def preview_comment_triggers(self, input):
        from types import SimpleNamespace
        return SimpleNamespace(agents=[])

    async def preview_issue_triggers(self, input):
        from types import SimpleNamespace
        return SimpleNamespace(triggers=[], total_count=0)

    async def list_agents(self):
        return []

    async def search_issues(self, query, project_id=None, status=None, limit=None):
        return []


class TestMCPServer:
    def test_server_name_and_version(self):
        client = MockClient()
        uc = UseCase(client)
        mcp_srv = MCPServer(uc)
        assert mcp_srv.server.name == "multica-mcp"

    def test_read_write_mode_has_16_tools(self):
        client = MockClient()
        uc = UseCase(client, read_only=False)
        mcp_srv = MCPServer(uc, read_only=False)
        tool_names = [t.name for t in mcp_srv._tools]
        assert len(tool_names) == 16
        # Read tools
        assert "multica_list_projects" in tool_names
        assert "multica_get_project" in tool_names
        assert "multica_list_tasks" in tool_names
        assert "multica_get_task" in tool_names
        assert "multica_search_tasks" in tool_names
        assert "multica_list_agents" in tool_names
        assert "multica_plan_task_breakdown" in tool_names
        assert "multica_preview_comment_triggers" in tool_names
        assert "multica_preview_issue_triggers" in tool_names
        # Write tools
        assert "multica_create_project" in tool_names
        assert "multica_create_task" in tool_names
        assert "multica_create_subtask" in tool_names
        assert "multica_update_task" in tool_names
        assert "multica_add_comment" in tool_names
        assert "multica_assign_task" in tool_names
        assert "multica_create_task_with_subtasks" in tool_names

    def test_read_only_mode_has_9_tools(self):
        client = MockClient()
        uc = UseCase(client, read_only=True)
        mcp_srv = MCPServer(uc, read_only=True)
        tool_names = [t.name for t in mcp_srv._tools]
        assert len(tool_names) == 9
        assert "multica_create_project" not in tool_names
        assert "multica_create_task" not in tool_names
        assert "multica_update_task" not in tool_names
        assert "multica_add_comment" not in tool_names

    @pytest.mark.asyncio
    async def test_handle_list_projects(self):
        client = MockClient()
        uc = UseCase(client)
        mcp_srv = MCPServer(uc)
        result = await mcp_srv._handle_call("multica_list_projects", {})
        assert result.isError is False
        assert len(result.content) == 1
        text = result.content[0].text
        assert "[" in text  # JSON array

    @pytest.mark.asyncio
    async def test_handle_get_project(self):
        client = MockClient()
        uc = UseCase(client)
        mcp_srv = MCPServer(uc)
        result = await mcp_srv._handle_call("multica_get_project", {"project_id": "p-1"})
        assert result.isError is False
        assert '"id": "p-1"' in result.content[0].text or '"id":"p-1"' in result.content[0].text

    @pytest.mark.asyncio
    async def test_handle_create_project_dry_run(self):
        client = MockClient()
        uc = UseCase(client)
        mcp_srv = MCPServer(uc)
        result = await mcp_srv._handle_call(
            "multica_create_project",
            {"title": "采购平台监控指标开发", "dry_run": True},
        )
        assert result.isError is False
        assert "(dry run)" in result.content[0].text

    @pytest.mark.asyncio
    async def test_handle_create_task_dry_run(self):
        client = MockClient()
        uc = UseCase(client)
        mcp_srv = MCPServer(uc)
        result = await mcp_srv._handle_call(
            "multica_create_task",
            {"project_id": "p-1", "title": "Test", "description": "desc", "dry_run": True},
        )
        assert result.isError is False
        assert "(dry run)" in result.content[0].text

    @pytest.mark.asyncio
    async def test_handle_unknown_tool(self):
        client = MockClient()
        uc = UseCase(client)
        mcp_srv = MCPServer(uc)
        result = await mcp_srv._handle_call("nonexistent_tool", {})
        assert result.isError is True
        assert "Unknown tool" in result.content[0].text

    @pytest.mark.asyncio
    async def test_handle_create_task_with_subtasks(self):
        client = MockClient()
        uc = UseCase(client)
        mcp_srv = MCPServer(uc)
        result = await mcp_srv._handle_call(
            "multica_create_task_with_subtasks",
            {
                "project_id": "p-1",
                "title": "Parent",
                "description": "desc",
                "subtasks": [
                    {"title": "s1", "description": "d1"},
                    {"title": "s2", "description": "d2"},
                ],
                "dry_run": True,
            },
        )
        assert result.isError is False
        assert "Parent" in result.content[0].text

    @pytest.mark.asyncio
    async def test_handle_plan_task_breakdown(self):
        client = MockClient()
        uc = UseCase(client)
        mcp_srv = MCPServer(uc)
        result = await mcp_srv._handle_call(
            "multica_plan_task_breakdown",
            {"title": "Feature", "description": "Build it"},
        )
        assert result.isError is False
        assert "Analysis and requirements" in result.content[0].text
