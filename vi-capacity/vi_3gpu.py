#!/usr/bin/env python3
"""
Vi AI-NOC - can the platform run on 3 H100?

The measured capacity per GPU does not change (same model, same token shapes).
What changes is ALLOCATION and HA POSTURE. This file works backwards from the
3-GPU constraint: what configuration it forces, how much headroom is left, and
at what point each assumption breaks it.

Key method: GPU-fractions add. A workload needing demand/capacity of a GPU can
share that GPU with another workload; a work-conserving scheduler makes the
requirement additive. That is what lets two pools collapse onto one.
"""
import json, math

cap = json.load(open("capacity.json"))
dem = json.load(open("demand.json"))
shd = json.load(open("shared.json"))

# measured, unchanged
KNEE = {"A": cap["pools"]["A"]["cap_tok_s"], "B": cap["pools"]["B"]["cap_tok_s"]}
PEAK = {"A": dem["pools"]["A"]["peak_tok_s"], "B": dem["pools"]["B"]["peak_tok_s"]}
AVG  = {"A": dem["pools"]["A"]["avg_tok_s"],  "B": dem["pools"]["B"]["avg_tok_s"]}
FLEET = 3

frac_peak = {k: PEAK[k]/KNEE[k] for k in KNEE}     # GPU-fractions at the SLO knee
frac_avg  = {k: AVG[k]/KNEE[k]  for k in KNEE}
ADD_PEAK, ADD_AVG = sum(frac_peak.values()), sum(frac_avg.values())

# Cross-check: the shared-pool sweep measured the blend directly on one GPU.
SHARED_KNEE = shd["knee"]["tok_s"]
MEAS_PEAK = sum(PEAK.values())/SHARED_KNEE
MEAS_AVG  = sum(AVG.values())/SHARED_KNEE
EFF = ADD_PEAK/MEAS_PEAK        # additive is slightly optimistic; correct by this
F_PEAK, F_AVG = MEAS_PEAK, MEAS_AVG

print("="*78)
print("MEASURED CAPACITY (unchanged - same model, same token shapes)")
for k in ("A","B"):
    print(f"  pool {k}: knee {KNEE[k]:7,.0f} tok/s per H100 | peak demand {PEAK[k]:7,.0f} tok/s"
          f" -> {frac_peak[k]:.3f} GPU")
print(f"\n  additive estimate (fractions add) : {ADD_PEAK:.3f} GPU at peak")
print(f"  MEASURED shared pool {SHARED_KNEE:,.0f} tok/s : {MEAS_PEAK:.3f} GPU at peak"
      f"   (average {MEAS_AVG:.3f} GPU)")
print(f"  the two methods agree within {abs(1-EFF):.1%} - additive is optimistic by that much,")
print(f"  so every headroom figure below is derated by it.")

print("\n" + "="*78)
print(f"CONSTRAINT: {FLEET} x H100, one shared pool")
for label, n in (("all 3 healthy", 3), ("one GPU failed (N+1)", 2), ("two failed", 1)):
    util = F_PEAK/n
    verdict = ("meets SLO with margin" if util <= 0.70 else
               "meets SLO, thin margin" if util <= 1.0 else "BREACHES SLO at peak")
    print(f"  {label:22} {n} serving -> {util:6.1%} of knee capacity   {verdict}")
print(f"  at average load, 3 healthy: {F_AVG/3:.1%} of knee capacity")

# --- how much demand growth 3 GPUs absorbs -------------------------------
# Interactive must always be served; RFO absorbs the rest.
def rfo_headroom(n_gpu):
    """How far RFO demand can grow on n GPUs, interactive served first.
    Uses the additive split (the classes move independently) derated by the
    efficiency loss the shared-pool sweep actually measured."""
    left = n_gpu - frac_peak["B"]
    return left / frac_peak["A"] * EFF

print("\n" + "="*78)
print("HEADROOM - how much the RFO workload can grow before 3 GPUs is not enough")
for label, n in (("with N+1 (2 must carry peak)", 2), ("no N+1 (all 3 carry peak)", 3)):
    h = rfo_headroom(n)
    print(f"  {label:32} {h:.2f}x the modelled RFO demand")

