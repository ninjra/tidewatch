#!/bin/bash
# SPDX-License-Identifier: Apache-2.0 OR Commercial
# Golden pipeline for tidewatch: minds-eye KONA traversal to adequacy.
# Usage: ./scripts/golden_pipeline.sh [repo_path]
set -euo pipefail

minds-eye "${1:-.}"
