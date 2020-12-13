#!/bin/sh
#
# Indexes the test databases.  It requires kma_index and make-kcst-db.sh
# on the PATH.  These are in the Docker container, so run like this:
#
#     BAP_DB_DIR=/tmp ../../bin/bap-docker-run ./index-databases.sh
#

set -e

BASE_DIR="$(realpath -e "$(dirname "$0")")"

# Index the Finders except KmerFinder (which comes preindexed) and pointfinder (below)
for D in resfinder virulencefinder plasmidfinder pmlst; do
    cd "$BASE_DIR/$D"
    grep -Ev '^[[:space:]]*(#|$)' config | cut -f1 | while read N REST; do
	kma_index -i "$N.fsa" -o "$N" 2>&1 | grep -v '^#' || true
    done
done

# Same for PointFinder but its files are split, and in subdirectories, yet we create single indices
for D in pointfinder; do
    cd "$BASE_DIR/$D"
    grep -Ev '^[[:space:]]*(#|$)' config | cut -f1 | while read N REST; do
        cd "$BASE_DIR/$D/$N" && 
        kma_index -i *.fsa -o "$N" 2>&1 | grep -v '^#' || true
    done
done

# Same for MLST database but its files are in subdirectories
for D in mlst; do
    cd "$BASE_DIR/$D"
    grep -Ev '^[[:space:]]*(#|$)' config | cut -f1 | while read N REST; do
        kma_index -i "$N/$N.fsa" -o "$N/$N" 2>&1 | grep -v '^#' || true
    done
done

# Add the KCST database to the MLST directory
cd "$BASE_DIR/mlst"
make-kcst-db.sh -f "$PWD"

# vim: sts=4:sw=4:ai:si:et
