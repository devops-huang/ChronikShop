#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One-shot setup for the Chronik PO demo.
# 一键环境准备 + 跑通 demo（CentOS/RHEL/Ubuntu/macOS 通用）
#
#   bash scripts/setup.sh              # 自动找 >=3.9 的 Python，建 venv，跑 demo
#   bash scripts/setup.sh --lang en    # 全英文产物（给客户看的那份）
#   bash scripts/setup.sh --docker     # 完全不用本机 Python，走 Docker
#   bash scripts/setup.sh --install-py # 没有新版 Python 时，尝试自动装一个
#
# 为什么需要它：CentOS 7/8、RHEL 8 自带的 python3 是 3.6，pip 只能装到 pydantic
# 1.9.x，于是报 "Could not find a version that satisfies pydantic>=2.7"。
# 这个脚本会先找到（或装好）一个 >=3.9 的解释器，再装依赖。
# ---------------------------------------------------------------------------
set -u

MIN_MAJOR=3
MIN_MINOR=9
LANGS="both"
USE_DOCKER=0
INSTALL_PY=0

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; DIM=$'\033[2m'; RST=$'\033[0m'
[ -t 1 ] || { RED=""; GRN=""; YEL=""; DIM=""; RST=""; }

say()  { printf '%s\n' "$*"; }
ok()   { printf '%s[ ok ]%s %s\n' "$GRN" "$RST" "$*"; }
warn() { printf '%s[warn]%s %s\n' "$YEL" "$RST" "$*"; }
die()  { printf '%s[fail]%s %s\n' "$RED" "$RST" "$*"; exit 1; }
hr()   { printf '%s\n' "------------------------------------------------------------"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --lang)     LANGS="${2:-both}"; shift 2 ;;
    --lang=*)   LANGS="${1#--lang=}"; shift ;;
    --docker)   USE_DOCKER=1; shift ;;
    --install-py) INSTALL_PY=1; shift ;;
    -h|--help)  sed -n '2,20p' "$0"; exit 0 ;;
    *)          say "unknown option: $1 (try --help)"; exit 2 ;;
  esac
done
case "$LANGS" in both|en|zh) ;; *) die "bad --lang '$LANGS' (use both|en|zh)" ;; esac

# repo root = parent of this script's directory
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DEMO="$ROOT"
[ -f "$DEMO/requirements.txt" ] || die "requirements.txt not found in $DEMO — run this from the demo/ directory"
cd "$DEMO" || die "cannot cd to $DEMO"

say "Chronik demo · setup / 环境准备"
hr
say "os      : $(uname -s) $(uname -r)"
if [ -f /etc/os-release ]; then say "distro  : $(. /etc/os-release; echo "${PRETTY_NAME:-$NAME}")"; fi
say "demo    : $DEMO"
say "lang    : $LANGS"
hr

version_ok() { # $1 = interpreter, prints 1 if >= MIN
  "$1" -c "import sys; sys.exit(0 if sys.version_info[:2] >= ($MIN_MAJOR,$MIN_MINOR) else 1)" >/dev/null 2>&1
}
version_of() { "$1" -c "import sys;print('%d.%d.%d' % sys.version_info[:3])" 2>/dev/null || echo "?"; }

# ---- 1. find a usable interpreter -----------------------------------------
find_python() {
  for cand in python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
    p=$(command -v "$cand" 2>/dev/null) || continue
    if version_ok "$p"; then printf '%s' "$p"; return 0; fi
  done
  # pyenv / conda / vendor installs that are not on PATH
  for d in "$HOME/.pyenv/shims" /opt/python/bin /opt/conda/bin /usr/local/bin \
           /usr/local/python3/bin /opt/rh/rh-python38/root/usr/bin; do
    for cand in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
      p="$d/$cand"
      [ -x "$p" ] || continue
      if version_ok "$p"; then printf '%s' "$p"; return 0; fi
    done
  done
  return 1
}

