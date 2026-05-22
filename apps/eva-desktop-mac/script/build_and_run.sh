#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
APP_EXECUTABLE_NAME="EvaDesktop"
APP_BUNDLE_NAME="evaOS"
DISPLAY_NAME="evaOS Workbench"
BUNDLE_ID="com.electricsheephq.EvaDesktop"
MIN_SYSTEM_VERSION="14.0"
VERSION="0.4.7"
BUILD_NUMBER="17"
UPDATE_MANIFEST_URL="${EVA_DESKTOP_UPDATE_MANIFEST_URL:-https://www.electricsheephq.com/evaos-workbench/updates.json}"
UPDATE_RELEASE_NOTES_URL="${EVA_DESKTOP_UPDATE_RELEASE_NOTES_URL:-https://www.electricsheephq.com/evaos-workbench}"
SPARKLE_APPCAST_URL="${EVA_DESKTOP_SPARKLE_APPCAST_URL:-https://www.electricsheephq.com/evaos-workbench/appcast.xml}"
SPARKLE_PUBLIC_ED_KEY="${EVA_DESKTOP_SPARKLE_PUBLIC_ED_KEY:-xbeQ5mJ0u7pwhQP716i8Ox7maymOnpxvahi4xZQNZOg=}"
SPARKLE_KEY_ACCOUNT="${EVA_DESKTOP_SPARKLE_KEY_ACCOUNT:-electricsheephq-evaos-workbench}"
SPARKLE_PRIVATE_KEY_FILE="${EVA_DESKTOP_SPARKLE_PRIVATE_KEY_FILE:-/Users/lume/.openclaw/secrets/evaos-workbench-sparkle-ed25519-private-key.txt}"
NOTARY_TIMEOUT="${EVA_DESKTOP_NOTARY_TIMEOUT:-45m}"
if [ "$MODE" = "--package-release" ] || [ "$MODE" = "package-release" ] || [ "$MODE" = "--notarize-release" ] || [ "$MODE" = "notarize-release" ]; then
  DEFAULT_UPDATE_DOWNLOAD_URL="https://www.electricsheephq.com/evaos-workbench/evaOS-Workbench-$VERSION.zip"
else
  DEFAULT_UPDATE_DOWNLOAD_URL="https://www.electricsheephq.com/evaos-workbench/evaOS-Workbench-Beta-$VERSION.zip"
fi
UPDATE_DOWNLOAD_URL="${EVA_DESKTOP_UPDATE_DOWNLOAD_URL:-$DEFAULT_UPDATE_DOWNLOAD_URL}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT_DIR/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
APP_BUNDLE="$DIST_DIR/$APP_BUNDLE_NAME.app"
APP_CONTENTS="$APP_BUNDLE/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_FRAMEWORKS="$APP_CONTENTS/Frameworks"
APP_RESOURCES="$APP_CONTENTS/Resources"
APP_BINARY="$APP_MACOS/$APP_EXECUTABLE_NAME"
INFO_PLIST="$APP_CONTENTS/Info.plist"
BETA_STAGING_DIR="$DIST_DIR/beta"
BETA_INSTALL_NOTES="$BETA_STAGING_DIR/BETA_INSTALL.md"
BETA_ZIP="$DIST_DIR/evaOS-Workbench-Beta-$VERSION.zip"
RELEASE_STAGING_DIR="$DIST_DIR/release"
RELEASE_INSTALL_NOTES="$RELEASE_STAGING_DIR/INSTALL.md"
RELEASE_ZIP="$DIST_DIR/evaOS-Workbench-$VERSION.zip"
BETA_UPDATE_MANIFEST="$DIST_DIR/updates.json"
BETA_UPDATE_MANIFEST_COMPAT="$DIST_DIR/evaos-workbench-updates.json"
APPCAST_OUTPUT="$DIST_DIR/appcast.xml"
NOTARY_STATUS_JSON="$DIST_DIR/notarization-status.json"
NOTARY_LOG_JSON="$DIST_DIR/notarization-log.json"
NOTARY_RELEASE_JSON="$DIST_DIR/notarization-release.json"

