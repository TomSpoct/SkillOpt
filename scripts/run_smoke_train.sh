#!/usr/bin/env bash
# SkillOpt price-watch smoke training run — 1 epoch, batch 4.
# Launches from the skillopt-pricewatch repo with ARK backend env vars.
set -euo pipefail
cd /home/tom/workspaces/emma/skillopt-pricewatch
export OPENAI_COMPATIBLE_BASE_URL="https://ark.cn-beijing.volces.com/api/plan/v3"
export OPENAI_COMPATIBLE_API_KEY="${HERMES_ARK_API_KEY}"
export OPENAI_COMPATIBLE_MODEL="deepseek-v4-flash"
exec .venv/bin/python scripts/train.py \
  --config configs/pricewatch/default.yaml \
  --cfg-options \
    train.batch_size=4 \
    train.num_epochs=1 \
    gradient.minibatch_size=2 \
    gradient.merge_batch_size=2 \
    optimizer.learning_rate=2 \
    evaluation.sel_env_num=0 \
    evaluation.test_env_num=0
