#!/usr/bin/env bash
# Static analysis: pyflakes (bugs), bandit (security) and shellcheck (shell scripts).
#   sudo apt install bandit python3-pyflakes shellcheck
# Debian's bandit cannot parse with Python 3.14 yet, so it is run under python3.11 when that exists.
cd "$(dirname "$0")/.." || exit 1
status=0
echo "== pyflakes";   python3 -m pyflakes ytdlp_gtk tests main.py || status=1
echo "== bandit";     py=python3; command -v python3.11 >/dev/null && py=python3.11
"$py" -m bandit -r ytdlp_gtk main.py -q -ll || status=1        # -ll: report medium and high only
echo "== shellcheck"; shellcheck packaging/*.sh packaging/AppRun packaging/ytdlp-gtk install.sh || status=1
[ $status = 0 ] && echo "ALL CLEAN" || echo "FINDINGS ABOVE"
exit $status
