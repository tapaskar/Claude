#!/usr/bin/env python3
"""
Vi Network AI Platform - GPU fleet v2, measured against the TSD's own pool.

The TSD (s12) states a Production GPU Inference Pool of:
    gpt-oss-120b   1x H200 141GB  x3 nodes   "latency-tolerant; 2 active for HA"
    E5             1x H200 141GB  x1 node    "throughput-bound - scale by concurrency"
  + 1x H200 non-production (dev/test, time-shared, no HA)

This checks that pool against measured capacity at the TSD's own volumes
(15M alarms/day) with Change Management included, both tracks dimensioned
pan-India, and reports where the pool's model coverage does not match the model
estate the TSD describes elsewhere.
"""
import glob, json, math, os, re

SHAPES = {"heavy": (6000, 400), "fast": (1500, 200), "mop": (12000, 2500)}
# SLO gate per tier. Heavy carries the agentic RFO loop and MOP-adjacent reasoning,
# so it is gated on end-to-end latency; fast serves humans and notifications, so it
# is gated on TTFT and a readable stream; MOP generation is batch and only has to
# land inside the change window.
GATES = {
    "heavy": ("request latency p95 <= 30 s", lambda r: r["lat_p95"] <= 30.0),
    "fast":  ("TTFT p95 <= 1500 ms and ITL p95 <= 25 ms",
              lambda r: r["ttft_p95"] <= 1500 and r["itl_p95"] <= 25),
    "mop":   ("request latency p95 <= 120 s", lambda r: r["lat_p95"] <= 120.0),
}
HEADROOM = 0.70
TSD_POOL = {"prod_gpt_oss": 3, "prod_e5": 1, "nonprod": 1}


def load_sweep():
    tiers = {}
    for f in sorted(glob.glob("sweep-h200/*_c*.json")):
        m = re.match(r"(heavy|fast|mop)_c(\d+)$", os.path.basename(f)[:-5])
        if not m:
            continue
        tier, conc = m.group(1), int(m.group(2))
        b = json.load(open(f))["benchmarks"][0]["metrics"]
        s = lambda k: b[k]["successful"]
        rps = s("requests_per_second")["mean"]
        pin, pout = SHAPES[tier]
        tiers.setdefault(tier, []).append(dict(
            tier=tier, conc=conc, rps=rps,
            lat_p95=s("request_latency")["percentiles"]["p95"],
            ttft_p95=s("time_to_first_token_ms")["percentiles"]["p95"],
            itl_p95=s("inter_token_latency_ms")["percentiles"]["p95"],
            tok_s=rps * (pin + pout)))
    for v in tiers.values():
        v.sort(key=lambda r: r["conc"])
    return tiers


