# Vi AI-NOC — capacity model

Dimensioning the five-agent RAN fault-management platform (~2M cells, ~10M alarms/day)
as an enterprise deployment: GPUs for the LLM tier, CPU/RAM/storage for everything else.

Serving capacity is **measured** with [GuideLLM](https://github.com/vllm-project/guidellm),
the vLLM project's SLO-aware benchmark harness. Demand is **derived** from the SoW volumes
and is a set of stated assumptions, each stress-tested in the sensitivity model.

Report: `../vi-ainoc-capacity-model.html`

## Result

Sized to a **3-GPU constraint**. (An earlier revision specified 14 with two sites; see
`three_gpu.json` and §5 of the report for exactly what the descope trades away.)

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

## Files

| File | What it does |
|---|---|
| `vi_demand.py` | Alarm funnel → token demand per workload and pool. Writes `demand.json`. |
| `vi_sweep.sh` | 11-point GuideLLM sweep, each workload class alone. Writes `sweep/*.json`. |
| `vi_sweep_shared.sh` | 5-point sweep of the **shared pool** — two `--data` sources in one run, so the scheduler sees genuinely mixed traffic. Writes `sweep-shared/*.json`. |
| `read_shared.py` | Folds the shared sweep in and picks its SLO knee. Writes `shared.json`. |
| `vi_3gpu.py` | Works backwards from the 3-GPU constraint: what it forces, headroom, and where each assumption breaks it. Writes `three_gpu.json`. |
| `vi_capacity.py` | Applies the SLO gate to the sweep, finds the knee, divides demand by it. Writes `capacity.json`. |
| `vi_cpu.py` | Per-component CPU/RAM/storage sizing with operational floors. Writes `cpu.json`. |
| `vi_sensitivity.py` | Moves each planning assumption, reports the effect on the fleet. Writes `sensitivity.json`. |

Run order: `vi_demand.py` → `vi_sweep.sh` → `vi_capacity.py` → `vi_sweep_shared.sh` →
`read_shared.py` → `vi_cpu.py` → `vi_sensitivity.py` → `vi_3gpu.py`.

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

Volumes taken from the SoW one-slide data flow (17 Aug): ~2M cells, ~10M raw alarms/day,
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
