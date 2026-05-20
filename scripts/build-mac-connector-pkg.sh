#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist/mac-connector"
PKG_ROOT="${DIST_DIR}/root"
PY_ROOT="${PKG_ROOT}/Library/Application Support/evaos-desktop-bridge/python"
IDENTIFIER="com.electricsheep.evaos-desktop-bridge"
VERSION="${EVAOS_DESKTOP_BRIDGE_VERSION:-0.1.0}"
SIGN_IDENTITY="${EVAOS_CONNECTOR_PKG_SIGN_IDENTITY:-}"
NOTARY_PROFILE="${EVAOS_CONNECTOR_NOTARY_PROFILE:-}"

rm -rf "${DIST_DIR}"
mkdir -p "${PKG_ROOT}/usr/local/bin" "${PKG_ROOT}/Library/LaunchAgents" "${PY_ROOT}" "${DIST_DIR}"

python3 -m pip install --target "${PY_ROOT}" "${ROOT_DIR}[gui]"

cat > "${PKG_ROOT}/usr/local/bin/evaos-desktop-bridge" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="/Library/Application Support/evaos-desktop-bridge/python${PYTHONPATH:+:${PYTHONPATH}}"
exec python3 -m evaos_desktop_bridge.cli "$@"
WRAPPER
chmod 0755 "${PKG_ROOT}/usr/local/bin/evaos-desktop-bridge"

install -m 0644 \
  "${ROOT_DIR}/packaging/LaunchAgents/com.electricsheep.evaos-desktop-bridge.plist" \
  "${PKG_ROOT}/Library/LaunchAgents/com.electricsheep.evaos-desktop-bridge.plist"

PKG_ARGS=(
  --root "${PKG_ROOT}"
  --identifier "${IDENTIFIER}"
  --version "${VERSION}"
  --install-location /
  "${DIST_DIR}/EvaOSDesktopBridge-${VERSION}.pkg"
)

if [[ -n "${SIGN_IDENTITY}" ]]; then
  PKG_ARGS=(--sign "${SIGN_IDENTITY}" "${PKG_ARGS[@]}")
fi

pkgbuild "${PKG_ARGS[@]}"

if [[ -n "${NOTARY_PROFILE}" ]]; then
  xcrun notarytool submit "${DIST_DIR}/EvaOSDesktopBridge-${VERSION}.pkg" \
    --keychain-profile "${NOTARY_PROFILE}" \
    --wait
  xcrun stapler staple "${DIST_DIR}/EvaOSDesktopBridge-${VERSION}.pkg"
fi

PKG_PATH="${DIST_DIR}/EvaOSDesktopBridge-${VERSION}.pkg"
if [[ -n "${SIGN_IDENTITY}" ]]; then
  if ! SIGNATURE_OUTPUT="$(pkgutil --check-signature "${PKG_PATH}" 2>&1)"; then
    printf 'Signature verification failed for %s\n%s\n' "${PKG_PATH}" "${SIGNATURE_OUTPUT}" >&2
    exit 1
  fi
  printf '%s\n' "${SIGNATURE_OUTPUT}"
else
  printf 'Skipping pkg signature check: EVAOS_CONNECTOR_PKG_SIGN_IDENTITY is not set.\n'
fi
shasum -a 256 "${PKG_PATH}" > "${PKG_PATH}.sha256"

printf 'Built %s\n' "${PKG_PATH}"
