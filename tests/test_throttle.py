"""Tests for the login throttle middleware."""


from multica_mcp.middleware import LoginThrottle


class TestLoginThrottle:
    def test_not_blocked_initially(self):
        t = LoginThrottle(max_failures=3, window=60, ban_duration=300)
        assert t.is_blocked("1.2.3.4") is False

    def test_below_threshold_not_blocked(self):
        t = LoginThrottle(max_failures=3, window=60, ban_duration=300)
        t.record_failure("1.2.3.4")
        t.record_failure("1.2.3.4")
        assert t.is_blocked("1.2.3.4") is False

    def test_blocks_after_max_failures(self):
        t = LoginThrottle(max_failures=3, window=60, ban_duration=300)
        for _ in range(3):
            t.record_failure("1.2.3.4")
        assert t.is_blocked("1.2.3.4") is True

    def test_separate_ips(self):
        t = LoginThrottle(max_failures=2, window=60, ban_duration=300)
        for _ in range(2):
            t.record_failure("1.1.1.1")
        assert t.is_blocked("1.1.1.1") is True
        assert t.is_blocked("2.2.2.2") is False

    def test_record_success_clears(self):
        t = LoginThrottle(max_failures=3, window=60, ban_duration=300)
        t.record_failure("1.2.3.4")
        t.record_failure("1.2.3.4")
        t.record_success("1.2.3.4")
        assert t.is_blocked("1.2.3.4") is False
        # After success, one failure shouldn't block
        t.record_failure("1.2.3.4")
        assert t.is_blocked("1.2.3.4") is False

    def test_asgi_middleware_allow_valid_key(self):
        t = LoginThrottle(max_failures=5, window=60, ban_duration=300)

        calls = []

        async def inner_app(scope, receive, send):
            calls.append("inner")
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        app = t.wrap_app("secret-key", inner_app)

        async def receive():
            return {"type": "http.request"}

        sent = []

        async def send(msg):
            sent.append(msg)

        import asyncio

        async def run():
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/test",
                "headers": [(b"authorization", b"Bearer secret-key")],
                "client": ("1.2.3.4", 12345),
            }
            await app(scope, receive, send)

        asyncio.run(run())
        assert calls == ["inner"]
        assert sent[0]["status"] == 200

    def test_asgi_middleware_reject_invalid_key(self):
        t = LoginThrottle(max_failures=5, window=60, ban_duration=300)

        async def inner_app(scope, receive, send):
            pass  # Should not be called

        app = t.wrap_app("secret-key", inner_app)

        async def receive():
            return {"type": "http.request"}

        sent = []

        async def send(msg):
            sent.append(msg)

        import asyncio

        async def run():
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/test",
                "headers": [(b"authorization", b"Bearer wrong-key")],
                "client": ("9.9.9.9", 12345),
            }
            await app(scope, receive, send)

        asyncio.run(run())
        assert sent[0]["status"] == 401
        assert t.is_blocked("9.9.9.9") is False  # only 1 failure

    def test_asgi_middleware_missing_auth_header(self):
        t = LoginThrottle(max_failures=5, window=60, ban_duration=300)

        async def inner_app(scope, receive, send):
            pass

        app = t.wrap_app("secret-key", inner_app)

        async def receive():
            return {"type": "http.request"}

        sent = []

        async def send(msg):
            sent.append(msg)

        import asyncio

        async def run():
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/test",
                "headers": [],
                "client": ("8.8.8.8", 12345),
            }
            await app(scope, receive, send)

        asyncio.run(run())
        assert sent[0]["status"] == 401
