#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Runs all of Tomate's tests. Exit status is non-zero if any suite fails.
cd "$(dirname "$0")/.." || exit 1
status=0
echo "== desktop integration";  python3 -m unittest -q tests.test_desktop_integration || status=1
echo; echo "== dependency check";  bash tests/test_depcheck.sh || status=1
echo; echo "== AppDir end-to-end"; bash tests/test_appdir.sh || status=1
exit $status
