#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
APP_NAME="EvaDesktop"
DISPLAY_NAME="evaOS Workbench"
BUNDLE_ID="com.electricsheephq.EvaDesktop"
MIN_SYSTEM_VERSION="14.0"
VERSION="0.1.4"
BUILD_NUMBER="1"
UPDATE_MANIFEST_URL="${EVA_DESKTOP_UPDATE_MANIFEST_URL:-https://www.electricsheephq.com/evaos-workbench/updates.json}"
UPDATE_RELEASE_NOTES_URL="${EVA_DESKTOP_UPDATE_RELEASE_NOTES_URL:-https://www.electricsheephq.com/evaos-workbench}"
if [ "$MODE" = "--package-release" ] || [ "$MODE" = "package-release" ] || [ "$MODE" = "--notarize-release" ] || [ "$MODE" = "notarize-release" ]; then
  DEFAULT_UPDATE_DOWNLOAD_URL="https://www.electricsheephq.com/evaos-workbench/evaOS-Workbench-$VERSION.zip"
else
  DEFAULT_UPDATE_DOWNLOAD_URL="https://www.electricsheephq.com/evaos-workbench/evaOS-Workbench-Beta-$VERSION.zip"
fi
UPDATE_DOWNLOAD_URL="${EVA_DESKTOP_UPDATE_DOWNLOAD_URL:-$DEFAULT_UPDATE_DOWNLOAD_URL}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
APP_CONTENTS="$APP_BUNDLE/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_RESOURCES="$APP_CONTENTS/Resources"
APP_BINARY="$APP_MACOS/$APP_NAME"
INFO_PLIST="$APP_CONTENTS/Info.plist"
BETA_STAGING_DIR="$DIST_DIR/beta"
BETA_INSTALL_NOTES="$BETA_STAGING_DIR/BETA_INSTALL.md"
BETA_ZIP="$DIST_DIR/evaOS-Workbench-Beta-$VERSION.zip"
RELEASE_STAGING_DIR="$DIST_DIR/release"
RELEASE_INSTALL_NOTES="$RELEASE_STAGING_DIR/INSTALL.md"
RELEASE_ZIP="$DIST_DIR/evaOS-Workbench-$VERSION.zip"
BETA_UPDATE_MANIFEST="$DIST_DIR/updates.json"
BETA_UPDATE_MANIFEST_COMPAT="$DIST_DIR/evaos-workbench-updates.json"

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

  codesign "${args[@]}" "$APP_BUNDLE"
}

cd "$ROOT_DIR"

pkill -x "$APP_NAME" >/dev/null 2>&1 || true

swift build
BUILD_BINARY="$(swift build --show-bin-path)/$APP_NAME"

rm -rf "$APP_BUNDLE"
mkdir -p "$APP_MACOS" "$APP_RESOURCES"
cp "$BUILD_BINARY" "$APP_BINARY"
chmod +x "$APP_BINARY"

if [ -d "$ROOT_DIR/Resources" ]; then
  cp -R "$ROOT_DIR/Resources/." "$APP_RESOURCES/"
fi

/usr/libexec/PlistBuddy -c "Clear dict" "$INFO_PLIST" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c "Add :CFBundleExecutable string $APP_NAME" "$INFO_PLIST"
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
2. Drag \`EvaDesktop.app\` to Applications or run it from this folder.
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
OpenClaw/Hermes tools. Live actions require a prior dry-run and matching
approval audit id. Workbench does not expose arbitrary shell, hidden AppleScript,
generic coordinates, password capture, payment/purchase automation, or generic
Codex app-server mutation.
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
    /usr/bin/ditto -c -k --norsrc --keepParent "EvaDesktop.app" "$BETA_ZIP"
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
2. Drag \`EvaDesktop.app\` to Applications.
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
  rm -rf "$RELEASE_STAGING_DIR/$APP_NAME.app"
  cp -R "$APP_BUNDLE" "$RELEASE_STAGING_DIR/"
  (
    cd "$RELEASE_STAGING_DIR"
    /usr/bin/ditto -c -k --norsrc --keepParent "EvaDesktop.app" "$RELEASE_ZIP"
    /usr/bin/zip -q "$RELEASE_ZIP" "INSTALL.md"
  )
}

package_release() {
  write_release_install_notes
  write_release_zip
  write_update_manifest "$RELEASE_ZIP" "release"
  codesign --verify --deep --strict "$APP_BUNDLE"
  echo "Created release artifact: $RELEASE_ZIP"
  echo "Created update manifest: $BETA_UPDATE_MANIFEST"
  echo "Created compatibility manifest copy: $BETA_UPDATE_MANIFEST_COMPAT"
  echo "Update manifest URL expected by app: $UPDATE_MANIFEST_URL"
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

  xcrun notarytool submit "$RELEASE_ZIP" "${auth_args[@]}" --wait
  xcrun stapler staple "$APP_BUNDLE"
  xcrun stapler validate "$APP_BUNDLE"
  write_release_zip
  write_update_manifest "$RELEASE_ZIP" "release"
  codesign --verify --deep --strict "$APP_BUNDLE"
  spctl --assess --type execute "$APP_BUNDLE"
  echo "Created notarized release artifact: $RELEASE_ZIP"
  echo "Created update manifest: $BETA_UPDATE_MANIFEST"
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
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\""
    ;;
  --telemetry|telemetry)
    open_app
    /usr/bin/log stream --info --style compact --predicate "subsystem == \"$BUNDLE_ID\""
    ;;
  --verify|verify)
    open_app
    sleep 1
    pgrep -x "$APP_NAME" >/dev/null
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
