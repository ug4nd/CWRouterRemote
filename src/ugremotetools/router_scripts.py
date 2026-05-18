from __future__ import annotations

import shlex


def q(value: str) -> str:
    return shlex.quote(str(value))


def detect_status_script() -> str:
    return r'''
echo "=== UGRemoteTools status ==="
echo "Package manager: $(command -v apk >/dev/null 2>&1 && echo apk || (command -v opkg >/dev/null 2>&1 && echo opkg || echo unknown))"
echo ""
echo "=== Tailscale ==="
/etc/init.d/tailscale status 2>/dev/null || true
tailscale status 2>/dev/null || true
echo "Tailscale IPv4: $(tailscale ip -4 2>/dev/null || true)"
echo ""
echo "=== Xray ==="
/etc/init.d/xray status 2>/dev/null || true
ps w | grep -i '[x]ray' || true
netstat -lntp 2>/dev/null | grep -E '12345|10808|10809' || true
echo ""
echo "=== DNS ==="
cat /tmp/resolv.conf.d/resolv.conf.auto 2>/dev/null || true
uci show dhcp.@dnsmasq[0] 2>/dev/null | grep -E 'noresolv|server' || true
echo ""
echo "=== Firewall ==="
(command -v fw4 >/dev/null 2>&1 && fw4 check) || true
uci show firewall 2>/dev/null | grep -E "Force-LAN-DNS|Block-LAN-WAN-UDP|tailscale|forwarding" || true
nft list chain inet fw4 xray_redirect_prerouting 2>/dev/null || true
echo ""
echo "=== Cron / rc.local ==="
crontab -l 2>/dev/null || true
echo ""
echo "=== rc.local ==="
cat /etc/rc.local 2>/dev/null || true
'''


def backup_script() -> str:
    return r'''
set -u
mkdir -p /etc/xray /etc/nftables.d
cp /etc/config/firewall /etc/config/firewall.working 2>/dev/null || true
cp /etc/config/network /etc/config/network.working 2>/dev/null || true
cp /etc/config/dhcp /etc/config/dhcp.working 2>/dev/null || true
cp /etc/xray/config.json /etc/xray/config.json.working 2>/dev/null || true
cp /etc/nftables.d/99-xray-redirect.nft /etc/nftables.d/99-xray-redirect.nft.working 2>/dev/null || true
cp /root/tailscale-wake-peer.sh /root/tailscale-wake-peer.sh.working 2>/dev/null || true
cp /root/tailscale-health.sh /root/tailscale-health.sh.working 2>/dev/null || true
cp /root/tailscale-daily-restart.sh /root/tailscale-daily-restart.sh.working 2>/dev/null || true
echo "Backups saved: firewall/network/dhcp/xray/nftables/tailscale scripts"
'''


def remove_v2raya_script() -> str:
    return r'''
set -u
/etc/init.d/v2raya stop 2>/dev/null || true
/etc/init.d/v2raya disable 2>/dev/null || true
ps w | grep -E '[x]ray.*v2raya' | awk '{print $1}' | xargs -r kill 2>/dev/null || true
killall v2raya 2>/dev/null || true
if command -v apk >/dev/null 2>&1; then
  apk del luci-app-v2raya v2raya 2>/dev/null || true
elif command -v opkg >/dev/null 2>&1; then
  opkg remove luci-app-v2raya v2raya 2>/dev/null || true
fi
rm -rf /etc/v2raya /var/etc/v2raya /usr/share/v2raya /var/log/v2raya
/etc/init.d/uhttpd restart 2>/dev/null || true
/etc/init.d/firewall restart 2>/dev/null || true
echo "v2rayA removed/disabled. xray-core was not removed."
'''


def install_base_script() -> str:
    return r'''
set -u
if command -v apk >/dev/null 2>&1; then
  echo "Detected apk"
  apk update || true
  apk add curl ca-bundle 2>/dev/null || true
elif command -v opkg >/dev/null 2>&1; then
  echo "Detected opkg"
  opkg update || true
  opkg install curl ca-bundle 2>/dev/null || true
else
  echo "No apk/opkg found; skipping package install"
fi
'''



