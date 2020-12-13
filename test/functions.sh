#!/bin/sh

LC_ALL="C"

run_bap() {

    "$(realpath -e "$BASE_DIR/../bin/BAP")" "$@" \
        2>&1 > "$BAP_WORK_DIR/run-bap.out" |
        tee -a "$BAP_WORK_DIR/run-bap.err"
}

make_workdir() {

    export BAP_WORK_DIR="$BASE_DIR/output/$BASE_NAME-$(date '+%Y%m%d%H%M%S')"

    mkdir -p "$BAP_WORK_DIR"

    [ -e "$BASE_DIR/output/latest" ] && 
        rm -f "$BASE_DIR/output/previous" &&
        mv -f "$BASE_DIR/output/latest" "$BASE_DIR/output/previous"

    ln -rsfT "$BAP_WORK_DIR" "$BASE_DIR/output/latest"
}

check_output() {

    cd "$BASE_DIR"

    REF_OUT="expect/$BASE_NAME/bap-summary.tsv"
    RUN_OUT="output/latest/bap-summary.tsv"

    if diff "$REF_OUT" "$RUN_OUT"; then
        printf "[OK] Run output matches expected output\n\n"
        return 0
    else
        printf "\n[FAIL] Run output does not match expected output\n\n"
        return 1
    fi
}

# vim: sts=4:sw=4:ai:si:et