# ---- 2. docker route -------------------------------------------------------
run_docker() {
  command -v docker >/dev/null 2>&1 || die "docker not installed. Try: bash scripts/setup.sh --install-py"
  ok "using Docker (no host Python needed)"
  ( cd "$ROOT/.." && [ -f docker-compose.yml ] ) || die "docker-compose.yml not found at repo root; clone the full repo (not just demo/)"
  if docker compose version >/dev/null 2>&1; then
    ( cd "$ROOT/.." && docker compose run --rm demo )
  else
    ( cd "$ROOT/.." && docker-compose run --rm demo )
  fi
}

if [ "$USE_DOCKER" = "1" ]; then
  run_docker
  hr; ok "artefacts: $DEMO/out/{csv,review,metrics.json}"
  exit 0
fi

PYBIN=$(find_python) && ok "interpreter: $PYBIN ($(version_of "$PYBIN"))"

if [ -z "${PYBIN:-}" ]; then
  warn "no Python >= $MIN_MAJOR.$MIN_MINOR found on this machine"
  say ""
  say "current ones:"
  for cand in python3 python; do
    p=$(command -v "$cand" 2>/dev/null) && say "  $p -> $(version_of "$p")"
  done

  if [ "$INSTALL_PY" = "1" ]; then
    say ""
    say "-> trying to install a newer Python (--install-py)"
    # uv: user-space, no root, works on CentOS 7 glibc 2.17
    if command -v curl >/dev/null 2>&1 && curl -LsSf --max-time 15 https://astral.sh/uv/install.sh -o /tmp/uv-install.sh 2>/dev/null; then
      sh /tmp/uv-install.sh >/dev/null 2>&1 || true
      if [ -x "$HOME/.local/bin/uv" ]; then
        export PATH="$HOME/.local/bin:$PATH"
        say "   uv installed, fetching CPython 3.11 ..."
        if uv python install 3.11 >/dev/null 2>&1; then
          uv venv --python 3.11 .venv >/dev/null 2>&1 && {
            ok "created .venv with uv-managed CPython 3.11"
            PYBIN="$DEMO/.venv/bin/python"
          }
        fi
      fi
    fi
    # package managers
    if [ -z "${PYBIN:-}" ]; then
      if command -v dnf >/dev/null 2>&1; then
        say "   dnf install python3.11 ..."
        dnf install -y python3.11 python3.11-pip >/dev/null 2>&1 || true
      elif command -v yum >/dev/null 2>&1; then
        say "   yum install python3.11 ..."
        yum install -y python3.11 python3.11-pip >/dev/null 2>&1 || yum install -y python311 >/dev/null 2>&1 || true
      elif command -v apt-get >/dev/null 2>&1; then
        say "   apt-get install python3.11 ..."
        apt-get update -qq >/dev/null 2>&1 || true
        apt-get install -y python3.11 python3.11-venv >/dev/null 2>&1 || true
      fi
      PYBIN=$(find_python) && ok "interpreter after install: $PYBIN ($(version_of "$PYBIN"))"
    fi
  fi

  if [ -z "${PYBIN:-}" ]; then
    say ""
    say "${RED}No usable Python.${RST} Pick one: 任选一条"
    say ""
    say "  A) auto-install (tries uv, then dnf/yum/apt):"
    say "     bash scripts/setup.sh --install-py"
    say ""
    say "  B) Docker (no host Python at all):"
    say "     bash scripts/setup.sh --docker"
    say ""
    say "  C) install 3.11 yourself, then re-run this script:"
    say "     dnf install -y python3.11 python3.11-pip        # CentOS8/RHEL8/Fedora"
    say "     yum install -y centos-release-scl-rh && yum install -y rh-python38  # CentOS 7"
    say "     curl -fsSL https://pyenv.run | bash && pyenv install 3.11.9 && pyenv local 3.11.9"
    say ""
    exit 1
  fi
