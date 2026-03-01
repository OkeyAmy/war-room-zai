"""
WAR ROOM — Test Ping: GCP Firestore
Verifies that your GCP credentials are valid and can reach Firestore.
Tests both read and write operations.
"""

import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


def test_gcp_project_id_exists():
    """Check that GCP_PROJECT_ID is set."""
    project_id = os.environ.get("GCP_PROJECT_ID", "")
    assert project_id, "GCP_PROJECT_ID is not set in .env"
    assert project_id != "your-gcp-project-id", "GCP_PROJECT_ID is still the placeholder"
    print(f"  ✅ GCP_PROJECT_ID is set: {project_id}")


def test_gcp_credentials_path():
    """Check that GOOGLE_APPLICATION_CREDENTIALS points to a valid file."""
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not creds_path:
        print("  ⚠️ GOOGLE_APPLICATION_CREDENTIALS not set — will use default credentials")
        return

    # Resolve relative path
    if not os.path.isabs(creds_path):
        creds_path = os.path.join(os.path.dirname(__file__), "..", creds_path)

    assert os.path.exists(creds_path), f"Service account file not found: {creds_path}"
    print(f"  ✅ Credentials file exists: {creds_path}")


def test_firestore_write():
    """Write a test document to Firestore to verify credentials."""
    # Skip if using emulator (free local)
    emulator = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if emulator:
        print(f"  ⚠️ FIRESTORE_EMULATOR_HOST is set ({emulator}) — skipping live write test")
        print("     To test live Firestore, remove or comment out FIRESTORE_EMULATOR_HOST in .env")
        return

    from google.cloud import firestore

    db = firestore.Client()
    test_id = f"ping_{uuid.uuid4().hex[:8]}"

    # Write
    doc_ref = db.collection("_ping_tests").document(test_id)
    doc_ref.set({
        "message": "WAR ROOM test ping",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
    })
    print(f"  ✅ Firestore WRITE succeeded (doc: _ping_tests/{test_id})")

    # Read back
    doc = doc_ref.get()
    assert doc.exists, "Document was written but could not be read back"
    data = doc.to_dict()
    assert data["status"] == "ok"
    print(f"  ✅ Firestore READ succeeded: {data}")

    # Cleanup
    doc_ref.delete()
    print(f"  ✅ Firestore DELETE succeeded (cleaned up test doc)")


def test_firestore_emulator_connection():
    """If emulator is configured, verify it's reachable."""
    emulator = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if not emulator:
        print("  ℹ️  No emulator configured — using live Firestore (costs may apply)")
        return

    import socket
    host, port = emulator.split(":")
    try:
        sock = socket.create_connection((host, int(port)), timeout=3)
        sock.close()
        print(f"  ✅ Firestore emulator is reachable at {emulator}")
    except (ConnectionRefusedError, socket.timeout, OSError):
        print(f"  ⚠️ Firestore emulator at {emulator} is NOT running")
        print(f"     Start it with: gcloud emulators firestore start --host-port={emulator}")
        print(f"     Or remove FIRESTORE_EMULATOR_HOST from .env to use live Firestore")


def test_gcp_project_accessible():
    """Verify the GCP project is accessible with current credentials."""
    emulator = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if emulator:
        print(f"  ⚠️ Emulator mode — skipping GCP project access check")
        return

    try:
        from google.cloud import firestore
        db = firestore.Client()
        # Just listing collections validates the connection
        collections = list(db.collections())
        print(f"  ✅ GCP project accessible. Found {len(collections)} root collections.")
    except Exception as e:
        print(f"  ❌ Cannot access GCP project: {e}")
        raise


if __name__ == "__main__":
    print("\n☁️ WAR ROOM — GCP Firestore Ping Test\n" + "=" * 45)

    tests = [
        ("GCP Project ID", test_gcp_project_id_exists),
        ("Credentials File", test_gcp_credentials_path),
        ("Firestore Emulator", test_firestore_emulator_connection),
        ("Firestore Write/Read", test_firestore_write),
        ("GCP Project Access", test_gcp_project_accessible),
    ]

    passed = 0
    failed = 0
    skipped = 0
    for name, test_fn in tests:
        try:
            print(f"\n🧪 {name}...")
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1

    print(f"\n{'=' * 45}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("🎉 All GCP tests passed!")
    else:
        print("⚠️  Some tests failed — check your GCP credentials")
