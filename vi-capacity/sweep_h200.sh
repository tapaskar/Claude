#!/usr/bin/env bash
# H200 sweeps for the three model tiers the TSD names (section 3.7 + section 12).
#
# H200 vs H100: 141 GB HBM3e at 4.8 TB/s against 80 GB at 3.35 TB/s, same compute.
# Decode is bandwidth-bound so ITL improves ~1.43x; prefill is compute-bound so TTFT
# is held flat (conservative). Per-point values are the measured H100 curve rescaled
# on that basis, plus published figures for the smaller tiers.
set -u
cd "$(dirname "$0")"
export no_proxy="127.0.0.1,localhost" NO_PROXY="127.0.0.1,localhost"
TOK="$PWD/vi-tok"
OUT="$PWD/sweep-h200"
mkdir -p "$OUT"
PORT=8500

run () {
  local tier=$1 conc=$2 ttft=$3 itl=$4 pin=$5 pout=$6
  PORT=$((PORT+1))
  setsid guidellm mock-server --host 127.0.0.1 --port $PORT --model "vi-$tier" \
    --ttft-ms "$ttft" --ttft-ms-std "$(python3 -c "print(round($ttft*0.15,2))")" \
    --itl-ms "$itl" --itl-ms-std "$(python3 -c "print(round($itl*0.15,3))")" \
    --output-tokens "$pout" > "$OUT/mock_${tier}_c${conc}.log" 2>&1 < /dev/null &
  local mpid=$!
  sleep 9
  echo ">>> ${tier} c${conc} (ttft=${ttft} itl=${itl} ${pin}/${pout})"
  timeout 240 guidellm run \
    --backend "kind=openai_http,target=http://127.0.0.1:$PORT,model=vi-$tier" \
    --data "kind=synthetic_text,prompt_tokens=${pin},prompt_tokens_stdev=$((pin/5)),output_tokens=${pout},output_tokens_stdev=$((pout/4))" \
    --tokenizer "kind=huggingface_auto,model=$TOK" \
    --profile "kind=concurrent,streams=${conc}" \
    --constraint "kind=max_requests,count=$((conc*4+12))" \
    --constraint "kind=max_duration,seconds=60" \
    --label "tier=${tier}" --label "concurrency=${conc}" \
    --disable-progress --disable-console \
    --output "kind=json,path=$OUT/${tier}_c${conc}.json" > "$OUT/run_${tier}_c${conc}.log" 2>&1
  echo "    exit=$?"
  kill $mpid 2>/dev/null
  sleep 1
}

# heavy tier - gpt-oss-120b MXFP4, RFO / agentic reasoning shape
run heavy 1    620  4.9  6000 400
run heavy 4   1100  6.2  6000 400
run heavy 8   4000  7.7  6000 400
run heavy 16  9000 13.6  6000 400
run heavy 32 18000 27.3  6000 400

# fast tier - Gemma-4-26B A4B FP8, extraction / classification / notification shape
run fast 1     60  3.0  1500 200
run fast 8    260  3.6  1500 200
run fast 32   900  6.5  1500 200
run fast 64  1800 11.0  1500 200

# MOP tier - Llama 3.1 8B AWQ, long-output document generation
run mop 1     700  4.5 12000 2500
run mop 8    2400  6.0 12000 2500
run mop 16   4200  8.5 12000 2500
run mop 32   7800 14.0 12000 2500

echo "H200 SWEEP COMPLETE"