detect_apple_development_identity() {
  security find-identity -p codesigning -v 2>/dev/null \
    | awk -F '"' '/Apple Development:/ { print $2; exit }'
}

resolve_signing_identity() {
  if [ -n "${EVA_DESKTOP_CODESIGN_IDENTITY:-}" ]; then
    printf '%s\n' "$EVA_DESKTOP_CODESIGN_IDENTITY"
    return
  fi
  if [ -n "${CODESIGN_IDENTITY:-}" ]; then
    printf '%s\n' "$CODESIGN_IDENTITY"
    return
  fi
  local detected
  detected="$(detect_apple_development_identity || true)"
  if [ -n "$detected" ]; then
    printf '%s\n' "$detected"
  else
    printf '%s\n' "-"
  fi
}

describe_signing_identity() {
  if [ "$SIGNING_IDENTITY" = "-" ]; then
    printf '%s\n' "ad-hoc"
    return
  fi
  security find-identity -p codesigning -v 2>/dev/null \
    | awk -v identity="$SIGNING_IDENTITY" 'index($0, identity) { split($0, parts, "\""); print parts[2]; exit }'
}

SIGNING_IDENTITY="$(resolve_signing_identity)"
SIGNING_LABEL="$(describe_signing_identity || true)"
SIGNING_KEYCHAIN="${EVA_DESKTOP_CODESIGN_KEYCHAIN:-${CODESIGN_KEYCHAIN:-}}"
SIGNING_TIMESTAMP="${EVA_DESKTOP_CODESIGN_TIMESTAMP:-auto}"
SIGNING_RUNTIME="0"
NOTARY_PROFILE="${EVA_DESKTOP_NOTARY_PROFILE:-evaos-workbench-notary}"
NOTARY_KEYCHAIN="${EVA_DESKTOP_NOTARY_KEYCHAIN:-$SIGNING_KEYCHAIN}"

if [ "$MODE" = "--package-release" ] || [ "$MODE" = "package-release" ] || [ "$MODE" = "--notarize-release" ] || [ "$MODE" = "notarize-release" ]; then
  SIGNING_RUNTIME="1"
fi

if [ "$MODE" = "--package-beta" ] || [ "$MODE" = "package-beta" ]; then
  if [[ "$SIGNING_IDENTITY" == Developer\ ID* ]] || [[ "$SIGNING_LABEL" == Developer\ ID* ]]; then
    echo "Beta packaging intentionally excludes Developer ID signing. Use Apple Development or unset EVA_DESKTOP_CODESIGN_IDENTITY for ad-hoc signing." >&2
    exit 2
  fi
fi

if [ "$MODE" = "--package-release" ] || [ "$MODE" = "package-release" ] || [ "$MODE" = "--notarize-release" ] || [ "$MODE" = "notarize-release" ]; then
  if [ "$SIGNING_IDENTITY" = "-" ]; then
    echo "Release packaging requires a Developer ID signing identity. Set EVA_DESKTOP_CODESIGN_IDENTITY." >&2
    exit 2
  fi
  if [[ "$SIGNING_LABEL" != Developer\ ID* ]] && [[ "$SIGNING_IDENTITY" != Developer\ ID* ]]; then
    echo "Release packaging requires a Developer ID Application identity. Resolved identity: ${SIGNING_LABEL:-$SIGNING_IDENTITY}" >&2
    exit 2
  fi
fi

