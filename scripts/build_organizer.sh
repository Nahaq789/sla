#!/usr/bin/env bash
# 整理役 Lambda のデプロイ用ディレクトリ (build/organizer/) を作る。
# Terraform の archive_file がこのディレクトリを zip 化するため、plan / apply の前に実行する。
#
# - 依存パッケージは uv.lock から書き出し、Lambda (arm64 / Python 3.13) 用のものを入れる
# - boto3 は Lambda ランタイムに同梱されているため入れない (dev グループのみ)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
src="${root}/agents/organizer"
out="${root}/build/organizer"

rm -rf "${out}"
mkdir -p "${out}"

uv export \
  --project "${src}" \
  --frozen \
  --no-dev \
  --no-emit-project \
  --quiet \
  --output-file "${root}/build/organizer-requirements.txt"

uv pip install \
  --quiet \
  --target "${out}" \
  --python-version 3.13 \
  --python-platform aarch64-manylinux2014 \
  --only-binary :all: \
  --link-mode copy \
  --requirement "${root}/build/organizer-requirements.txt"

# zip の中身が毎回同じになるよう、インストール時に作られる実行環境依存のファイルを除く
# (bin/ のスクリプトにはビルドしたマシンの Python のパスが入る。Lambda では使わない)
rm -rf "${out}/bin"
find "${out}" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "${out}" -path "*.dist-info/RECORD" -delete
find "${out}" -path "*.dist-info/INSTALLER" -delete

cp "${src}"/*.py "${out}/"
cp -r "${src}/prompts" "${out}/"
