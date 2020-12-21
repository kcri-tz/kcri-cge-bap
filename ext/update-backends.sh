#!/bin/sh
#
# Downloads or updates the backends according to the versions
# in backend-versions.config.
#

BASE_DIR="$(realpath -e "$(dirname "$0")")"
CFG_FILE="$BASE_DIR/backend-versions.config"
VERSIONS_PY="$(realpath "$BASE_DIR/../src/kcribap/kcri/bap/shims/versions.py")"
VERSIONS_PY_TMP="$VERSIONS_PY.tmp"

err_exit() {
    rm -f "$VERSIONS_PY_TMP" || true
    echo "$(basename "$0"): $*" >&2
    exit 1
}

# Usage check and blurb if fails

[ $# -gt 0 ] && printf "
Usage: $(basename "$0")

  Downloads and/or updates the backends, according to the versions in
  $(basename "$CFG_FILE").

" && exit 1 || true

# Check for directories and files

[ -d "$BASE_DIR" ] || err_exit "no such directory: $BASE_DIR"
[ -r "$CFG_FILE" ] || err_exit "no such file: $CFG_FILE"

# Write the start of the kcri.bap.shims.versions module

cat >"$VERSIONS_PY_TMP" <<EOF
#!/usr/bin/env python3
#
# kcri.bap.shims.versions - generated by update-backends.sh.
# Used by the shims to report their backend service version.
#
BACKEND_VERSIONS = dict()
EOF

# Iterate over the non-comment lines in CFG_FILE

LINE=1
grep -E '^ *[^#]' "$CFG_FILE" | while read NAME VER URL REST; do

    LINE=$((LINE + 1))
    [ -n "$NAME" -a -n "$VER" -a -n "$URL" -a -z "$REST" ] ||
        err_exit "invalid line in $CFG_FILE: line $LINE"

    printf '%s ... ' "$NAME"

    # Switch on whether URL is for git or a tarball download

    if [ "${URL%gz}" = "${URL}" ]; then  # assume git

        DIR="$BASE_DIR/$NAME"
        [ -d "$DIR" ] || git clone -q "$URL" "$DIR" && cd "$DIR" || 
            err_exit "failed to clone $NAME: $URL"

        [ -d "$DIR/.git" ] && cd "$DIR" || err_exit "no git repository: $DIR"

        GIT_OLD="$(git describe --dirty --broken --tags --abbrev=1 --always)"

        git checkout -q master && git pull -q --ff-only --tags ||
            err_exit "failed to pull master for: $NAME"

        GIT_MASTER="$(git describe --dirty --broken --tags --abbrev=1 --always)"
       
        git checkout -q "$VER" ||
            err_exit "failed to check out: $NAME $VER"

        GIT_NEW="$(git describe --dirty --broken --tags --abbrev=1 --always)"

        [ "$GIT_OLD" = "$VER" -o "$GIT_OLD" = "$GIT_NEW" ] && 
            printf '%s' "$VER" ||
            printf '%s -> %s' "$GIT_OLD" "$VER"
        [ "$GIT_NEW" = "$VER" ] || printf ' = %s' "$GIT_NEW"
        [ "$GIT_NEW" = "$GIT_MASTER" ] || printf ' (master is %s)' "$GIT_MASTER"

    else # tarball

        DIR="$BASE_DIR/$NAME"
        [ -d "$DIR" ] || mkdir -p "$DIR"

        CUR_VER="$(cat "$DIR/.bap_version_crumb" 2>/dev/null)" || CUR_VER="(none)"

        if [ "$CUR_VER" = "$VER" ]; then
            printf '%s' "$VER"
        else
            printf '%s -> %s ' "$CUR_VER" "$VER"

            DL_URL="$(echo "$URL" | sed -e "s/@VERSION@/$VER/g")"
            TGZ_FILE="$BASE_DIR/$(basename "$DL_URL")"
            wget -qO "$TGZ_FILE" -c "$DL_URL" || err_exit "failed to download: $DL_URL"

            TMP_DIR="$(mktemp -d)"
            tar -C "$TMP_DIR" -xzf "$TGZ_FILE" || err_exit "failed to unpack: $TGZ_FILE"

            # We trust they use standard packaging, so all there is is a single directory:
            SRC_DIR="$TMP_DIR/$(ls "$TMP_DIR")"
            [ -d "$SRC_DIR" ] || err_exit "bad tarball: does not unpack as single directory: $(basename "$TGZ_FILE")"

            # Move the unpacked directory (with arbitrary name) to plain NAME
            rm -rf "$DIR" || true
            mv -T "$SRC_DIR" "$DIR" || err_exit "failed to move directory to $NAME: $SRC_DIR"

            # Leave our version crumb, so we remember what it is
            echo "$VER" >"$DIR/.bap_version_crumb"

            rm -f "$TGZ_FILE"
        fi

    fi

    printf '\n'

    # Write the version into the kcri.bap.shims.versions module

    printf 'BACKEND_VERSIONS["%s"] = "%s"\n' "$NAME" "$VER" >>"$VERSIONS_PY_TMP"

done

# Move the generated VERSIONS_PY_TMP over the previous iff different

cmp --quiet "$VERSIONS_PY_TMP" "$VERSIONS_PY" &&
    rm -f "$VERSIONS_PY_TMP" ||
    mv "$VERSIONS_PY_TMP" "$VERSIONS_PY"

exit 0

# vim: sts=4:sw=4:et:ai:si
