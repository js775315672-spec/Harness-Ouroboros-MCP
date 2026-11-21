"""Review boundary: this package cannot merge or deploy."""
def require_manual_merge(base_branch: str, approval_reference: str | None = None):
    if base_branch == "main" and not approval_reference:
        raise PermissionError("main requires independent human approval")
    raise PermissionError("automatic merging and deployment are disabled in OFC P0")
