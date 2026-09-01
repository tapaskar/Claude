#!/usr/bin/env python3
"""
Vi AI-NOC - GPU sizing from the GuideLLM sweep.

Reads every sweep/*.json GuideLLM produced, applies the per-pool SLO gate,
finds the highest-throughput operating point that still passes, and divides
peak-hour demand by it.

Note on token accounting: the mock backend reports usage.prompt_tokens with its
own internal tokenizer, so GuideLLM's prompt_token_count is not meaningful here.
requests_per_second, request_latency, TTFT and ITL ARE measured end-to-end and
are used as-is; throughput is derived as measured req/s x the configured token
shape. On real hardware vLLM reports true usage and prompt_token_count is used
directly.
"""
import json, glob, math, os, re

SHAPES = {"A": (6000, 400), "B": (2000, 400)}
POOL_NAME = {"A": "GenAI RFO agent (throughput class)",
             "B": "Action & Interface / operator chat (interactive class)"}

# SLO gates. Pool A: an RFO must be attached to the UAI well inside the ticket
# window, so the gate is end-to-end request latency. Pool B: a human is waiting,
# so the gate is TTFT plus a readable streaming rate (>= 40 tok/s => ITL <= 25 ms).
GATES = {
    "A": dict(desc="request latency p95 <= 30 s",
              check=lambda r: r["lat_p95"] <= 30.0),
    "B": dict(desc="TTFT p95 <= 1500 ms AND ITL p95 <= 25 ms",
              check=lambda r: r["ttft_p95"] <= 1500.0 and r["itl_p95"] <= 25.0),
}

HEADROOM   = 0.70   # run at 70% of SLO-passing capacity: p95 drifts as you approach the knee
DR_SITES   = 2      # active/active across two data centres
GPU_HOURLY = 3.20   # [PLAN] fully-loaded on-prem H100 $/GPU-hr incl. power, DC, amortisation
API_PER_1M = 0.60   # [PLAN] blended $/1M tokens for a comparable hosted open-weight endpoint


def load():
    rows = []
    for f in sorted(glob.glob("sweep/*.json")):
        tag = os.path.basename(f)[:-5]
        m = re.match(r"([AB])_c(\d+)$", tag)
        if not m:
            continue
        pool, conc = m.group(1), int(m.group(2))
        b = json.load(open(f))["benchmarks"][0]["metrics"]
        s = lambda k: b[k]["successful"]
        pin, pout = SHAPES[pool]
        rps = s("requests_per_second")["mean"]
        rows.append(dict(
            pool=pool, conc=conc, rps=rps,
            lat_med=s("request_latency")["median"],
            lat_p95=s("request_latency")["percentiles"]["p95"],
            ttft_med=s("time_to_first_token_ms")["median"],
            ttft_p95=s("time_to_first_token_ms")["percentiles"]["p95"],
            itl_med=s("inter_token_latency_ms")["median"],
            itl_p95=s("inter_token_latency_ms")["percentiles"]["p95"],
            out_tok_s=rps * pout,
            tok_s=rps * (pin + pout),
            n=s("request_latency")["count"],
        ))
    return sorted(rows, key=lambda r: (r["pool"], r["conc"]))


