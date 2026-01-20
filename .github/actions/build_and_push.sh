#!/usr/bin/env sh
set -eu

REGISTRY="docker.hsyhhssyy.net"
USERNAME="hsyhhssyy"

: "${REGISTRY_PASSWORD:?REGISTRY_PASSWORD is required}"
: "${IMAGE_NAME:?IMAGE_NAME is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"

DOCKERFILE_PATH="${DOCKERFILE_PATH:-./Dockerfile}"
CONTEXT_DIR="${CONTEXT_DIR:-.}"
PUSH_LATEST="${PUSH_LATEST:-false}"   # true/false
EXTRA_TAGS="${EXTRA_TAGS:-}"          # e.g. "v1.2.3"

echo "==> Login ${REGISTRY} as ${USERNAME}"
echo "${REGISTRY_PASSWORD}" | docker login "${REGISTRY}" -u "${USERNAME}" --password-stdin

FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "==> Build: ${FULL_IMAGE}"
docker build -f "${DOCKERFILE_PATH}" -t "${FULL_IMAGE}" "${CONTEXT_DIR}"

echo "==> Push: ${FULL_IMAGE}"
docker push "${FULL_IMAGE}"

if [ -n "${EXTRA_TAGS}" ]; then
  for t in ${EXTRA_TAGS}; do
    EXTRA_IMAGE="${REGISTRY}/${IMAGE_NAME}:${t}"
    echo "==> Tag & Push extra: ${EXTRA_IMAGE}"
    docker tag "${FULL_IMAGE}" "${EXTRA_IMAGE}"
    docker push "${EXTRA_IMAGE}"
  done
fi

if [ "${PUSH_LATEST}" = "true" ]; then
  LATEST_IMAGE="${REGISTRY}/${IMAGE_NAME}:latest"
  echo "==> Tag & Push latest: ${LATEST_IMAGE}"
  docker tag "${FULL_IMAGE}" "${LATEST_IMAGE}"
  docker push "${LATEST_IMAGE}"
fi

echo "==> Done."
