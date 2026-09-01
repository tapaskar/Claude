#!/usr/bin/env python3
"""
Vi AI-NOC RAN FM - workload demand model.

Volumes marked [SLIDE] come from Vi_FM_One_Slide_17th_Aug.pptx.
Volumes marked [PLAN] are engineering planning assumptions to be validated in
the data workshop - each one is a dial, and the sensitivity block at the bottom
shows what the sizing does when you turn it.
"""
import json

# ---------------------------------------------------------------- volumes ---
CELLS                 = 2_000_000     # [SLIDE] ~2M cells national
RAW_ALARMS_DAY        = 10_000_000    # [SLIDE] ~10M raw alarms/day network-wide
RAN_LINKED_FRAC       = 0.70          # [SLIDE] ~70% RAN-linked after CI-scope filter
KPI_GB_DAY            = 285           # [SLIDE] NPM + SevOne
LOG_GB_DAY            = 30            # [SLIDE] element logs

IN_SCOPE_ALARMS       = RAW_ALARMS_DAY * RAN_LINKED_FRAC          # 7.0M/day

# Deterministic normalize/dedup/flap-suppression, no LLM (Correlation Agent, WF lane)
DEDUP_SURVIVAL        = 0.10          # [PLAN] 90% suppressed as dup/flap
DISTINCT_EVENTS       = IN_SCOPE_ALARMS * DEDUP_SURVIVAL          # 700k/day

# Temporal/CI/topology correlation -> Unique Actionable Incidents (WF+ML, no LLM)
EVENTS_PER_UAI        = 20            # [PLAN]
UAI_DAY               = DISTINCT_EVENTS / EVENTS_PER_UAI          # 35k/day

# End-to-end compression actually achieved (SoW target is >=90%)
COMPRESSION           = 1 - UAI_DAY / IN_SCOPE_ALARMS

# Only a subset of UAIs earn a GenAI RFO: P1-P3 + anything ticketed
RFO_FRAC              = 0.35          # [PLAN]
RFO_DAY               = UAI_DAY * RFO_FRAC                        # 12.25k/day

TICKET_DAY            = 8_000         # [PLAN] enriched UAI tickets written to HPSM
HANDOVER_DOCS_DAY     = 120           # [PLAN] 3 shifts x ~40 circles/regions
CHAT_SESSIONS_DAY     = 300           # [PLAN] operator Q&A over an incident
CHAT_TURNS            = 8             # [PLAN]

# ------------------------------------------------------------ token shapes ---
# GenAI RFO agent: agentic evidence loop, RAG over SOP/MOP/OEM/3GPP/historical RCA
RFO_TURNS             = 3             # [PLAN] retrieve -> reason -> draft
RFO_IN_PER_TURN       = 6_000         # alarm evidence + KPI window + 4-6 chunks
RFO_OUT_PER_TURN      = 400

# Action & Interface agent: ticket text, SMS/email/chat, work-order content
TICKET_IN, TICKET_OUT = 2_500, 500
HANDOVER_IN, HANDOVER_OUT = 30_000, 1_500
CHAT_IN, CHAT_OUT     = 2_000, 300

WORKLOADS = [
    # name,                pool, count/day,                    in,             out
    ("GenAI RFO (agentic)", "A", RFO_DAY * RFO_TURNS,          RFO_IN_PER_TURN, RFO_OUT_PER_TURN),
    ("Ticket enrichment",   "B", TICKET_DAY,                   TICKET_IN,       TICKET_OUT),
    ("Shift handover",      "B", HANDOVER_DOCS_DAY,            HANDOVER_IN,     HANDOVER_OUT),
    ("Operator chat Q&A",   "B", CHAT_SESSIONS_DAY*CHAT_TURNS, CHAT_IN,         CHAT_OUT),
]

# Alarms are not uniform: storms (fibre cut, grid outage, weather) concentrate load.
# Peak hour carries ~10% of the day vs 4.17% if flat.
PEAK_HOUR_SHARE       = 0.10          # [PLAN]
PEAK_FACTOR           = PEAK_HOUR_SHARE / (1/24)                  # 2.4x
TARGET_UTILISATION    = 0.60          # [PLAN] headroom before the queueing cliff


def compute():
    rows, tot = [], {"A": [0, 0, 0], "B": [0, 0, 0]}
    for name, pool, n, tin, tout in WORKLOADS:
        i, o = n * tin, n * tout
        rows.append(dict(workload=name, pool=pool, calls_day=round(n),
                         in_tok_day=round(i), out_tok_day=round(o),
                         total_tok_day=round(i + o)))
        tot[pool][0] += i; tot[pool][1] += o; tot[pool][2] += n
    return rows, tot


if __name__ == "__main__":
    rows, tot = compute()
    print(f"Funnel:  {RAW_ALARMS_DAY:,} raw -> {IN_SCOPE_ALARMS:,.0f} in-scope "
          f"-> {DISTINCT_EVENTS:,.0f} distinct -> {UAI_DAY:,.0f} UAI/day")
    print(f"End-to-end alarm->incident compression: {COMPRESSION*100:.2f}%  (SoW target >=90%)")
    print(f"Peak factor {PEAK_FACTOR:.1f}x, target utilisation {TARGET_UTILISATION:.0%}\n")

    print(f"{'workload':<22}{'pool':<6}{'calls/day':>12}{'in tok/day':>16}{'out tok/day':>14}")
    for r in rows:
        print(f"{r['workload']:<22}{r['pool']:<6}{r['calls_day']:>12,}"
              f"{r['in_tok_day']:>16,}{r['out_tok_day']:>14,}")

    print()
    summary = {}
    for pool in ("A", "B"):
        i, o, n = tot[pool]
        t = i + o
        avg, peak = t / 86400, t / 86400 * PEAK_FACTOR
        summary[pool] = dict(calls_day=round(n), in_tok_day=round(i), out_tok_day=round(o),
                             total_tok_day=round(t), avg_tok_s=round(avg, 1),
                             peak_tok_s=round(peak, 1),
                             avg_req_s=round(n/86400, 3),
                             peak_req_s=round(n/86400*PEAK_FACTOR, 3))
        print(f"POOL {pool}: {n:>10,.0f} calls/day | {t:>14,.0f} tok/day "
              f"| avg {avg:8,.0f} tok/s | peak-hour {peak:8,.0f} tok/s "
              f"| peak {n/86400*PEAK_FACTOR:6.2f} req/s")

    grand = sum(s["total_tok_day"] for s in summary.values())
    print(f"\nGRAND TOTAL: {grand:,} tokens/day  ({grand/1e6:,.0f}M/day, {grand*365/1e9:,.1f}B/year)")

    json.dump(dict(rows=rows, pools=summary,
                   funnel=dict(raw=RAW_ALARMS_DAY, in_scope=IN_SCOPE_ALARMS,
                               distinct=DISTINCT_EVENTS, uai=UAI_DAY,
                               compression=COMPRESSION),
                   peak_factor=PEAK_FACTOR, target_util=TARGET_UTILISATION,
                   grand_total_tok_day=grand),
              open("demand.json", "w"), indent=1)
