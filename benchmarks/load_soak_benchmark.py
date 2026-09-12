"""
AyuSetu Appendix C.7 — Concurrency & Soak Benchmark Harness
===========================================================
Authoritative evaluation runner simulating 50 concurrent kiosk intake sessions
and measuring latency distribution (p50, p95, p99), error rate, and throughput.
"""

import concurrent.futures
import time
from typing import Any, Dict, List
import uuid6

from ayusetu.common.session_cache import SessionCache
from ayusetu.redflag.engine import RedFlagEngine
from ayusetu.redflag.models import StructuredClinicalFact
from ayusetu.clinical.models import SlotDTO, SlotSource, ReportedBy
from ayusetu.clinical.summary_engine import summary_synthesis_engine


def simulate_single_kiosk_workflow(worker_idx: int) -> Dict[str, Any]:
    """Execute complete in-memory kiosk session intake turn."""
    t0 = time.perf_counter()
    sess_id = str(uuid6.uuid7())
    enc_id = str(uuid6.uuid7())

    # 1. Session Cache initialization
    cache = SessionCache()
    sess = cache.create_session(encounter_id=enc_id, session_id=sess_id)

    # 2. Add slots
    slots = [
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="hpi.chief_complaint",
            value=f"Worker {worker_idx} symptom description",
            source=SlotSource.UTTERANCE,
            reported_by=ReportedBy.PATIENT,
            confidence=0.98,
            elicited=True,
        ),
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="vitals.systolic_bp",
            value=125,
            source=SlotSource.TOUCH,
            reported_by=ReportedBy.PATIENT,
            confidence=1.0,
            elicited=True,
        ),
    ]

    # 3. Red Flag evaluation
    facts = [StructuredClinicalFact(path="vitals.systolic_bp", value=125, confidence=1.0)]
    events = RedFlagEngine.evaluate(facts)

    # 4. Five-Gate Summary synthesis
    summary = summary_synthesis_engine.synthesize(encounter_id=enc_id, slots=slots)

    # 5. Panic clear
    cache.panic_clear(sess_id)


    t1 = time.perf_counter()
    duration_ms = (t1 - t0) * 1000.0

    return {
        "worker_idx": worker_idx,
        "duration_ms": duration_ms,
        "success": summary is not None,
    }


class ConcurrencyLoadBenchmarkHarness:
    """Appendix C.7 Concurrency and Load Simulation."""

    def __init__(self, concurrent_workers: int = 50, target_p99_ms: float = 1500.0):
        self.concurrent_workers = concurrent_workers
        self.target_p99_ms = target_p99_ms

    def run_benchmark(self, iterations_per_worker: int = 2) -> Dict[str, Any]:
        total_tasks = self.concurrent_workers * iterations_per_worker
        latencies_ms: List[float] = []
        errors = 0

        t_start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrent_workers) as executor:
            futures = [
                executor.submit(simulate_single_kiosk_workflow, i)
                for i in range(total_tasks)
            ]
            for f in concurrent.futures.as_completed(futures):
                try:
                    res = f.result()
                    latencies_ms.append(res["duration_ms"])
                    if not res["success"]:
                        errors += 1
                except Exception:
                    errors += 1

        t_end = time.perf_counter()
        total_duration = t_end - t_start

        latencies_ms.sort()
        n = len(latencies_ms)
        p50 = latencies_ms[int(n * 0.50)] if n else 0.0
        p95 = latencies_ms[int(n * 0.95)] if n else 0.0
        p99 = latencies_ms[int(n * 0.99)] if n else 0.0
        error_rate = errors / max(1, total_tasks)

        return {
            "status": "EXECUTED",
            "concurrent_workers": self.concurrent_workers,
            "total_sessions": total_tasks,
            "total_duration_sec": round(total_duration, 2),
            "throughput_sessions_per_sec": round(total_tasks / max(1e-6, total_duration), 2),
            "p50_latency_ms": round(p50, 2),
            "p95_latency_ms": round(p95, 2),
            "p99_latency_ms": round(p99, 2),
            "error_count": errors,
            "error_rate": round(error_rate, 4),
            "meets_p99_target": p99 <= self.target_p99_ms,
        }