def install_tailscale_script(auth_key: str = "") -> str:
    return f'''
set -u
AUTH_KEY={q(auth_key)}

echo "Installing Tailscale package if needed..."
if command -v apk >/dev/null 2>&1; then
  echo "Detected apk"
  apk update || true
  apk add tailscale ca-bundle curl 2>/dev/null || apk add tailscale 2>/dev/null || true
elif command -v opkg >/dev/null 2>&1; then
  echo "Detected opkg"
  opkg update || true
  opkg install tailscale ca-bundle curl 2>/dev/null || opkg install tailscale 2>/dev/null || true
else
  echo "No apk/opkg found; cannot auto-install Tailscale package"
fi

if ! command -v tailscale >/dev/null 2>&1; then
  echo "ERROR: tailscale command not found after install attempt"
  exit 1
fi

/etc/init.d/tailscale enable 2>/dev/null || true
/etc/init.d/tailscale start 2>/dev/null || /etc/init.d/tailscale restart 2>/dev/null || true
sleep 5

uci set network.tailscale=interface
uci set network.tailscale.proto='none'
uci set network.tailscale.device='tailscale0'
uci commit network

FIRST=""
for IDX in $(uci show firewall | sed -n "s/firewall\.@zone\[\([0-9]*\)\]\.name='tailscale'/\1/p"); do
  if [ -z "$FIRST" ]; then
    FIRST="$IDX"
  else
    uci delete firewall.@zone[$IDX]
  fi
done

if [ -z "$FIRST" ]; then
  uci add firewall zone
  ZONE='@zone[-1]'
else
  ZONE="@zone[$FIRST]"
fi

uci set firewall.$ZONE.name='tailscale'
uci set firewall.$ZONE.input='ACCEPT'
uci set firewall.$ZONE.output='ACCEPT'
uci set firewall.$ZONE.forward='ACCEPT'
uci -q delete firewall.$ZONE.network
uci -q delete firewall.$ZONE.device
uci add_list firewall.$ZONE.network='tailscale'
uci add_list firewall.$ZONE.device='tailscale0'
uci commit firewall

/etc/init.d/network reload 2>/dev/null || true
if command -v fw4 >/dev/null 2>&1; then
  fw4 check || exit 1
fi
/etc/init.d/firewall restart

if [ -n "$AUTH_KEY" ]; then
  echo "Connecting Tailscale using auth key..."
  HOSTNAME="$(uci -q get system.@system[0].hostname)"
  [ -z "$HOSTNAME" ] && HOSTNAME="$(hostname)"
  [ -z "$HOSTNAME" ] && HOSTNAME="openwrt"
  tailscale up --authkey "$AUTH_KEY" --accept-dns=false --shields-up=false --hostname="$HOSTNAME" >/tmp/ugremote-tailscale-auth.log 2>&1 || {{
    echo "ERROR: tailscale up with auth key failed"
    cat /tmp/ugremote-tailscale-auth.log 2>/dev/null || true
    exit 1
  }}
else
  echo "No auth key supplied. Applying prefs to existing Tailscale login..."
  tailscale set --shields-up=false --accept-dns=false >/tmp/ugremote-tailscale-set.log 2>&1 || {{
    HOSTNAME="$(uci -q get system.@system[0].hostname)"
    [ -z "$HOSTNAME" ] && HOSTNAME="$(hostname)"
    [ -z "$HOSTNAME" ] && HOSTNAME="openwrt"
    tailscale up --accept-dns=false --shields-up=false --hostname="$HOSTNAME" >/tmp/ugremote-tailscale-up.log 2>&1 || true
  }}
fi

sleep 3
TS_IP="$(tailscale ip -4 2>/dev/null || true)"
if [ -z "$TS_IP" ]; then
  echo "WARNING: Tailscale has no IPv4 yet. If this is first setup, check auth key or Tailscale admin console."
else
  echo "Tailscale IPv4: $TS_IP"
fi

tailscale status 2>/dev/null || true
'''

