#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# migrate_ado_to_github.sh
# Azure DevOps -> GitHub single-repository migration script
#
# WHAT THIS SCRIPT DOES (in order):
#   1. Optionally creates the destination GitHub repo if it does not exist.
#   2. Mirror-clones the source repo from Azure DevOps (or refreshes an
#      existing mirror clone with a fast incremental fetch).
#   3. Strips large files and folders from git history using git-filter-repo
#      (controlled by STRIP_PATHS). This prevents GitHub's 100 MB file size
#      limit from blocking the push. If STRIP_PATHS is empty, this step is
#      skipped entirely and the history is pushed as-is.
#   4. Pushes all branches, tags, and refs to GitHub using git push --mirror.
#   5. Optionally sets the default branch in GitHub.
#   6. Optionally grants a GitHub team a specified permission level on the repo.
#   7. Optionally migrates Git LFS objects (auto-detected or forced via --lfs).
#   8. Validates the migration by comparing branch lists, tag lists, and the
#      default branch HEAD SHA between source and destination.
#   9. Writes a report directory with diffs and a summary file for sign-off.
#
# RERUN BEHAVIOR:
#   Safe to rerun at any time. On rerun the script fetches only new commits
#   (incremental), strips large paths again, and pushes the delta to GitHub.
#   Useful for cutover day: freeze ADO writes, rerun script, switch teams.
#
# CONFIGURATION:
#   Edit the hardcoded defaults below (lines starting after this block) to
#   set ADO_ORG, ADO_PROJECT, REPO_NAME, GH_ORG, STRIP_PATHS, etc.
#   All values can also be overridden via command-line arguments (see --help).
# =============================================================================

usage() {
  cat <<'EOF'
Usage:
  migrate_ado_to_github.sh \
    --ado-org <ado_org> \
    --ado-project <ado_project> \
    --repo <repo_name> \
    --gh-org <github_org> \
    [--default-branch <main|master>] \
    [--workdir <path>] \
    [--create-github-repo] \
    [--lfs <auto|on|off>]

Required args:
  --ado-org            Azure DevOps organization
  --ado-project        Azure DevOps project
  --repo               Repository name (example: prospect_geo_mapping)
  --gh-org             GitHub organization

Optional args:
  --default-branch     Branch to compare SHA after migration (default: main)
  --workdir            Workspace for migration artifacts (default: $HOME/migrations)
  --create-github-repo    Create destination repo using gh CLI if missing
  --no-create-github-repo Skip creating destination repo
  --set-default-branch    Set DEFAULT_BRANCH as the default branch in GitHub after push
  --no-set-default-branch Skip setting default branch in GitHub after push
  --lfs                   LFS mode: auto, on, off (default: auto)
  -h, --help              Show this help

Notes:
  - Destination GitHub repo should be empty for first migration.
  - You must be authenticated to both Azure DevOps and GitHub before running.
  - For cutover day, run this again after freeze/read-only on Azure DevOps.
EOF
}

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

count_lines() {
  local file="$1"
  if [[ -f "$file" ]]; then
    wc -l <"$file" | tr -d ' '
  else
    echo 0
  fi
}

ADO_ORG="RCCD-DevOps"
ADO_PROJECT="RCCB Data Science"
# https://dev.azure.com/RCCD-DevOps/RCCB%20Data%20Science/_git/prospect_geo_mapping
REPO_NAME="prospect_geo_mapping"
GH_ORG="Reyes-Coca-Cola-Bottling"
DEFAULT_BRANCH="main"
WORKDIR="${HOME}/migrations"
CREATE_GH_REPO="true"
SET_DEFAULT_BRANCH="true"
TEAM_SLUG="rccb-ds"
TEAM_PERMISSION="admin"
LFS_MODE="auto"
# Space-separated list of paths to strip from history before pushing to GitHub.
# Add any path that contains files exceeding GitHub's 100 MB file size limit.
# If left empty (""), the strip step is skipped entirely and history is pushed as-is.
STRIP_PATHS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ado-org)
      ADO_ORG="${2:-}"
      shift 2
      ;;
    --ado-project)
      ADO_PROJECT="${2:-}"
      shift 2
      ;;
    --repo)
      REPO_NAME="${2:-}"
      shift 2
      ;;
    --gh-org)
      GH_ORG="${2:-}"
      shift 2
      ;;
    --default-branch)
      DEFAULT_BRANCH="${2:-}"
      shift 2
      ;;
    --workdir)
      WORKDIR="${2:-}"
      shift 2
      ;;
    --create-github-repo)
      CREATE_GH_REPO="true"
      shift
      ;;
    --no-create-github-repo)
      CREATE_GH_REPO="false"
      shift
      ;;
    --set-default-branch)
      SET_DEFAULT_BRANCH="true"
      shift
      ;;
    --no-set-default-branch)
      SET_DEFAULT_BRANCH="false"
      shift
      ;;
    --lfs)
      LFS_MODE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$ADO_ORG" || -z "$ADO_PROJECT" || -z "$REPO_NAME" || -z "$GH_ORG" ]]; then
  echo "Missing required arguments." >&2
  usage
  exit 1
