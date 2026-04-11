#!/bin/bash
#
# Sync skills from local directories to the openclaw-skills repository
#
# Usage:
#   ./sync-skills.sh              # Sync all skills
#   ./sync-skills.sh --dry-run    # Preview changes
#   ./sync-skills.sh skill1 ...  # Sync specific skills

set -uo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$SCRIPT_DIR"
SOURCE_DIRS=(
    "/home/ozp/clawd/skills"
    "/home/ozp/.wcgw/skills"
)
INDEX_FILE="$REPO_DIR/skills_index.json"
DRY_RUN=false
SPECIFIC_SKILLS=()

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            -*)
                log_error "Unknown option: $1"
                exit 1
                ;;
            *)
                SPECIFIC_SKILLS+=("$1")
                shift
                ;;
        esac
    done
}

show_help() {
    cat << 'EOF'
Sync skills from local directories to the openclaw-skills repository

Usage:
  ./sync-skills.sh              Sync all skills from local directories
  ./sync-skills.sh --dry-run    Preview changes without applying
  ./sync-skills.sh skill-name   Sync only specific skill(s)

Directories scanned:
  /home/ozp/clawd/skills/       Main OpenClaw skills
  /home/ozp/.wcgw/skills/        WCGW skills

Examples:
  ./sync-skills.sh                    # Sync everything
  ./sync-skills.sh --dry-run          # Preview what would change
  ./sync-skills.sh skill-creator        # Sync only skill-creator
  ./sync-skills.sh skill1 skill2      # Sync multiple skills
EOF
}

# Check if a directory is a valid skill directory
is_skill_dir() {
    local dir="$1"
    # Must be a directory, not hidden, and contain SKILL.md
    [[ -d "$dir" ]] && [[ "$(basename "$dir")" != .* ]] && [[ -f "$dir/SKILL.md" ]]
}

# Extract skill metadata from SKILL.md
extract_skill_metadata() {
    local skill_file="$1"
    local name=""
    local description=""
    local category=""
    local risk=""

    # Parse YAML frontmatter
    local in_frontmatter=false
    local frontmatter=""

    while IFS= read -r line; do
        if [[ "$line" == "---" ]]; then
            if [[ "$in_frontmatter" == false ]]; then
                in_frontmatter=true
                continue
            else
                break
            fi
        fi
        if [[ "$in_frontmatter" == true ]]; then
            frontmatter+="$line\n"
        fi
    done < "$skill_file"

    # Extract values using basic parsing
    name=$(echo -e "$frontmatter" | grep "^name:" | head -1 | cut -d':' -f2- | sed 's/^[[:space:]]*//')
    description=$(echo -e "$frontmatter" | grep "^description:" | head -1 | cut -d':' -f2- | sed 's/^[[:space:]]*//')
    category=$(echo -e "$frontmatter" | grep "^category:" | head -1 | cut -d':' -f2- | sed 's/^[[:space:]]*//')
    risk=$(echo -e "$frontmatter" | grep "^risk:" | head -1 | cut -d':' -f2- | sed 's/^[[:space:]]*//')

    echo "$name|$description|$category|$risk"
}

# Get directory hash for change detection
get_dir_hash() {
    local dir="$1"
    # Use find + sort + md5sum to create a stable hash
    find "$dir" -type f -name "*.md" -o -name "*.sh" -o -name "*.json" -o -name "*.py" 2>/dev/null | \
        sort | \
        xargs -I {} md5sum {} 2>/dev/null | \
        md5sum | \
        cut -d' ' -f1
}

# Find skill in source directories
find_skill_source() {
    local skill_name="$1"
    for source_dir in "${SOURCE_DIRS[@]}"; do
        local skill_path="$source_dir/$skill_name"
        if is_skill_dir "$skill_path"; then
            echo "$skill_path"
            return 0
        fi
    done
    return 1
}

# Calculate directory modification time (newest file)
get_dir_mtime() {
    local dir="$1"
    find "$dir" -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1
}

# Sync a single skill
sync_skill() {
    local skill_name="$1"
    local source_path
    local target_path="$REPO_DIR/$skill_name"

    # Find source
    source_path=$(find_skill_source "$skill_name") || {
        log_error "Skill '$skill_name' not found in source directories"
        return 1
    }

    local action=""
    local needs_update=false

    if [[ ! -d "$target_path" ]]; then
        action="ADD"
        needs_update=true
    else
        # Compare modification times
        local source_mtime target_mtime
        source_mtime=$(get_dir_mtime "$source_path")
        target_mtime=$(get_dir_mtime "$target_path")

        # Also compare hashes
        local source_hash target_hash
        source_hash=$(get_dir_hash "$source_path")
        target_hash=$(get_dir_hash "$target_path")

        if [[ "$source_mtime" != "$target_mtime" ]] || [[ "$source_hash" != "$target_hash" ]]; then
            action="UPDATE"
            needs_update=true
        fi
    fi

    if [[ "$needs_update" == true ]]; then
        if [[ "$DRY_RUN" == true ]]; then
            log_warn "[DRY-RUN] Would $action: $skill_name"
        else
            log_info "$action: $skill_name"

            # Remove old version if updating
            if [[ -d "$target_path" ]]; then
                rm -rf "$target_path"
            fi

            # Copy skill directory
            cp -r "$source_path" "$target_path"

            # Clean up any .bak files or temporary files
            find "$target_path" -name "*.bak" -delete 2>/dev/null || true
            find "$target_path" -name ".*" -type f -delete 2>/dev/null || true

            log_success "$skill_name synced successfully"
        fi
        return 0
    else
        log_info "UNCHANGED: $skill_name"
        return 2  # Special return for "no changes"
    fi
}

