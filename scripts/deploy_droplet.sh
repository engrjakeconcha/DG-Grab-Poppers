#!/usr/bin/env bash
set -euo pipefail

DROPLET_HOST="${DROPLET_HOST:-root@157.230.194.50}"
APP_ROOT="${APP_ROOT:-/opt/daddygrab-super-app/app}"
SYSTEMD_UNIT="${SYSTEMD_UNIT:-daddygrab-bot.service}"

echo "Deploying Daddy Grab bot to ${DROPLET_HOST}:${APP_ROOT}"

ssh -o StrictHostKeyChecking=accept-new "${DROPLET_HOST}" "mkdir -p ${APP_ROOT}"
rsync -av --delete \
  --exclude '.git' \
  --exclude 'venv' \
  --exclude '__pycache__' \
  ./ "${DROPLET_HOST}:${APP_ROOT}/"

ssh "${DROPLET_HOST}" "
  python3 -m venv ${APP_ROOT}/venv &&
  ${APP_ROOT}/venv/bin/pip install --upgrade pip &&
  ${APP_ROOT}/venv/bin/pip install -r ${APP_ROOT}/requirements.txt &&
  cp ${APP_ROOT}/deploy/${SYSTEMD_UNIT} /etc/systemd/system/${SYSTEMD_UNIT} &&
  systemctl daemon-reload &&
  systemctl enable ${SYSTEMD_UNIT} &&
  systemctl restart ${SYSTEMD_UNIT} &&
  systemctl --no-pager --full status ${SYSTEMD_UNIT}
"
