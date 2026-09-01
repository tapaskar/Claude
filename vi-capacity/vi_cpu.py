#!/usr/bin/env python3
"""
Vi AI-NOC RAN FM - CPU / memory / storage sizing for the non-LLM tiers.

The LLM tier is sized by GuideLLM (vi_capacity.py). This file sizes everything
else, which is where most of the platform actually lives: ingest, streaming
correlation, classical ML, graph, vector, orchestration, storage, observability.

Every component is sized for the PEAK-HOUR rate, then divided by a target
utilisation, then given an HA replica count. Units are vCPU (1 vCPU = 1 SMT
thread of a current Xeon/EPYC) and GB RAM.
"""
import json
from vi_demand import (IN_SCOPE_ALARMS, DISTINCT_EVENTS, UAI_DAY, KPI_GB_DAY,
                       LOG_GB_DAY, CELLS, PEAK_FACTOR, TARGET_UTILISATION)

# ------------------------------------------------------------ stream rates ---
alarm_avg_s   = IN_SCOPE_ALARMS / 86400                 # ~81/s
alarm_peak_s  = alarm_avg_s * PEAK_FACTOR               # ~194/s sustained peak hour
alarm_storm_s = 5_000                                   # [PLAN] transient storm burst

KPI_REC_BYTES = 500                                     # [PLAN]
kpi_avg_s     = KPI_GB_DAY * 1e9 / KPI_REC_BYTES / 86400
kpi_peak_s    = kpi_avg_s * PEAK_FACTOR

# Anomaly scoring surface: cells x KPIs at 15-min granularity
KPIS_PER_CELL = 20                                      # [PLAN]
SAMPLES_DAY   = 96                                      # 15-min
score_rows_s  = CELLS * KPIS_PER_CELL * SAMPLES_DAY / 86400

# ------------------------------------------------------------- components ---
# per_vcpu = conservative planning throughput per vCPU, not a vendor peak.
# floor    = the smallest replica anyone actually deploys in production for this
#            component regardless of load (JVM heap, compaction, rebalance,
#            index build, GC headroom). At Vi's event rates most components are
#            FLOOR-dominated, not throughput-dominated - that is the headline.
COMPONENTS = [
    dict(name="Kafka brokers", basis="ingest+retention",
         rate=alarm_peak_s + kpi_peak_s, per_vcpu=25_000, replicas=3, ram=128, floor=16,
         note="sized by retention, partitions and replication, not by throughput"),
    dict(name="Flink - normalize/dedup/flap", basis="alarm events/s",
         rate=max(alarm_peak_s, alarm_storm_s * 0.3), per_vcpu=4_000, replicas=3, ram=96,
         floor=16, note="stateful windows + topology enrichment; sized for storm burst"),
    dict(name="Flink - KPI windowing", basis="KPI records/s",
         rate=kpi_peak_s, per_vcpu=8_000, replicas=3, ram=128, floor=16,
         note="285 GB/day is the platform's real firehose"),
    dict(name="Anomaly scoring (ML lane)", basis="feature rows/s",
         rate=score_rows_s, per_vcpu=25_000, replicas=3, ram=128, floor=16,
         note="feature build dominates, not model inference"),
    dict(name="Correlation -> UAI", basis="distinct events/s",
         rate=DISTINCT_EVENTS / 86400 * PEAK_FACTOR, per_vcpu=1_500, replicas=3, ram=64,
         floor=8, note="graph traversal per candidate group"),
    dict(name="Graph DB (topology)", basis="query/s",
         rate=UAI_DAY / 86400 * PEAK_FACTOR * 30, per_vcpu=800, replicas=3, ram=256,
         floor=16, note="~2M cells + transport/core; RAM-resident, RAM is the constraint"),
    dict(name="Vector store (RAG index)", basis="retrievals/s",
         rate=UAI_DAY / 86400 * PEAK_FACTOR * 0.35 * 6, per_vcpu=400, replicas=3, ram=192,
         floor=8, note="300 GB knowledge+index per slide; HNSW in RAM"),
    dict(name="Workflow engine (Temporal)", basis="state transitions/s",
         rate=UAI_DAY / 86400 * PEAK_FACTOR * 150, per_vcpu=1_200, replicas=3, ram=64,
         floor=8, note="one durable workflow per UAI; its history IS the audit trail"),
    dict(name="Agent runtime / API", basis="agent steps/s",
         rate=UAI_DAY / 86400 * PEAK_FACTOR * 12, per_vcpu=250, replicas=3, ram=64,
         floor=8, note="I/O-bound orchestration around the 5 agents"),
    dict(name="Prediction batch (ML lane)", basis="cells scored/s",
         rate=CELLS / (4 * 3600), per_vcpu=2_000, replicas=2, ram=128, floor=16,
         note="HW/SW failure, battery, temp - 4h nightly window; also trains here"),
    dict(name="Observability + token accounting", basis="samples/s",
         rate=(alarm_peak_s + kpi_peak_s) * 0.2, per_vcpu=15_000, replicas=3, ram=192,
         floor=16, note="1.5 TB / 15-30 day per slide; token table per agent"),
    dict(name="Postgres / metadata", basis="fixed", rate=0, per_vcpu=1, replicas=3, ram=128,
         fixed_vcpu=16, floor=16, note="Temporal persistence, model registry, config"),
    dict(name="K8s control plane + ingress", basis="fixed", rate=0, per_vcpu=1, replicas=3,
         ram=64, fixed_vcpu=8, floor=8, note="etcd quorum, ingress, secrets, service mesh"),
]

