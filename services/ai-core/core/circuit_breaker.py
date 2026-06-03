import sys
import datetime
from datetime import timedelta, datetime, UTC
import pybreaker

async def call_async(breaker: pybreaker.CircuitBreaker, func, *args, **kwargs):
    """
    Executes a callable asynchronously using the rules of the circuit breaker.
    Avoids using pybreaker's built-in call_async which relies on Tornado's gen.coroutine
    and is broken on modern Python versions.
    """
    with breaker._lock:
        state = breaker.state
        if isinstance(state, pybreaker.CircuitOpenState):
            timeout = timedelta(seconds=breaker.reset_timeout)
            opened_at = breaker._state_storage.opened_at
            if opened_at and datetime.now(UTC) < opened_at + timeout:
                error_msg = "Timeout not elapsed yet, circuit breaker still open"
                raise pybreaker.CircuitBreakerError(error_msg)
            # Timeout elapsed, transition to half-open
            breaker.half_open()
            state = breaker.state

        state.before_call(func, *args, **kwargs)
        for listener in breaker.listeners:
            listener.before_call(breaker, func, *args, **kwargs)

    try:
        ret = await func(*args, **kwargs)
    except BaseException as e:
        with breaker._lock:
            if breaker.is_system_error(e):
                breaker._inc_counter()
                for listener in breaker.listeners:
                    listener.failure(breaker, e)
                breaker.state.on_failure(e)
            else:
                breaker._state_storage.reset_counter()
                breaker.state.on_success()
                for listener in breaker.listeners:
                    listener.success(breaker)
        raise e
    else:
        with breaker._lock:
            breaker._state_storage.reset_counter()
            breaker.state.on_success()
            for listener in breaker.listeners:
                listener.success(breaker)
        return ret
