#!/bin/bash
usage() { echo "Usage: $0 [-n <NAME>]" 1>&2; exit 1; }

while getopts ":n:" o; do
    case "${o}" in
        n)
            n=${OPTARG}
            ;;
        *)
            usage
            ;;
    esac
done
shift $((OPTIND-1))

if [ -z "${n}" ]; then
    usage
fi

docker build -t ce-report-build .
docker run --rm -v "${PWD}"/dist:/vol --env NAME="$n" ce-report-build
