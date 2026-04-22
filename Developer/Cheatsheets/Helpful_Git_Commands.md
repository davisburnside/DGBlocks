
# Git Commands

# (bash) A git command to find the commit ID (and how many commits behind current) that a string was present in a repo, like "def some_old_func", updated 2/17/26

git log -S "def some_old_func" --oneline
# Get the commit hash where it last appeared
COMMIT=$(git log -S "def some_old_func(" --oneline | head -1 | cut -d' ' -f1)
# Get the commit hash where it last appeared
COMMIT=$(git log -S "def some_old_func(" --oneline | head -1 | cut -d' ' -f1)
# Count commits since then
git rev-list --count COMM$COMMIT..HEAD
