#!/usr/bin/env python3
"""
Vi Network AI Platform - demand model v2: FM + Change Management.

Sources
  [TSD]  SNOC AI Use Cases TSD (IBM, 20-08-26) - the authoritative engineering doc.
         s12: 15M alarms/day, 1M-node topology graph, 52k batch / 5 min, 500k peak
         burst in <180 s, pan-India ~22 circles, 150-250 concurrent users.
         s3.7: model tiering - gpt-oss-120b heavy, Gemma 4 26B (A4B) fast,
         Gemma 4 E4B pre-filter, Llama 3.1 8B for MOP generation, E5 embeddings,
         plus a VLM (s3.4.6) for diagrams and scanned documents.
         s6.8-6.13: eight CHM agents across Paco, VoLTE and IP domains.
  [PLAN] engineering planning assumption - to validate in the data workshop.

Scope: both tracks are dimensioned pan-India. TSD s12 already sizes FM that way
(15M alarms/day across ~22 circles); CHM is dimensioned to the same footprint so
the pool is bought once against the full estate.
"""
import json

# ----------------------------------------------------------- FM, pan-India ---
RAW_ALARMS_DAY   = 15_000_000        # [TSD] s12 - was 10M on the Aug one-slide
RAN_LINKED_FRAC  = 0.70              # [PLAN]
IN_SCOPE         = RAW_ALARMS_DAY * RAN_LINKED_FRAC
DEDUP_SURVIVAL   = 0.10              # [PLAN]
DISTINCT         = IN_SCOPE * DEDUP_SURVIVAL
EVENTS_PER_UAI   = 20                # [PLAN]
UAI_DAY          = DISTINCT / EVENTS_PER_UAI
RFO_FRAC         = 0.35              # [PLAN]
RFO_DAY          = UAI_DAY * RFO_FRAC
TICKET_DAY       = UAI_DAY * 0.23    # [PLAN] ~ same ratio as the Aug model

# ------------------------------------------------- CHM, pan-India -----------
# [TSD] s6.11: max 5 concurrent changes per circle; P1 changes in 02:00-06:00.
# Across ~22 circles that per-circle cap is what bounds national execution volume.
CR_DAY           = 1_250             # [PLAN] Paco + VoLTE + IP, all circles
CHANGE_ITEMS_DAY = 3_750             # [PLAN] NEs touched across those CRs

# [TSD] s5.1: release documents are QUARTERLY / BI-ANNUAL - OEM release notes,
# technical bulletins and upgrade guides. So MOP generation is a burst workload,
# not a daily rate: 4 OEMs (Nokia, Ericsson, Huawei, ZTE) x 3 domains per circle.
DOCS_PER_BURST   = 150               # [PLAN] national release drop
BURST_WINDOW_H   = 24                # [PLAN] must be indexed before the calendar builds
RELEASE_DOCS_DAY = DOCS_PER_BURST / 90.0     # steady-state average between drops

MOPS_PER_DOC     = 15                # [PLAN] one per NE-type / activity combination
ROLLBACK_FRAC    = 0.05              # [PLAN]
MIS_REPORTS_DAY  = 60                # [PLAN] circle + national rollups

# ------------------------------------------------------------- workloads -----
# tier: heavy = gpt-oss-120b | fast = Gemma 4 26B A4B | mop = Llama 3.1 8B AWQ
WORKLOADS = [
    # --- Fault Management (pan-India) ---
    ("FM · GenAI RFO, agentic loop",   "FM",  "heavy", RFO_DAY * 3,        6_000,   400),
    ("FM · ticket enrichment",         "FM",  "fast",  TICKET_DAY,         2_500,   500),
    ("FM · shift handover",            "FM",  "heavy", 120,               30_000, 1_500),
    ("FM · operator chat Q&A",         "FM",  "fast",  2_400,              2_000,   300),
    # --- Change Management (pan-India) ---
    # burst workloads - sized on the quarterly drop, not the daily mean
    ("CHM · MOP generation (burst)",   "CHM", "mop",   DOCS_PER_BURST * MOPS_PER_DOC
                                                        * 24 / BURST_WINDOW_H,
                                                                          12_000, 2_500),
    ("CHM · release-doc parsing",      "CHM", "fast",  DOCS_PER_BURST * 40
                                                        * 24 / BURST_WINDOW_H,
                                                                           4_000,   600),
    ("CHM · scope classification",     "CHM", "fast",  CHANGE_ITEMS_DAY,   1_500,   200),
    ("CHM · risk assess + runbook",    "CHM", "heavy", CR_DAY,             4_000,   800),
    ("CHM · customer intimation",      "CHM", "fast",  CR_DAY * 3,           800,   200),
    ("CHM · pre/post-check summary",   "CHM", "fast",  CR_DAY * 2,         2_500,   400),
    ("CHM · rollback narrative",       "CHM", "heavy", CR_DAY * ROLLBACK_FRAC,
                                                                           5_000, 1_000),
    ("CHM · MIS reporting",            "CHM", "heavy", MIS_REPORTS_DAY,   25_000, 2_000),
]