def dns_script(lan_ip: str, dns1: str, dns2: str, dns3: str) -> str:
    return f'''
set -u
LAN_IP={q(lan_ip)}
DNS1={q(dns1)}
DNS2={q(dns2)}
DNS3={q(dns3)}

echo "Configuring WAN DNS: $DNS1 $DNS2 $DNS3"
uci set network.wan.peerdns='0'
uci -q delete network.wan.dns
uci add_list network.wan.dns="$DNS1"
uci add_list network.wan.dns="$DNS2"
uci add_list network.wan.dns="$DNS3"
uci commit network

uci set dhcp.@dnsmasq[0].noresolv='1'
uci -q delete dhcp.@dnsmasq[0].server
uci add_list dhcp.@dnsmasq[0].server="$DNS1"
uci add_list dhcp.@dnsmasq[0].server="$DNS2"
uci add_list dhcp.@dnsmasq[0].server="$DNS3"
uci commit dhcp
/etc/init.d/dnsmasq restart || true

while uci show firewall | grep -q "name='Force-LAN-DNS'"; do
  IDX="$(uci show firewall | grep "name='Force-LAN-DNS'" | head -n1 | sed -n "s/firewall\.@redirect\[\([0-9]*\)\].*/\1/p")"
  [ -z "$IDX" ] && break
  uci delete firewall.@redirect[$IDX]
done

uci add firewall redirect
uci set firewall.@redirect[-1].name='Force-LAN-DNS'
uci set firewall.@redirect[-1].src='lan'
uci set firewall.@redirect[-1].dest='lan'
uci set firewall.@redirect[-1].proto='tcp udp'
uci set firewall.@redirect[-1].src_dport='53'
uci set firewall.@redirect[-1].dest_ip="$LAN_IP"
uci set firewall.@redirect[-1].dest_port='53'
uci set firewall.@redirect[-1].target='DNAT'
uci commit firewall

if command -v fw4 >/dev/null 2>&1; then
  fw4 check || exit 1
fi
/etc/init.d/firewall restart

echo "DNS configured. resolv.conf.auto:"
cat /tmp/resolv.conf.d/resolv.conf.auto 2>/dev/null || true
'''


def tailscale_zone_script() -> str:
    return r'''
set -u
uci set network.tailscale=interface
uci set network.tailscale.proto='none'
uci set network.tailscale.device='tailscale0'
uci commit network

FIRST=""
for IDX in $(uci show firewall | sed -n "s/firewall\.@zone\[\([0-9]*\)\]\.name='tailscale'/\1/p"); do
  if [ -z "$FIRST" ]; then
    FIRST="$IDX"
  else
    uci delete firewall.@zone[$IDX]
  fi
done

if [ -z "$FIRST" ]; then
  uci add firewall zone
  ZONE='@zone[-1]'
else
  ZONE="@zone[$FIRST]"
fi

uci set firewall.$ZONE.name='tailscale'
uci set firewall.$ZONE.input='ACCEPT'
uci set firewall.$ZONE.output='ACCEPT'
uci set firewall.$ZONE.forward='ACCEPT'
uci -q delete firewall.$ZONE.network
uci -q delete firewall.$ZONE.device
uci add_list firewall.$ZONE.network='tailscale'
uci add_list firewall.$ZONE.device='tailscale0'
uci commit firewall

/etc/init.d/network reload 2>/dev/null || true
if command -v fw4 >/dev/null 2>&1; then
  fw4 check || exit 1
fi
/etc/init.d/firewall restart
/etc/init.d/tailscale enable 2>/dev/null || true
/etc/init.d/tailscale restart 2>/dev/null || true
sleep 5
HOSTNAME="$(uci -q get system.@system[0].hostname)"
[ -z "$HOSTNAME" ] && HOSTNAME="$(hostname)"
[ -z "$HOSTNAME" ] && HOSTNAME="openwrt"
tailscale set --shields-up=false --accept-dns=false 2>/tmp/ugremote-tailscale-set.log || tailscale up --accept-dns=false --shields-up=false --hostname="$HOSTNAME" 2>/tmp/ugremote-tailscale-up.log || true

echo "Tailscale zone configured"
tailscale status 2>/dev/null || true
'''