H = rfo_headroom(2)
print(f"\n  Under the N+1 rule ({H:.2f}x), each dial can move this far alone:")
BASE = dict(uai=35_000, rfo_frac=0.35, turns=3, ctx=6_000)
print(f"    incidents/day   35,000  ->  {BASE['uai']*H:>7,.0f}")
print(f"    RFO share         35%   ->  {BASE['rfo_frac']*H:>7.0%}")
print(f"    agent turns          3  ->  {BASE['turns']*H:>7.1f}")
print(f"    RFO context      6,000  ->  {(BASE['ctx']+400)*H-400:>7,.0f} tokens")

SCEN = [("Every incident gets an RFO", 2.63), ("Compression misses: 3x incidents", 2.75),
        ("Agent loop 3 -> 6 turns", 2.00), ("RFO context 6k -> 24k", 3.47),
        ("Verbose RFO 400 -> 1,500 out", 1.17), ("Chat becomes primary UI", 1.00)]
print("\n  Against the sensitivity scenarios:")
for name, mult in SCEN:
    ok = mult <= H
    need = math.ceil(frac_peak["A"]*mult + frac_peak["B"]) + 1   # +1 for N+1
    print(f"    {'OK ' if ok else 'NO '} {name:36} {mult:.2f}x"
          f"{'' if ok else f'  -> needs {need} GPU'}")

# --- what the 3-GPU constraint costs ------------------------------------
print("\n" + "="*78)
print("WHAT THE 3-GPU CONSTRAINT FORCES (vs the 14-GPU design)")
GIVE = [
 ("Two physical pools", "One shared pool, vLLM priority scheduling",
  "Interactive is only 0.24 GPU of load - it never justified its own hardware."),
 ("Two sites, active/active", "Single site",
  "A DC outage takes the AI-NOC offline. The NOC's existing manual process is the fallback."),
 ("2 dedicated non-prod GPUs", "Rented H100 hours for model bake-offs",
  "Needed a few days a quarter, not continuously. Functional tests run against a small model."),
 ("2 dedicated training GPUs", "None",
  "Anomaly and prediction are classical ML and train on CPU. No LLM fine-tuning in phase 1."),
 ("N+1 per site (5 GPU)", "N+1 across the whole platform (3 GPU)",
  "One spare, not one per pool per site."),
]
for was, now, why in GIVE:
    print(f"  {was:28} -> {now}\n      {why}")

# --- platform + economics -----------------------------------------------
cpu = json.load(open("cpu.json"))
print("\n" + "="*78)
print("PLATFORM AND COST AT SINGLE SITE")
print(f"  CPU platform stays {cpu['total_vcpu']} vCPU / {cpu['total_ram_gb']:,} GB "
      f"- it was always sized for ONE site.")
print(f"  NOTE: the 14-GPU design implied two active sites, which would have doubled")
print(f"        the CPU platform to {cpu['total_vcpu']*2} vCPU and storage to "
      f"{cpu['storage_raw_gb']*2/1000:.1f} TB. That was not stated. Single site removes it.")
GPU_HR = 3.20
for n, lbl in ((14, "original"), (3, "constrained")):
    print(f"  {lbl:12} {n:>2} H100 @ ${GPU_HR}/GPU-hr = ${n*GPU_HR*8760/1e3:>6,.0f}k/year")
print(f"  saving: ${(14-3)*GPU_HR*8760/1e3:,.0f}k/year on GPU alone")

json.dump(dict(fleet=FLEET, frac_peak=frac_peak, frac_avg=frac_avg,
               f_peak=F_PEAK, f_avg=F_AVG,
               util={str(n): F_PEAK/n for n in (1,2,3)},
               headroom_n1=rfo_headroom(2), headroom_no_n1=rfo_headroom(3),
               scenarios=[(n,m,m<=H) for n,m in SCEN],
               gave_up=GIVE,
               cost_14=14*GPU_HR*8760, cost_3=3*GPU_HR*8760),
          open("three_gpu.json","w"), indent=1)
