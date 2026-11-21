#!/usr/bin/env bash
# Τρέχει στον Proxmox host: install-lxc.sh [--auto|--install|--update|--pack] [thilek-vX.Y.Z.zip]
set -euo pipefail
# ---- ΠΑΡΑΜΕΤΡΟΙ (προσάρμοσε πριν την πρώτη εγκατάσταση) ----
APP=thilek; CTID=115; HOSTNAME=thilek; IP=192.168.1.59/24; GW=192.168.1.1; DNS=192.168.1.1
CORES=1; RAM=1024; SWAP=256; DISK=16; STORAGE=local-lvm; BRIDGE=vmbr0; PORT=8010
# -----------------------------------------------------------
MODE=${1:---auto}; ZIP=${2:-$(ls -t "$PWD"/${APP}-v*.zip 2>/dev/null | head -1 || true)}
CRED=/root/${APP}-ct${CTID}-credentials.txt
log(){ echo "[$(date +%H:%M:%S)] $*"; }
exists(){ pct status "$CTID" >/dev/null 2>&1; }
[ "$MODE" = --pack ] && { echo "Το --pack τρέχει στα Windows/Linux: python tools/make_release.py"; exit 0; }
[ -n "$ZIP" ] && [ -f "$ZIP" ] || { echo "Δεν βρέθηκε zip ($ZIP). Δώσε: $0 $MODE ${APP}-vX.Y.Z.zip"; exit 1; }
[ "$MODE" = --auto ] && { exists && MODE=--update || MODE=--install; }

push_and_provision(){
  pct push "$CTID" "$ZIP" /root/${APP}.zip
  pct exec "$CTID" -- python3 -c "import zipfile;zipfile.ZipFile('/root/${APP}.zip').extractall('/root/${APP}-src')"
  pct exec "$CTID" -- bash /root/${APP}-src/${APP}/proxmox/provision-inside.sh "$1"
}
health(){ for i in $(seq 1 20); do
  out=$(pct exec "$CTID" -- curl -fsS "http://127.0.0.1:${PORT}/health" 2>/dev/null) && { log "health: $out"; return 0; }; sleep 2; done
  log "ΑΠΟΤΥΧΙΑ health check — δες: pct exec $CTID -- journalctl -u $APP -n 50"; return 1; }

case "$MODE" in
--install)
  exists && { echo "Το CT $CTID υπάρχει ήδη· χρησιμοποίησε --update"; exit 1; }
  TPL=$(pveam list local 2>/dev/null | awk '/debian-12-standard/{print $1}' | tail -1)
  if [ -z "$TPL" ]; then pveam update >/dev/null; T=$(pveam available --section system | awk '/debian-12-standard/{print $2}' | tail -1); pveam download local "$T"; TPL=local:vztmpl/$T; fi
  log "Δημιουργία CT $CTID ($IP)"
  pct create "$CTID" "$TPL" --hostname "$HOSTNAME" --cores $CORES --memory $RAM --swap $SWAP \
     --rootfs ${STORAGE}:${DISK} --net0 name=eth0,bridge=$BRIDGE,ip=$IP,gw=$GW --nameserver "$DNS" \
     --unprivileged 1 --features nesting=0 --onboot 1
  pct start "$CTID"; for i in $(seq 1 30); do pct exec "$CTID" -- ping -c1 -W1 "$GW" >/dev/null 2>&1 && break; sleep 2; done
  PASS=$(openssl rand -hex 7)
  push_and_provision "install:$PASS"
  umask 077; printf 'app=%s\nurl=http://%s:%s/\nuser=admin\npassword=%s\n' "$APP" "${IP%/*}" "$PORT" "$PASS" > "$CRED"
  health && log "Έτοιμο. Στοιχεία: $CRED";;
--update)
  exists || { echo "Δεν υπάρχει CT $CTID· χρησιμοποίησε --install"; exit 1; }
  pct exec "$CTID" -- /usr/local/bin/${APP}-backup || true
  push_and_provision update; health;;
*) echo "Άγνωστο mode $MODE"; exit 1;;
esac
