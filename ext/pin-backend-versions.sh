#!/bin/sh
#
# Pins the versions in backend-versions.config to the current state of
# their repositories / downloads.  Run this script when bringing out a
# release, so that the release is reproducible.
#

LC_ALL="C"
BASE_DIR="$(realpath -e "$(dirname "$0")")"
CFG_FILE="$BASE_DIR/backend-versions.config"
NEW_FILE="$BASE_DIR/backend-versions.config.new"

# Function to exit with error message $* on stderr
err_exit() { 
    echo "$(basename "$0"): $*" >&2
    [ ! -f "$NEW_FILE" ] || rm -rf "$NEW_FILE"
    exit 1
}

# Usage check and blurb if fails
[ $# -gt 0 ] && printf "
Usage: $(basename "$0")

  Updates $(basename "$CFG_FILE") to reflect the current backend versions,
  so that this release can be reproduced by running ./update-backends.sh.

" && exit 1

# Check for directories and files
[ -d "$BASE_DIR" ] || err_exit "no such directory: $BASE_DIR"
[ -r "$CFG_FILE" ] || err_exit "no such file: $CFG_FILE"

# Make a copy, else we write the file we are reading and havoc ensues
cp "$CFG_FILE" "$NEW_FILE"

# Iterate over the non-comment lines in CFG_FILE
LINE=1
grep -E '^ *[^#].*$' "$CFG_FILE" | while read NAME VER URL REST; do

    LINE=$((LINE + 1))
    [ -n "$NAME" -a -n "$VER" -a -n "$URL" -a -z "$REST" ] ||
        err_exit "invalid line in $CFG_FILE: line $LINE"

    DIR="$BASE_DIR/$NAME"

    [ -d "$DIR" ] || err_exit "backend directory not present: $NAME"

    # Switch on whether URL is for git or a tarball download

    if [ "${URL%gz}" = "${URL}" ]; then  # assume git
        [ -d "$DIR/.git" ] && cd "$DIR" || err_exit "no git repository: $DIR"
        CUR_VER="$(git describe --dirty --broken --tags --abbrev=1 --always)" ||
            err_exit "git describe failed in $DIR"
    else # assume tar ball
        CUR_VER="$(cat "$DIR/.bap_version_crumb" 2>/dev/null)" || 
            err_exit "backend version unknown (not installed with update-backends?): $NAME"
    fi

    # If actual version is different, update the field in NEW_FILE

    if [ "$CUR_VER" = "$VER" ]; then
        echo "unchanged $NAME = $CUR_VER"
    else
        echo "pinning $NAME $VER => $CUR_VER"

        awk -F '\t' -v "R=$NAME" -v "V=$CUR_VER" 'BEGIN { OFS=FS }
            { if (NF==3 && $1==R) print $1, V, $3; else print $0; }' \
            "$CFG_FILE" >"$NEW_FILE" ||
            err_exit "failed to set version field for $NAME in $CFG_FILE"
    fi

done

# Move the new file over the old
mv "$NEW_FILE" "$CFG_FILE"

exit 0

# vim: sts=4:sw=4:et:ai:si
