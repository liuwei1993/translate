#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ASR_DIR="$ROOT/models/asr"
if [[ -f "$ASR_DIR/tokens.txt" ]]; then
  echo "ASR model already present"
  exit 0
fi
mkdir -p "$ROOT/models"
TMP="$(mktemp -d)"
ASR_URLS=(
  "https://ghfast.top/https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2"
  "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2"
)
downloaded=0
for url in "${ASR_URLS[@]}"; do
  echo "trying $url"
  if curl -L --connect-timeout 20 --retry 2 --retry-delay 2 -o "$TMP/asr.tar.bz2" "$url"; then
    downloaded=1
    break
  fi
  rm -f "$TMP/asr.tar.bz2"
done
if [[ "$downloaded" != 1 ]]; then
  echo "failed to download ASR model" >&2
  exit 1
fi
tar -xjf "$TMP/asr.tar.bz2" -C "$TMP"
rm -rf "$ASR_DIR"
mv "$TMP"/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20 "$ASR_DIR"
rm -rf "$TMP"
test -f "$ASR_DIR/encoder-epoch-99-avg-1.int8.onnx"
test -f "$ASR_DIR/decoder-epoch-99-avg-1.onnx"
test -f "$ASR_DIR/joiner-epoch-99-avg-1.int8.onnx"
test -f "$ASR_DIR/tokens.txt"
