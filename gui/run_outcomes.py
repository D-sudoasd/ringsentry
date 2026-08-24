"""Pure batch-result and run-summary contracts used by the GUI."""


# Batch logs have a small, explicit protocol.  In particular, a QC ``ERROR:``
# is a review signal rather than a failed conversion when the file also has a
# terminal ``SUCCESS:`` line.
_BATCH_LOG_SUCCESS_PREFIX = "SUCCESS:"
_BATCH_LOG_FAILURE_PREFIX = "FAILED:"
_BATCH_LOG_SKIP_PREFIX = "SKIPPED:"
_BATCH_LOG_CANCEL_PREFIX = "CANCELLED"
_BATCH_LOG_WORKER_ERROR_PREFIX = "ERROR LOADING/PROCESSING"
MAX_PREFLIGHT_SAMPLE_COUNT = 20


def classify_batch_result(logs):
    """Classify one file's worker log lines using terminal-result markers.

    Returns ``success``, ``failed``, ``skipped``, ``cancelled`` or ``unknown``.
    QC finding lines such as ``ERROR: ... QC ...`` intentionally do not count
    as failures; a later ``SUCCESS:`` line is the authoritative file result.
    The explicit worker-processing error prefix is retained for the exception
    path used by ``process_one_file``.
    """
    messages = [str(line).strip() for line in (logs or [])]
    upper_messages = [message.upper() for message in messages]
    has_success = any(
        message.startswith(_BATCH_LOG_SUCCESS_PREFIX) for message in messages
    )
    has_failed = any(
        message.startswith(_BATCH_LOG_FAILURE_PREFIX)
        or "WORKER EXCEPTION" in upper
        or upper.startswith(_BATCH_LOG_WORKER_ERROR_PREFIX)
        for message, upper in zip(messages, upper_messages)
    )
    has_cancelled = any(
        upper.startswith(_BATCH_LOG_CANCEL_PREFIX) for upper in upper_messages
    )
    has_skipped = any(
        message.startswith(_BATCH_LOG_SKIP_PREFIX) for message in messages
    )

    if has_cancelled:
        return "cancelled"
    if has_failed:
        return "failed"
    if has_success:
        return "success"
    if has_skipped:
        return "skipped"
    return "unknown"


def is_manual_review_log(line) -> bool:
    """Return whether a run log line belongs in the manual-review section."""
    upper = str(line).upper()
    return any(
        marker in upper
        for marker in ("REVIEW:", "WARNING:", "ERROR", _BATCH_LOG_FAILURE_PREFIX)
    )


def normalize_preflight_sample_count(requested, total_count: int) -> int:
    """Bound a configured QC sample count for conversion preflight.

    The quality page owns the user-facing value.  Preflight only applies a
    safety ceiling so an accidental value cannot turn a conversion start into
    an unbounded full-directory scan.
    """
    total = max(0, int(total_count))
    if total == 0:
        return 0
    try:
        count = int(requested)
    except (TypeError, ValueError):
        count = total
    return min(max(1, count), total, MAX_PREFLIGHT_SAMPLE_COUNT)


def classify_batch_outcome(stats, total_count: int, cancellation_requested=False) -> str:
    """Return a stable outcome key for the completion summary."""
    total = max(0, int(total_count))
    if cancellation_requested or int(stats.get("cancelled", 0)):
        return "cancelled"
    failed = int(stats.get("failed", 0))
    if total and failed >= total:
        return "all_failed"
    if failed:
        return "partial_failure"
    if total and int(stats.get("skipped", 0)) >= total:
        return "all_skipped"
    if total == 0:
        return "empty"
    return "success"


BATCH_OUTCOME_LABELS = {
    "success": "成功",
    "partial_failure": "部分失败",
    "all_failed": "全失败",
    "cancelled": "取消",
    "all_skipped": "全部跳过",
    "empty": "无文件",
}
