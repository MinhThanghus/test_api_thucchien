"""Run in a local terminal; secrets are entered without echo and never saved."""
import argparse
import getpass
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.thucchien.ai"
OUT = Path(__file__).resolve().parent / "evidence"


def request(url, key, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return response.status, json.load(response), response.headers
    except urllib.error.HTTPError as error:
        # Do not print server error bodies, which may contain credentials.
        raise SystemExit(f"HTTP {error.code}: request failed; check credentials/access with BTC.")
    except (urllib.error.URLError, TimeoutError):
        raise SystemExit("Network error or timeout. Do not automatically retry a paid request.")


def save(name, value):
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="Exact low-cost chat model granted to the team")
    args = parser.parse_args()
    key = os.environ.get("GATEWAY_KEY") or getpass.getpass("Gateway key (hidden): ")
    if not key or key != key.strip() or key.endswith("\\"):
        raise SystemExit("Invalid key formatting. Paste the original key from the exam page.")
    status, body, _ = request(BASE + "/key/info", key)
    info = body.get("info", body)
    safe = {k: info[k] for k in ("models", "spend", "max_budget", "team_id", "rpm_limit", "tpm_limit") if k in info}
    save("01-key-info.json", {"http_status": status, "info": safe})
    team_id = info.get("team_id")
    remaining = None
    team = {}
    if team_id:
        status, body, _ = request(BASE + "/team/info?" + urllib.parse.urlencode({"team_id": team_id}), key)
        team = body.get("team_info", {})
        safe_team = {k: team[k] for k in ("models", "spend", "max_budget", "rpm_limit", "tpm_limit") if k in team}
        save("01-team-budget.json", {"http_status": status, "team_info": safe_team})
        if team.get("max_budget") is not None and team.get("spend") is not None:
            remaining = float(team["max_budget"]) - float(team["spend"])
    if not args.model:
        print("Rerun with --model EXACT_MODEL from BTC's documentation. Model lists may include access groups; Gateway validates access. No paid call made.")
        return
    # key/team model lists may contain access groups instead of model IDs.
    # Only Gateway can resolve those groups and enforce the actual permissions.
    if remaining is None or remaining < 0.01:
        raise SystemExit("Cannot confirm at least $0.01 of remaining team budget. No paid call made.")
    print("Sending one chat request; Gateway will validate model access.")
    status, body, headers = request(BASE + "/chat/completions", key, {
        "model": args.model,
        "messages": [{"role": "user", "content": "Xin chào từ đội E2Hero. Trả lời một câu ngắn."}],
        "max_tokens": 256,
    })
    choices = body.get("choices", [])
    if not choices or not choices[0].get("message", {}).get("content"):
        raise SystemExit("Response did not contain choices[0].message.content. No success evidence saved.")
    save("01-chat.json", {"http_status": status, "model": args.model,
        "choices": [{"message": {"content": choices[0]["message"]["content"]}}],
        "cost_usd": headers.get("x-litellm-response-cost")})


if __name__ == "__main__":
    main()
