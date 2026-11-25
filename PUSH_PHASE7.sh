#!/usr/bin/env bash
# ── Push فاز ۷ ────────────────────────────────────────────────────────────
# کامیت آماده است: b9f4702  (main و master هر دو به آن اشاره می‌کنند)
# فقط توکن لازم است، چون شبکهٔ توکن در این محیط بین نشست‌ها ذخیره نمی‌شود.
#
#   export GITHUB_TOKEN=ghp_xxxxxxxx
#   ./PUSH_PHASE7.sh
#
set -euo pipefail
cd "$(dirname "$0")"

: "${GITHUB_TOKEN:?GITHUB_TOKEN را تنظیم کن: export GITHUB_TOKEN=ghp_...}"

git push "https://${GITHUB_TOKEN}@github.com/Hossein13abb/fahmyar.git" main master

echo
echo "✓ push شد. بررسی:"
git ls-remote origin refs/heads/main refs/heads/master
