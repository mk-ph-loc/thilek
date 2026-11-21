# TH-ILEK — Τράπεζα Θεμάτων Ηλεκτρολογίας
Ένας χρήστης, χωρίς διαχείριση χρηστών (Basic auth με έναν κωδικό). FastAPI + SQLite. Η βάση **ξαναχτίζεται από τα αρχεία** (`thilek-rebuild`).
## Εγκατάσταση (από Windows)
`cd C:\Users\manolis\Downloads; .\deploy-thilek.ps1 .\thilek-v0.1.0.zip`
Προσαρμογή CTID/IP/θύρας: μεταβλητές στην κορυφή του `proxmox/install-lxc.sh`.
## Δεδομένα από το Google Drive (μία φορά)
1. Στα Windows: `rclone authorize "drive"` → αντίγραψε το token.
2. Στο CT: `runuser -u thilek -- rclone config` (νέο remote `gdrive`, type drive, επικόλληση token, scope read-only αρκεί).
3. `thilek-sync && thilek-rebuild`
## Οθόνη ελέγχου
http://<IP>:8010/review (χρήστης admin, κωδικός από το credentials). Επιβεβαίωσε ή διόρθωσε τις προτάσεις σελίδων βιβλίου ανά ερώτημα.

## Εντολές στο CT
`thilek-sync` (Drive → /var/lib/thilek/data) · `thilek-rebuild` · `thilek-backup` · `systemctl status thilek`
## Δομή δεδομένων
`<ΜΑΘΗΜΑ>/{01_ODIGIES,02_VIVLIA,03_YLI,04_TRAPEZA/{orig,derived},05_PANELLADIKA,06_DIAGONISMATA,07_EXAGOGES}` — βλ. `docs/NAMING.md`.
Λύσεις εκπαιδευτικού (`<ID>.<θέμα>-<υπ>.md` + `images/`) μπαίνουν στο `04_TRAPEZA/orig/`· σελίδα `/lyseis` (βλ. Οδηγίες §15). Η βάση αναβαθμίζεται αυτόματα στην εκκίνηση (migrations).