fi

if [[ "$LFS_MODE" != "auto" && "$LFS_MODE" != "on" && "$LFS_MODE" != "off" ]]; then
  echo "Invalid --lfs value: $LFS_MODE (expected auto|on|off)" >&2
  exit 1
fi

require_cmd git
if [[ "$CREATE_GH_REPO" == "true" || "$SET_DEFAULT_BRANCH" == "true" || -n "$TEAM_SLUG" ]]; then
  require_cmd gh
fi

ADO_PROJECT_ENCODED="${ADO_PROJECT// /%20}"
SOURCE_URL="https://dev.azure.com/${ADO_ORG}/${ADO_PROJECT_ENCODED}/_git/${REPO_NAME}"
TARGET_URL="https://github.com/${GH_ORG}/${REPO_NAME}.git"

mkdir -p "$WORKDIR"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_DIR="$WORKDIR/reports/${REPO_NAME}_${TIMESTAMP}"
MIRROR_DIR="$WORKDIR/${REPO_NAME}.git"
GH_CHECK_DIR="$WORKDIR/${REPO_NAME}_gh_check_${TIMESTAMP}.git"

mkdir -p "$REPORT_DIR"

log "Starting migration for ${REPO_NAME}"
log "Source: ${SOURCE_URL}"
log "Target: ${TARGET_URL}"
log "Report dir: ${REPORT_DIR}"

if [[ "$CREATE_GH_REPO" == "true" ]]; then
  log "Ensuring destination GitHub repository exists"
  if gh repo view "${GH_ORG}/${REPO_NAME}" >/dev/null 2>&1; then
    log "GitHub repo already exists: ${GH_ORG}/${REPO_NAME}"
  else
    gh repo create "${GH_ORG}/${REPO_NAME}" --internal --confirm
    log "Created GitHub repo: ${GH_ORG}/${REPO_NAME}"
  fi
fi

log "Preparing mirror clone"
if [[ -n "$STRIP_PATHS" && -d "$MIRROR_DIR" ]]; then
  log "STRIP_PATHS is set: removing stale mirror to ensure fresh clone before strip"
  rm -rf "$MIRROR_DIR"
fi
if [[ -d "$MIRROR_DIR" ]]; then
  log "Mirror directory exists, refreshing from source"
  git -C "$MIRROR_DIR" remote set-url origin "$SOURCE_URL"
  git -C "$MIRROR_DIR" fetch --prune origin
else
  git clone --mirror "$SOURCE_URL" "$MIRROR_DIR"
fi

