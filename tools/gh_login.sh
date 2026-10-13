#!/usr/bin/env bash
# Logowanie gh przez OAuth device flow.
# Kod jednorazowy pokazujemy użytkownikowi; token nigdy nie trafia do rozmowy —
# leci prosto z curl do `gh auth login --with-token`.
set -u

CLIENT=178c6fc778ccc68e1d6a
SCOPE="repo,read:org,gist,workflow"
GH="/c/Program Files/GitHub CLI/gh.exe"
TMP="${LOCALAPPDATA:-/tmp}/Temp"
mkdir -p "$TMP"
CODE_JSON="$TMP/gh_device.json"
STATUS="$TMP/gh_login_status.txt"

resp=$(curl -s -X POST -H "Accept: application/json" -d "client_id=$CLIENT&scope=$SCOPE" https://github.com/login/device/code)
printf '%s' "$resp" > "$CODE_JSON"

read_dev() { python -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get(sys.argv[2],''))" "$CODE_JSON" "$1"; }
DEVICE_CODE=$(read_dev device_code)
USER_CODE=$(read_dev user_code)
INTERVAL=$(read_dev interval); INTERVAL=${INTERVAL:-5}

if [ -z "$DEVICE_CODE" ] || [ -z "$USER_CODE" ]; then
  echo "BLAD: GitHub nie zwrocil kodu"; echo "$resp" > "$STATUS"; exit 1
fi
echo "KOD=$USER_CODE URL=https://github.com/login/device" > "$STATUS"
echo "code=$USER_CODE interval=${INTERVAL}s — czekam na zatwierdzenie w przegladarce"

while true; do
  sleep "$INTERVAL"
  poll=$(curl -s -X POST -H "Accept: application/json" \
    -d "client_id=$CLIENT&device_code=$DEVICE_CODE&grant_type=urn:ietf:params:oauth:grant-type:device_code" \
    https://github.com/login/oauth/access_token)
  case "$poll" in
    *access_token*)
      token=$(printf '%s' "$poll" | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
      if printf '%s' "$token" | timeout 30 "$GH" auth login --with-token 2>/dev/null; then
        echo "LOGIN_OK (with-token)" > "$STATUS"
      elif printf '%s' "$token" | timeout 30 "$GH" auth login --with-token --insecure-storage 2>/dev/null; then
        echo "LOGIN_OK (insecure-storage)" > "$STATUS"
      else
        login=$(curl -s -H "Authorization: token $token" https://api.github.com/user \
          | python -c "import json,sys; print(json.load(sys.stdin).get('login',''))")
        mkdir -p "${APPDATA:-$HOME}/GitHub CLI"
        printf 'github.com:\n    users:\n        %s:\n            oauth_token: %s\n    git_protocol: https\n    oauth_token: %s\n    user: %s\n' \
          "$login" "$token" "$token" "$login" > "${APPDATA:-$HOME}/GitHub CLI/hosts.yml"
        chmod 600 "${APPDATA:-$HOME}/GitHub CLI/hosts.yml" 2>/dev/null
        echo "LOGIN_OK (hosts.yml: $login)" > "$STATUS"
      fi
      "$GH" auth setup-git >/dev/null 2>&1
      "$GH" auth status >> "$STATUS" 2>&1
      echo "LOGIN_COMPLETE" >> "$STATUS"
      unset token poll
      exit 0 ;;
    *authorization_pending*) : ;;
    *slow_down*) INTERVAL=$((INTERVAL + 5)) ;;
    *expired_token*) echo "CODE_EXPIRED" > "$STATUS"; exit 1 ;;
    *access_denied*) echo "USER_DENIED" > "$STATUS"; exit 1 ;;
    *) echo "UNEXPECTED: $poll" > "$STATUS"; exit 1 ;;
  esac
done
