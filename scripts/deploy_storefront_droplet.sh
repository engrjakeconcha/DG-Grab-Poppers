#!/usr/bin/env bash
set -euo pipefail

DROPLET_HOST="${DROPLET_HOST:-root@157.230.194.50}"
APP_ROOT="${APP_ROOT:-/opt/daddygrab-storefront/current}"
SERVICE_NAME="${SERVICE_NAME:-daddygrab-storefront-api.service}"
NGINX_SITE_NAME="${NGINX_SITE_NAME:-daddygrab-storefront}"
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-.env.storefront}"

echo "Deploying Daddy Grab storefront runtime to ${DROPLET_HOST}:${APP_ROOT}"

if [[ ! -f "${LOCAL_ENV_FILE}" ]]; then
  echo "Missing ${LOCAL_ENV_FILE}. Pull or create it before droplet deploy." >&2
  exit 1
fi

ssh -o StrictHostKeyChecking=accept-new "${DROPLET_HOST}" "
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y nginx nodejs npm rsync
  mkdir -p ${APP_ROOT}
"

rsync -av --delete \
  --exclude '.git' \
  --exclude '.vercel' \
  --exclude 'node_modules' \
  --exclude '__pycache__' \
  --exclude '.env' \
  --exclude '.env.storefront' \
  ./ "${DROPLET_HOST}:${APP_ROOT}/"

rsync -av "${LOCAL_ENV_FILE}" "${DROPLET_HOST}:${APP_ROOT}/.env"

ssh "${DROPLET_HOST}" "
  cd ${APP_ROOT} &&
  npm ci --omit=dev &&
  cp deploy/${SERVICE_NAME} /etc/systemd/system/${SERVICE_NAME} &&
  cp deploy/daddygrab-storefront-nginx.conf /etc/nginx/sites-available/${NGINX_SITE_NAME} &&
  ln -sf /etc/nginx/sites-available/${NGINX_SITE_NAME} /etc/nginx/sites-enabled/${NGINX_SITE_NAME} &&
  rm -f /etc/nginx/sites-enabled/default &&
  systemctl daemon-reload &&
  systemctl enable ${SERVICE_NAME} nginx &&
  nginx -t &&
  systemctl restart ${SERVICE_NAME} &&
  systemctl restart nginx &&
  systemctl --no-pager --full status ${SERVICE_NAME} | head -n 20 &&
  systemctl --no-pager --full status nginx | head -n 20
"
