import sys
from installer.common import paths
from installer.common.container import find_version_image_tar, detect_engine, load_image


def load_version_container_best_effort() -> None:
    vr = paths.version_root()
    tar = find_version_image_tar(vr)
    if not tar:
        print("ℹ️ No version-specific image tarball found under images/. Skipping load.")
        return
    print(f"🔧 Found version image: {tar}")
    try:
        engine = detect_engine()
        print(f"🔧 Loading image with: {engine}")
        load_image(engine, tar)
        print("✔️ Version image loaded successfully.")
    except Exception as e:
        print(f"❌ ERROR: image load failed: {e}", file=sys.stderr)
