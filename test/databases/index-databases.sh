#!/bin/sh
#
# Indexes the test databases.  It requires kma_index and make-kcst-db.sh
# on the PATH.  These are in the Docker container, so run like this:
#
#     BAP_DB_DIR=/tmp ../../bin/bap-docker-run ./index-databases.sh
#

LC_ALL="C"
set -e

BASE_DIR="$(realpath -e "$(dirname "$0")")"
RUN_CONT="$(realpath -e "$BASE_DIR/../../bin/bap-container-run")"

# Index the Finders except KmerFinder and PointFinder
for D in resfinder virulencefinder plasmidfinder pmlst; do
    printf 'Indexing %s ... ' $D
    cd "$BASE_DIR/$D"
    grep -Ev '^[[:space:]]*(#|$)' config | cut -f1 | while read N REST; do
	"$RUN_CONT" kma_index -i "$N.fsa" -o "$N" 2>&1 | grep -v '^#' || true
    done
    printf 'OK\n'
done

# Same for MLST database but its files are in subdirectories
# In the upstream databases there is also alleles/species/*.fsa for all
# loci, but it is unclear whether we must combine into species/species.fsa.
for D in mlst; do
    printf 'Indexing %s ... ' $D
    cd "$BASE_DIR/$D"
    grep -Ev '^[[:space:]]*(#|$)' config | cut -f1 | while read N REST; do
        "$RUN_CONT" kma_index -i "$N/$N.fsa" -o "$N/$N" 2>&1 | grep -v '^#' || true
    done
    printf 'OK\n'
done

# Add the KCST database to the MLST directory
printf 'Creating KCST database (please be patient) ... ' $D
BAP_WORK_DIR="$BASE_DIR/mlst" "$RUN_CONT" make-kcst-db.sh -f "."
printf 'OK\n'

# KmerFinder in production comes pre-indexed and needs no indexing.
# In test same setup as PointFinder: loci per subdirectory, combines into
# single index per subdirectory.
for D in kmerfinder pointfinder; do
    printf 'Indexing %s ... ' $D
    cd "$BASE_DIR/$D"
    grep -Ev '^[[:space:]]*(#|$)' config | cut -f1 | while read N REST; do
        cd "$BASE_DIR/$D/$N" && 
        "$RUN_CONT" kma_index -i *.f?a -o "$N" 2>&1 | grep -v '^#' || true
    done
    printf 'OK\n'
done

# vim: sts=4:sw=4:ai:si:et
