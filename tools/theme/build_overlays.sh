#!/usr/bin/env bash
# Run on the build box (needs a synced AOSP/Lineage tree for aapt2, the API 25
# android.jar and apksigner + the AOSP test key). Builds theme/overlays/* into
# signed APKs under theme/out/. minSdk 1 keeps the explicit "-v4" qualifiers
# (aapt2 strips version qualifiers at or below minSdk).
# usage: TREE=~/android/lineage-22.2 tools/theme/build_overlays.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
TREE=${TREE:-$HOME/android/lineage-22.2}
AAPT2=$TREE/out/host/linux-x86/bin/aapt2
JAR=$TREE/prebuilts/sdk/25/public/android.jar
JAVA=$(ls -d "$TREE"/prebuilts/jdk/jdk*/linux-x86/bin/java | tail -1)
SIGNER=("$JAVA" -jar "$TREE/prebuilts/sdk/tools/linux/lib/apksigner.jar")
KEY=$TREE/build/make/target/product/security/testkey
rm -rf theme/out; mkdir -p theme/out
while read -r n; do
  t=$(mktemp -d)
  "$AAPT2" compile --dir "theme/overlays/$n/res" -o "$t/res.zip"
  "$AAPT2" link -I "$JAR" --manifest "theme/overlays/$n/AndroidManifest.xml" \
    --min-sdk-version 1 --target-sdk-version 25 --no-auto-version -o "$t/u.apk" "$t/res.zip"
  "${SIGNER[@]}" sign --key "$KEY.pk8" --cert "$KEY.x509.pem" --out "theme/out/$n.apk" "$t/u.apk"
  rm -rf "$t"
done < theme/overlays/LIST
ls -l theme/out
