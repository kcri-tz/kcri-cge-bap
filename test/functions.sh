#!/bin/sh

LC_ALL="C"

run_bap() {

    "$(realpath -e "$BASE_DIR/../bin/BAP")" "$@" \
        2>&1 > "${OUTPUT_DIR:-$PWD}/run-bap.out" |
        tee -a "${OUTPUT_DIR:-$PWD}/run-bap.err"
}

make_output_dir() {

    export OUTPUT_DIR="$BASE_DIR/output/$BASE_NAME-$(date '+%Y%m%d%H%M%S')"

    mkdir -p "$OUTPUT_DIR"

    [ -e "$BASE_DIR/output/latest" ] && 
        rm -f "$BASE_DIR/output/previous" &&
        mv -f "$BASE_DIR/output/latest" "$BASE_DIR/output/previous"

    ln -rsfT "$OUTPUT_DIR" "$BASE_DIR/output/latest"
}

check_output() {

    cd "$BASE_DIR"

    REF_OUT="expect/$BASE_NAME/bap-summary.tsv"
    RUN_OUT="output/latest/bap-summary.tsv"

    if diff "$REF_OUT" "$RUN_OUT"; then
        printf "[OK] Run output matches expected output\n\n"
        return 0
    else
        printf "\n[FAIL] Run output does not match expected output: $BASE_NAME\n\n"
        return 1
    fi
}

# vim: sts=4:sw=4:ai:si:et
