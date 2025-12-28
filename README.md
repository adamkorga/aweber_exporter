# AWeber Broadcast Exporter

A simple Python tool to export all your AWeber broadcasts (sent, scheduled, and drafts) into a clean, single Markdown file useful for analyzing own newsletter history. Data file can be easily imported into LLM (pick your poison ;) ) for review.

It handles OAuth authorization, pagination, and extracts preview text hidden in HTML headers.

## Prerequisites

1.  **AWeber Labs Account:** You need a free developer account at [labs.aweber.com](https://labs.aweber.com/).
2.  **App Credentials:** Create an app in AWeber Labs with `https://localhost` as the **OAuth Redirect URI** / **Callback URL**. Grab the `Client ID` and `Client Secret`.

## Setup

1.  **Clone & Venv:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    pip install -r requirements.txt
    ```

2.  **Configuration:**
    Run `cp .env.dist .env` and update AWEBER_CLIENT_ID and AWEBER_CLIENT_SECRET.

## Usage

1.  Run the script:
    ```bash
    python aweber_dumper.py
    ```
2.  Follow the instructions in the console to authorize the app via your browser.
3.  The script will cache the token locally (`aweber_token.json`) for future runs.

## Notes

* **OS Support:** Developed and tested on Linux. It *should* work on Windows, but no promises.
* **Scopes:** The script requests `account.read`, `list.read`, and `email.read` permissions.