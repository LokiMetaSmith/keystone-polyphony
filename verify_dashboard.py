import time
from playwright.sync_api import sync_playwright

def verify_dashboard():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate to Dashboard
        print("Navigating to dashboard...")
        try:
            page.goto("http://localhost:8000")
        except Exception as e:
            print(f"Failed to load page: {e}")
            return

        # Wait for loading to finish
        try:
            page.wait_for_selector(".panel", timeout=5000)
            print("Dashboard loaded.")
        except Exception:
            print("Timeout waiting for .panel. Page content:")
            print(page.content())
            return

        # Check Node ID present
        content = page.content()
        if "Node ID:" in content:
            print("Node ID found.")
        else:
            print("Node ID NOT found.")

        # Take screenshot of Status tab
        print("Taking status screenshot...")
        page.screenshot(path="dashboard_status.png")

        # Click Thoughts tab
        print("Clicking Thoughts tab...")
        try:
            page.click("text=Thoughts")
            time.sleep(1) # Wait for render
            page.screenshot(path="dashboard_thoughts.png")
        except Exception as e:
            print(f"Failed to click Thoughts: {e}")

        # Click Logs tab
        print("Clicking Logs tab...")
        try:
            page.click("text=Logs")
            time.sleep(1)
            page.screenshot(path="dashboard_logs.png")
        except Exception as e:
            print(f"Failed to click Logs: {e}")

        browser.close()

if __name__ == "__main__":
    verify_dashboard()
