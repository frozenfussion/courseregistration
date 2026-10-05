#!/usr/bin/env bash
# Regenerates the static font files the PDF brochure uses (WeasyPrint reads static fonts most reliably).
# Needs the dev requirements:  pip install -r requirements-dev.txt
# The variable fonts in app/static/fonts come from https://github.com/google/fonts (SIL Open Font License).
set -euo pipefail
cd "$(dirname "$0")/../app/static/fonts"
fonttools varLib.instancer Inter.ttf wght=400 opsz=14 -o pdf-Inter-400.ttf -q
fonttools varLib.instancer Inter.ttf wght=500 opsz=14 -o pdf-Inter-500.ttf -q
fonttools varLib.instancer Inter.ttf wght=600 opsz=14 -o pdf-Inter-600.ttf -q
fonttools varLib.instancer BodoniModa.ttf wght=400 opsz=28 -o pdf-BodoniModa-400.ttf -q
fonttools varLib.instancer BodoniModa-Italic.ttf wght=400 opsz=28 -o pdf-BodoniModa-Italic-400.ttf -q
echo "Done."
