#!/usr/bin/env bash
# SINGLE SOURCE OF THE darnlang VERSION for this repo — which is darnlang itself.
#
# It exists because the workflows here source it like every consumer does, and it was MISSING: the
# issue workflow was copied from a consumer, kept the `. tools/darnlang_ref.sh` line, and this repo
# had no tools/ directory at all. Every issue opened on this PUBLIC repo would have gone red at the
# install step, on the tool's own repository. Found by review before it shipped.
#
# ⚠️ IT POINTS AT THE WORKING TREE, not at a published tag, and that is deliberate here and nowhere
# else. Gating this repo with an older release would let a regression through on the very commit
# that introduces it, and would not exercise the code being changed.
export DARNLANG_REF="."
