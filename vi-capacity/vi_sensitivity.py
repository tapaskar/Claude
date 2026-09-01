#!/usr/bin/env python3
"""
Vi AI-NOC - sensitivity of the GPU fleet to each planning assumption.

The capacity per GPU is MEASURED (GuideLLM sweep). The demand is ASSUMED.
So every argument about fleet size is really an argument about one of these
dials. This prints how far each one has to move before the answer changes.
"""
import json, math

cap = json.load(open("capacity.json"))
dem = json.load(open("demand.json"))

CAP_A = cap["pools"]["A"]["usable_tok_s"]      # 70%-headroom SLO-passing capacity
CAP_B = cap["pools"]["B"]["usable_tok_s"]
PEAK  = dem["peak_factor"]

BASE = dict(uai_day=35_000, rfo_frac=0.35, rfo_turns=3, rfo_in=6_000, rfo_out=400,
            ticket_day=8_000, ticket_in=2_500, ticket_out=500,
            handover_day=120, handover_in=30_000, handover_out=1_500,
            chat_calls=2_400, chat_in=2_000, chat_out=300)


def fleet(p):
    a = p["uai_day"] * p["rfo_frac"] * p["rfo_turns"] * (p["rfo_in"] + p["rfo_out"])
    b = (p["ticket_day"] * (p["ticket_in"] + p["ticket_out"])
         + p["handover_day"] * (p["handover_in"] + p["handover_out"])
         + p["chat_calls"] * (p["chat_in"] + p["chat_out"]))
    pa, pb = a / 86400 * PEAK, b / 86400 * PEAK
    ga, gb = max(1, math.ceil(pa / CAP_A)), max(1, math.ceil(pb / CAP_B))
    return dict(tok_day=a + b, peak_a=pa, peak_b=pb, serving=ga + gb,
                prod=(ga + 1) * 2 + (gb + 1) * 2)


base = fleet(BASE)
print(f"BASELINE  {base['tok_day']/1e6:,.0f}M tok/day  ->  {base['serving']} serving, "
      f"{base['prod']} production H100\n")
print(f"measured usable capacity: pool A {CAP_A:,.0f} tok/s | pool B {CAP_B:,.0f} tok/s per H100\n")

SCENARIOS = [
    ("Every UAI gets an RFO (not 35%)",            dict(rfo_frac=1.0)),
    ("Compression misses: 3x more UAI/day",        dict(uai_day=105_000)),
    ("Deeper agent loop: 6 turns not 3",           dict(rfo_turns=6)),
    ("Long-context RFO: 24k in not 6k",            dict(rfo_in=24_000)),
    ("Verbose RFO: 1,500 out not 400",             dict(rfo_out=1_500)),
    ("Chat becomes the primary UI: 50k calls/day", dict(chat_calls=50_000)),
    ("WORST CASE: every UAI, 6 turns, 24k ctx",    dict(rfo_frac=1.0, rfo_turns=6, rfo_in=24_000)),
    ("LEAN: RFO only for P1/P2 (12% of UAI)",      dict(rfo_frac=0.12)),
]

print(f"{'scenario':<46}{'tok/day':>12}{'x base':>8}{'peak A':>10}{'serving':>9}{'prod':>7}")
print(f"{'baseline':<46}{base['tok_day']/1e6:>11,.0f}M{1.0:>8.1f}"
      f"{base['peak_a']:>10,.0f}{base['serving']:>9}{base['prod']:>7}")
rows = []
for name, delta in SCENARIOS:
    p = dict(BASE); p.update(delta)
    f = fleet(p)
    rows.append(dict(name=name, **{k: round(v, 1) for k, v in f.items()}))
    print(f"{name:<46}{f['tok_day']/1e6:>11,.0f}M{f['tok_day']/base['tok_day']:>8.1f}"
          f"{f['peak_a']:>10,.0f}{f['serving']:>9}{f['prod']:>7}")

# ---- break-even volume for on-prem vs hosted API ---------------------------
GPU_HOURLY, API_PER_1M = 3.20, 0.60
prod = cap["prod_total"]
onprem_yr = prod * GPU_HOURLY * 8760
be_tok_yr = onprem_yr / API_PER_1M * 1e6
print(f"\nBUILD-VS-BUY BREAK-EVEN")
print(f"  {prod} H100 on-prem costs ${onprem_yr/1e3:,.0f}k/year fully loaded")
print(f"  that buys {be_tok_yr/1e9:,.0f}B tokens/year of hosted API at ${API_PER_1M}/1M")
print(f"  current demand is {dem['grand_total_tok_day']*365/1e9:,.0f}B/year "
      f"-> on-prem breaks even at {be_tok_yr/(dem['grand_total_tok_day']*365):.1f}x today's volume")
print(f"  Vi requires private endpoints anyway, so the fleet is bought for")
print(f"  data residency and HA, not for unit cost.")

json.dump(dict(baseline=base, scenarios=rows,
               cap_a=CAP_A, cap_b=CAP_B,
               breakeven_tok_yr=be_tok_yr, onprem_yr=onprem_yr),
          open("sensitivity.json", "w"), indent=1)
