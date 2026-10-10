#!/usr/bin/env bash
# Build the web shell and install it on a connected Huawei phone.
# Usage:
#   scripts/install_webcap.sh
#   scripts/install_webcap.sh 3XQ0224C18027829
#   scripts/install_webcap.sh --skip-build
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$ROOT/apps/webcap"

DEVECO_CLI_CLT_PATH="${DEVECO_CLI_CLT_PATH:-/opt/command-line-tools}"
export DEVECO_CLI_CLT_PATH
HDC_DIR="$DEVECO_CLI_CLT_PATH/sdk/default/openharmony/toolchains"
export PATH="$DEVECO_CLI_CLT_PATH/bin:$HDC_DIR:${HOME}/.local/bin:${PATH}"

if ! command -v devecocli >/dev/null 2>&1; then
  shopt -s nullglob
  for bin in "$HOME"/.nvm/versions/node/*/bin; do
    if [[ -x "$bin/devecocli" ]]; then
      export PATH="$bin:$PATH"
    fi
  done
  shopt -u nullglob
fi
if ! command -v devecocli >/dev/null 2>&1; then
  echo "找不到 devecocli。请先安装 @deveco/deveco-cli，并确认 command-line-tools 在 DEVECO_CLI_CLT_PATH。" >&2
  exit 1
fi

if [[ -z "${JAVA_HOME:-}" || ! -x "${JAVA_HOME}/bin/java" ]]; then
  unset JAVA_HOME
  shopt -s nullglob
  candidates=(
    "$HOME"/tools/pycharm/pycharm-*/jbr
    /usr/lib/jvm/java-17-openjdk-*
    /usr/lib/jvm/java-21-openjdk-*
  )
  shopt -u nullglob
  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate/bin/java" ]]; then
      JAVA_HOME="$candidate"
      break
    fi
  done
fi
if [[ -z "${JAVA_HOME:-}" ]]; then
  echo "找不到 Java。请设置 JAVA_HOME。" >&2
  exit 1
fi
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$PATH"

DEVICE="${WEBCAP_DEVICE:-}"
EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      cat <<'EOF'
用法: scripts/install_webcap.sh [序列号] [devecocli run 的其他参数]

连着一台华为手机时直接运行，会编译网页壳并安装到手机上。
多台设备时传入序列号，或设置 WEBCAP_DEVICE。
  --skip-build    跳过编译，安装已有包
  --uninstall     安装前先卸载
EOF
      exit 0
      ;;
    --device)
      DEVICE="${2:-}"
      shift 2
      ;;
    --)
      shift
      EXTRA+=("$@")
      break
      ;;
    -*)
      EXTRA+=("$1")
      shift
      ;;
    *)
      if [[ -z "$DEVICE" ]]; then
        DEVICE="$1"
        shift
      else
        echo "多余参数: $1" >&2
        exit 1
      fi
      ;;
  esac
done

DEVICE_JSON="$(devecocli device list --format json)"
PICKED="$(python3 -c '
import json, sys
wanted = sys.argv[1]
devices = [d for d in json.loads(sys.argv[2]) if d.get("kind") == "device"]
if wanted:
    for device in devices:
        if wanted in (device.get("serial"), device.get("name")):
            print(device["serial"])
            print(device.get("name") or device["serial"])
            raise SystemExit(0)
    print("没有找到设备: " + wanted, file=sys.stderr)
    raise SystemExit(1)
if len(devices) == 1:
    print(devices[0]["serial"])
    print(devices[0].get("name") or devices[0]["serial"])
    raise SystemExit(0)
if not devices:
    print("没有连上华为设备。请打开 USB 调试后再试。", file=sys.stderr)
    raise SystemExit(1)
print("连着多台设备，请指定序列号:", file=sys.stderr)
for device in devices:
    print("  %s  %s" % (device.get("serial", ""), device.get("name", "")), file=sys.stderr)
raise SystemExit(1)
' "$DEVICE" "$DEVICE_JSON")"
SERIAL="${PICKED%%$'\n'*}"
NAME="${PICKED#*$'\n'}"
echo "安装到 ${NAME} (${SERIAL})"

cd "$APP_DIR"
devecocli run --device "$SERIAL" "${EXTRA[@]}"