# ---------------------------------------------------------------- storage ---
# From the slide's own storage card (hot window + intelligence + records + self-mon)
STORAGE_LOGICAL_GB = (4_000 + 400 + 1_000 + 500 + 25 + 300 + 30 + 500 + 300 + 400
                      + 200 + 1_500)          # = 9,155 GB ~ the slide's ~9.3 TB
REPLICATION = 3
GROWTH_HEADROOM = 1.6


def compute():
    rows, tot_v, tot_r, floor_bound = [], 0, 0, 0
    for c in COMPONENTS:
        if "fixed_vcpu" in c:
            need = per = c["fixed_vcpu"]
        else:
            raw = c["rate"] / c["per_vcpu"] / TARGET_UTILISATION / c["replicas"]
            need = max(1, 4 * round(raw / 4 + 0.49))     # throughput-derived, 4-vCPU steps
            per = max(c["floor"], need)                  # operational floor wins if bigger
        bound = "floor" if per > need else "throughput"
        floor_bound += (bound == "floor")
        v, r = per * c["replicas"], c["ram"] * c["replicas"]
        tot_v += v; tot_r += r
        rows.append(dict(name=c["name"], basis=c["basis"], rate=round(c["rate"], 1),
                         vcpu_throughput=need, vcpu_per_replica=per, bound=bound,
                         replicas=c["replicas"], vcpu_total=v, ram_total_gb=r,
                         note=c["note"]))
    return rows, tot_v, tot_r, floor_bound


if __name__ == "__main__":
    print(f"alarms  {alarm_avg_s:8,.0f}/s avg   {alarm_peak_s:8,.0f}/s peak-hour "
          f"  {alarm_storm_s:,}/s storm burst")
    print(f"KPI recs{kpi_avg_s:8,.0f}/s avg   {kpi_peak_s:8,.0f}/s peak-hour")
    print(f"anomaly scoring surface: {score_rows_s:,.0f} feature-rows/s\n")

    rows, tot_v, tot_r, floor_bound = compute()
    print(f"{'component':<34}{'basis':<22}{'rate/s':>11}{'thru':>6}{'depl':>6}"
          f"{'bound by':>11}{'reps':>6}{'vCPU':>7}{'RAM GB':>8}")
    for r in rows:
        print(f"{r['name']:<34}{r['basis']:<22}{r['rate']:>11,.0f}"
              f"{r['vcpu_throughput']:>6}{r['vcpu_per_replica']:>6}{r['bound']:>11}"
              f"{r['replicas']:>6}{r['vcpu_total']:>7}{r['ram_total_gb']:>8}")
    print(f"{'':<34}{'':<22}{'':>11}{'':>6}{'':>6}{'':>11}{'TOTAL':>6}{tot_v:>7}{tot_r:>8}")
    print(f"\n=> {floor_bound}/{len(rows)} components are sized by their operational FLOOR, "
          f"not by Vi's event rate.")

    prod_raw = STORAGE_LOGICAL_GB * REPLICATION * GROWTH_HEADROOM
    print(f"\nStorage: {STORAGE_LOGICAL_GB:,} GB logical (slide) "
          f"x{REPLICATION} replication x{GROWTH_HEADROOM} growth = {prod_raw/1000:,.1f} TB raw NVMe/SSD")

    # Non-prod: dev/UAT/model-eval at ~40% of prod CPU, ~25% of storage
    print(f"Non-prod (dev/UAT/eval): ~{round(tot_v*0.4):,} vCPU, ~{round(tot_r*0.4):,} GB RAM, "
          f"~{prod_raw*0.25/1000:,.1f} TB")
    print(f"\nProd servers @ 96 vCPU / 768 GB each: "
          f"~{max(-(-tot_v//96), -(-tot_r//768)):,.0f} nodes (CPU-bound: {-(-tot_v//96)}, "
          f"RAM-bound: {-(-tot_r//768)})")

    json.dump(dict(rows=rows, total_vcpu=tot_v, total_ram_gb=tot_r,
                   storage_logical_gb=STORAGE_LOGICAL_GB, storage_raw_gb=prod_raw,
                   rates=dict(alarm_avg_s=alarm_avg_s, alarm_peak_s=alarm_peak_s,
                              kpi_avg_s=kpi_avg_s, kpi_peak_s=kpi_peak_s,
                              score_rows_s=score_rows_s)),
              open("cpu.json", "w"), indent=1)
