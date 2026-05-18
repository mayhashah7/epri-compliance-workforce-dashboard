"""Synthetic AMI generator — meters, substations, interval reads, events."""
from __future__ import annotations

import asyncio
import math
import random
import uuid
from datetime import datetime, timezone

import numpy as np

from .config import settings
from .store import store

PERSONAS = ["residential", "residential", "residential", "residential",
            "commercial-small", "commercial-large", "industrial",
            "ev-owner", "solar"]
TARIFFS = ["R-1", "R-2-TOU", "C-Small", "C-Large", "I-1"]
REGIONS = ["west-feeder", "east-feeder", "north-feeder", "south-feeder"]

# Map center (a fictional service territory near Austin, TX)
CENTER_LAT, CENTER_LON = 30.27, -97.74


def _persona_baseline_kw(persona: str) -> float:
    return {
        "residential": 0.45,
        "commercial-small": 4.5,
        "commercial-large": 35.0,
        "industrial": 180.0,
        "ev-owner": 0.85,
        "solar": 0.30,
    }.get(persona, 0.5)


def build_topology(seed: int = 42) -> None:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    n_subs = settings.substation_count
    total_meters = settings.meter_count

    meters_per_sub = total_meters // n_subs
    feeders_per_sub = 8
    xfmrs_per_feeder = 6
    meters_per_xfmr = max(1, meters_per_sub // (feeders_per_sub * xfmrs_per_feeder))

    for s in range(n_subs):
        sub_id = f"S-{s+1:02d}"
        sub_lat = CENTER_LAT + (s - n_subs / 2) * 0.05 + rng.uniform(-0.02, 0.02)
        sub_lon = CENTER_LON + (s - n_subs / 2) * 0.07 + rng.uniform(-0.02, 0.02)
        store.substations[sub_id] = {
            "substation_id": sub_id,
            "name": f"Substation {s+1}",
            "lat": sub_lat,
            "lon": sub_lon,
            "feeder_count": feeders_per_sub,
        }
        xfmr_list: list[dict] = []
        for f in range(feeders_per_sub):
            feeder_id = f"{sub_id}-F{f+1:02d}"
            for t in range(xfmrs_per_feeder):
                xfmr_id = f"{sub_id}-T{f+1:02d}{t+1:02d}"
                xfmr_lat = sub_lat + np_rng.normal(0, 0.012)
                xfmr_lon = sub_lon + np_rng.normal(0, 0.012)
                meter_count_xfmr = 0
                for _ in range(meters_per_xfmr):
                    meter_count_xfmr += 1
                    persona = rng.choice(PERSONAS)
                    baseline = _persona_baseline_kw(persona)
                    mid = f"M-{uuid.uuid4().hex[:10].upper()}"
                    store.meters[mid] = {
                        "id": mid,
                        "meter_id": mid,
                        "substation_id": sub_id,
                        "feeder_id": feeder_id,
                        "transformer_id": xfmr_id,
                        "persona": persona,
                        "tariff": rng.choice(TARIFFS),
                        "lat": xfmr_lat + np_rng.normal(0, 0.0008),
                        "lon": xfmr_lon + np_rng.normal(0, 0.0008),
                        "baseline_kw": baseline,
                        "online": True,
                        "tamper_flag": False,
                        "flat_overnight": False,
                        "last_kw": baseline,
                        "last_voltage": 240.0,
                        "opt_in_DR": rng.random() < 0.35,
                        "installed_at": "2022-01-01",
                    }
                xfmr_list.append({
                    "transformer_id": xfmr_id,
                    "feeder_id": feeder_id,
                    "lat": xfmr_lat,
                    "lon": xfmr_lon,
                    "meter_count": meter_count_xfmr,
                })
        store.transformers_by_sub[sub_id] = xfmr_list

    print(f"[simulator] Topology built: {len(store.substations)} subs, "
          f"{sum(len(v) for v in store.transformers_by_sub.values())} transformers, "
          f"{len(store.meters)} meters")

    # Mark a small fraction of meters with anomalous traits to make scoring fun
    rng2 = random.Random(seed + 1)
    candidates = [m for m in store.meters.values() if m["persona"] == "residential"]
    for m in rng2.sample(candidates, min(15, len(candidates))):
        m["tamper_flag"] = True
    for m in rng2.sample(candidates, min(40, len(candidates))):
        m["flat_overnight"] = True


# ── Read tick + scenarios ──────────────────────────────────────────────────

def _diurnal_factor(now: datetime) -> float:
    hr = now.hour + now.minute / 60.0
    # Two peaks: morning (7-9) and evening (17-21)
    return 0.55 + 0.25 * math.sin((hr - 6) / 24 * 2 * math.pi) + 0.20 * math.sin((hr - 18) / 24 * 2 * math.pi)


async def tick_reads() -> None:
    now = datetime.now(timezone.utc)
    factor = _diurnal_factor(now)
    rng = np.random.default_rng()

    sub_totals: dict[str, float] = {}
    sample_reads = []
    for m in store.meters.values():
        if not m["online"]:
            m["last_kw"] = 0.0
            m["last_voltage"] = 0.0
            continue
        kw = max(0.0, m["baseline_kw"] * factor * rng.normal(1.0, 0.12))
        if m["persona"] == "solar" and 8 <= now.hour <= 18:
            kw -= max(0.0, 1.5 * math.sin((now.hour - 6) / 12 * math.pi))  # backfeed
        if m["persona"] == "ev-owner" and 22 <= now.hour <= 24:
            kw += 6.0  # EV charging
        if m.get("flat_overnight") and now.hour < 6:
            kw = m["baseline_kw"] * 0.95  # suspiciously flat
        if m.get("theft_active"):
            kw = max(kw * 0.05, 0.001)
        voltage = 240.0 + rng.normal(0, 1.4)
        if m["persona"] == "solar" and kw < 0:
            voltage += 6  # backfeed-driven voltage rise
        m["last_kw"] = round(kw, 3)
        m["last_voltage"] = round(voltage, 1)
        sub_totals[m["substation_id"]] = sub_totals.get(m["substation_id"], 0.0) + kw

        # Append to interval read buffer (sample 1/20 to limit memory)
        if rng.random() < 0.05:
            store.reads_by_meter[m["meter_id"]].append({
                "ts": now.isoformat(),
                "kw": m["last_kw"],
                "kwh": round(m["last_kw"] * 0.25, 4),  # 15-min energy
                "voltage": m["last_voltage"],
            })
        if len(sample_reads) < 50 and rng.random() < 0.001:
            sample_reads.append({"meter_id": m["meter_id"], "kw": m["last_kw"], "voltage": m["last_voltage"]})

    await store.broadcast({
        "type": "tick",
        "data": {
            "ts": now.isoformat(),
            "sub_totals_kw": {k: round(v, 1) for k, v in sub_totals.items()},
            "system_kw": round(sum(sub_totals.values()), 1),
            "samples": sample_reads,
        }
    })


async def simulator_loop() -> None:
    if not settings.enable_simulator:
        return
    print("[simulator] Loop starting…")
    while True:
        try:
            await tick_reads()
        except Exception as e:  # noqa: BLE001
            print(f"[simulator] tick error: {e}")
        await asyncio.sleep(2.0)


# ── Scenarios ──────────────────────────────────────────────────────────────


async def scenario_nerc_question() -> dict:
    evt = {
        "id": str(uuid.uuid4()),
        "kind": "nerc-question",
        "label": "NERC CIP Question",
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": 'What does CIP-013-2 say about supply-chain risk?',
        "details": {"vertical": "compliance-workforce", "agent": "cwm-compliance-doc-retrieval"},
    }
    store.events.append(evt)
    await store.broadcast({"type": "scenario", **evt})
    asyncio.create_task(_dispatch_safe(evt))
    return {**evt, "agent_dispatched": "cwm-compliance-doc-retrieval"}


async def scenario_violation_draft() -> dict:
    evt = {
        "id": str(uuid.uuid4()),
        "kind": "violation-draft",
        "label": "Self-Report Draft",
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": 'Draft a self-report for the PRC-005 missed maintenance',
        "details": {"vertical": "compliance-workforce", "agent": "cwm-violation-report-creation"},
    }
    store.events.append(evt)
    await store.broadcast({"type": "scenario", **evt})
    asyncio.create_task(_dispatch_safe(evt))
    return {**evt, "agent_dispatched": "cwm-violation-report-creation"}


async def scenario_outage_report() -> dict:
    evt = {
        "id": str(uuid.uuid4()),
        "kind": "outage-report",
        "label": "PUC Outage Report",
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": 'Generate the May major-event-day filing for PUC',
        "details": {"vertical": "compliance-workforce", "agent": "cwm-outage-regulatory-reporting"},
    }
    store.events.append(evt)
    await store.broadcast({"type": "scenario", **evt})
    asyncio.create_task(_dispatch_safe(evt))
    return {**evt, "agent_dispatched": "cwm-outage-regulatory-reporting"}


async def scenario_code_conflict() -> dict:
    evt = {
        "id": str(uuid.uuid4()),
        "kind": "code-conflict",
        "label": "Code Conflict",
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": 'Reconcile NESC vs IEEE 516 on hot-stick clearance',
        "details": {"vertical": "compliance-workforce", "agent": "cwm-codes-standards-interpretation"},
    }
    store.events.append(evt)
    await store.broadcast({"type": "scenario", **evt})
    asyncio.create_task(_dispatch_safe(evt))
    return {**evt, "agent_dispatched": "cwm-codes-standards-interpretation"}


async def scenario_crew_question() -> dict:
    evt = {
        "id": str(uuid.uuid4()),
        "kind": "crew-question",
        "label": "Crew Q&A",
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": 'How do I isolate a faulted feeder during back-feed conditions?',
        "details": {"vertical": "compliance-workforce", "agent": "cwm-virtual-training-assistant"},
    }
    store.events.append(evt)
    await store.broadcast({"type": "scenario", **evt})
    asyncio.create_task(_dispatch_safe(evt))
    return {**evt, "agent_dispatched": "cwm-virtual-training-assistant"}


async def scenario_course_create() -> dict:
    evt = {
        "id": str(uuid.uuid4()),
        "kind": "course-create",
        "label": "Build Training Course",
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": 'Build a 4-hour course on URD splicing from manual M-118',
        "details": {"vertical": "compliance-workforce", "agent": "cwm-training-course-creation"},
    }
    store.events.append(evt)
    await store.broadcast({"type": "scenario", **evt})
    asyncio.create_task(_dispatch_safe(evt))
    return {**evt, "agent_dispatched": "cwm-training-course-creation"}


async def scenario_safety_pattern() -> dict:
    evt = {
        "id": str(uuid.uuid4()),
        "kind": "safety-pattern",
        "label": "Safety Pattern",
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": 'Find recurring near-miss patterns in last 90 days',
        "details": {"vertical": "compliance-workforce", "agent": "cwm-safety-report-analysis"},
    }
    store.events.append(evt)
    await store.broadcast({"type": "scenario", **evt})
    asyncio.create_task(_dispatch_safe(evt))
    return {**evt, "agent_dispatched": "cwm-safety-report-analysis"}


async def scenario_storm_deploy() -> dict:
    evt = {
        "id": str(uuid.uuid4()),
        "kind": "storm-deploy",
        "label": "Storm Deployment Plan",
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": 'Plan crew deployment for 380 outages across 14 districts',
        "details": {"vertical": "compliance-workforce", "agent": "cwm-post-storm-crew-deployment"},
    }
    store.events.append(evt)
    await store.broadcast({"type": "scenario", **evt})
    asyncio.create_task(_dispatch_safe(evt))
    return {**evt, "agent_dispatched": "cwm-post-storm-crew-deployment"}

async def _dispatch_safe(evt: dict) -> None:
    """Lazy-import the agent runner to avoid an import cycle, and never raise."""
    try:
        from .agents import auto_dispatch_for_event
        await auto_dispatch_for_event(evt)
    except Exception as e:
        print(f"[scenario] auto-dispatch failed: {e}")


SCENARIOS = {
    "nerc-question": scenario_nerc_question,
    "violation-draft": scenario_violation_draft,
    "outage-report": scenario_outage_report,
    "code-conflict": scenario_code_conflict,
    "crew-question": scenario_crew_question,
    "course-create": scenario_course_create,
    "safety-pattern": scenario_safety_pattern,
    "storm-deploy": scenario_storm_deploy,
}

SCENARIO_META = [
    {"id": "nerc-question",  "label": "📋 NERC CIP Q&A",        "agent": "cwm-compliance-doc-retrieval",     "hint": "What does CIP-013-2 say about supply-chain risk?"},
    {"id": "violation-draft","label": "📝 Self-Report Draft",   "agent": "cwm-violation-report-creation",    "hint": "Draft a self-report for the PRC-005 missed maintenance"},
    {"id": "outage-report",  "label": "📊 PUC Outage Report",   "agent": "cwm-outage-regulatory-reporting",  "hint": "Generate the May major-event-day filing for PUC"},
    {"id": "code-conflict",  "label": "⚖️ Code Conflict",       "agent": "cwm-codes-standards-interpretation","hint": "Reconcile NESC vs IEEE 516 on hot-stick clearance"},
    {"id": "crew-question",  "label": "👷 Crew Q&A",            "agent": "cwm-virtual-training-assistant",   "hint": "How do I isolate a faulted feeder during back-feed?"},
    {"id": "course-create",  "label": "🎓 Build Training",      "agent": "cwm-training-course-creation",     "hint": "Build a 4-hour course on URD splicing from manual M-118"},
    {"id": "safety-pattern", "label": "🦺 Safety Pattern",      "agent": "cwm-safety-report-analysis",       "hint": "Find recurring near-miss patterns in last 90 days"},
    {"id": "storm-deploy",   "label": "🌀 Storm Deployment",    "agent": "cwm-post-storm-crew-deployment",   "hint": "Plan crew deployment for 380 outages across 14 districts"},
]