# Update skills_index.json
update_index() {
    local skills_added=0
    local skills_updated=0
    local tmp_index
    tmp_index=$(mktemp)

    echo "[" > "$tmp_index"
    local first=true

    # Process all skills in repo
    for skill_dir in "$REPO_DIR"/*/; do
        [[ -d "$skill_dir" ]] || continue
        local skill_name
        skill_name=$(basename "$skill_dir")

        # Skip special directories
        [[ "$skill_name" == ".git" ]] && continue
        [[ -f "$REPO_DIR/$skill_name" ]] && continue
        [[ ! -f "$skill_dir/SKILL.md" ]] && continue

        local metadata
        metadata=$(extract_skill_metadata "$skill_dir/SKILL.md")
        IFS='|' read -r name description category risk <<< "$metadata"

        # Use directory name if name not found
        [[ -z "$name" ]] && name="$skill_name"
        [[ -z "$category" ]] && category="uncategorized"
        [[ -z "$risk" ]] && risk="low"

        # Add comma if not first
        if [[ "$first" == true ]]; then
            first=false
        else
            echo "," >> "$tmp_index"
        fi

        # Write JSON entry
        cat >> "$tmp_index" << EOF
  {
    "path": "$skill_name",
    "name": "$name",
    "description": "$description",
    "category": "$category",
    "risk": "$risk"
  }
EOF
    done

    echo "" >> "$tmp_index"
    echo "]" >> "$tmp_index"

    if [[ "$DRY_RUN" == true ]]; then
        rm "$tmp_index"
    else
        mv "$tmp_index" "$INDEX_FILE"
        log_success "Updated $INDEX_FILE"
    fi
}

# Note: README table generation disabled - update manually or use a template
# The index file (skills_index.json) is updated automatically

# Main function
main() {
    parse_args "$@"

    log_info "Starting skills sync..."
    log_info "Repository: $REPO_DIR"
    log_info "Source directories: ${SOURCE_DIRS[*]}"

    if [[ "$DRY_RUN" == true ]]; then
        log_warn "DRY RUN MODE - No changes will be made"
    fi

    local skills_to_sync=()

    # Determine which skills to sync
    if [[ ${#SPECIFIC_SKILLS[@]} -gt 0 ]]; then
        skills_to_sync=("${SPECIFIC_SKILLS[@]}")
    else
        # Find all skills in source directories
        for source_dir in "${SOURCE_DIRS[@]}"; do
            if [[ -d "$source_dir" ]]; then
                for skill_dir in "$source_dir"/*/; do
                    [[ -d "$skill_dir" ]] || continue
                    is_skill_dir "$skill_dir" || continue
                    skills_to_sync+=("$(basename "$skill_dir")")
                done
            fi
        done
    fi

    # Remove duplicates
    skills_to_sync=($(printf '%s\n' "${skills_to_sync[@]}" | sort -u))

    log_info "Found ${#skills_to_sync[@]} skills to process"

    local added=0
    local updated=0
    local unchanged=0
    local failed=0

    for skill in "${skills_to_sync[@]}"; do
        sync_skill "$skill"
        local ret=$?
        if [[ $ret -eq 0 ]]; then
            if [[ -d "$REPO_DIR/$skill" ]]; then
                ((updated++))
            else
                ((added++))
            fi
        elif [[ $ret -eq 2 ]]; then
            ((unchanged++))
        else
            ((failed++))
        fi
    done

    log_info "Sync results: $added added, $updated updated, $unchanged unchanged, $failed failed"

    # Update index if changes were made
    if [[ "$DRY_RUN" == false ]] && [[ $((added + updated)) -gt 0 ]]; then
        update_index
        log_warn "Remember to update README.md skill table manually if needed"
    fi

    # Summary
    echo ""
    log_success "Sync complete!"

    if [[ "$DRY_RUN" == false ]] && [[ $((added + updated)) -gt 0 ]]; then
        echo ""
        log_info "Next steps:"
        echo "  1. Review changes: git status && git diff"
        echo "  2. Stage changes: git add ."
        echo "  3. Commit: git commit -m 'Sync skills from local directories'"
        echo "  4. Push: git push origin main"
        echo "  5. Sync in MC: POST /api/v1/skills/packs/{pack_id}/sync"
    fi
}

main "$@"
