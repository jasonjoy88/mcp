# 接入 WorkBuddy 配置片段

把下面的 `mcpServers` 段**合并**进 `~/.workbuddy/mcp.json`（注意：文件名是 `mcp.json`，**不是** `.mcp.json`，少一个点）。

---

## 场景一：接本机运行的实例（局域网调试）

```json
{
  "mcpServers": {
    "multica": {
      "url": "http://127.0.0.1:8080/mcp",
      "headers": {
        "Authorization": "Bearer <MCP_API_KEY 的值>"
      }
    }
  }
}
```

## 场景二：接服务端部署的实例（推荐）

```json
{
  "mcpServers": {
    "multica": {
      "url": "https://your-domain.example.com/mcp",
      "headers": {
        "Authorization": "Bearer <MCP_API_KEY 的值>"
      }
    }
  }
}
```

> 如果服务端没设 `MCP_API_KEY`（无鉴权），可以省略 `headers`。
> 但暴露到公网的实例**必须**设置，否则任何人都能操作你的 Multica 数据。

---

## 生效方式

1. 保存 `~/.workbuddy/mcp.json`
2. 打开 WorkBuddy 的连接器管理页
3. 右上角「**自定义连接器**」入口
4. 找到新出现的 `multica`，点「**信任**」
5. 回到对话，15 个 `multica_*` 工具即可调用

> ⚠️ 新加的 MCP **不会自动激活**，必须手动点「信任」这一步。

---

## 验证是否接通

在 WorkBuddy 对话里直接说：

```
用 multica 列出我所有的项目
```

预期：模型调用 `multica_list_projects`，返回项目列表。

如果失败，按这个顺序排查：

| 现象 | 排查方向 |
|---|---|
| 连接器列表里没有 multica | `mcp.json` 路径或 JSON 格式错；确认是 `~/.workbuddy/mcp.json` |
| 工具调不通、超时 | 服务端没起 / 端口不通 / 防火墙。先 `curl http://<host>:8080/mcp` 验证 |
| 返回 401 | `MCP_API_KEY` 与 `headers` 里的值不一致 |
| 返回 workspace 相关错误 | `MULTICA_WORKSPACE_ID` / `SLUG` 没配，且账号有多个 workspace |
| 返回 403 | Multica PAT 权限不足，或 token 已失效 |

---

## 服务端自检命令

```bash
# 1. 服务是否活着（无鉴权时）
curl -i http://127.0.0.1:8080/mcp

# 2. 带鉴权测试（有设置 MCP_API_KEY 时）
curl -i http://127.0.0.1:8080/mcp \
  -H "Authorization: Bearer your-secret-key"

# 3. Docker 查看日志
docker logs -f multica-mcp

# 4. 确认容器环境变量生效
docker exec multica-mcp env | grep -E "MULTICA_|MCP_"
```