if [[ -n "$STRIP_PATHS" ]]; then
  FILTER_REPO_BIN="$(command -v git-filter-repo 2>/dev/null || echo '')"
  if [[ -z "$FILTER_REPO_BIN" ]]; then
    # fallback: common conda/pip install location
    FILTER_REPO_BIN="/anaconda/envs/azureml_py38/bin/git-filter-repo"
  fi
  if [[ ! -x "$FILTER_REPO_BIN" ]]; then
    echo "git-filter-repo not found. Install with: pip install git-filter-repo" >&2
    exit 1
  fi
  log "Stripping large paths from history using git-filter-repo"
  FILTER_ARGS=()
  for STRIP_PATH in $STRIP_PATHS; do
    log "Configured path to strip: ${STRIP_PATH}"
    FILTER_ARGS+=(--path "$STRIP_PATH")
  done
  if [[ ${#FILTER_ARGS[@]} -gt 0 ]]; then
    FILTER_ARGS+=(--invert-paths)
    # Must cd into the mirror directory; git-filter-repo does not support -C
    (cd "$MIRROR_DIR" && "$FILTER_REPO_BIN" "${FILTER_ARGS[@]}" --force)
    # filter-repo removes the push remote as a safety measure; restore it
    git -C "$MIRROR_DIR" remote set-url --push origin "$TARGET_URL" 2>/dev/null || \
      git -C "$MIRROR_DIR" remote add origin "$TARGET_URL" 2>/dev/null || true
    log "Strip complete, push remote restored"
  else
    log "No paths required stripping, skipping git-filter-repo"
  fi
fi

log "Capturing source branch/tag baseline"
git -C "$MIRROR_DIR" for-each-ref refs/heads --format='%(refname:short)' | sort >"$REPORT_DIR/ado_branches.txt"
git -C "$MIRROR_DIR" for-each-ref refs/tags --format='%(refname:short)' | sort >"$REPORT_DIR/ado_tags.txt"
git -C "$MIRROR_DIR" show-ref | sort >"$REPORT_DIR/ado_show_ref.txt"

ADO_BRANCH_COUNT="$(count_lines "$REPORT_DIR/ado_branches.txt")"
ADO_TAG_COUNT="$(count_lines "$REPORT_DIR/ado_tags.txt")"
log "ADO branches: ${ADO_BRANCH_COUNT}, tags: ${ADO_TAG_COUNT}"

log "Pushing mirrored refs to GitHub"
git -C "$MIRROR_DIR" remote set-url --push origin "$TARGET_URL"
PUSH_LOG="$REPORT_DIR/push_mirror.log"
set +e
git -C "$MIRROR_DIR" push --mirror >"$PUSH_LOG" 2>&1
PUSH_EXIT=$?
set -e
if [[ "$PUSH_EXIT" -ne 0 ]]; then
  if grep -Eiq 'deny updating a hidden ref|refs/pull/.*/merge' "$PUSH_LOG"; then
    if grep -Eiq 'Authentication failed|Repository not found|unable to access|Could not read from remote repository|fatal:' "$PUSH_LOG"; then
      log "Push failed with non-recoverable errors; see $PUSH_LOG"
      exit "$PUSH_EXIT"
    fi
    log "Warning: push exited with code ${PUSH_EXIT} due to rejected hidden refs (expected for ADO PR refs)"
  else
    log "Push failed; see $PUSH_LOG"
    exit "$PUSH_EXIT"
  fi
fi

if [[ "$SET_DEFAULT_BRANCH" == "true" ]]; then
  log "Setting default branch to ${DEFAULT_BRANCH} in GitHub"
  gh repo edit "${GH_ORG}/${REPO_NAME}" --default-branch "${DEFAULT_BRANCH}"
  log "Default branch set to ${DEFAULT_BRANCH}"
fi

if [[ -n "$TEAM_SLUG" ]]; then
  log "Granting team '${TEAM_SLUG}' ${TEAM_PERMISSION} access to ${GH_ORG}/${REPO_NAME}"
  gh api "orgs/${GH_ORG}/teams/${TEAM_SLUG}/repos/${GH_ORG}/${REPO_NAME}" \
    --method PUT \
    -f permission="${TEAM_PERMISSION}"
  log "Team access granted"
fi

DO_LFS="false"
if [[ "$LFS_MODE" == "on" ]]; then
  DO_LFS="true"
elif [[ "$LFS_MODE" == "auto" ]]; then
  if command -v git-lfs >/dev/null 2>&1 || git lfs version >/dev/null 2>&1; then
    if git -C "$MIRROR_DIR" show-ref --verify --quiet "refs/heads/${DEFAULT_BRANCH}"; then
      if git -C "$MIRROR_DIR" show "refs/heads/${DEFAULT_BRANCH}:.gitattributes" 2>/dev/null | grep -q "filter=lfs"; then
        DO_LFS="true"
      fi
    fi
  fi
fi

if [[ "$DO_LFS" == "true" ]]; then
  require_cmd git
  if ! command -v git-lfs >/dev/null 2>&1 && ! git lfs version >/dev/null 2>&1; then
    echo "LFS requested, but git-lfs is not installed." >&2
    exit 1
  fi

  LFS_WORK_DIR="$WORKDIR/${REPO_NAME}_lfs_work_${TIMESTAMP}"
  log "Running LFS migration via temporary working clone"
  git clone "$SOURCE_URL" "$LFS_WORK_DIR"
  git -C "$LFS_WORK_DIR" lfs fetch --all
  git -C "$LFS_WORK_DIR" remote add github "$TARGET_URL"
  git -C "$LFS_WORK_DIR" lfs push --all github
  rm -rf "$LFS_WORK_DIR"
  log "LFS objects pushed"
else
  log "Skipping LFS migration (mode=${LFS_MODE})"
fi

log "Cloning destination mirror for validation"
git clone --mirror "$TARGET_URL" "$GH_CHECK_DIR"

git -C "$GH_CHECK_DIR" for-each-ref refs/heads --format='%(refname:short)' | sort >"$REPORT_DIR/gh_branches.txt"
git -C "$GH_CHECK_DIR" for-each-ref refs/tags --format='%(refname:short)' | sort >"$REPORT_DIR/gh_tags.txt"
git -C "$GH_CHECK_DIR" show-ref | sort >"$REPORT_DIR/gh_show_ref.txt"

GH_BRANCH_COUNT="$(count_lines "$REPORT_DIR/gh_branches.txt")"
GH_TAG_COUNT="$(count_lines "$REPORT_DIR/gh_tags.txt")"

BRANCH_DIFF_FILE="$REPORT_DIR/branch_diff.txt"
TAG_DIFF_FILE="$REPORT_DIR/tag_diff.txt"
SHA_COMPARE_FILE="$REPORT_DIR/default_branch_sha.txt"

set +e
diff -u "$REPORT_DIR/ado_branches.txt" "$REPORT_DIR/gh_branches.txt" >"$BRANCH_DIFF_FILE"
BRANCH_DIFF_EXIT=$?
diff -u "$REPORT_DIR/ado_tags.txt" "$REPORT_DIR/gh_tags.txt" >"$TAG_DIFF_FILE"
TAG_DIFF_EXIT=$?
set -e

SOURCE_SHA="missing"
TARGET_SHA="missing"
if git -C "$MIRROR_DIR" show-ref --verify --quiet "refs/heads/${DEFAULT_BRANCH}"; then
  SOURCE_SHA="$(git -C "$MIRROR_DIR" rev-parse "refs/heads/${DEFAULT_BRANCH}")"
fi
if git -C "$GH_CHECK_DIR" show-ref --verify --quiet "refs/heads/${DEFAULT_BRANCH}"; then
  TARGET_SHA="$(git -C "$GH_CHECK_DIR" rev-parse "refs/heads/${DEFAULT_BRANCH}")"
fi

{
  echo "default_branch=${DEFAULT_BRANCH}"
  echo "ado_sha=${SOURCE_SHA}"
  echo "github_sha=${TARGET_SHA}"
  if [[ "$SOURCE_SHA" == "$TARGET_SHA" && "$SOURCE_SHA" != "missing" ]]; then
    echo "sha_match=true"
  else
    echo "sha_match=false"
  fi
} >"$SHA_COMPARE_FILE"

SUMMARY_FILE="$REPORT_DIR/summary.txt"
{
  echo "repo=${REPO_NAME}"
  echo "source_url=${SOURCE_URL}"
  echo "target_url=${TARGET_URL}"
  echo "ado_branch_count=${ADO_BRANCH_COUNT}"
  echo "gh_branch_count=${GH_BRANCH_COUNT}"
  echo "ado_tag_count=${ADO_TAG_COUNT}"
  echo "gh_tag_count=${GH_TAG_COUNT}"
  echo "branch_diff_exit=${BRANCH_DIFF_EXIT}"
  echo "tag_diff_exit=${TAG_DIFF_EXIT}"
  echo "default_branch=${DEFAULT_BRANCH}"
  echo "ado_default_branch_sha=${SOURCE_SHA}"
  echo "gh_default_branch_sha=${TARGET_SHA}"
  if [[ "$SOURCE_SHA" == "$TARGET_SHA" && "$SOURCE_SHA" != "missing" ]]; then
    echo "default_branch_sha_match=true"
  else
    echo "default_branch_sha_match=false"
  fi
} >"$SUMMARY_FILE"

rm -rf "$GH_CHECK_DIR"

log "Migration complete"
log "Summary: ${SUMMARY_FILE}"
log "Branch diff: ${BRANCH_DIFF_FILE}"
log "Tag diff: ${TAG_DIFF_FILE}"
log "Default branch SHA check: ${SHA_COMPARE_FILE}"

if [[ "$BRANCH_DIFF_EXIT" -ne 0 || "$TAG_DIFF_EXIT" -ne 0 || "$SOURCE_SHA" != "$TARGET_SHA" ]]; then
  echo
  echo "Validation detected differences. Review report files under:"
  echo "  ${REPORT_DIR}"
  exit 2
fi

echo
echo "Validation passed. Next suggested actions:"
echo "  1) Run repository build/tests from a fresh GitHub clone"
echo "  2) Set branch protections/rulesets in GitHub"
echo "  3) For production cutover, freeze ADO writes and rerun this script"
