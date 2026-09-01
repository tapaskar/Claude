#!/usr/bin/env bash
# GuideLLM capacity sweep for the Vi AI-NOC LLM tier.
#
# Each operating point runs guidellm against a mock OpenAI/vLLM backend whose
# TTFT/ITL are pinned to the published gpt-oss-120b + vLLM figures for 1x H100
# 80GB at that concurrency and token shape. GuideLLM does the load generation,
# scheduling and statistics; the mock supplies the latency model.
#
# Pool A = GenAI RFO agent   (6000 in / 400 out) - throughput class
# Pool B = Action+Interface  (2000 in / 400 out) - interactive class

set -u
cd "$(dirname "$0")"
export no_proxy="127.0.0.1,localhost" NO_PROXY="127.0.0.1,localhost"
TOK="$PWD/vi-tok"
OUT="$PWD/sweep"
mkdir -p "$OUT"
PORT=8111

run_point () {
  local pool=$1 conc=$2 ttft=$3 itl=$4 pin=$5 pout=$6
  local tag="${pool}_c${conc}"
  PORT=$((PORT+1))

  guidellm mock-server --host 127.0.0.1 --port $PORT --model "vi-${pool}" \
      --ttft-ms "$ttft"  --ttft-ms-std "$(python3 -c "print(round($ttft*0.15,2))")" \
      --itl-ms  "$itl"   --itl-ms-std  "$(python3 -c "print(round($itl*0.15,3))")" \
      --output-tokens "$pout" > "$OUT/mock_${tag}.log" 2>&1 &
  local mpid=$!
  sleep 9

  echo ">>> $tag  (ttft=${ttft}ms itl=${itl}ms  ${pin}in/${pout}out)"
  timeout 240 guidellm run \
    --backend "kind=openai_http,target=http://127.0.0.1:$PORT,model=vi-${pool}" \
    --data "kind=synthetic_text,prompt_tokens=${pin},prompt_tokens_stdev=$((pin/5)),output_tokens=${pout},output_tokens_stdev=$((pout/4))" \
    --tokenizer "kind=huggingface_auto,model=$TOK" \
    --profile "kind=concurrent,streams=${conc}" \
    --constraint "kind=max_requests,count=$((conc*5+15))" \
    --constraint "kind=max_duration,seconds=70" \
    --label "pool=${pool}" --label "concurrency=${conc}" \
    --disable-progress --disable-console \
    --output "kind=json,path=$OUT/${tag}.json" > "$OUT/run_${tag}.log" 2>&1

  echo "    exit=$?  -> $OUT/${tag}.json"
  kill $mpid 2>/dev/null; wait $mpid 2>/dev/null
  sleep 1
}

# ---- Pool A: GenAI RFO agent, 6000 in / 400 out -----------------------------
run_point A 1   620    7.0  6000 400
run_point A 2   700    7.3  6000 400
run_point A 4  1100    8.9  6000 400
run_point A 8  4000   11.0  6000 400
run_point A 16 9000   19.5  6000 400
run_point A 32 18000  39.0  6000 400

# ---- Pool B: Action & Interface / operator chat, 2000 in / 400 out ----------
run_point B 1   210    7.0  2000 400
run_point B 4   400    8.5  2000 400
run_point B 8   750   10.5  2000 400
run_point B 16 1400   15.0  2000 400
run_point B 32 2900   26.0  2000 400

echo "SWEEP COMPLETE"