def main():
    rows = load()
    demand = json.load(open("demand.json"))
    results = {}

    for pool in ("A", "B"):
        pr = [r for r in rows if r["pool"] == pool]
        if not pr:
            continue
        gate = GATES[pool]
        print(f"\n{'='*104}\nPOOL {pool} - {POOL_NAME[pool]}")
        print(f"token shape {SHAPES[pool][0]} in / {SHAPES[pool][1]} out   |   "
              f"SLO gate: {gate['desc']}\n")
        print(f"{'conc':>5}{'req/s':>9}{'lat p95 s':>11}{'TTFT p95':>11}{'ITL p95':>10}"
              f"{'out tok/s':>11}{'tok/s':>10}{'SLO':>7}")
        best = None
        for r in pr:
            ok = gate["check"](r)
            r["slo_ok"] = ok
            if ok and (best is None or r["tok_s"] > best["tok_s"]):
                best = r
            print(f"{r['conc']:>5}{r['rps']:>9.3f}{r['lat_p95']:>11.1f}"
                  f"{r['ttft_p95']:>11.0f}{r['itl_p95']:>10.1f}"
                  f"{r['out_tok_s']:>11.0f}{r['tok_s']:>10,.0f}"
                  f"{('PASS' if ok else 'FAIL'):>7}")

        if best is None:
            print("  !! no operating point meets the SLO - model or hardware must change")
            continue

        d = demand["pools"][pool]
        cap = best["tok_s"]
        usable = cap * HEADROOM
        gpus_avg  = d["avg_tok_s"]  / usable
        gpus_peak = d["peak_tok_s"] / usable
        serving = max(1, math.ceil(gpus_peak))
        per_site = serving + 1                       # N+1 within a site
        total = per_site * DR_SITES

        results[pool] = dict(knee_conc=best["conc"], cap_tok_s=cap, usable_tok_s=usable,
                             gpus_avg=gpus_avg, gpus_peak=gpus_peak, serving=serving,
                             per_site=per_site, total=total,
                             lat_p95=best["lat_p95"], ttft_p95=best["ttft_p95"],
                             itl_p95=best["itl_p95"], rps=best["rps"])

        print(f"\n  SLO-passing knee : concurrency {best['conc']}  ->  {cap:,.0f} tok/s per H100"
              f"  ({best['rps']:.2f} req/s)")
        print(f"  usable @ {HEADROOM:.0%} headroom : {usable:,.0f} tok/s per H100")
        print(f"  demand           : avg {d['avg_tok_s']:,.0f} tok/s | "
              f"peak-hour {d['peak_tok_s']:,.0f} tok/s")
        print(f"  GPUs required    : {gpus_avg:.2f} at average, {gpus_peak:.2f} at peak-hour "
              f"-> {serving} serving")
        print(f"  with N+1 and {DR_SITES} sites : {per_site} per site, {total} H100 total")

    # ------------------------------------------------------------- summary ---
    print(f"\n{'='*104}\nPLATFORM GPU SUMMARY")
    ser = sum(v["serving"] for v in results.values())
    tot = sum(v["total"] for v in results.values())
    print(f"  serving GPUs (peak-hour, SLO-met, 30% headroom) : {ser}")
    print(f"  production H100 incl. N+1 across {DR_SITES} sites   : {tot}")
    print(f"  non-prod (eval harness, model bake-off, regression): 2")
    print(f"  ML training / fine-tune (shared, off-peak)         : 2")
    print(f"  ---------------------------------------------------------------")
    print(f"  TOTAL GPU FLEET                                    : {tot + 4} x H100 80GB")

    # ------------------------------------------------------------ economics ---
    tok_yr = demand["grand_total_tok_day"] * 365
    onprem = tot * GPU_HOURLY * 8760
    api    = tok_yr / 1e6 * API_PER_1M
    print(f"\nECONOMICS (indicative)")
    print(f"  token volume            : {demand['grand_total_tok_day']/1e6:,.0f}M/day, "
          f"{tok_yr/1e9:,.1f}B/year")
    print(f"  on-prem {tot} H100 @ ${GPU_HOURLY}/GPU-hr : ${onprem/1e6:,.2f}M/year "
          f"(${onprem/(tok_yr/1e6):,.2f}/1M tokens at this volume)")
    print(f"  hosted API @ ${API_PER_1M}/1M          : ${api/1e6:,.2f}M/year")
    print(f"  -> on-prem is {'CHEAPER' if onprem < api else 'MORE EXPENSIVE'} by "
          f"${abs(onprem-api)/1e6:,.2f}M/year at this volume")
    print(f"  NOTE: Vi SoW section 2 requires approved on-prem/private LLM endpoints,")
    print(f"        so this is a floor-cost comparison, not a live build-vs-buy option.")

    # utilisation reality check - the number that actually decides on-prem economics
    util = demand["pools"]["A"]["avg_tok_s"] + demand["pools"]["B"]["avg_tok_s"]
    cap_all = sum(results[p]["cap_tok_s"] * results[p]["serving"] for p in results)
    print(f"\n  average utilisation of the serving fleet: {util/cap_all:.1%} "
          f"({util:,.0f} of {cap_all:,.0f} tok/s)")
    print(f"  -> the fleet is sized by PEAK and by HA, not by average load.")

    json.dump(dict(points=rows, pools=results, headroom=HEADROOM, dr_sites=DR_SITES,
                   serving=ser, prod_total=tot, fleet=tot + 4,
                   onprem_usd_yr=onprem, api_usd_yr=api),
              open("capacity.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
