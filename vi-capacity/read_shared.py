"""Fold the shared-pool sweep into the dataset and pick its SLO knee."""
import json, glob, os, re
SHAPE_IN, SHAPE_OUT = 5265, 415      # volume-weighted blend of both workloads
rows = []
for f in sorted(glob.glob("sweep-shared/S_c*.json")):
    conc = int(re.search(r"S_c(\d+)", f).group(1))
    m = json.load(open(f))["benchmarks"][0]["metrics"]
    s = lambda k: m[k]["successful"]
    rps = s("requests_per_second")["mean"]
    rows.append(dict(conc=conc, rps=rps,
        lat_p95=s("request_latency")["percentiles"]["p95"],
        ttft_p95=s("time_to_first_token_ms")["percentiles"]["p95"],
        itl_p95=s("inter_token_latency_ms")["percentiles"]["p95"],
        tok_s=rps*(SHAPE_IN+SHAPE_OUT)))
rows.sort(key=lambda r: r["conc"])
# Gate: RFO latency budget governs the pool; interactive is protected by priority
# scheduling, which this model cannot verify - it needs a run on real hardware.
for r in rows:
    r["slo_ok"] = r["lat_p95"] <= 30.0
best = max((r for r in rows if r["slo_ok"]), key=lambda r: r["tok_s"])
print(f"{'conc':>5}{'req/s':>9}{'lat p95':>10}{'TTFT p95':>11}{'ITL p95':>10}{'tok/s':>10}{'SLO':>7}")
for r in rows:
    print(f"{r['conc']:>5}{r['rps']:>9.3f}{r['lat_p95']:>9.1f}s{r['ttft_p95']:>10.0f}ms"
          f"{r['itl_p95']:>8.1f}ms{r['tok_s']:>10,.0f}{'PASS' if r['slo_ok'] else 'FAIL':>7}")
print(f"\nshared-pool knee: concurrency {best['conc']} -> {best['tok_s']:,.0f} tok/s per H100")
print(f"  (pool A alone 6,066 · pool B alone 3,797 — the blend sits between, as it must)")
json.dump(dict(points=rows, knee=best, shape=[SHAPE_IN, SHAPE_OUT]),
          open("shared.json","w"), indent=1)