def main():
    sweeps = load_sweep()
    dem = json.load(open("demand_v2.json"))
    knees, out = {}, {}

    print("=" * 96)
    print("MEASURED CAPACITY PER H200 141GB, BY MODEL TIER")
    for tier in ("heavy", "fast", "mop"):
        rows = sweeps.get(tier, [])
        if not rows:
            print(f"  {tier}: no sweep data"); continue
        desc, gate = GATES[tier]
        print(f"\n  {tier.upper()}  ({SHAPES[tier][0]} in / {SHAPES[tier][1]} out)   gate: {desc}")
        print(f"  {'conc':>5}{'req/s':>9}{'lat p95':>10}{'TTFT p95':>11}{'ITL p95':>10}"
              f"{'tok/s':>10}{'SLO':>7}")
        best = None
        for r in rows:
            r["slo_ok"] = gate(r)
            if r["slo_ok"] and (best is None or r["tok_s"] > best["tok_s"]):
                best = r
            print(f"  {r['conc']:>5}{r['rps']:>9.3f}{r['lat_p95']:>9.1f}s"
                  f"{r['ttft_p95']:>10.0f}ms{r['itl_p95']:>8.1f}ms{r['tok_s']:>10,.0f}"
                  f"{'PASS' if r['slo_ok'] else 'FAIL':>7}")
        knees[tier] = best
        print(f"  -> knee at concurrency {best['conc']}: {best['tok_s']:,.0f} tok/s per H200")

    # ---------------------------------------------------------- fleet ------
    print("\n" + "=" * 96)
    print("PAN-INDIA DEMAND OVER MEASURED CAPACITY   (FM + Change Management)")
    print(f"  {'tier':<8}{'peak tok/s':>12}{'knee/GPU':>11}{'usable@70%':>12}{'GPU frac':>10}")
    total, detail = 0.0, {}
    for tier in ("heavy", "fast", "mop"):
        if tier not in dem["tiers"] or tier not in knees:
            continue
        peak = dem["tiers"][tier]["peak_tok_s"]
        knee = knees[tier]["tok_s"]
        usable = knee * HEADROOM
        frac = peak / usable
        total += frac
        detail[tier] = dict(peak=peak, knee=knee, usable=usable, frac=frac)
        print(f"  {tier:<8}{peak:>12,.0f}{knee:>11,.0f}{usable:>12,.0f}{frac:>10.3f}")
    serving = max(1, math.ceil(total))
    print(f"  {'TOTAL':<8}{'':>12}{'':>11}{'':>12}{total:>10.3f}  -> {serving} GPU serving")
    print(f"  with N+1: {serving + 1} production GPU for the LLM tiers")
    out = dict(detail=detail, total_frac=total, serving=serving, prod=serving + 1)

    # ------------------------------------------------- vs the TSD's pool ----
    nat = out
    print("\n" + "=" * 96)
    print("AGAINST THE TSD's OWN POOL (section 12)")
    print(f"  TSD states : {TSD_POOL['prod_gpt_oss']} x H200 for gpt-oss-120b "
          f"(2 active for HA) + {TSD_POOL['prod_e5']} x H200 for E5 "
          f"= {TSD_POOL['prod_gpt_oss'] + TSD_POOL['prod_e5']} production, "
          f"+{TSD_POOL['nonprod']} non-prod")
    print(f"  This model : {nat['serving']} serving + 1 for N+1 = {nat['prod']} production "
          f"for the LLM tiers, plus E5")
    heavy_frac = nat["detail"]["heavy"]["frac"]
    knee_h = knees["heavy"]["tok_s"]
    peak_h = dem["tiers"]["heavy"]["peak_tok_s"]
    print(f"\n  The 3 gpt-oss-120b nodes carry the heavy tier, which needs "
          f"{heavy_frac:.2f} usable-GPU at peak.")
    print(f"  {'active':>8}{'% of 70% target':>18}{'% of raw knee':>15}   verdict")
    for n in (3, 2, 1):
        of_target = heavy_frac / n
        of_knee = peak_h / (knee_h * n)
        if of_knee > 1.0:
            v = "SLO BREACH at peak"
        elif of_target > 1.0:
            v = "meets SLO but the headroom policy is spent"
        else:
            v = "comfortable"
        print(f"  {n:>8}{of_target:>17.1%}{of_knee:>15.1%}   {v}")
    print(f"\n  So the TSD's stated posture - 'latency-tolerant; 2 active for HA' - is")
    print(f"  exactly at the edge once CHM is in pan-India and alarms are at the TSD's 15M/day.")
    print(f"  Two active still meets the SLO, but with ~0% of the 30% headroom left.")

    # ---- E5 is over-provisioned; that card is the answer to the edge above ----
    RFO_DAY = dem["funnel"]["rfo"]
    emb_q = RFO_DAY * 6 + dem["chm"]["cr_day"] * 8      # retrievals/day
    E5_RATE = 5_000                                                 # [PLAN] emb/s on one H200
    CORPUS_CHUNKS = 20_000_000                                      # [PLAN] KB + release docs
    print(f"\n  THE E5 NODE IS THE SLACK IN THIS POOL")
    print(f"    query embeddings   : {emb_q:,.0f}/day = {emb_q/86400:.1f}/s")
    print(f"    one H200 does      : ~{E5_RATE:,}/s for an E5-large-class encoder (0.7 GB FP16)")
    print(f"    utilisation        : {emb_q/86400/E5_RATE:.4%}")
    print(f"    full re-index of {CORPUS_CHUNKS/1e6:.0f}M chunks: "
          f"{CORPUS_CHUNKS/E5_RATE/60:.0f} min, and it is a one-off")
    print(f"    -> a dedicated 141 GB card for a 0.7 GB model is the one clear")
    print(f"       over-provision in the pool. Co-resident E5 with the fast tier and")
    print(f"       that card joins the serving pool: 3 heavy-capable + 1 mixed, which")
    print(f"       turns 'two active at the edge' into 'three active with margin'.")

    MISSING = [
        ("Gemma 4 26B (A4B)", "fast tier - extraction, classification, notifications",
         "named in s3.7 model tiering; no node allocated in the s12 pool"),
        ("Gemma 4 E4B", "optional bulk pre-filtering",
         "named in s3.7; no node allocated"),
        ("Llama 3.1 8B (AWQ)", "MOP generation in the GEN Doc Agent",
         "named in s6.8 and the CHM mapping table; no node allocated"),
        ("VLM", "topology diagrams, screenshots, scanned documents",
         "named in s3.4.6 and listed as a T0 dependency; no node allocated"),
    ]
    print(f"\n  MODEL-COVERAGE GAP - the s12 pool allocates nodes for 2 of the 6 model")
    print(f"  tiers the TSD describes elsewhere:")
    for name, role, note in MISSING:
        print(f"    - {name:<20} {role}\n        {note}")

    # co-residency check on a 141 GB card
    RESIDENT = [("gpt-oss-120b", "MXFP4", 62), ("Gemma 4 26B A4B", "FP8", 26),
                ("Llama 3.1 8B", "AWQ INT4", 6), ("VLM ~12B", "FP8", 13)]
    tot = sum(g for _, _, g in RESIDENT)
    print(f"\n  Can they co-reside on one H200 141GB?")
    for n, q, g in RESIDENT:
        print(f"    {n:<18} {q:<10} {g:>4} GB")
    print(f"    {'TOTAL':<18} {'':<10} {tot:>4} GB of 141 GB "
          f"-> {141 - tot} GB left for KV cache")
    print(f"    Weights fit. But co-resident models share COMPUTE, so the measured")
    print(f"    per-tier capacity above cannot simply be added on one card - that is")
    print(f"    the thing to test on hardware before committing to the pool.")

    json.dump(dict(knees={k: v for k, v in knees.items()}, fleet=out,
                   e5=dict(queries_day=emb_q, rate=E5_RATE,
                           util=emb_q/86400/E5_RATE, corpus=CORPUS_CHUNKS),
                   tsd_pool=TSD_POOL, missing=MISSING, resident=RESIDENT,
                   headroom=HEADROOM,
                   sweeps={k: v for k, v in sweeps.items()}),
              open("fleet_v2.json", "w"), indent=1)


if __name__ == "__main__":
    main()
