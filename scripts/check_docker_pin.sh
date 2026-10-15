#!/usr/bin/env bash
# Validate the framework pin in docker/Dockerfile BEFORE pushing.
#
# Why this exists: the Dockerfile builds the framework by fetching it from GitHub,
# so the pin cannot be validated by building locally unless the commit is already
# pushed. That makes it a chicken-and-egg problem, and getting it wrong costs a
# ~13 minute CI cycle that fails at step 4 with a git error rather than a Docker
# error. This has happened once already: an abbreviated SHA was substituted for
# the full one, and `git fetch` does not resolve an abbreviated object name -- it
# fails with "couldn't find remote ref", not with a checkout error.
#
# Checks, in order of how badly they hurt:
#   1. the pin is a full 40-character hex SHA (an abbreviation can never work)
#   2. the pin differs from the SHA of the commit that contains the Dockerfile
#      (the pin cannot name its own commit -- that commit does not exist yet)
#   3. the pinned commit is reachable on the remote the Dockerfile fetches from,
#      by replaying the Dockerfile's own git sequence into a scratch directory
#
# Usage: scripts/check_docker_pin.sh
# Exit 0 if the pin is good, 1 otherwise.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="${REPO_ROOT}/docker/Dockerfile"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "${SCRATCH}"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

[[ -f "${DOCKERFILE}" ]] || fail "no ${DOCKERFILE}"

# The fetch URL is hardcoded in the Dockerfile on purpose (an ARG would live in CI
# config rather than git), so read it from there rather than duplicating it.
REMOTE="$(grep -oE 'git remote add origin https://[^ ]+' "${DOCKERFILE}" \
          | head -1 | awk '{print $NF}')"
[[ -n "${REMOTE}" ]] || fail "could not find 'git remote add origin <url>' in the Dockerfile"

# The pin is the argument to `git fetch ... origin <sha>` in the framework step.
PIN="$(grep -oE 'git fetch -q --depth=1 origin [0-9a-f]+' "${DOCKERFILE}" \
       | head -1 | awk '{print $NF}')"
[[ -n "${PIN}" ]] || fail "could not find 'git fetch ... origin <sha>' in the Dockerfile"

echo "docker pin : ${PIN}"
echo "fetch from : ${REMOTE}"

# 1. must be a full SHA -- git fetch cannot resolve an abbreviation
if [[ ! "${PIN}" =~ ^[0-9a-f]{40}$ ]]; then
    fail "pin is not a full 40-character SHA.
      'git fetch --depth=1 origin <short-sha>' fails with
      'couldn't find remote ref' -- it does not resolve abbreviations, and it
      fails at FETCH time, not at checkout, which reads like a network problem.
      Use: git rev-parse <commit>"
fi

# 2. must not be the commit that contains this Dockerfile
SELF="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
if [[ "${PIN}" == "${SELF}" ]]; then
    fail "pin ${PIN} is the SHA of the commit that contains this Dockerfile.
      That commit does not exist on the remote yet, so the fetch cannot succeed.
      This is why BUMPING.md says the pin always names the last known-good commit:
      commit and push your work, THEN bump the pin in a following commit."
fi

# 3. replay the Dockerfile's own sequence against the remote
echo "replaying the Dockerfile git sequence ..."
git -C "${SCRATCH}" init -q .
git -C "${SCRATCH}" remote add origin "${REMOTE}"
if ! git -C "${SCRATCH}" fetch -q --depth=1 origin "${PIN}"; then
    fail "pin ${PIN} is not fetchable from ${REMOTE}.
      Either it was never pushed, or the branch history no longer makes it
      reachable. Note that get_code_packages_test.sh clones --branch XSCAPE /
      --branch main before fetching its SHA, so a force-push or branch deletion
      upstream can make a previously valid pin unfetchable."
fi
git -C "${SCRATCH}" checkout -q FETCH_HEAD
GOT="$(git -C "${SCRATCH}" rev-parse HEAD)"
if [[ "${GOT}" != "${PIN}" ]]; then
    fail "checked out ${GOT}, expected ${PIN}"
fi

echo "OK: pin ${PIN} is fetchable from ${REMOTE} and checks out exactly."