def redirect_and_udp_block_script(vless_server_ip: str, xray_port: int = 12345, block_udp: bool = True) -> str:
    server_line = f"    {vless_server_ip}/32,\n" if vless_server_ip.strip() else ""
    block_part = r'''
while uci show firewall | grep -q "name='Block-LAN-WAN-UDP'"; do
  IDX="$(uci show firewall | grep "name='Block-LAN-WAN-UDP'" | head -n1 | sed -n "s/firewall\.@rule\[\([0-9]*\)\].*/\1/p")"
  [ -z "$IDX" ] && break
  uci delete firewall.@rule[$IDX]
done

uci add firewall rule
uci set firewall.@rule[-1].name='Block-LAN-WAN-UDP'
uci set firewall.@rule[-1].src='lan'
uci set firewall.@rule[-1].dest='wan'
uci set firewall.@rule[-1].proto='udp'
uci set firewall.@rule[-1].target='REJECT'
uci commit firewall
''' if block_udp else r'''
while uci show firewall | grep -q "name='Block-LAN-WAN-UDP'"; do
  IDX="$(uci show firewall | grep "name='Block-LAN-WAN-UDP'" | head -n1 | sed -n "s/firewall\.@rule\[\([0-9]*\)\].*/\1/p")"
  [ -z "$IDX" ] && break
  uci delete firewall.@rule[$IDX]
done
uci commit firewall
'''
    return f'''
set -u
mkdir -p /etc/nftables.d
cat > /etc/nftables.d/99-xray-redirect.nft << 'EOF2'
set xray_bypass_v4 {{
  type ipv4_addr
  flags interval
  elements = {{
    0.0.0.0/8,
    10.0.0.0/8,
{server_line}    100.64.0.0/10,
    127.0.0.0/8,
    169.254.0.0/16,
    172.16.0.0/12,
    192.168.0.0/16,
    224.0.0.0/4,
    240.0.0.0/4
  }}
}}

chain xray_redirect_prerouting {{
  type nat hook prerouting priority dstnat; policy accept;

  iifname "br-lan" ip daddr @xray_bypass_v4 return;

  iifname "br-lan" meta l4proto tcp redirect to :{int(xray_port)};
}}
EOF2

{block_part}
if command -v fw4 >/dev/null 2>&1; then
  fw4 check || exit 1
else
  echo "WARNING: fw4 not found. /etc/nftables.d redirect requires OpenWrt fw4/nftables."
fi
/etc/init.d/firewall restart
cp /etc/nftables.d/99-xray-redirect.nft /etc/nftables.d/99-xray-redirect.nft.working 2>/dev/null || true
cp /etc/config/firewall /etc/config/firewall.working 2>/dev/null || true
nft list chain inet fw4 xray_redirect_prerouting 2>/dev/null || true
uci show firewall 2>/dev/null | grep Block-LAN-WAN-UDP || true
'''


