
import httpx
import sys

# Test note from user requirements
TEST_NOTE = """Property is a 3 bed / 2 bath residential home, approx 1850 sq ft, located in Denver, CO.
Modern condition, typical suburban lot.

Look for closed comps in Denver, CO.
Prioritize similar size and bed/bath count.
Goal is a defensible price range with clear rationale."""

URL = "http://localhost:8000/ui/generate"

def verify():
    print(f"Testing POST to {URL} with test note...")
    try:
        response = httpx.post(URL, data={"notes": TEST_NOTE}, timeout=30.0)
    except httpx.ConnectError:
        print("ERROR: Could not connect to localhost:8000. Is the server running?")
        sys.exit(1)

    print(f"Response Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"ERROR: Expected 200 OK, got {response.status_code}")
        print(response.text[:500])
        sys.exit(1)

    content = response.text
    
    # Check for success indicators
    if "CMA Report - Generated" in content:
        print("SUCCESS: Report page generated.")
    elif "CMA Report" in content:
        print("SUCCESS: Report page generated (found 'CMA Report').")
    else:
        print("FAILURE: Did not find 'CMA Report - Generated' in response.")
        
        # Try to extract error message
        import re
        error_match = re.search(r'<p class="text-sm text-red-700">(.*?)</p>', content)
        if error_match:
            print(f"Server returned error: {error_match.group(1)}")
        else:
            print("Could not find specific error message in HTML.")
            print("Response output dump:")
            print(content)
        sys.exit(1)

    # Check for validation errors
    if "Validation Error" in content or "validation error" in content:
        print("FAILURE: Validation error found in response.")
        print(content[:1000])
        sys.exit(1)

    print("Test passed successfully.")

if __name__ == "__main__":
    verify()