sign_app_bundle() {
  local args=(--force --sign "$SIGNING_IDENTITY")

  if [ "$SIGNING_IDENTITY" = "-" ]; then
    args+=(--timestamp=none)
  else
    if [ -n "$SIGNING_KEYCHAIN" ]; then
      args+=(--keychain "$SIGNING_KEYCHAIN")
    fi
    if [ "$SIGNING_RUNTIME" = "1" ]; then
      args+=(--options runtime)
    fi
    case "$SIGNING_TIMESTAMP" in
      auto|"")
        ;;
      none)
        args+=(--timestamp=none)
        ;;
      *)
        args+=(--timestamp="$SIGNING_TIMESTAMP")
        ;;
    esac
  fi

  if [ -d "$APP_FRAMEWORKS/Sparkle.framework" ]; then
    codesign "${args[@]}" "$APP_FRAMEWORKS/Sparkle.framework"
  fi
  sign_nested_bridge_binaries "${args[@]}"
  codesign --deep "${args[@]}" "$APP_BUNDLE"
}

sign_nested_bridge_binaries() {
  local args=("$@")
  local bridge_bin_dir="$APP_RESOURCES/Bridge/bin"
  if [ ! -d "$bridge_bin_dir" ]; then
    return
  fi
  while IFS= read -r binary; do
    if file "$binary" | grep -q "Mach-O"; then
      codesign "${args[@]}" "$binary"
    fi
  done < <(find "$bridge_bin_dir" -type f -perm +111)
}

copy_sparkle_framework() {
  local sparkle_framework
  sparkle_framework="$(find "$ROOT_DIR/.build/artifacts" -path "*Sparkle.framework" -type d 2>/dev/null | head -n 1 || true)"
  if [ -z "$sparkle_framework" ]; then
    echo "Sparkle.framework was not found after swift build." >&2
    exit 2
  fi
  rm -rf "$APP_FRAMEWORKS/Sparkle.framework"
  mkdir -p "$APP_FRAMEWORKS"
  /usr/bin/ditto "$sparkle_framework" "$APP_FRAMEWORKS/Sparkle.framework"
}

copy_bridge_helper() {
  local bridge_dir="$APP_RESOURCES/Bridge"
  local bridge_script="$bridge_dir/evaos-desktop-bridge"
  local bridge_bin_dir="$bridge_dir/bin"

  rm -rf "$bridge_dir"
  mkdir -p "$bridge_dir/src" "$bridge_bin_dir"
  cp -R "$REPO_ROOT/src/evaos_desktop_bridge" "$bridge_dir/src/"
  copy_peekaboo_helper "$bridge_bin_dir"
  cat > "$bridge_script" <<'EOF'
#!/bin/sh
set -eu

BRIDGE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

if [ -n "${EVAOS_DESKTOP_BRIDGE_PYTHON:-}" ] && [ -x "${EVAOS_DESKTOP_BRIDGE_PYTHON:-}" ]; then
  PYTHON_BIN="$EVAOS_DESKTOP_BRIDGE_PYTHON"
else
  PYTHON_BIN=""
  for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if [ -x "$candidate" ]; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "evaos-desktop-bridge: python3 was not found. Install Python 3 or contact ElectricSheep support." >&2
  exit 127
fi

export PYTHONPATH="$BRIDGE_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$BRIDGE_DIR/bin:$PATH"
export PYTHONDONTWRITEBYTECODE=1
exec "$PYTHON_BIN" -m evaos_desktop_bridge.cli "$@"
EOF
  find "$bridge_dir" -name "__pycache__" -type d -prune -exec rm -rf {} +
  chmod +x "$bridge_script"
}

copy_peekaboo_helper() {
  local bridge_bin_dir="$1"
  local peekaboo_source="${EVAOS_PEEKABOO_BIN:-}"
  if [ -z "$peekaboo_source" ]; then
    peekaboo_source="$(command -v peekaboo 2>/dev/null || true)"
  fi
  if [ -z "$peekaboo_source" ]; then
    for candidate in /opt/homebrew/bin/peekaboo /usr/local/bin/peekaboo; do
      if [ -x "$candidate" ]; then
        peekaboo_source="$candidate"
        break
      fi
    done
  fi
  if [ -n "$peekaboo_source" ] && [ -x "$peekaboo_source" ]; then
    cp "$peekaboo_source" "$bridge_bin_dir/peekaboo"
    chmod +x "$bridge_bin_dir/peekaboo"
  else
    cat > "$bridge_bin_dir/peekaboo" <<'EOF'
#!/bin/sh
set -eu
for candidate in /opt/homebrew/bin/peekaboo /usr/local/bin/peekaboo; do
  if command -v "$candidate" >/dev/null 2>&1; then
    exec "$candidate" "$@"
  fi
done
echo "peekaboo not installed. Install with: brew install steipete/tap/peekaboo" >&2
exit 127
EOF
    chmod +x "$bridge_bin_dir/peekaboo"
  fi
}

