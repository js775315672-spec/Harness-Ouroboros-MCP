"""POSIX bounded adapter subprocess capture; rejects output before unbounded buffering.

For Linux CI. This is a protocol safety primitive, NOT model or GPU evidence.
"""
import os
import selectors
import signal
import subprocess
import time


def capture_adapter(cmd, request, timeout, max_stdout=200000):
    if os.name != "posix":
        raise RuntimeError("bounded adapter capture currently requires POSIX")
    if not isinstance(request, str):
        raise ValueError("request must be a string")
    data = request.encode("utf-8")
    if len(data) > 65536:
        raise ValueError("adapter request exceeds 64 KiB")
    deadline = time.monotonic() + timeout
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, start_new_session=True,
                            bufsize=0)
    selector = selectors.DefaultSelector()
    output = bytearray()
    pending = memoryview(data)
    try:
        os.set_blocking(proc.stdout.fileno(), False)
        os.set_blocking(proc.stdin.fileno(), False)
        selector.register(proc.stdout, selectors.EVENT_READ)
        if pending:
            selector.register(proc.stdin, selectors.EVENT_WRITE)
        else:
            proc.stdin.close()
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("model adapter timed out")
            events = selector.select(min(remaining, 0.25))
            for key, _ in events:
                if key.fileobj is proc.stdin:
                    try:
                        n = os.write(proc.stdin.fileno(), pending[:16384])
                    except BrokenPipeError:
                        n = len(pending)
                    pending = pending[n:]
                    if not pending:
                        selector.unregister(proc.stdin)
                        proc.stdin.close()
                else:
                    chunk = os.read(proc.stdout.fileno(), min(65536, max_stdout + 1 - len(output)))
                    if chunk:
                        output.extend(chunk)
                        if len(output) > max_stdout:
                            raise ValueError("adapter failed or returned excessive output")
                    else:
                        selector.unregister(proc.stdout)
                        proc.stdout.close()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("model adapter timed out")
        proc.wait(timeout=remaining)
        if proc.returncode:
            raise ValueError("adapter failed or returned excessive output")
        try:
            return output.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("adapter emitted invalid UTF-8") from exc
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("model adapter timed out") from exc
    finally:
        selector.close()
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        for pipe in (proc.stdin, proc.stdout):
            if pipe and not pipe.closed:
                pipe.close()
