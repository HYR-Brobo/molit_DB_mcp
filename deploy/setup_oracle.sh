#!/usr/bin/env bash
# Oracle Cloud 무료 VM(서울/춘천, Ubuntu)에 MCP 서버를 올리는 스크립트.
# 사용법 (VM 안에서):
#   sudo MOLIT_KEY='서비스키' MCP_TOKEN='16자 이상 비밀토큰' bash setup_oracle.sh
# 다시 실행하면 최신 코드로 업데이트됨.
set -euo pipefail

REPO="https://github.com/HYR-Brobo/molit_DB_mcp.git"
APP=/opt/molit-mcp
ENV_FILE=/etc/molit-mcp.env

[ "$(id -u)" = 0 ] || { echo "sudo로 실행해 주세요."; exit 1; }

# 0) 이 VM에서 국토부 서버에 닿는지 먼저 확인 (안 되면 이후 작업이 무의미)
echo "== 국토부 서버 연결 확인"
if curl -s -o /dev/null -m 10 "https://openapi.molit.go.kr/"; then
  echo "   https 연결 OK"
elif curl -s -o /dev/null -m 10 "http://openapi.molit.go.kr/"; then
  echo "   http 연결 OK"
else
  echo "   연결 실패: 이 VM에서도 국토부 서버가 막혀 있습니다. 여기서 중단합니다."; exit 1
fi

# 1) 패키지
apt-get update -y
apt-get install -y python3-venv git curl gpg debian-keyring debian-archive-keyring apt-transport-https
if ! command -v caddy >/dev/null; then
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi

# 2) 코드 + 가상환경
if [ -d "$APP/.git" ]; then git -C "$APP" pull --ff-only; else git clone "$REPO" "$APP"; fi
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"

# 3) 비밀값 (처음 한 번만 필요. 이미 있으면 새 값이 주어진 경우에만 덮어씀)
if [ -n "${MOLIT_KEY:-}" ] && [ -n "${MCP_TOKEN:-}" ]; then
  umask 077
  printf 'MOLIT_KEY=%s\nMCP_TOKEN=%s\n' "$MOLIT_KEY" "$MCP_TOKEN" > "$ENV_FILE"
elif [ ! -f "$ENV_FILE" ]; then
  echo "MOLIT_KEY, MCP_TOKEN을 같이 넘겨 주세요."; exit 1
fi

# 4) 서버 상시 실행 (재부팅해도 자동 시작)
cat > /etc/systemd/system/molit-mcp.service <<EOF
[Unit]
Description=MOLIT MCP server
After=network-online.target

[Service]
EnvironmentFile=$ENV_FILE
Environment=HOST=127.0.0.1 PORT=8000
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/python molit_mcp.py --web
Restart=always
DynamicUser=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now molit-mcp
systemctl restart molit-mcp

# 5) HTTPS 주소: 도메인 없이 공인IP로 sslip.io 주소를 쓰고, Caddy가 인증서를 자동 발급
PUBIP=$(curl -s -m 10 https://api.ipify.org)
DOMAIN="${PUBIP//./-}.sslip.io"
cat > /etc/caddy/Caddyfile <<EOF
$DOMAIN {
    reverse_proxy 127.0.0.1:8000
}
EOF

# Oracle Ubuntu 이미지는 OS 방화벽이 80/443을 막아 둠 → 열기
for p in 80 443; do
  iptables -C INPUT -p tcp --dport $p -j ACCEPT 2>/dev/null \
    || iptables -I INPUT 5 -p tcp --dport $p -j ACCEPT
done
command -v netfilter-persistent >/dev/null && netfilter-persistent save || true

systemctl restart caddy

echo
echo "== 완료"
echo "   커넥터 주소: https://$DOMAIN/mcp"
echo "   (Oracle 콘솔의 보안 목록에서 80·443 인바운드를 열어야 인증서 발급이 됩니다)"
echo "   상태 확인: systemctl status molit-mcp caddy"