ensure_app_rpaths() {
  local frameworks_rpath="@executable_path/../Frameworks"
  if ! otool -l "$APP_BINARY" | grep -q "$frameworks_rpath"; then
    install_name_tool -add_rpath "$frameworks_rpath" "$APP_BINARY"
  fi
}

cd "$ROOT_DIR"

pkill -x "$APP_EXECUTABLE_NAME" >/dev/null 2>&1 || true

swift build
BUILD_BINARY="$(swift build --show-bin-path)/$APP_EXECUTABLE_NAME"

rm -rf "$APP_BUNDLE" "$DIST_DIR/EvaDesktop.app"
mkdir -p "$APP_MACOS" "$APP_FRAMEWORKS" "$APP_RESOURCES"
cp "$BUILD_BINARY" "$APP_BINARY"
chmod +x "$APP_BINARY"
copy_sparkle_framework
ensure_app_rpaths

if [ -d "$ROOT_DIR/Resources" ]; then
  cp -R "$ROOT_DIR/Resources/." "$APP_RESOURCES/"
fi
copy_bridge_helper

/usr/libexec/PlistBuddy -c "Clear dict" "$INFO_PLIST" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c "Add :CFBundleExecutable string $APP_EXECUTABLE_NAME" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string $BUNDLE_ID" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleName string '$DISPLAY_NAME'" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string '$DISPLAY_NAME'" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundlePackageType string APPL" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $BUILD_NUMBER" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string $MIN_SYSTEM_VERSION" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :NSPrincipalClass string NSApplication" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes array" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0 dict" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLName string $BUNDLE_ID" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes array" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string evaos" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :SUFeedURL string $SPARKLE_APPCAST_URL" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :SUPublicEDKey string $SPARKLE_PUBLIC_ED_KEY" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :SUEnableAutomaticChecks bool true" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :SUAutomaticallyUpdate bool false" "$INFO_PLIST"
/usr/libexec/PlistBuddy -c "Add :SUVerifyUpdateBeforeExtraction bool true" "$INFO_PLIST"

sign_app_bundle

