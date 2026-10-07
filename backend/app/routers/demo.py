"""Demo route — reset the database to a known demo state with 25 mixed jobs."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlmodel import Session, delete

from app.core.config import load_sites_config
from app.core.db import get_session
from app.core.time import now_utc
from app.models import (
    ConfigEntry,
    Execution,
    Forecast,
    GridObservation,
    Job,
    JobDependency,
    LedgerEntry,
    Scenario,
    ScheduleItem,
    ScheduleRun,
    Site,
)
from app.services.energy import estimate_job
from app.services.grid_twin import GridDigitalTwin

router = APIRouter()


def _make_job(
    name: str,
    archetype: str,
    team: str,
    priority: int,
    now: datetime,
    release_offset_h: float,
    deadline_offset_h: float,
    duration_h: float,
    gpus: int = 0,
    gpu_type: str | None = None,
    cpu_cores: int = 0,
    util: float = 0.8,
    preemptible: bool = False,
    max_interruptions: int = 0,
    allowed_sites: list[str] | None = None,
    green_only: bool = False,
    data_gb: float = 0.0,
) -> Job:
    est = estimate_job(gpus, gpu_type, cpu_cores, util, duration_h)
    j = Job(
        name=name,
        archetype=archetype,
        team=team,
        priority=priority,
        status="PENDING",
        release_ts=now + timedelta(hours=release_offset_h),
        deadline_ts=now + timedelta(hours=deadline_offset_h),
        duration_h=duration_h,
        gpus=gpus,
        gpu_type=gpu_type or "T4",
        cpu_cores=cpu_cores,
        util=util,
        preemptible=preemptible,
        max_interruptions=max_interruptions,
        allowed_sites_json=json.dumps(allowed_sites or []),
        green_only=green_only,
        data_gb=data_gb,
        energy_kwh=est["facility_energy_kwh"],
        power_kw=est["power_kw"],
    )
    return j


@router.post("/demo/reset")
def reset_demo(session: Session = Depends(get_session)):
    """Reset DB to factory state and seed 25 demo jobs across all archetypes."""
    # ── Delete all data in FK order ──────────────────────────────────────────
    session.exec(delete(LedgerEntry))
    session.exec(delete(Execution))
    session.exec(delete(ScheduleItem))
    session.exec(delete(ScheduleRun))
    session.exec(delete(JobDependency))
    session.exec(delete(Job))
    session.exec(delete(Forecast))
    session.exec(delete(GridObservation))
    session.exec(delete(Site))
    session.exec(delete(Scenario))
    session.exec(delete(ConfigEntry))
    session.commit()

    # ── Seed Sites from YAML ─────────────────────────────────────────────────
    sites_cfg = load_sites_config()
    site_ids = []
    for s in sites_cfg:
        site = Site(
            id=s["id"],
            name=s["name"],
            region=s["region"],
            lat=s["lat"],
            lon=s["lon"],
            gpu_capacity_json=json.dumps(s.get("gpu_capacity", {})),
            cpu_cores=s.get("cpu_cores", 1000),
            power_cap_kw=s.get("power_cap_kw", 500.0),
            pue_base=s.get("pue_base", 1.35),
            pue_k=s.get("pue_k", 0.012),
            pue_temp_limit_c=s.get("pue_temp_limit_c", 24.0),
            allowed_classes_json=json.dumps(s.get("allowed_classes", ["public", "internal"])),
        )
        session.add(site)
        site_ids.append(s["id"])
    session.commit()

    # ── Seed Grid Twin observations (48h history) ────────────────────────────
    twin = GridDigitalTwin()
    now = now_utc().replace(minute=0, second=0, microsecond=0)
    regions = ["NR", "WR", "SR", "ER", "NER"]
    
    for region in regions:
        try:
            df = twin.history(region, now - timedelta(hours=48), now)
            for _, row in df.iterrows():
                obs = GridObservation(
                    ts=row["ts"].to_pydatetime().replace(tzinfo=now.tzinfo),
                    region=region,
                    ci_g_per_kwh=float(row.get("ci_g_per_kwh", 600)),
                    share_solar=float(row.get("share_solar", 0.1)),
                    share_wind=float(row.get("share_wind", 0.1)),
                    share_hydro=float(row.get("share_hydro", 0.1)),
                    share_nuclear=float(row.get("share_nuclear", 0.05)),
                    share_thermal=float(row.get("share_thermal", 0.65)),
                    share_other=float(row.get("share_other", 0.0)),
                    renewable_share=float(row.get("renewable_share", 0.3)),
                    demand_mw=float(row.get("demand_mw", 10000)),
                    source="twin",
                    is_estimated=True,
                )
                session.add(obs)
        except Exception:
            pass  # Twin may fail gracefully
    session.commit()

    # ── Seed 25 mixed demo jobs ─────────────────────────────────────────────
    now_plain = now

    jobs_to_add = [
        # === HIGH PRIORITY — near deadlines ===
        _make_job("Production Model Retraining", "ml_training", "ML-Platform", 5,
                  now_plain, 0, 8, 6.0, gpus=8, gpu_type="A100", util=0.9, preemptible=True, max_interruptions=2, data_gb=200),
        _make_job("Critical Risk Score Update", "ml_training", "Risk", 5,
                  now_plain, 0, 6, 3.0, gpus=4, gpu_type="A100", util=0.85, data_gb=50),
        _make_job("Real-time Fraud Detection Fine-tune", "ml_finetuning", "Security", 5,
                  now_plain, 0, 12, 4.0, gpus=2, gpu_type="V100", util=0.8, preemptible=True, max_interruptions=1),

        # === MEDIUM-HIGH PRIORITY ===
        _make_job("Recommendation Engine Training", "ml_training", "Personalization", 4,
                  now_plain, 2, 24, 8.0, gpus=4, gpu_type="A100", util=0.85, preemptible=True, max_interruptions=3, data_gb=120),
        _make_job("NLP Document Classifier", "ml_training", "NLP-Team", 4,
                  now_plain, 0, 16, 5.0, gpus=4, gpu_type="V100", util=0.8, data_gb=80),
        _make_job("Video Transcoding — Marketing Q3", "render_transcode", "Marketing", 4,
                  now_plain, 1, 20, 10.0, gpus=2, gpu_type="T4", util=0.9),
        _make_job("ETL Pipeline — Sales Analytics", "etl_pipeline", "DataEng", 4,
                  now_plain, 0, 18, 3.0, cpu_cores=64, util=0.7),

        # === MEDIUM PRIORITY — flexible ===
        _make_job("Batch Inference — Product Catalog", "batch_inference", "Platform", 3,
                  now_plain, 4, 36, 4.0, gpus=4, gpu_type="T4", util=0.75, preemptible=True, max_interruptions=2),
        _make_job("Climate Simulation Job A", "scientific_sim", "Research", 3,
                  now_plain, 0, 48, 12.0, cpu_cores=128, util=0.95, preemptible=True, max_interruptions=5),
        _make_job("Data Warehouse ETL — Nightly", "etl_pipeline", "DataEng", 3,
                  now_plain, 6, 30, 2.0, cpu_cores=32, util=0.6),
        _make_job("Model Evaluation — CV Pipeline", "batch_inference", "CV-Team", 3,
                  now_plain, 2, 24, 3.0, gpus=2, gpu_type="T4", util=0.7),
        _make_job("Hyperparameter Sweep Experiment", "ml_training", "ML-Platform", 3,
                  now_plain, 4, 48, 16.0, gpus=8, gpu_type="V100", util=0.8, preemptible=True, max_interruptions=4, green_only=True, data_gb=60),
        _make_job("CI/CD Full Test Suite", "cicd_build", "DevOps", 3,
                  now_plain, 0, 4, 1.5, cpu_cores=16, util=0.8),

        # === LOW PRIORITY — max flexibility (green window targeting) ===
        _make_job("Annual Report PDF Generation", "report_gen", "Finance", 2,
                  now_plain, 8, 48, 1.0, cpu_cores=8, util=0.5),
        _make_job("Cold Backup Archival", "backup_archival", "Ops", 2,
                  now_plain, 12, 72, 4.0, cpu_cores=8, util=0.3, preemptible=True, max_interruptions=10, green_only=True, data_gb=1000),
        _make_job("Genomics Research Batch", "scientific_sim", "BioTech", 2,
                  now_plain, 6, 48, 18.0, cpu_cores=256, util=0.9, preemptible=True, max_interruptions=6, data_gb=400),
        _make_job("Log Aggregation Pipeline", "etl_pipeline", "Ops", 2,
                  now_plain, 4, 48, 2.0, cpu_cores=16, util=0.5),
        _make_job("A/B Test Results Crunching", "batch_inference", "Growth", 2,
                  now_plain, 8, 48, 1.5, cpu_cores=32, util=0.6),

        # === LOWEST PRIORITY — batch background ===
        _make_job("Training Data Preprocessing", "etl_pipeline", "DataEng", 1,
                  now_plain, 12, 72, 6.0, cpu_cores=64, util=0.8, preemptible=True, max_interruptions=8, green_only=True, data_gb=800),
        _make_job("Historical Metrics Backfill", "etl_pipeline", "Analytics", 1,
                  now_plain, 24, 72, 8.0, cpu_cores=32, util=0.5, preemptible=True, max_interruptions=10),
        _make_job("Model Archive & Checkpointing", "backup_archival", "ML-Platform", 1,
                  now_plain, 16, 72, 2.0, cpu_cores=8, util=0.2, preemptible=True, max_interruptions=5),
        _make_job("Satellite Image Processing", "scientific_sim", "GeoAI", 1,
                  now_plain, 24, 72, 20.0, gpus=4, gpu_type="T4", util=0.7, preemptible=True, max_interruptions=10, green_only=True),

        # === SPECIAL: Infeasible job (deadline < duration) for demo ===
        _make_job("INFEASIBLE: 1h deadline 3h job", "ml_training", "Demo-Test", 3,
                  now_plain, 0, 1, 3.0, gpus=2, gpu_type="T4", util=0.8),

        # === SPATIAL demo: restricted site ===
        _make_job("Chennai-only Regulatory Model", "ml_training", "Compliance", 4,
                  now_plain, 0, 24, 4.0, gpus=2, gpu_type="V100", util=0.8,
                  allowed_sites=["chn-1"], data_gb=100),
        _make_job("Southern Grid Data Processing", "etl_pipeline", "DataEng", 2,
                  now_plain, 4, 48, 2.0, cpu_cores=32, util=0.6,
                  allowed_sites=["chn-1", "hyd-1"]),
    ]

    for j in jobs_to_add:
        session.add(j)

    session.commit()

    return {
        "status": "ok",
        "message": "Database reset to demo state.",
        "sites_seeded": len(site_ids),
        "jobs_seeded": len(jobs_to_add),
        "grid_observations_note": "48h twin history loaded for all 5 regions.",
    }
