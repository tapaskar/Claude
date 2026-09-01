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
         s6.8-6.13: eight CHM agents, GUJ Circle, Paco/VoLTE/IP domains.
  [PLAN] engineering planning assumption - to validate in the data workshop.

Scope. FM is pan-India from the start (TSD s12 sizes on 15M alarms/day across
~22 circles). CHM is pan-India at target too, with Gujarat as Phase 1 - so the
GPU pool has to be sized for the target state and Phase 1 is only the entry
point. Both phases are computed here; PHASE selects which one the run reports.
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

# --------------------------------- CHM: Gujarat in Phase 1, pan-India target --
# [TSD] s6.11: max 5 concurrent changes per circle; P1 changes in 02:00-06:00.
# That per-circle cap is what bounds execution volume, and it scales with circles.
import os
PHASE = os.environ.get("PHASE", "national")      # "guj" (phase 1) or "national"

# Gujarat baseline
GUJ_CR_DAY       = 100               # [PLAN] Paco + VoLTE + IP, GUJ circle
GUJ_ITEMS_DAY    = 300               # [PLAN] NEs touched across those CRs
# [TSD] s5.1: release documents are QUARTERLY / BI-ANNUAL - OEM release notes,
# technical bulletins and upgrade guides. So MOP generation is a burst workload,
# not a daily rate: 4 OEMs (Nokia, Ericsson, Huawei, ZTE) x 3 domains per drop.
GUJ_DOCS_PER_BURST = 12              # [TSD-derived] 4 OEMs x 3 domains
BURST_WINDOW_H     = 24              # [PLAN] must be indexed before the calendar builds

# Gujarat is one of Vi's larger circles - roughly 8% of the national network, so
# pan-India CHM is ~12.5x the Gujarat baseline, not 22x.
NATIONAL_MULT    = 12.5              # [PLAN]
SCALE            = 1.0 if PHASE == "guj" else NATIONAL_MULT

CR_DAY           = GUJ_CR_DAY    * SCALE
CHANGE_ITEMS_DAY = GUJ_ITEMS_DAY * SCALE
DOCS_PER_BURST   = GUJ_DOCS_PER_BURST * SCALE
RELEASE_DOCS_DAY = DOCS_PER_BURST / 90.0     # steady-state average between drops
MOPS_PER_DOC     = 15                # [PLAN] one per NE-type / activity combination
ROLLBACK_FRAC    = 0.05              # [PLAN]
MIS_REPORTS_DAY  = 20 * (1 if PHASE == "guj" else 3)   # [PLAN] national rollups too

# ------------------------------------------------------------- workloads -----
# tier: heavy = gpt-oss-120b | fast = Gemma 4 26B A4B | mop = Llama 3.1 8B AWQ
WORKLOADS = [
    # --- Fault Management (pan-India) ---
    ("FM · GenAI RFO, agentic loop",   "FM",  "heavy", RFO_DAY * 3,        6_000,   400),
    ("FM · ticket enrichment",         "FM",  "fast",  TICKET_DAY,         2_500,   500),
    ("FM · shift handover",            "FM",  "heavy", 120,               30_000, 1_500),
    ("FM · operator chat Q&A",         "FM",  "fast",  2_400,              2_000,   300),
    # --- Change Management (Gujarat in phase 1, pan-India at target) ---
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
    scope = "Gujarat, phase 1" if PHASE == "guj" else f"pan-India ({NATIONAL_MULT}x Gujarat)"
    print(f"CHM [{scope}]: {CR_DAY:,.0f} CRs/day, {CHANGE_ITEMS_DAY:,.0f} change items")
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

    grand = sum(v["total_tok"] for v in out_tier.values())
    print(f"\nGRAND TOTAL {grand/1e6:,.0f}M tokens/day  ({grand*365/1e9:,.1f}B/year)")

    json.dump(dict(phase=PHASE, scale=SCALE, rows=rows, tiers=out_tier, tracks=out_track,
                   funnel=dict(raw=RAW_ALARMS_DAY, in_scope=IN_SCOPE,
                               distinct=DISTINCT, uai=UAI_DAY, rfo=RFO_DAY),
                   chm=dict(cr_day=CR_DAY, items=CHANGE_ITEMS_DAY,
                            docs_per_burst=DOCS_PER_BURST,
                            mops_per_burst=DOCS_PER_BURST * MOPS_PER_DOC,
                            burst_window_h=BURST_WINDOW_H),
                   peak_factor=PEAK_FACTOR, grand_total=grand),
              open(f"demand_v2_{PHASE}.json", "w"), indent=1)