def cron_tailscale_script(peer_ip: str = "100.77.73.23", delay_seconds: int = 90) -> str:
    peer = q(peer_ip)
    delay = int(delay_seconds)
    return f"""
set -u
PEER_IP={peer}
DELAY={delay}

cat > /root/tailscale-wake-peer.sh << EOF2
#!/bin/sh
PEER_IP={peer}
DELAY={delay}
logger -t tailscale-wake "Startup wake script started, waiting ${{DELAY}}s"
sleep "$DELAY"
/etc/init.d/tailscale enable >/dev/null 2>&1
/etc/init.d/tailscale start >/dev/null 2>&1
HOSTNAME="$(uci -q get system.@system[0].hostname)"
[ -z "$HOSTNAME" ] && HOSTNAME="$(hostname)"
[ -z "$HOSTNAME" ] && HOSTNAME="openwrt"
tailscale set --shields-up=false --accept-dns=false >/tmp/tailscale-wake-set.log 2>&1
if [ "$?" -ne 0 ]; then
  tailscale up --accept-dns=false --shields-up=false --hostname="$HOSTNAME" >/tmp/tailscale-wake-up.log 2>&1
fi
i=1
while [ "$i" -le 12 ]; do
  logger -t tailscale-wake "Wake ping to $PEER_IP attempt $i"
  tailscale ping "$PEER_IP" >/tmp/tailscale-wake-peer.log 2>&1
  if [ "$?" -eq 0 ]; then
    logger -t tailscale-wake "Peer $PEER_IP reachable"
    exit 0
  fi
  sleep 10
  i=$((i + 1))
done
logger -t tailscale-wake "Peer $PEER_IP not reachable after wake attempts"
exit 1
EOF2
chmod +x /root/tailscale-wake-peer.sh

cat > /root/tailscale-health.sh << EOF2
#!/bin/sh
LOCKDIR="/tmp/tailscale-health.lock"
PEER_IP={peer}
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT
HOSTNAME="$(uci -q get system.@system[0].hostname)"
[ -z "$HOSTNAME" ] && HOSTNAME="$(hostname)"
[ -z "$HOSTNAME" ] && HOSTNAME="openwrt"
log() {{ logger -t tailscale-health "$*"; }}
wake_peer() {{
  if [ -n "$PEER_IP" ]; then
    log "Wake ping to peer $PEER_IP"
    tailscale ping "$PEER_IP" >/tmp/tailscale-health-peer-ping.log 2>&1
  fi
}}
ensure_up() {{
  /etc/init.d/tailscale enable >/dev/null 2>&1
  /etc/init.d/tailscale start >/dev/null 2>&1
  sleep 10
  tailscale set --shields-up=false --accept-dns=false >/tmp/tailscale-health-set.log 2>&1
  if [ "$?" -ne 0 ]; then
    tailscale up --accept-dns=false --shields-up=false --hostname="$HOSTNAME" >/tmp/tailscale-health-up.log 2>&1
  fi
  sleep 5
  wake_peer
}}
TS_IP="$(tailscale ip -4 2>/dev/null)"
if [ -z "$TS_IP" ]; then
  log "No Tailscale IP. Restarting."
  /etc/init.d/tailscale restart >/tmp/tailscale-health-restart.log 2>&1
  sleep 20
  ensure_up
  TS_IP_AFTER="$(tailscale ip -4 2>/dev/null)"
  if [ -z "$TS_IP_AFTER" ]; then
    log "Still no Tailscale IP after restart."
    exit 1
  fi
  log "Recovered Tailscale IP: $TS_IP_AFTER"
  exit 0
fi
tailscale status 2>/dev/null | grep -q "offline"
if [ "$?" -eq 0 ]; then
  log "Tailscale status contains offline. Restarting."
  /etc/init.d/tailscale restart >/tmp/tailscale-health-restart.log 2>&1
  sleep 20
  ensure_up
  exit 0
fi
/etc/init.d/tailscale status >/dev/null 2>&1
if [ "$?" -ne 0 ]; then
  log "Tailscale service is not running. Starting."
  ensure_up
  exit 0
fi
wake_peer
exit 0
EOF2
chmod +x /root/tailscale-health.sh

cat > /root/tailscale-daily-restart.sh << EOF2
#!/bin/sh
LOCKDIR="/tmp/tailscale-daily.lock"
PEER_IP={peer}
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT
HOSTNAME="$(uci -q get system.@system[0].hostname)"
[ -z "$HOSTNAME" ] && HOSTNAME="$(hostname)"
[ -z "$HOSTNAME" ] && HOSTNAME="openwrt"
logger -t tailscale-daily "Daily Tailscale restart started."
/etc/init.d/tailscale restart >/tmp/tailscale-daily-restart.log 2>&1
sleep 20
tailscale set --shields-up=false --accept-dns=false >/tmp/tailscale-daily-set.log 2>&1
if [ "$?" -ne 0 ]; then
  tailscale up --accept-dns=false --shields-up=false --hostname="$HOSTNAME" >/tmp/tailscale-daily-up.log 2>&1
fi
sleep 5
if [ -n "$PEER_IP" ]; then
  logger -t tailscale-daily "Wake ping to peer $PEER_IP"
  tailscale ping "$PEER_IP" >/tmp/tailscale-daily-peer-ping.log 2>&1
fi
TS_IP="$(tailscale ip -4 2>/dev/null)"
if [ -z "$TS_IP" ]; then
  logger -t tailscale-daily "No Tailscale IP after daily restart."
  exit 1
fi
logger -t tailscale-daily "Daily Tailscale restart OK. IP: $TS_IP"
exit 0
EOF2
chmod +x /root/tailscale-daily-restart.sh

if [ -f /etc/rc.local ]; then
  cp /etc/rc.local /etc/rc.local.ugremote-backup 2>/dev/null || true
fi
cat > /etc/rc.local << 'EOF2'
/root/tailscale-wake-peer.sh &

exit 0
EOF2
chmod +x /etc/rc.local

touch /etc/crontabs/root
sed -i '/check-tailscale.sh/d' /etc/crontabs/root
sed -i '/check-firewall.sh/d' /etc/crontabs/root
sed -i '/tailscale-health.sh/d' /etc/crontabs/root
sed -i '/tailscale-daily-restart.sh/d' /etc/crontabs/root
sed -i '/tailscale-wake-peer.sh/d' /etc/crontabs/root
sed -i '/router-reboot-startup.sh/d' /etc/crontabs/root
echo "*/5 * * * * /root/tailscale-health.sh" >> /etc/crontabs/root
echo "0 12 * * * /root/tailscale-daily-restart.sh" >> /etc/crontabs/root
/etc/init.d/cron enable
/etc/init.d/cron restart

echo "Tailscale cron/rc.local configured. Peer wake IP: $PEER_IP, delay: $DELAY seconds"
echo "--- crontab ---"
crontab -l
echo "--- rc.local ---"
cat /etc/rc.local
"""


