#!/bin/bash

set -e

# Create directory $1 or use $PWD
DIR="${1:-"$PWD"}"
[ -d "$DIR" ] || mkdir -p "$DIR"
DIR="$(realpath -e "$DIR")"

# Clone the database repositories
# All except kmerfinder_db and cgmlstfinder_db have their data in the repo.
# For kmerfinder and cgmlstfinder, we do the actual download below.
git clone "https://bitbucket.org/genomicepidemiology/kmerfinder_db.git" kmerfinder
git clone "https://bitbucket.org/genomicepidemiology/mlst_db.git" mlst
git clone "https://bitbucket.org/genomicepidemiology/plasmidfinder_db.git" plasmidfinder
git clone "https://bitbucket.org/genomicepidemiology/pmlst_db.git" pmlst
git clone "https://bitbucket.org/genomicepidemiology/resfinder_db.git" resfinder
git clone "https://bitbucket.org/genomicepidemiology/resfinder_db.git" pointfinder
git clone "https://bitbucket.org/genomicepidemiology/virulencefinder_db.git" virulencefinder
git clone "https://bitbucket.org/genomicepidemiology/salmonellatypefinder_db.git" salmonellatypefinder
git clone "https://bitbucket.org/genomicepidemiology/choleraefinder_db.git" choleraefinder
git clone "https://bitbucket.org/genomicepidemiology/cgmlstfinder_db.git" cgmlstfinder

# The kmerfinder and cgmlstfinder databases are stored on the CGE ftp server.
# Here we download that (HUGE) data.

# Download and index the KmerFinder data
#cd "$DIR/kmerfinder" && ./INSTALL.sh kma_index non_interactive

# Download and index the cgMLSTFinder data
#cd "$DIR/cgmlstfinder" && ./INSTALL.sh kma_index all

# Install KCST Database - use the container KCST
#cd "$DIR/mlst" && make-kcst-db.sh -f .

exit 0
