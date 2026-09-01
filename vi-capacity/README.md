# Vi AI-NOC — capacity model

Dimensioning the five-agent RAN fault-management platform (~2M cells, ~10M alarms/day)
as an enterprise deployment: GPUs for the LLM tier, CPU/RAM/storage for everything else.

Serving capacity is **measured** with [GuideLLM](https://github.com/vllm-project/guidellm),
the vLLM project's SLO-aware benchmark harness. Demand is **derived** from the SoW volumes
and is a set of stated assumptions, each stress-tested in the sensitivity model.

Report: `../vi-ainoc-capacity-model.html`

## Result

| | |
|---|---|
| GPU fleet | 14 × H100 80GB (10 production over 2 sites, 2 non-prod, 2 training) |
| Serving GPUs at peak | 3 |
| CPU platform | 488 vCPU / 4,768 GB RAM, ≈7 dual-socket nodes (RAM-bound) |
| Storage | 43.9 TB raw NVMe |
| Token demand | 268.5M/day (98B/year) |

The headline: peak demand needs about two GPUs of serving. The rest of the fleet is HA,
DR, eval and training. 11 of the 13 platform components are sized by their operational
floor rather than by Vi's event rate.

## Files

| File | What it does |
|---|---|
| `vi_demand.py` | Alarm funnel → token demand per workload and pool. Writes `demand.json`. |
| `vi_sweep.sh` | Runs the 11-point GuideLLM sweep (2 pools × concurrency). Writes `sweep/*.json`. |
| `vi_capacity.py` | Applies the SLO gate to the sweep, finds the knee, divides demand by it. Writes `capacity.json`. |
| `vi_cpu.py` | Per-component CPU/RAM/storage sizing with operational floors. Writes `cpu.json`. |
| `vi_sensitivity.py` | Moves each planning assumption, reports the effect on the fleet. Writes `sensitivity.json`. |

Run order: `vi_demand.py` → `vi_sweep.sh` → `vi_capacity.py` → `vi_cpu.py` → `vi_sensitivity.py`.

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
- `sweep/*.json` has had its per-request records reduced to counts — the bodies were
  synthetic filler text, not signal.

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

python vi_demand.py && python vi_capacity.py && python vi_sensitivity.py
```

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
