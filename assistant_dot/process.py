"""Bounded trusted local executables; never a shell or arbitrary command API."""

import os
import selectors
import signal
import subprocess
import time

from .storage import LocalError


def bounded_process(arguments, timeout=15, limit=524288):
    """Collect bounded bytes from a trusted argv and kill on timeout/overflow.

    Callers own the executable/argument allowlist. No exception includes output.
    """
    process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, start_new_session=True,
                               stderr=subprocess.PIPE, env={"PATH": os.environ.get("PATH", os.defpath),
                                                            "LANG": "en_US.UTF-8", "HOME": os.path.expanduser("~")})
    output = bytearray()
    errors = 0
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "out")
            selector.register(process.stderr, selectors.EVENT_READ, "err")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LocalError("local adapter timed out")
                for key, _ in selector.select(min(remaining, 0.2)):
                    data = os.read(key.fileobj.fileno(), 16384)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    if key.data == "out":
                        output.extend(data)
                    else:
                        errors += len(data)
                    if len(output) > limit or errors > 16384:
                        raise LocalError("local adapter output exceeds limits")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LocalError("local adapter timed out")
            process.wait(timeout=remaining)
            if process.returncode:
                raise LocalError("local adapter failed; no credentials or raw errors returned")
            return bytes(output)
    except subprocess.TimeoutExpired:
        raise LocalError("local adapter timed out") from None
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        process.stdout.close()
        process.stderr.close()
