#!/bin/sh
#
# Clones the CGE database repos from the CGE BitBucket.
#

LC_ALL="C"

IDX_SCRIPT="$(realpath "$(dirname "$0")/index-databases.sh")"

# Check usage and set DEST to full path to directory $1
[ $# -eq 1 ] && [ -d "$1" ] && DEST="$(realpath -e "$1" 2>/dev/null)" || {
    echo "Usage: $(basename "$0") DB_DIR"
    exit 1
}

# Write error message and exit
err_exit() { echo "$(basename "$0"): $*" >&2; exit 1; }

# Clone the database repositories
for DB in \
    cgmlstfinder \
    choleraefinder \
    disinfinder \
    kmerfinder \
    mlst \
    plasmidfinder \
    pmlst \
    pointfinder \
    resfinder \
    salmonellatypefinder \
    virulencefinder
do
    DIR="$DEST/$DB"
    if [ -d "$DIR" ]; then
        cd "$DIR" && git pull || err_exit "git pull failed for: $DB"
    else
        git clone "https://bitbucket.org/genomicepidemiology/${DB}_db.git" "$DIR" ||
            err_exit "git clone failed for: $DB"
    fi
done

# Index the databases
"$IDX_SCRIPT" "$DEST"

# Done.
# Remind the user to download the KmerFinder and cgMLSTFinder databases.
cat <<EOF
NOTE: The KmerFinder and cgMLSTFinder databases are not complete yet.
      You must download their data from the CGE ftp site.
      Refer to their README files for instructions.
EOF

exit 0

# vim: sts=4:sw=4:ai:si:et
