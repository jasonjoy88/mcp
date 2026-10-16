# multica-mcp Python 版容器化
#
# 用法：
#   docker build -t multica-mcp:py .
#   docker run -d --name multica-mcp -p 8080:8080 \
#     -e MULTICA_BASE_URL=https://multica.leyodev.cn \
#     -e MULTICA_TOKEN=mul_xxxxx \
#     -e MULTICA_WORKSPACE_ID=ai-bug \
#     -e MCP_TRANSPORT=http \
#     -e MCP_API_KEY=your-secret \
#     multica-mcp:py

FROM python:3.12-slim

WORKDIR /app

# 时区 + 证书（OAuth 回调 / HTTPS 出站都需要）
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# 先装依赖，利用层缓存
RUN pip install --no-cache-dir \
    "mcp>=1.0.0" \
    "httpx>=0.27.0" \
    "pydantic>=2.0.0" \
    "pydantic-settings>=2.0.0" \
    "python-json-logger>=2.0.0" \
    "starlette>=0.37.0" \
    "uvicorn[standard]>=0.27.0"

# 再拷代码
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps .

# 关键默认值：Buddy App 是服务端部署，默认必须是 http 而不是 stdio
ENV MCP_TRANSPORT=http \
    MCP_HTTP_PORT=8080 \
    LOG_LEVEL=info

EXPOSE 8080

# 健康检查：复用 uvicorn 的根路径探测
# 注意：若启用了 MCP_API_KEY，无鉴权请求会返回 401，
# 这仍说明服务活着，因此用 TCP 连通性判断更稳妥。
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import socket,sys; s=socket.socket(); s.settimeout(3); sys.exit(0 if s.connect_ex(('127.0.0.1',8080))==0 else 1)"

ENTRYPOINT ["multica-mcp"]
