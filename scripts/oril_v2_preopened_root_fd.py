"""Experimental evidence read anchored to an independently supplied open directory FD.

The caller, NOT this module, must authenticate the FD and expected digest.
This is not GPU attestation or a production approval gate.
"""
import hashlib
import os
import stat


def read_from_trusted_root_fd(root_fd, relative_path, expected_sha256, max_bytes=16 * 1024 * 1024):
    if os.name != "posix" or not all(hasattr(os, k) for k in ("O_NOFOLLOW", "O_DIRECTORY")):
        raise RuntimeError("POSIX descriptor traversal required")
    if type(root_fd) is not int or root_fd < 0:
        raise ValueError("trusted root fd required")
    if type(relative_path) is not str or not relative_path or "\\\\" in relative_path or "\\x00" in relative_path:
        raise ValueError("unsafe relative path")
    parts = relative_path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError("unsafe relative path")
    if type(expected_sha256) is not str or len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise ValueError("trusted digest required")
    if type(max_bytes) is not int or not (0 < max_bytes <= 256 * 1024 * 1024):
        raise ValueError("invalid size limit")
    fd = os.dup(root_fd)
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise ValueError("root fd must be directory")
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=fd)
        try:
            st = os.fstat(child)
            if not stat.S_ISREG(st.st_mode):
                raise ValueError("not a regular file")
            if st.st_size > max_bytes:
                raise ValueError("oversized evidence")
            with os.fdopen(os.dup(child), "rb") as stream:
                data = stream.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError("oversized evidence")
            if hashlib.sha256(data).hexdigest() != expected_sha256:
                raise ValueError("evidence digest mismatch")
            return data
        finally:
            os.close(child)
    finally:
        os.close(fd)
