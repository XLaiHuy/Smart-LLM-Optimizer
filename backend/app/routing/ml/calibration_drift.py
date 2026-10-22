"""Dynamic Calibration Drift Engine for Multi-LLM Routing.

Monitors real-time serving outcomes in a sliding window (e.g. 200 requests)
and applies In-memory Dynamic Threshold Shifts when error or retry rates drift,
safeguarding quality by routing borderline tasks to reference models until stability is restored.
"""

from __future__ import annotations

import collections
import threading


class DriftObservation:
    __slots__ = ("success", "is_retry", "tool_error", "user_dislike", "timestamp")

    def __init__(
        self,
        success: bool = True,
        is_retry: bool = False,
        tool_error: bool = False,
        user_dislike: bool = False,
        timestamp: float = 0.0,
    ) -> None:
        self.success = success
        self.is_retry = is_retry
        self.tool_error = tool_error
        self.user_dislike = user_dislike
        self.timestamp = timestamp


class DriftAdaptiveCalibrator:
    """In-memory sliding-window calibrator to counteract distribution and calibration drift."""

    def __init__(
        self,
        window_size: int = 200,
        error_threshold: float = 0.03,  # 3% acceptable error rate
        max_shift: float = 0.15,  # Maximum threshold upward shift
    ) -> None:
        self.window_size = window_size
        self.error_threshold = error_threshold
        self.max_shift = max_shift
        self._buffer: collections.deque[DriftObservation] = collections.deque(maxlen=window_size)
        self._lock = threading.Lock()

    def record_outcome(
        self,
        *,
        success: bool = True,
        is_retry: bool = False,
        tool_error: bool = False,
        user_dislike: bool = False,
    ) -> None:
        """Record the outcome of a served request into the sliding window."""
        obs = DriftObservation(
            success=success,
            is_retry=is_retry,
            tool_error=tool_error,
            user_dislike=user_dislike,
        )
        with self._lock:
            self._buffer.append(obs)

    def compute_drift_metrics(self) -> dict[str, float]:
        """Compute rolling error and retry metrics."""
        with self._lock:
            total = len(self._buffer)
            if total == 0:
                return {
                    "total_samples": 0.0,
                    "error_rate": 0.0,
                    "retry_rate": 0.0,
                    "tool_error_rate": 0.0,
                    "delta_shift": 0.0,
                }
            failures = sum(
                1
                for o in self._buffer
                if (not o.success or o.is_retry or o.tool_error or o.user_dislike)
            )
            retries = sum(1 for o in self._buffer if o.is_retry)
            tool_errs = sum(1 for o in self._buffer if o.tool_error)

            error_rate = failures / total
            retry_rate = retries / total
            tool_error_rate = tool_errs / total

            # Compute conservative threshold shift if error exceeds tolerance
            excess = max(0.0, error_rate - self.error_threshold)
            delta_shift = min(self.max_shift, excess * 2.0)

            return {
                "total_samples": float(total),
                "error_rate": float(error_rate),
                "retry_rate": float(retry_rate),
                "tool_error_rate": float(tool_error_rate),
                "delta_shift": float(delta_shift),
            }

    def get_dynamic_threshold(self, base_threshold: float) -> float:
        """Adjust base threshold with current drift shift, bounded in [0.0, 1.0]."""
        metrics = self.compute_drift_metrics()
        shift = metrics["delta_shift"]
        return min(1.0, max(0.0, base_threshold + shift))