# [TSD] s12 - alarms arrive in 5-minute batches, avg 52k, peak burst 10x.
PEAK_HOUR_SHARE = 0.10               # [PLAN]
PEAK_FACTOR     = PEAK_HOUR_SHARE / (1 / 24)


def compute():
    rows, tier, track = [], {}, {}
    for name, trk, tr, n, tin, tout in WORKLOADS:
        i, o = n * tin, n * tout
        rows.append(dict(workload=name, track=trk, tier=tr, calls_day=round(n),
                         in_tok=round(i), out_tok=round(o), total_tok=round(i + o),
                         tin=tin, tout=tout))
        for d, k in ((tier, tr), (track, trk)):
            a = d.setdefault(k, [0, 0, 0])
            a[0] += i; a[1] += o; a[2] += n
    return rows, tier, track


if __name__ == "__main__":
    rows, tier, track = compute()
    print(f"FM funnel [TSD 15M/day]: {RAW_ALARMS_DAY:,} raw -> {IN_SCOPE:,.0f} in-scope "
          f"-> {DISTINCT:,.0f} distinct -> {UAI_DAY:,.0f} UAI -> {RFO_DAY:,.0f} RFO/day")
    print(f"CHM [pan-India]: {CR_DAY:,.0f} CRs/day, {CHANGE_ITEMS_DAY:,.0f} change items")
    print(f"CHM release drop [TSD quarterly]: {DOCS_PER_BURST:,.0f} docs -> "
          f"{DOCS_PER_BURST*MOPS_PER_DOC:,.0f} MOPs in a {BURST_WINDOW_H}h window "
          f"(daily mean {RELEASE_DOCS_DAY*MOPS_PER_DOC:,.1f} MOPs)")
    print(f"peak factor {PEAK_FACTOR:.1f}x\n")

    print(f"{'workload':<32}{'track':<6}{'tier':<7}{'calls/day':>11}"
          f"{'in tok/day':>14}{'out tok/day':>13}")
    for r in rows:
        print(f"{r['workload']:<32}{r['track']:<6}{r['tier']:<7}{r['calls_day']:>11,}"
              f"{r['in_tok']:>14,}{r['out_tok']:>13,}")

    print()
    out_tier = {}
    for k in ("heavy", "fast", "mop"):
        if k not in tier:
            continue
        i, o, n = tier[k]
        t = i + o
        out_tier[k] = dict(calls_day=round(n), in_tok=round(i), out_tok=round(o),
                           total_tok=round(t), avg_tok_s=round(t / 86400, 1),
                           peak_tok_s=round(t / 86400 * PEAK_FACTOR, 1))
        print(f"TIER {k:<6} {n:>9,.0f} calls/day  {t:>14,.0f} tok/day  "
              f"avg {t/86400:8,.0f} tok/s   peak {t/86400*PEAK_FACTOR:9,.0f} tok/s")

    print()
    out_track = {}
    for k in ("FM", "CHM"):
        i, o, n = track[k]
        t = i + o
        out_track[k] = dict(calls_day=round(n), total_tok=round(t),
                            avg_tok_s=round(t / 86400, 1),
                            peak_tok_s=round(t / 86400 * PEAK_FACTOR, 1))
        print(f"TRACK {k:<4} {n:>9,.0f} calls/day  {t:>14,.0f} tok/day  "
              f"({t / sum(track[x][0] + track[x][1] for x in track):.1%} of tokens)")

    burst_names = {"CHM · MOP generation (burst)", "CHM · release-doc parsing"}
    chm_burst = sum(r["total_tok"] for r in rows if r["workload"] in burst_names)
    chm_steady = sum(r["total_tok"] for r in rows
                     if r["track"] == "CHM" and r["workload"] not in burst_names)
    print(f"\n  CHM steady state {chm_steady/1e6:,.0f}M/day | "
          f"release-drop burst {chm_burst/1e6:,.0f}M/day")

    grand = sum(v["total_tok"] for v in out_tier.values())
    print(f"\nGRAND TOTAL {grand/1e6:,.0f}M tokens/day  ({grand*365/1e9:,.1f}B/year)")

    json.dump(dict(rows=rows, tiers=out_tier, tracks=out_track,
                   chm_split=dict(steady=chm_steady, burst=chm_burst),
                   funnel=dict(raw=RAW_ALARMS_DAY, in_scope=IN_SCOPE,
                               distinct=DISTINCT, uai=UAI_DAY, rfo=RFO_DAY),
                   chm=dict(cr_day=CR_DAY, items=CHANGE_ITEMS_DAY,
                            docs_per_burst=DOCS_PER_BURST,
                            mops_per_burst=DOCS_PER_BURST * MOPS_PER_DOC,
                            burst_window_h=BURST_WINDOW_H),
                   peak_factor=PEAK_FACTOR, grand_total=grand),
              open("demand_v2.json", "w"), indent=1)
