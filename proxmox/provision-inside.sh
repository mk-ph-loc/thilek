#!/usr/bin/env bash
# Τρέχει ΜΕΣΑ στο CT. Ιδεμπότεντ: το update δεν πειράζει config/δεδομένα.
set -euo pipefail
APP=thilek; USR=thilek; PORT=8010
SRC=/root/${APP}-src/${APP}; OPT=/opt/${APP}; CFGD=/etc/${APP}; VAR=/var/lib/${APP}; BAK=/var/backups/${APP}
MODE=${1:-update}
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq; apt-get install -y -qq python3 python3-venv python3-pip poppler-utils sqlite3 rclone curl cron >/dev/null
id "$USR" >/dev/null 2>&1 || useradd --system --home "$VAR" --shell /usr/sbin/nologin "$USR"
mkdir -p "$OPT" "$CFGD" "$VAR/data" "$BAK"
# κώδικας
rm -rf "$OPT/app" "$OPT/tools" "$OPT/proxmox"; cp -r "$SRC/app" "$SRC/tools" "$SRC/proxmox" "$SRC/requirements.txt" "$OPT/"
[ -d "$OPT/venv" ] || python3 -m venv "$OPT/venv"
"$OPT/venv/bin/pip" install -q --upgrade pip; "$OPT/venv/bin/pip" install -q -r "$OPT/requirements.txt"
# config: μόνο αν λείπει
if [ ! -f "$CFGD/config.yaml" ]; then
  PASS=${MODE#install:}; [ "$PASS" = "$MODE" ] && PASS=$(openssl rand -hex 7)
  cat > "$CFGD/config.yaml" <<EOF
db: $VAR/thilek.db
data_root: $VAR/data
admin_password: "$PASS"
EOF
fi
chown root:"$USR" "$CFGD/config.yaml"; chmod 0640 "$CFGD/config.yaml"
chown -R "$USR":"$USR" "$VAR" "$BAK"; chown -R root:root "$OPT"
# PATH (το pct enter δεν περιλαμβάνει /usr/local/bin)
echo 'export PATH=$PATH:/usr/local/bin' > /etc/profile.d/thilek.sh
grep -q 'usr/local/bin' /root/.bashrc || echo 'export PATH=$PATH:/usr/local/bin' >> /root/.bashrc
# εντολές συντήρησης
cat > /usr/local/bin/${APP}-rebuild <<EOF
#!/bin/sh
exec runuser -u $USR -- $OPT/venv/bin/python $OPT/tools/rebuild.py $VAR/data $VAR/thilek.db
EOF
cat > /usr/local/bin/${APP}-sync <<EOF
#!/bin/sh
# Συγχρονισμός Drive -> data. Απαιτεί: runuser -u $USR -- rclone config  (remote "gdrive")
exec runuser -u $USR -- rclone sync "\${1:-gdrive:TH-ILEK}" $VAR/data --exclude "07_EXAGOGES/**" -v
EOF
cat > /usr/local/bin/${APP}-backup <<EOF
#!/bin/sh
[ -f $VAR/thilek.db ] && sqlite3 $VAR/thilek.db ".backup $BAK/thilek-\$(date +%F).db"
find $BAK -name 'thilek-*.db' -mtime +30 -delete
EOF
chmod 0755 /usr/local/bin/${APP}-{rebuild,sync,backup}
echo "30 3 * * * root /usr/local/bin/${APP}-backup" > /etc/cron.d/${APP}-backup
# systemd με sandbox
cat > /etc/systemd/system/${APP}.service <<EOF
[Unit]
Description=TH-ILEK question bank
After=network.target
[Service]
User=$USR
WorkingDirectory=$OPT
ExecStart=$OPT/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$VAR
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload; systemctl enable --now ${APP}; systemctl restart ${APP}
# πρώτο build της βάσης αν υπάρχουν δεδομένα
[ -d "$VAR/data" ] && ls "$VAR/data" | grep -q . && /usr/local/bin/${APP}-rebuild || echo "Δεν υπάρχουν δεδομένα ακόμα: ρύθμισε rclone και τρέξε ${APP}-sync && ${APP}-rebuild"