write_beta_install_notes() {
  rm -rf "$BETA_STAGING_DIR"
  mkdir -p "$BETA_STAGING_DIR"
  cat > "$BETA_INSTALL_NOTES" <<EOF
# evaOS Workbench Beta $VERSION

This is an internal/friendly beta build. It is not Developer ID signed or
notarized yet.

## Install

1. Unzip \`evaOS-Workbench-Beta-$VERSION.zip\`.
2. Drag \`$APP_BUNDLE_NAME.app\` to Applications or run it from this folder.
3. If macOS Gatekeeper blocks the first launch, right-click the app and choose
   Open. Do not globally disable Gatekeeper.

## Known Beta Limits

- No Developer ID signing.
- No notarization.
- Automatic update checks are enabled. Workbench checks the ElectricSheep
  update manifest and opens the newest installer package when an update is
  available. Background self-replacement is deferred until Developer ID signing.
- Keychain trust may reset between ad-hoc builds. If Workbench repeatedly asks
  for Keychain access, use Reset Local Session on the sign-in screen or clear
  only the Workbench desktop session item:

  \`\`\`bash
  security delete-generic-password \\
    -s com.electricsheephq.EvaDesktop.session \\
    -a desktop-session
  \`\`\`

## Agent Control Boundary

The customer beta supports named Mac and iPhone controls through audited
OpenClaw/Hermes tools. Full Access can operate continuously after the customer
starts a visible session; Ask Permission and legacy guarded actions require
dry-run/approval at high-impact boundaries. Workbench does not expose arbitrary
shell, hidden AppleScript, password capture, payment/purchase automation, or
generic Codex app-server mutation.
EOF
}

write_update_manifest() {
  local artifact="$1"
  local channel="$2"
  local sha256
  sha256="$(shasum -a 256 "$artifact" | awk '{print $1}')"
  cat > "$BETA_UPDATE_MANIFEST" <<EOF
{
  "version": "$VERSION",
  "build": "$BUILD_NUMBER",
  "channel": "$channel",
  "minimum_system_version": "$MIN_SYSTEM_VERSION",
  "download_url": "$UPDATE_DOWNLOAD_URL",
  "sha256": "$sha256",
  "release_notes_url": "$UPDATE_RELEASE_NOTES_URL",
  "published_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
  cp "$BETA_UPDATE_MANIFEST" "$BETA_UPDATE_MANIFEST_COMPAT"
}

package_beta() {
  write_beta_install_notes
  rm -f "$BETA_ZIP"
  cp -R "$APP_BUNDLE" "$BETA_STAGING_DIR/"
  (
    cd "$BETA_STAGING_DIR"
    /usr/bin/ditto -c -k --norsrc --keepParent "$APP_BUNDLE_NAME.app" "$BETA_ZIP"
    /usr/bin/zip -q "$BETA_ZIP" "BETA_INSTALL.md"
  )
  write_update_manifest "$BETA_ZIP" "beta"
  codesign --verify --deep --strict "$APP_BUNDLE"
  echo "Created beta artifact: $BETA_ZIP"
  echo "Created update manifest: $BETA_UPDATE_MANIFEST"
  echo "Created compatibility manifest copy: $BETA_UPDATE_MANIFEST_COMPAT"
  echo "Update manifest URL expected by app: $UPDATE_MANIFEST_URL"
  echo "Signing identity: $SIGNING_IDENTITY"
  echo "Signing label: ${SIGNING_LABEL:-unknown}"
}

write_release_install_notes() {
  rm -rf "$RELEASE_STAGING_DIR"
  mkdir -p "$RELEASE_STAGING_DIR"
  cat > "$RELEASE_INSTALL_NOTES" <<EOF
# evaOS Workbench $VERSION

This build is signed with the ElectricSheep Developer ID Application
certificate. Customer-hosted release builds should be notarized; if macOS blocks
a non-notarized internal canary, right-click the app and choose Open.

## Install

1. Unzip \`evaOS-Workbench-$VERSION.zip\`.
2. Drag \`$APP_BUNDLE_NAME.app\` to Applications.
3. Launch \`evaOS Workbench\` and sign in with ElectricSheep.

## Recovery

If a previous beta session causes stale local auth, use Reset Local Session on
the sign-in screen or remove only the Workbench session item:

\`\`\`bash
security delete-generic-password \\
  -s com.electricsheephq.EvaDesktop.session \\
  -a desktop-session
\`\`\`
EOF
}

write_release_zip() {
  rm -f "$RELEASE_ZIP"
  mkdir -p "$RELEASE_STAGING_DIR"
  rm -rf "$RELEASE_STAGING_DIR/$APP_BUNDLE_NAME.app"
  cp -R "$APP_BUNDLE" "$RELEASE_STAGING_DIR/"
  (
    cd "$RELEASE_STAGING_DIR"
    /usr/bin/ditto -c -k --norsrc --keepParent "$APP_BUNDLE_NAME.app" "$RELEASE_ZIP"
  )
}

write_sparkle_appcast() {
  local archive_dir="$DIST_DIR/sparkle-updates"
  local generate_appcast="$ROOT_DIR/.build/artifacts/sparkle/Sparkle/bin/generate_appcast"
  local archive_name
  archive_name="$(basename "$RELEASE_ZIP")"

  if [ ! -x "$generate_appcast" ]; then
    echo "Sparkle generate_appcast tool was not found at $generate_appcast" >&2
    exit 2
  fi

  rm -rf "$archive_dir"
  mkdir -p "$archive_dir"
  cp "$RELEASE_ZIP" "$archive_dir/$archive_name"
  cat > "$archive_dir/${archive_name%.zip}.html" <<EOF
<h2>evaOS Workbench $VERSION</h2>
<ul>
  <li>Adds Desktop Control Engine V2 with customer-granted Full Access and Ask Permission modes.</li>
  <li>Expands OpenClaw and Hermes Mac/iPhone tools for screen, mouse, keyboard, browser, and iPhone Mirroring workflows.</li>
  <li>Keeps private VM-to-Mac pairing, visible session state, audit logs, and the Workbench kill switch.</li>
</ul>
EOF

  local key_args=()
  if [ -f "$SPARKLE_PRIVATE_KEY_FILE" ]; then
    key_args+=(--ed-key-file "$SPARKLE_PRIVATE_KEY_FILE")
  else
    key_args+=(--account "$SPARKLE_KEY_ACCOUNT")
  fi

  "$generate_appcast" \
    "${key_args[@]}" \
    --download-url-prefix "https://www.electricsheephq.com/evaos-workbench/" \
    --release-notes-url-prefix "https://www.electricsheephq.com/evaos-workbench/" \
    --link "$UPDATE_RELEASE_NOTES_URL" \
    -o "$APPCAST_OUTPUT" \
    "$archive_dir"
  python3 - "$APPCAST_OUTPUT" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text()
text = text.replace("<title>EvaDesktop</title>", "<title>evaOS Workbench</title>", 1)
text = text.replace("<title>evaOS</title>", "<title>evaOS Workbench</title>", 1)
path.write_text(text)
PY
  echo "Created Sparkle appcast: $APPCAST_OUTPUT"
}

package_release() {
  write_release_install_notes
  write_release_zip
  write_update_manifest "$RELEASE_ZIP" "release"
  write_sparkle_appcast
  codesign --verify --deep --strict "$APP_BUNDLE"
  echo "Created release artifact: $RELEASE_ZIP"
  echo "Created update manifest: $BETA_UPDATE_MANIFEST"
  echo "Created Sparkle appcast: $APPCAST_OUTPUT"
  echo "Created compatibility manifest copy: $BETA_UPDATE_MANIFEST_COMPAT"
  echo "Update manifest URL expected by app: $UPDATE_MANIFEST_URL"
  echo "Sparkle appcast URL expected by app: $SPARKLE_APPCAST_URL"
  echo "Signing identity: $SIGNING_IDENTITY"
  echo "Signing label: ${SIGNING_LABEL:-unknown}"
  if [ -n "$SIGNING_KEYCHAIN" ]; then
    echo "Signing keychain: $SIGNING_KEYCHAIN"
  fi
}

notarize_release() {
  package_release

  local auth_args=(--keychain-profile "$NOTARY_PROFILE")
  if [ -n "$NOTARY_KEYCHAIN" ]; then
    auth_args+=(--keychain "$NOTARY_KEYCHAIN")
  fi

  local submit_json="$DIST_DIR/notarization-submit.json"
  xcrun notarytool submit "$RELEASE_ZIP" "${auth_args[@]}" --output-format json --no-progress > "$submit_json"
  local submission_id
  submission_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("id",""))' "$submit_json")"
  if [ -z "$submission_id" ]; then
    echo "Notary submission did not return an id. See $submit_json" >&2
    exit 2
  fi
  echo "Submitted notarization: $submission_id"
  local artifact_sha
  artifact_sha="$(shasum -a 256 "$RELEASE_ZIP" | awk '{print $1}')"
  python3 - "$submission_id" "$artifact_sha" "$RELEASE_ZIP" "$VERSION" "$BUILD_NUMBER" "$NOTARY_TIMEOUT" > "$NOTARY_RELEASE_JSON" <<'PY'
import json
import pathlib
import sys
submission_id, artifact_sha, artifact, version, build, timeout = sys.argv[1:]
print(json.dumps({
    "submission_id": submission_id,
    "artifact": str(pathlib.Path(artifact).resolve()),
    "artifact_sha256": artifact_sha,
    "version": version,
    "build": build,
    "notary_timeout": timeout,
    "status": "submitted",
}, indent=2))
PY
  echo "Submission metadata: $NOTARY_RELEASE_JSON"

  set +e
  xcrun notarytool wait "$submission_id" "${auth_args[@]}" --timeout "$NOTARY_TIMEOUT" --output-format json --no-progress > "$NOTARY_STATUS_JSON"
  local wait_status=$?
  set -e
  if [ "$wait_status" -ne 0 ]; then
    xcrun notarytool info "$submission_id" "${auth_args[@]}" --output-format json > "$NOTARY_STATUS_JSON" || true
  fi

  local notary_status
  notary_status="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status",""))' "$NOTARY_STATUS_JSON" 2>/dev/null || true)"
  if [ "$notary_status" != "Accepted" ]; then
    echo "Notarization status: ${notary_status:-unknown}. Apple will continue processing if status is In Progress."
    echo "Submission id: $submission_id"
    echo "Status file: $NOTARY_STATUS_JSON"
    if [ "$notary_status" = "Invalid" ] || [ "$notary_status" = "Rejected" ]; then
      xcrun notarytool log "$submission_id" "${auth_args[@]}" "$NOTARY_LOG_JSON" || true
      echo "Notarization log: $NOTARY_LOG_JSON" >&2
      exit 2
    fi
    exit 75
  fi

  xcrun notarytool log "$submission_id" "${auth_args[@]}" "$NOTARY_LOG_JSON" || true
  xcrun stapler staple "$APP_BUNDLE"
  xcrun stapler validate "$APP_BUNDLE"
  write_release_zip
  write_update_manifest "$RELEASE_ZIP" "release"
  write_sparkle_appcast
  local final_artifact_sha
  final_artifact_sha="$(shasum -a 256 "$RELEASE_ZIP" | awk '{print $1}')"
  python3 - "$submission_id" "$final_artifact_sha" "$RELEASE_ZIP" "$VERSION" "$BUILD_NUMBER" "$NOTARY_TIMEOUT" > "$NOTARY_RELEASE_JSON" <<'PY'
import json
import pathlib
import sys
submission_id, artifact_sha, artifact, version, build, timeout = sys.argv[1:]
print(json.dumps({
    "submission_id": submission_id,
    "artifact": str(pathlib.Path(artifact).resolve()),
    "artifact_sha256": artifact_sha,
    "version": version,
    "build": build,
    "notary_timeout": timeout,
    "status": "accepted",
}, indent=2))
PY
  codesign --verify --deep --strict "$APP_BUNDLE"
  spctl --assess --type execute "$APP_BUNDLE"
  echo "Created notarized release artifact: $RELEASE_ZIP"
  echo "Created update manifest: $BETA_UPDATE_MANIFEST"
  echo "Created Sparkle appcast: $APPCAST_OUTPUT"
}

open_app() {
  /usr/bin/open -n "$APP_BUNDLE"
}

case "$MODE" in
  run)
    open_app
    ;;
  --debug|debug)
    lldb -- "$APP_BINARY"
    ;;
  --logs|logs)
    open_app
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_EXECUTABLE_NAME\""
    ;;
  --telemetry|telemetry)
    open_app
    /usr/bin/log stream --info --style compact --predicate "subsystem == \"$BUNDLE_ID\""
    ;;
  --verify|verify)
    open_app
    sleep 1
    pgrep -x "$APP_EXECUTABLE_NAME" >/dev/null
    ;;
  --package-beta|package-beta)
    package_beta
    ;;
  --package-release|package-release)
    package_release
    ;;
  --notarize-release|notarize-release)
    notarize_release
    ;;
  *)
    echo "usage: $0 [run|--debug|--logs|--telemetry|--verify|--package-beta|--package-release|--notarize-release]" >&2
    exit 2
    ;;
esac
