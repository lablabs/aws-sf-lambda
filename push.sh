#!/usr/bin/env bash
set -e

ME=$(basename "$0")
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

S3_BUCKET="${S3_BUCKET:-terraform-lambda-ll}"
VERSION=$(git rev-parse HEAD 2>/dev/null | cut -c 1-7)
PACKAGE_NAME="$1"
DO_CLEANUP="${2:-yes}"

logOut() {
  echo "[${ME}] ${1}"
}

failErrOut() {
  echo "[${ME}] ERROR - ${1} ! Exiting ..." >&2
  exit 1
}

validateInput() {
  [[ -z $PACKAGE_NAME ]] && failErrOut 'Package name must be set'
  command -v zip >/dev/null 2>&1 || failErrOut 'ZIP is required but it is not installed'
}

buildPackage() {
  logOut "Building ${PACKAGE_NAME}-${VERSION}.zip package ..."
  cd "${DIR}/${PACKAGE_NAME}" || exit 1
  sh build.sh -n "${PACKAGE_NAME}-${VERSION}" && mv "dist/${PACKAGE_NAME}-${VERSION}.zip" "${DIR}/" && cd "${DIR}" || exit
}

pushPackage() {
  logOut "Pushing ${PACKAGE_NAME}-${VERSION}.zip package ..."
  aws s3 cp "${DIR}/${PACKAGE_NAME}-${VERSION}.zip" "s3://${S3_BUCKET}/${PACKAGE_NAME}/" > /dev/null
}

doCleanup() {
  logOut "Deleting *.zip files - rm ${DIR}/*.zip ..."
  rm ${DIR}/*.zip 2> /dev/null
}

validateInput
buildPackage
pushPackage
[[ "$DO_CLEANUP" == "yes" ]] && doCleanup
