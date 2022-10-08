#!/bin/sh
#
# Indexes the CGE databases in directory "$1".
# Works for both the test and real databases.
#

LC_ALL="C"

# Check usage and set BASE_DIR to full path of target directory
[ $# -eq 1 ] && [ -d "$1" ] && BASE_DIR="$(realpath -e "$1" 2>/dev/null)" || {
    echo "Usage: $(basename "$0") DB_DIR"
    exit 1
}

# Function to blurt an error and abort
err_exit() { echo "$(basename "$0"): $*" >&2; exit 1; }

# Function returns true if any file matching $1 is newer than file $2
any_newer() { [ ! -e "$2" ] || [ -n "$(find . -name "$1" -cnewer "$2" 2>/dev/null || true)" ]; }

# Add our directory to the PATH for kma_index and make-kcst-db.sh
PATH="$(realpath -e "$(dirname "$0")"):$PATH"

# Index the plain vanilla finders
for D in resfinder disinfinder virulencefinder plasmidfinder pmlst choleraefinder; do
    printf 'Indexing %s ... ' $D
    cd "$BASE_DIR/$D"
    grep -Ev '^[[:space:]]*(#|$)' config | cut -f1 | while read N REST; do
        any_newer "$N.fsa" "$N.seq.b" &&
	kma_index -i "$N.fsa" -o "$N" 2>&1 | grep -v '^#' || 
        true
    done
    [ $D != resfinder ] || kma_index -i *.fsa -o ./all
    printf 'OK\n'
done

# Same for MLST database but its files are in subdirectories.
# Note: the upstream database also has alleles/species/*.fsa for the loci,
#       but these have apparently already been catted to species/species.fsa.
for D in mlst; do
    printf 'Indexing %s ... ' $D
    cd "$BASE_DIR/$D"
    grep -Ev '^[[:space:]]*(#|$)' config | cut -f1 | while read N REST; do
        any_newer "$N/$N.fsa" "$N/$N.seq.b" &&
        kma_index -i "$N/$N.fsa" -o "$N/$N" 2>&1 | grep -v '^#' || 
        true
    done
    printf 'OK\n'
done

# Add the KCST database to the MLST directory (patching out a problematic allele)
printf 'Creating KCST database (this may take a while) ... ' $D
cd "$BASE_DIR/mlst"
p='ctropicalis/ctropicalis.fsa'
[ ! -f "$p" ] || sed -i.bak -Ee '/>SAPT4_139/,+1d' "$p"
make-kcst-db.sh -f "."
[ ! -f "$p.bak" ] || mv -f "$p.bak" "$p"
printf 'OK\n'

# PointFinder has loci per subdirectory, but they are catted to a single
# index per subdirectory.
for D in pointfinder; do
    printf 'Indexing %s ... ' $D
    cd "$BASE_DIR/$D"
    grep -Ev '^[[:space:]]*(#|$)' config | cut -f1 | while read N REST; do
        cd "$BASE_DIR/$D/$N" &&
        any_newer '*.fsa' "$N.seq.b" &&
        kma_index -i *.fsa -o "$N" 2>&1 | grep -v '^#' || 
        true
    done
    printf 'OK\n'
done

# cgMLSTFinder and KmerFinder come pre-indexed in production.  In test we
# have no cgMLST, but we have a KmerFinder database we build from source.

for D in kmerfinder; do
    printf 'Indexing %s ... ' $D
    cd "$BASE_DIR/$D"
    [ -f config ] && grep -Ev '^[[:space:]]*(#|$)' config | cut -f1 | while read N REST; do
        B="${N%.*}"
        S="${N##*.}"
        [ "$S" != "$B" ] || S='-'
        cd "$BASE_DIR/$D/$B" &&
        any_newer '*.fna' "$N.seq.b" &&
        kma_index -i *.fna -o "$N" -Sparse "$S" 2>&1 | grep -v '^#' ||
        true
    done
    printf 'OK\n'
done

exit 0

# vim: sts=4:sw=4:ai:si:et
