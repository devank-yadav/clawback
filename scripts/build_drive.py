"""Lay out data/drive/Peak Bar Co/<Distributor>/0N .../ as copies of each Peak Bar account's documents and records:
what we upload to Google Drive for the demo. Re-run after a data change; it rebuilds the folder from scratch.

Run: python scripts/build_drive.py"""
import re
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "drive" / "Peak Bar Co"
F = {1: "01 Contracts", 2: "02 Promotions", 3: "03 Remittances", 4: "04 Deductions & backup",
     5: "05 Correspondence", 6: "06 Sales data", 7: "07 Orders & shipping"}
CONTRACT_NAMES = {
    "kehe-vendor-policies-2015-peak-bar.txt": "KeHE Vendor Policies & Procedures 2015-05-31 (filed).txt",
    "walmart-supplier-agreement-2013-peak-bar.txt": "Walmart Supplier Agreement 2013-04-18 (filed).txt",
    "five-below-vendor-agreement-2023-excerpt-peak-bar.txt": "Five Below Vendor Agreement 2023 (filed excerpt).txt",
    "five-below-vendor-agreement-2025-excerpt-peak-bar.txt": "Five Below Vendor Agreement 2025 (filed excerpt).txt",
    "unfi-clearvue-supplier-agreement-2010-peak-bar.txt": "UNFI ClearVue Supplier Agreement 2010-01-01 (filed, redacted).txt",
    "sams-club-grocery-merchandise-agreement-2020-excerpt-peak-bar.txt":
        "Sam's Club Grocery Merchandise Agreement 607499-64-2 2020-02-03 (filed).txt",
}
PROMO = re.compile(r"promotion|instant-savings|summer", re.I)
POLICY = re.compile(r"ep-admin|price-list", re.I)
BROKER = re.compile(r"broker", re.I)
REMIT = {"peak-bar-unfi-remittance-7781234-2026-04-20": "2026-04-20 UNFI remit chk 7781234",
         "peak-bar-sams-retail-link-40018266-2026-04-16": "2026-04-16 Retail Link remittance chk 40018266"}
NAMES = {"peak-bar-kehe-ep-admin-2026-03-02": "2026-03-02 KeHE CONNECT notice - EP admin change",
         "peak-bar-kehe-promotion-2026-03": "2026-03 KeHE Promo Submission PB-OI-2603",
         "peak-bar-unfi-mcb-promotion-2026-03": "2026-03 UNFI MCB deal sheet PB-MCB-0326",
         "peak-bar-sams-instant-savings-2026-03": "2026-03 Instant Savings agreement PB-IS-0326",
         "spring-promo": "Spring promo agreement SPRING-26 (signed)", "amendment-1": "Amendment 1 (signed, cap 6,000)",
         "summer-draft": "Summer promo draft"}


def nice(stem: str, prefix: str) -> str:
    if stem in NAMES:
        return NAMES[stem]
    s = stem[len(prefix) + 1:] if stem.startswith(prefix + "-") else stem
    m = re.search(r"(\d{4}-\d{2}-\d{2}|\d{4}-\d{2}|\d{4}-q\d)", s)
    date = ""
    if m:
        date = m.group(1).upper().replace("-Q", " Q") if "q" in m.group(1) else m.group(1)
        s = (s[:m.start()] + s[m.end():]).strip("-")
    words = s.replace("-", " ").strip()
    words = words[:1].upper() + words[1:]
    return f"{date} {words}".strip()


def put(src: Path, folder: int, dist: Path, name: str, made: list):
    dst = dist / F[folder] / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    made.append(dst)


if OUT.exists():
    shutil.rmtree(OUT)
made: list[Path] = []
accounts = sorted(p for p in (DATA / "accounts").iterdir() if (p / "account.yaml").is_file())
for a in accounts:
    y = yaml.safe_load((a / "account.yaml").read_text())
    if (y.get("supplier") or y["id"]) != "peak-bar":
        continue
    dist = OUT / y["distributor"]["name"]
    pre = "" if y["id"] == "peak-bar" else y["id"]
    for name in y.get("contracts", []):
        put(DATA / "contracts" / name, 1, dist, CONTRACT_NAMES.get(name, name), made)
    for p in sorted((a / "deals").glob("*.md")):
        put(p, 2 if PROMO.search(p.stem) else 1, dist, nice(p.stem, pre) + p.suffix, made)
    for p in sorted((a / "notices").glob("*.md")):
        put(p, 2 if POLICY.search(p.stem) else 4, dist, nice(p.stem, pre) + p.suffix, made)
    for p in sorted((a / "emails").glob("*.eml")):
        put(p, 2 if BROKER.search(p.stem) else 5, dist, nice(p.stem, pre) + p.suffix, made)
    for p in sorted((a / "remittances").glob("*")):
        put(p, 3, dist, REMIT.get(p.stem, p.stem) + p.suffix, made)
    if y["id"] == "peak-bar":
        for p in sorted((DATA / "samples" / "remittances").glob("northmart-*")):
            put(p, 3, dist, "2026-04-10 Northmart remittance RA-2026-0410-118" + p.suffix, made)
    files = {
        "charges/march.csv": (4, "Deductions export 2026-03.csv"), "charges/april.csv": (4, "Deductions export 2026-04.csv"),
        "charges/older.csv": (4, "Deductions export, older open items.csv"),
        "fees/backup.csv": (4, "Deduction backup lines.csv"),
        "payments/prior.csv": (3, "Prior remittance lines.csv"), "payments/debit-balances.csv": (3, "Debit balances.csv"),
        "history/remittances.csv": (3, "Remittance history 2025-10 to 2026-03.csv"),
        "history/deductions.csv": (4, "Deduction history 2025-10 to 2026-03.csv"),
        "sales/store-sales.csv": (6, "Weekly sales on promotion 2026-03.csv"),
        "history/sales.csv": (6, "Weekly sales on promotion, earlier weeks.csv"),
        "plan/promo-plan.csv": (2, "Promotion plan 2026.csv"), "pricing/price-list.csv": (1, "Agreed price list.csv"),
        "deliveries/pod.csv": (7, "Proof of delivery 2026-03.csv"),
        "deliveries/appointments.csv": (7, "Delivery appointment log 2026-03.csv"),
        "purchases/purchase-orders.csv": (7, "Purchase orders 2026-03.csv"),
        "shipments/documents.csv": (7, "Shipping documents log 2026-03.csv"),
        "history/invoices.csv": (7, "Invoices 2025-10 to 2026-03.csv"),
    }
    for rel, (folder, name) in files.items():
        if (a / rel).is_file():
            put(a / rel, folder, dist, name, made)
company = OUT / "_Company"
company.mkdir(parents=True, exist_ok=True)
shutil.copyfile(ROOT / "config" / "policy.yaml", company / "Owner policy.yaml")
made.append(company / "Owner policy.yaml")
y = yaml.safe_load((DATA / "accounts" / "peak-bar" / "account.yaml").read_text())
(company / "Approved senders.txt").write_text(
    "People whose written approval can change a deal (besides a document signed by both parties):\n"
    + "".join(f"{s}\n" for s in y["approved_senders"]), encoding="utf-8")
made.append(company / "Approved senders.txt")
for f in sorted(made):
    print(f.relative_to(OUT))
print(len(made), "files")
