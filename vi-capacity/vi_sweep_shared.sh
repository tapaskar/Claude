#!/usr/bin/env bash
# Shared-pool sweep: one vLLM deployment serving BOTH workloads.
#
# Traffic is genuinely mixed - two --data sources in one guidellm run, so the
# scheduler sees the real 78/22 blend of long RFO prompts and short interactive
# ones rather than an averaged stand-in. The mock's TTFT/ITL per operating point
# are the measured pool-A curve scaled by the blended prefill ratio (5,265/6,000).
set -u
cd "$(dirname "$0")"
export no_proxy="127.0.0.1,localhost" NO_PROXY="127.0.0.1,localhost"
TOK="$PWD/vi-tok"; OUT="$PWD/sweep-shared"; mkdir -p "$OUT"
PORT=8400

run () {
  local conc=$1 ttft=$2 itl=$3
  PORT=$((PORT+1))
  setsid guidellm mock-server --host 127.0.0.1 --port $PORT --model vi-shared \
    --ttft-ms "$ttft" --ttft-ms-std "$(python3 -c "print(round($ttft*0.15,2))")" \
    --itl-ms "$itl"   --itl-ms-std  "$(python3 -c "print(round($itl*0.15,3))")" \
    --output-tokens 415 > "$OUT/mock_c${conc}.log" 2>&1 < /dev/null &
  local mpid=$!
  sleep 10
  echo ">>> shared c${conc} (ttft=${ttft} itl=${itl})"
  timeout 260 guidellm run \
    --backend "kind=openai_http,target=http://127.0.0.1:$PORT,model=vi-shared" \
    --data "kind=synthetic_text,prompt_tokens=6000,prompt_tokens_stdev=1200,output_tokens=400,output_tokens_stdev=100" \
    --data "kind=synthetic_text,prompt_tokens=2700,prompt_tokens_stdev=900,output_tokens=466,output_tokens_stdev=120" \
    --tokenizer "kind=huggingface_auto,model=$TOK" \
    --profile "kind=concurrent,streams=${conc}" \
    --constraint "kind=max_requests,count=$((conc*5+15))" \
    --constraint "kind=max_duration,seconds=70" \
    --label "pool=shared" --label "concurrency=${conc}" \
    --disable-progress --disable-console \
    --output "kind=json,path=$OUT/S_c${conc}.json" > "$OUT/run_c${conc}.log" 2>&1
  echo "    exit=$?"
  kill $mpid 2>/dev/null; sleep 1
}

run 1     545   6.9
run 4     966   8.7
run 8    3512  10.8
run 16   7902  19.1
run 32  15804  38.2
echo "SHARED SWEEP COMPLETE"
