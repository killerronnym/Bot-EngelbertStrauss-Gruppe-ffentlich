import sys
import os
import logging

# Configure logging to capture output
logging.basicConfig(level=logging.DEBUG)

# Add paths
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "web_dashboard"))

try:
    from web_dashboard.app import app
    print("App imported successfully.")
except Exception as e:
    print(f"Failed to import app: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Mock session to bypass login
with app.test_client() as client:
    with client.session_transaction() as sess:
        sess["user"] = "admin"
        sess["role"] = "admin"
    
    print("--- Testing /id-finder ---")
    try:
        rv = client.get("/id-finder")
        print(f"Status: {rv.status_code}")
        if rv.status_code != 200:
            print(f"Response: {rv.data.decode('utf-8')[:500]}...")
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()

    print("\n--- Testing /live-moderation ---")
    try:
        rv = client.get("/live-moderation")
        print(f"Status: {rv.status_code}")
        if rv.status_code != 200:
             print(f"Response: {rv.data.decode('utf-8')[:500]}...")
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
