#!/usr/bin/env python3
"""
Create LinkedIn Session File from Cookie
"""
import sys
import json
from pathlib import Path

def create_session():
    print("="*60)
    print("LinkedIn Cookie Session Creator")
    print("="*60)
    print("\nSince you are running in a headless cloud environment, you cannot")
    print("view the graphical Chrome window directly.")
    print("\nTo log in, please provide your LinkedIn 'li_at' cookie from your")
    print("local computer's browser.")
    print("\nHow to get your li_at cookie:")
    print("1. Open standard Chrome on your local computer")
    print("2. Log in to LinkedIn (https://www.linkedin.com)")
    print("3. Press F12 to open Developer Tools")
    print("4. Go to Application > Storage > Cookies > https://www.linkedin.com")
    print("5. Double click the 'li_at' row and copy its Value")
    
    try:
        li_at = input("\nPaste your li_at cookie value here: ").strip()
    except KeyboardInterrupt:
        print("\nCancelled.")
        return

    if not li_at:
        print("No cookie provided. Exiting.")
        return
        
    data = {
        "cookies": [
            {
                "name": "li_at",
                "value": li_at,
                "domain": ".linkedin.com",
                "path": "/",
                "expires": -1,
                "httpOnly": True,
                "secure": True,
                "sameSite": "None"
            }
        ],
        "origins": []
    }

    session_path = Path("linkedin_session.json")
    with open(session_path, "w") as f:
        json.dump(data, f, indent=2)

    print("\n" + "="*60)
    print("✅ Success! Session file created.")
    print("="*60)
    print(f"\nSession saved to: {session_path}")
    print("\nYou can now run your scraping scripts like:")
    print("  python samples/scrape_jobs.py")
    print("="*60 + "\n")

if __name__ == "__main__":
    create_session()
