#!/usr/bin/env python3
"""Experimental POSIX descriptor-anchored evidence snapshot; NOT GPU attestation.

Requires an independently trusted root directory and trusted expected digest.
A malicious actor with write access to the root can replace the *root itself*
before opening; this function does not establish root provenance.
"""
import hashlib
import os
import pathlib
import stat


def read_evidence_snapshot(root, relative_path, expected_sha256, max_bytes=16 * 1024 * 1024):
    """Read only regular files below an opened root, without following symlinks.

    The traversal is relative to directory FDs; replacement of path components
    after opening does not redirect an already opened FD. This is POSIX-only.
    """
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise RuntimeError("POSIX O_NOFOLLOW and O_DIRECTORY required")
    if type(relative_path) is not str or not relative_path or "\\" in relative_path or "\x00" in relative_path:
        raise ValueError("unsafe relative path")
    parts = relative_path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError("unsafe relative path")
    if type(expected_sha256) is not str or len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise ValueError("trusted digest required")
    if type(max_bytes) is not int or not (0 < max_bytes <= 256 * 1024 * 1024):
        raise ValueError("invalid size limit")
    root_path = pathlib.Path(root)
    # Never silently follow a symlink at the root itself.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(root_path, flags)
    try:
        for part in parts[:-1]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=fd)
        try:
            st = os.fstat(file_fd)
            if not stat.S_ISREG(st.st_mode):
                raise ValueError("not a regular file")
            if st.st_size > max_bytes:
                raise ValueError("oversized evidence")
            with os.fdopen(os.dup(file_fd), "rb") as f:
                payload = f.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise ValueError("oversized evidence")
            if hashlib.sha256(payload).hexdigest() != expected_sha256:
                raise ValueError("evidence digest mismatch")
            return payload
        finally:
            os.close(file_fd)
    finally:
        os.close(fd)
