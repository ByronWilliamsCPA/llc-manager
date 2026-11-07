"""Failure throttle for the break-glass login."""

import ipaddress
import time
from collections import OrderedDict, deque
from collections.abc import Callable

# Per client: 5 failures per 15 minutes.
DEFAULT_MAX_FAILURES = 5
DEFAULT_WINDOW_SECONDS = 15 * 60
DEFAULT_MAX_TRACKED = 10_000

# Across all clients: 20 failures per 15 minutes, after which every attempt is
# refused until the window slides. #CRITICAL: this deliberately trades
# break-glass availability during an active attack for the confidentiality of
# the financial data, because a distributed guesser would otherwise get 5
# attempts per address it controls.
# #VERIFY: tests/unit/test_auth_break_glass.py::TestGlobalBudget.
GLOBAL_MAX_FAILURES = 20
GLOBAL_WINDOW_SECONDS = 15 * 60
GLOBAL_KEY = "*"

_IPV6_PREFIX = 64


def client_key(host: str) -> str:
    """Normalize a client address into its throttle key.

    IPv4-mapped IPv6 addresses count as the IPv4 address they wrap, and an IPv6
    address counts as its ``/64`` network, because one subscriber normally
    controls a whole ``/64`` and could otherwise rotate addresses freely. A value
    that is not an IP address is returned unchanged.

    Args:
        host (str): The client address as seen after proxy handling.

    Returns:
        str: The key the failure counts are kept under.
    """
    # #EDGE: an attacker choosing addresses inside one /64 (or spelling the same
    # address several ways) must not get a fresh budget each time.
    # #VERIFY: tests/unit/test_auth_throttle.py::TestClientKey.
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        network = ipaddress.IPv6Network((address.packed, _IPV6_PREFIX), strict=False)
        return str(network)
    return str(address)


class LoginThrottle:
    """Block a client after too many failed attempts in a sliding window.

    State is held in process memory.

    #ASSUME: every attempt from one client reaches the same process. With two
    replicas (the ``docker-compose.prod.yml`` default) or several workers the
    effective limit is the per-process limit times the process count.
    #VERIFY: keep the break-glass login off by default, and move this state to
    a shared store before raising ``api_workers`` or the replica count.

    Args:
        max_failures (int): Failures within the window that trigger a block.
        window_seconds (float): Length of the sliding window.
        max_tracked (int): Most distinct clients remembered; the least
            recently active client is forgotten first, which bounds memory.
        clock (Callable[[], float]): Monotonic time source (injectable for
            tests).
    """

    def __init__(
        self,
        *,
        max_failures: int = DEFAULT_MAX_FAILURES,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        max_tracked: int = DEFAULT_MAX_TRACKED,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_failures = max_failures
        self._window = window_seconds
        self._max_tracked = max_tracked
        self._clock = clock
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()

    @property
    def tracked_clients(self) -> int:
        """How many distinct clients currently have recorded failures."""
        return len(self._failures)

    def _recent(self, key: str) -> deque[float]:
        """Return the client's failures inside the window, pruning old ones.

        Args:
            key (str): Client identifier.

        Returns:
            deque[float]: Timestamps still inside the window, oldest first.
        """
        failures = self._failures.get(key)
        if failures is None:
            return deque()
        cutoff = self._clock() - self._window
        while failures and failures[0] <= cutoff:
            failures.popleft()
        if not failures:
            del self._failures[key]
            return deque()
        return failures

    def is_blocked(self, key: str) -> bool:
        """Whether the client has used up its failures.

        Args:
            key (str): Client identifier, normally the IP address.

        Returns:
            bool: True when the client must not be allowed another attempt.
        """
        return len(self._recent(key)) >= self._max_failures

    def retry_after(self, key: str) -> int:
        """Seconds until the oldest counted failure leaves the window.

        Args:
            key (str): Client identifier.

        Returns:
            int: Whole seconds to wait, at least 1 while blocked, else 0.
        """
        failures = self._recent(key)
        if len(failures) < self._max_failures:
            return 0
        remaining = failures[0] + self._window - self._clock()
        return max(1, int(remaining) + 1)

    def record_failure(self, key: str) -> None:
        """Count a failed attempt.

        Args:
            key (str): Client identifier.
        """
        failures = self._recent(key)
        failures.append(self._clock())
        self._failures[key] = failures
        self._failures.move_to_end(key)
        while len(self._failures) > self._max_tracked:
            self._failures.popitem(last=False)

    def forget_latest(self, key: str) -> None:
        """Give back the most recent failure, such as a reserved attempt that won.

        Args:
            key (str): Client identifier.
        """
        failures = self._recent(key)
        if failures:
            failures.pop()
        if not failures:
            self._failures.pop(key, None)

    def reset(self, key: str) -> None:
        """Forget a client's failures, after a successful login.

        Args:
            key (str): Client identifier.
        """
        self._failures.pop(key, None)