fi

# ---- 3. venv ---------------------------------------------------------------
if [ -x "$DEMO/.venv/bin/python" ]; then
  if ! version_ok "$DEMO/.venv/bin/python"; then
    warn "existing .venv uses $(version_of "$DEMO/.venv/bin/python") — recreating it"
    rm -rf "$DEMO/.venv"
  fi
fi

if [ ! -x "$DEMO/.venv/bin/python" ]; then
  say ""
  say "-> creating .venv with $PYBIN"
  "$PYBIN" -m venv .venv || die "venv creation failed (on Debian/Ubuntu try: apt install python3-venv)"
fi
VPY="$DEMO/.venv/bin/python"
ok "venv: $VPY ($(version_of "$VPY"))"

# ---- 4. dependencies -------------------------------------------------------
say ""
say "-> installing dependencies (1-3 minutes)"
"$VPY" -m pip install -q --upgrade pip >/dev/null 2>&1 || true

MIRROR="${CHRONIK_PIP_MIRROR:-https://pypi.tuna.tsinghua.edu.cn/simple}"

# NOTE: always pass --index-url explicitly. If PIP_INDEX_URL is exported, pip
# would keep using it even on the "plain PyPI" attempt and the fallback would
# silently repeat the same failure.
pip_install() { # $1 = index url
  "$VPY" -m pip install -q --retries 2 --timeout 20 --index-url "$1" -r requirements.txt
}

INSTALLED=0
# 1) an explicit index the user exported wins
if [ -n "${PIP_INDEX_URL:-}" ]; then
  say "   using PIP_INDEX_URL=$PIP_INDEX_URL"
  pip_install "$PIP_INDEX_URL" && INSTALLED=1
fi
# 2) plain PyPI
if [ "$INSTALLED" = "0" ]; then
  say "   trying pypi.org ..."
  pip_install "https://pypi.org/simple" && INSTALLED=1
fi
# 3) mirror (mainland servers frequently cannot reach pypi.org reliably)
if [ "$INSTALLED" = "0" ]; then
  warn "pypi.org failed or timed out -> retrying via mirror: $MIRROR"
  pip_install "$MIRROR" && INSTALLED=1
fi
if [ "$INSTALLED" = "0" ]; then
  say ""
  die "pip install failed. Manual options:
       $VPY -m pip install --index-url $MIRROR -r requirements.txt
       CHRONIK_PIP_MIRROR=https://mirrors.aliyun.com/pypi/simple bash scripts/setup.sh
       bash scripts/setup.sh --docker        # no pip on the host at all"
fi
ok "dependencies installed"

# ---- 5. preflight ----------------------------------------------------------
say ""
"$VPY" scripts/doctor.py || true

# ---- 6. run ----------------------------------------------------------------
say ""
hr
say "-> running the pipeline"
"$VPY" -m chronik.cli --lang "$LANGS" || die "pipeline failed"
"$VPY" -m chronik.preview --lang "$LANGS" >/dev/null 2>&1 && ok "review cards rendered (PNG)"

hr
say ""
say "${GRN}Done.${RST} 看这几个文件 / look at these:"
say "  $DEMO/out/csv/                 CSV，每单一个（给 ERP 的那份）"
say "  $DEMO/out/review/review.html   复核页（浏览器打开，每条 flag 附原文截图）"
say "  $DEMO/out/review/preview_*.png 每单一张复核卡"
say "  $DEMO/out/metrics.json         放行率 / 置信度 / 每单成本"
say ""
say "打开复核页 / open the review sheet:"
say "  Windows: start out\\review\\review.html"
say "  macOS:   open out/review/review.html"
say "  Linux:   xdg-open out/review/review.html  (无桌面就用 scp 拷回本地)"
say ""
say "全英文（上客户）/ English only:  python -m chronik.cli --lang en"
say "测试 / tests:                    $VPY -m pytest -q"