def install_xray_script() -> str:
    return r'''
set -u
if command -v xray >/dev/null 2>&1; then
  echo "xray already installed: $(command -v xray)"
  xray version 2>/dev/null || true
else
  if command -v apk >/dev/null 2>&1; then
    echo "Detected apk"
    apk update || true
    apk add xray-core ca-bundle curl 2>/dev/null || apk add xray-core 2>/dev/null || true
  elif command -v opkg >/dev/null 2>&1; then
    echo "Detected opkg"
    opkg update || true
    opkg install xray-core ca-bundle curl 2>/dev/null || opkg install xray-core 2>/dev/null || true
  else
    echo "ERROR: no apk/opkg package manager found"
    exit 1
  fi
fi
if ! command -v xray >/dev/null 2>&1; then
  echo "ERROR: xray command not found after install attempt"
  exit 1
fi
mkdir -p /etc/xray
if [ ! -f /etc/config/xray ]; then
  cat > /etc/config/xray << 'EOF2'
config xray 'enabled'
	option enabled '1'

config xray 'config'
	option confdir '/etc/xray'
	list conffiles '/etc/xray/config.json'
	option datadir '/usr/share/xray'
	option dialer ''
	option format 'json'
EOF2
else
  uci set xray.enabled.enabled='1' 2>/dev/null || true
  uci commit xray 2>/dev/null || true
fi
/etc/init.d/xray enable 2>/dev/null || true
xray version 2>/dev/null || true
echo "xray-core install/check completed"
'''
