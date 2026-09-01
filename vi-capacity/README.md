# Vi AI-NOC — capacity model

Dimensioning the Vi Network AI Platform — Fault Management and Change Management — as an
enterprise deployment: GPUs for the model estate, CPU/RAM/storage for everything else.

Serving capacity is **measured** with [GuideLLM](https://github.com/vllm-project/guidellm),
the vLLM project's SLO-aware benchmark harness. Demand is **derived** from the volumes the
IBM SNOC TSD states, and every value that is not in the document is marked `[PLAN]`.

Report: `../vi-ainoc-capacity-model.html`

## Result — v2, against the IBM SNOC TSD

Re-derived against the **IBM SNOC AI Use Cases TSD (20-08-26)**, which supersedes the
August one-slide: 15M alarms/day (not 10M), **H200 141GB** (not H100 80GB), a six-model
tiered estate, and the eight Change Management agents. CHM is pan-India at target with
Gujarat as Phase 1.

| | |
|---|---|
| Production GPU (LLM tiers) | **4 × H200 141GB** — 3 serving + 1 for N+1 |
| Peak demand, pan-India CHM | 2.40 usable-GPU (heavy 2.06, fast 0.16, mop 0.17) |
| Peak demand, Gujarat Phase 1 | 2.12 usable-GPU |
| Change Management share | 18% of tokens pan-India, 0.33 GPU — it adds tiers, not cards |
| TSD's own pool (§12) | 3 × H200 gpt-oss-120b + 1 × H200 E5, +1 non-prod |

**The total matches; the split does not.** An independent measured model lands on the
TSD's own 4 production H200. But the TSD allocates 3 of them to gpt-oss-120b and
dedicates 1 to E5, and the heavy tier alone needs 2.06 — so the stated posture
("latency-tolerant; 2 active for HA") has no headroom left:

| State | % of measured knee | Verdict |
|---|---|---|
| 3 cards healthy | 48% | comfortable |
| 2 active (the TSD's HA posture) | 72% | meets SLO, the 30% headroom policy is spent |
| 1 surviving | 145% | SLO breach at peak |

Two findings follow. **E5 is the slack**: a 0.7 GB encoder serving 1.4 queries/second sits
at 0.03% of a 141 GB card. Co-locate it with the fast tier and all four cards become
heavy-capable — same spend, three active at peak instead of two at the edge. And the §12
pool **allocates nodes for 2 of the 6 model tiers the TSD describes**: Gemma 4 26B (A4B),
Gemma 4 E4B, Llama 3.1 8B and the VLM have no allocation. Their weights co-reside in 107
of 141 GB, but compute does not — that is the one thing to test on the real card.

<details><summary>Earlier revisions</summary>

Sized to a **3-GPU constraint** against the August one-slide (10M alarms/day, H100 80GB);
before that, 14 GPUs across two sites. See `three_gpu.json` and §5 of the report.

| | |
|---|---|
| GPU fleet | 3 × H100 80GB — one shared pool, single site, N+1 |
| Peak-hour utilisation | 45.8% of capacity; 68.6% with one GPU down |
| Growth headroom | 1.57× RFO demand before a 4th GPU, N+1 kept |
| CPU platform | 488 vCPU / 4,768 GB RAM, ≈7 dual-socket nodes (RAM-bound), single site |
| Storage | 43.9 TB raw NVMe |
| Token demand | 268.5M/day (98B/year) |

Peak-hour demand across both workloads measures **1.373 GPU of work**. Three is not a
throughput number — two GPUs would meet the SLO — it is the smallest fleet where a GPU can
fail during the busiest hour and the platform still holds.

Two other findings survive the resize: 11 of the 13 platform components are sized by their
operational floor rather than by Vi's event rate, and RFO context length moves total demand
more than incident count does (6,000 tokens works, 9,640 is the ceiling).

### Two methods, cross-validated

| Method | GPU needed at peak |
|---|---|
| Additive (capacity fractions add across classes) | 1.321 |
| Measured directly on one shared pool | 1.373 |

They agree to within 3.8%. The additive method is the optimistic one, so every headroom
figure in `vi_3gpu.py` is derated by that difference.

</details>

## Files

| File | What it does |
|---|---|
| `extract_pdf.py` | Pulls text out of the TSD. The image's `cryptography` package is broken and panics rather than raising ImportError, so pypdf's own fallback never fires — this blocks the module so it does. |
| `vi_demand_v2.py` | **v2** — FM + CHM demand by model tier, at TSD volumes. `PHASE=guj` or `PHASE=national`. Writes `demand_v2_*.json`. |
| `sweep_h200.sh` | **v2** — 13-point GuideLLM sweep across the three model tiers, calibrated to H200. Writes `sweep-h200/*.json`. |
| `vi_fleet_v2.py` | **v2** — capacity per tier, fleet, and the comparison against the TSD's §12 pool. Writes `fleet_v2.json`. |
| `vi_demand.py` | Alarm funnel → token demand per workload and pool. Writes `demand.json`. |
| `vi_sweep.sh` | 11-point GuideLLM sweep, each workload class alone. Writes `sweep/*.json`. |
| `vi_sweep_shared.sh` | 5-point sweep of the **shared pool** — two `--data` sources in one run, so the scheduler sees genuinely mixed traffic. Writes `sweep-shared/*.json`. |
| `read_shared.py` | Folds the shared sweep in and picks its SLO knee. Writes `shared.json`. |
| `vi_3gpu.py` | Works backwards from the 3-GPU constraint: what it forces, headroom, and where each assumption breaks it. Writes `three_gpu.json`. |
| `vi_capacity.py` | Applies the SLO gate to the sweep, finds the knee, divides demand by it. Writes `capacity.json`. |
| `vi_cpu.py` | Per-component CPU/RAM/storage sizing with operational floors. Writes `cpu.json`. |
| `vi_sensitivity.py` | Moves each planning assumption, reports the effect on the fleet. Writes `sensitivity.json`. |

Run order (v2): `PHASE=guj vi_demand_v2.py` → `PHASE=national vi_demand_v2.py` →
`sweep_h200.sh` → `vi_fleet_v2.py`.

Run order (v1, H100 / August one-slide): `vi_demand.py` → `vi_sweep.sh` → `vi_capacity.py`
→ `vi_sweep_shared.sh` → `read_shared.py` → `vi_cpu.py` → `vi_sensitivity.py` → `vi_3gpu.py`.

## What was measured vs. modelled

**Measured by GuideLLM (real load generation, scheduling and statistics):** request rate,
end-to-end latency, TTFT, ITL, concurrency, and their percentile distributions.

**Supplied by the latency model:** the machine this ran on has no GPU, so the backend is
`guidellm mock-server` with TTFT and ITL pinned per operating point to published
gpt-oss-120b + vLLM figures for a single H100 80GB. The saturation point reproduces the
reported ~6,100 tok/s.

Two consequences worth knowing:

- The mock reports `usage.prompt_tokens` with its own tokenizer, so GuideLLM's
  `prompt_token_count` is not meaningful here. Throughput is therefore derived as measured
  req/s × the configured token shape. On a real backend vLLM reports true usage and the
  counters are used directly.
- `sweep/*.json` and `sweep-shared/*.json` have had their per-request records reduced to
  counts — the bodies were synthetic filler text, not signal.
- The mock applies one latency profile per run, so the shared-pool sweep establishes the
  *throughput* blend but not the *interaction* between long prefills and short interactive
  requests. Priority scheduling has to be validated on hardware — that is the single
  open question in the design.

## Reproducing against real hardware

```bash
vllm serve openai/gpt-oss-120b --port 8000 --max-model-len 32768

guidellm run \
  --backend kind=openai_http,target=http://localhost:8000,model=openai/gpt-oss-120b \
  --data "kind=synthetic_text,prompt_tokens=6000,prompt_tokens_stdev=1200,output_tokens=400,output_tokens_stdev=100" \
  --profile kind=concurrent,streams=8 \
  --override 'profile.streams' 1,2,4,8,16,32 \
  --constraint kind=max_duration,seconds=120 \
  --output kind=html,path=pool-a.html --output kind=json,path=pool-a.json

python vi_demand.py && python vi_capacity.py && python vi_3gpu.py
```

The test that matters most for a 3-GPU fleet is mixed traffic — pass two `--data` sources
in one run and check that interactive TTFT p95 holds under 1.5 s while long RFO prefills
share the GPU. If priority scheduling cannot hold it, the classes need separating again,
and that is a fourth GPU.

The entire fleet number rests on one measured quantity — tok/s per GPU at the SLO — and it
moves by a factor of three across plausible model, quantisation and context-length choices.
Run the sweep before the procurement, and again on every model change.

## Assumptions

**v2 takes its fixed values from the TSD** (marked `[TSD]` in `vi_demand_v2.py`): 15M
alarms/day and a 1M-node topology graph (§12); 52k batch per 5 minutes with a 500k burst
to clear in <180 s (§12); H200 141GB on vLLM with FP8/MXFP4 (§12, §3.7); the six-model
tiering (§3.4.6, §3.7, §6.8); eight CHM agents, Gujarat first (§6.8–6.13); quarterly /
bi-annual release documents (§5.1); max 5 concurrent changes per circle (§6.11).

CHM volumes are `[PLAN]`: 100 CRs/day for Gujarat scaling to 1,250 pan-India (Gujarat
taken as ~8% of the national network, so ~12.5×, not 22×), and a release drop of 12
documents for Gujarat / 150 national producing 15 MOPs each inside a 24-hour window.

v1 volumes were taken from the SoW one-slide data flow (17 Aug): ~2M cells, ~10M raw alarms/day,
~70% RAN-linked, KPIs ≈285 GB/day, logs ≈30 GB/day, ~9.2 TB logical storage.

Everything else — dedup survival rate, events per incident, the share of incidents earning
a generated RFO, token shapes, peak factor, utilisation target — is an engineering planning
assumption marked `[PLAN]` in `vi_demand.py` and moved one at a time in `vi_sensitivity.py`.
They are to be validated against Vi actuals in the data workshop.

With three GPUs and N+1 held, each of these breaks the fleet above:

| Assumption | Modelled | Ceiling |
|---|---|---|
| RFO context length | 6,000 tok | 9,640 tok |
| Actionable incidents per day | 35,000 | 54,900 |
| Share of incidents earning an RFO | 35% | 55% |
| Agent turns per RFO | 3 | 4.7 |

### Correction to the earlier revision

The 14-GPU design specified two active sites but reported a single-site CPU platform. Run
properly, two active sites would have needed **976 vCPU and 88 TB**, not 488 and 44. Going
single-site makes the published CPU and storage figures correct as they stand.
