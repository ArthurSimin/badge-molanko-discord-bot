#!/usr/bin/env python3
# utils/mcskin.py

import os
import json
import re
import urllib.request
import urllib.error

email_env = os.getenv("EMAIL")
email_str = f"; <{email_env}>" if email_env else (_ for _ in ()).throw(ValueError("need email"))

USER_AGENT = f"Molankobot/1.0 (+https://git.gay/lanlan3292/molanko-discord-bot{email_str})"

def is_uuid(s: str) -> bool:
    s = s.strip()
    if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', s, re.IGNORECASE):
        return True
    if re.match(r'^[0-9a-f]{32}$', s, re.IGNORECASE):
        return True
    return False

def fetch_url(url: str, headers: dict = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req) as resp:
        return resp.read()

def get_uuid_from_mojang(name: str) -> str:
    # Primary API
    url = f"https://api.mojang.com/users/profiles/minecraft/{name}"
    try:
        data = fetch_url(url, {"User-Agent": USER_AGENT})
        info = json.loads(data.decode('utf-8'))
        return info['id']  # no dashes
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    # Fallback API
    url2 = f"https://api.minecraftservices.com/minecraft/profile/lookup/name/{name}"
    try:
        data = fetch_url(url2, {"User-Agent": USER_AGENT})
        info = json.loads(data.decode('utf-8'))
        return info['id']  # also no dashes
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Player '{name}' not found") from None
        raise

def get_player_image(player: str, img_type: str = "head") -> bytes:
    """
    Fetch Minecraft player image (head or full skin) from vzge.me.

    Args:
        player (str): Minecraft username or UUID (with/without hyphens)
        img_type (str): 'head' or 'skin' (default: 'head')

    Returns:
        bytes: PNG image data

    Raises:
        ValueError: if player not found or invalid
        Exception: on network or API errors
    """
    # Normalize UUID
    if is_uuid(player):
        uuid = player.replace('-', '')  # remove hyphens
    else:
        uuid = get_uuid_from_mojang(player)

    # Choose endpoint
    if img_type == "face":
        url = f"https://vzge.me/face/384/{uuid}"
    else:  # skin
        url = f"https://vzge.me/full/384/{uuid}"

    return fetch_url(url, {"User-Agent": USER_AGENT})