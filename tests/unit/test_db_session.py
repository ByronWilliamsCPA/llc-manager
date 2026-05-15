"""Tests for the async DB-session dependency lifecycle.

The ``get_async_session`` dependency is one of the most critical pieces of
infrastructure: every request that touches the DB flows through it. It must
commit on success, roll back on exception, and always close the session.
These tests substitute ``AsyncSessionLocal`` with a recording fake so we can
verify the lifecycle without a running Postgres instance.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeAsyncSession:
    """Records the lifecycle methods invoked by ``get_async_session``."""

    def __init__(self) -> None:
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.close = AsyncMock()

    async def __aenter__(self) -> "_FakeAsyncSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()


def _patch_session_factory(session: _FakeAsyncSession):
    """Patch ``AsyncSessionLocal`` so it returns our fake context manager."""
    factory = MagicMock(return_value=session)
    return patch("llc_manager.db.session.AsyncSessionLocal", factory)


class TestGetAsyncSession:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_commits_on_success(self) -> None:
        from llc_manager.db.session import get_async_session

        session = _FakeAsyncSession()
        with _patch_session_factory(session):
            async for s in get_async_session():
                assert s is session

        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
        session.close.assert_awaited()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rolls_back_on_exception(self) -> None:
        from llc_manager.db.session import get_async_session

        session = _FakeAsyncSession()
        with _patch_session_factory(session):
            gen = get_async_session()
            received = await gen.__anext__()
            assert received is session
            with pytest.raises(RuntimeError, match="boom"):
                # Throwing into the generator simulates an endpoint that
                # raised an exception while the session was checked out.
                await gen.athrow(RuntimeError("boom"))

        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()
        session.close.assert_awaited()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_session_closed_even_when_commit_raises(self) -> None:
        """``finally: await session.close()`` must run unconditionally."""
        from llc_manager.db.session import get_async_session

        session = _FakeAsyncSession()
        session.commit.side_effect = RuntimeError("commit failed")

        with (
            _patch_session_factory(session),
            pytest.raises(RuntimeError, match="commit failed"),
        ):
            async for _ in get_async_session():
                pass

        session.rollback.assert_awaited_once()
        session.close.assert_awaited()
