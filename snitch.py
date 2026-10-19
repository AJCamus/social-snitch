#!/usr/bin/env python3
"""
The Social Snitch — polls Aaron's socials for new comments, prioritizes them,
and prints a digest. Run on a schedule (cron); quiet unless there's action.

Sources: The Smile Virus FB page, Aaron's personal FB timeline, @the.smile.virus IG.
Classification: NEEDS YOU (questions, long comments) / HATER PLAYS (negativity)
                / NOISE (everything else, summarized).

Usage: snitch.py [--force]   # --force ignores the interval gate
Config: config.json next to this script: interval_minutes, quiet_until (ISO or null)
State: state.json next to this script: last_run, seen comment ids
"""
import json, os, re, subprocess, sys, time
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
FB = "/opt/hatch/bin/facebook-cli"
IG = "/opt/hatch/bin/instagram-cli"
PAGE_ID = "1301936386340842"
FB_USER_ID = "636243420"
IG_ACCOUNT_ID = "17841479843683258"
IG_USERNAME = "the.smile.virus"

HATER_RE = re.compile(
    r"\b(hate|stupid|dumb|idiot|moron|fake|scam|trash|garbage|sucks|suck|"
    r"terrible|awful|horrible|worst|lame|cringe|slop|soulless|talentless|"
    r"kill|die|shut up|loser|clown|joke)\b", re.I)

def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def run(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return json.loads(out.stdout) if out.stdout.strip() else {}
    except Exception:
        return {}

DEBUG_LOGGED = {"done": False}

def log_comment_shape(c):
    """Log the raw keys of one comment so we can fix parsing. Once only."""
    if DEBUG_LOGGED["done"]:
        return
    DEBUG_LOGGED["done"] = True
    try:
        with open(os.path.join(HERE, "comment-shape-debug.json"), "w") as f:
            json.dump(c, f, indent=1, default=str)
    except Exception:
        pass

def pick_author(c):
    for k in ("author_name", "username", "author", "from", "commenter"):
        v = c.get(k)
        if isinstance(v, dict):
            v = v.get("name") or v.get("username")
        if v:
            return str(v)
    return "someone"

def get(d, *keys):
    """First present key, trying nested 'data' wrappers."""
    for k in keys:
        if isinstance(d, dict) and k in d and d[k]:
            return d[k]
    return None

def fb_comments_on(post_id):
    d = run([FB, "post", "comments", "read", "--post-id", post_id, "--limit", "25"])
    items = []
    data = get(d, "data") or []
    post_url = (d.get("summary") or {}).get("post_url", "")
    for c in data:
        if not isinstance(c, dict):
            continue
        log_comment_shape(c)
        cid = str(c.get("comment_id") or c.get("id") or "")
        text = c.get("text") or c.get("message") or c.get("comment_text") or ""
        author = pick_author(c)
        url = c.get("comment_url") or c.get("url") or post_url
        if not url.startswith("http"):
            url = "https://" + url.lstrip("/")
        items.append({"id": "fb:" + cid, "author": str(author),
                      "text": str(text), "url": url})
    time.sleep(1)  # be gentle with the API
    return items, post_url

def ig_comments_on(media_id):
    d = run([IG, "fetch-post-comments", "--account-id", IG_ACCOUNT_ID,
             "--post-ids", media_id])
    items = []
    for pg in (d.get("post_groups") or []):
        for c in (pg.get("comments") or []):
            if not isinstance(c, dict):
                continue
            cid = str(c.get("comment_id") or c.get("id") or c.get("pk") or "")
            text = c.get("text") or ""
            author = c.get("username") or (c.get("user") or {}).get("username", "someone") \
                if isinstance(c.get("user"), dict) else "someone"
            url = f"https://www.instagram.com/p/{media_id}/"
            items.append({"id": "ig:" + cid, "author": str(author),
                          "text": str(text), "url": url})
    time.sleep(1)
    return items

def classify(text):
    t = text.strip()
    if not t:
        return "noise"
    if HATER_RE.search(t):
        return "hater"
    if "?" in t or len(t.split()) > 12:
        return "needs_you"
    return "noise"

def main():
    force = "--force" in sys.argv
    config = load_json(os.path.join(HERE, "config.json"),
                       {"interval_minutes": 5, "quiet_until": None})
    state = load_json(os.path.join(HERE, "state.json"),
                      {"last_run": None, "seen": []})
    now = datetime.now(timezone.utc)

    if not force:
        qu = config.get("quiet_until")
        if qu:
            try:
                if now < datetime.fromisoformat(qu):
                    return  # quiet weekend mode
            except ValueError:
                pass
        lr = state.get("last_run")
        if lr:
            try:
                elapsed = (now - datetime.fromisoformat(lr)).total_seconds() / 60
                if elapsed < config.get("interval_minutes", 5):
                    return  # not time yet
            except ValueError:
                pass

    seen = set(state.get("seen", []))
    buckets = {"needs_you": [], "hater": [], "noise": []}

    def harvest(items, post_label, post_url):
        for c in items:
            if not c["id"] or c["id"] in seen:
                continue
            seen.add(c["id"])
            c["post"] = post_label
            if not c["url"]:
                c["url"] = post_url
            buckets[classify(c["text"])].append(c)

    # 1. FB page posts
    d = run([FB, "pages", "posts", "list", "--page-id", PAGE_ID, "--limit", "10"])
    for p in (d.get("results") or []):
        oid = p.get("object_id")
        if not oid:
            continue
        label = "Page: " + (p.get("metadata") or {}).get("caption_excerpt", "")[:50]
        comments, purl = fb_comments_on(str(oid))
        harvest(comments, label, purl)

    # 2. Personal timeline
    d = run([FB, "timeline", "fetch", "--profile-id", FB_USER_ID, "--limit", "5"])
    for p in (d.get("posts") or []):
        pid = p.get("post_id")
        if not pid or str(p.get("author_id")) != FB_USER_ID:
            continue
        label = "Wall: " + str(p.get("post_caption") or "")[:50]
        comments, purl = fb_comments_on(str(pid))
        harvest(comments, label, purl or p.get("url") or "")

    # 3. Instagram
    d = run([IG, "posts", "--account-id", IG_ACCOUNT_ID,
             "--username", IG_USERNAME, "--limit", "10"])
    for p in (d.get("posts") or []):
        if not p.get("comments"):
            continue
        label = "IG: " + str(p.get("post_caption") or "")[:50]
        harvest(ig_comments_on(str(p.get("post_id"))), label,
                p.get("url") or "")

    # trim seen list so state doesn't grow forever
    state["seen"] = sorted(seen)[-2000:]
    state["last_run"] = now.isoformat()
    with open(os.path.join(HERE, "state.json"), "w") as f:
        json.dump(state, f)

    action = buckets["needs_you"] + buckets["hater"]
    if not action and not buckets["noise"]:
        return  # nothing new at all — stay silent
    if not action:
        return  # only noise — stay silent (digest loves signal, not static)

    local = now.astimezone().strftime("%Y-%m-%d %H:%M %Z")
    print(f"SNITCH DIGEST — {local}")
    print()
    if buckets["needs_you"]:
        print(f"NEEDS YOU ({len(buckets['needs_you'])}):")
        for c in buckets["needs_you"]:
            print(f"- {c['author']} on {c['post']}: \"{c['text'][:140]}\"")
            print(f"  [Open]({c['url']})")
        print()
    if buckets["hater"]:
        print(f"HATER PLAYS ({len(buckets['hater'])}):")
        for c in buckets["hater"]:
            print(f"- {c['author']} on {c['post']}: \"{c['text'][:140]}\"")
            print(f"  [Open]({c['url']})")
        print()
    if buckets["noise"]:
        print(f"Also: {len(buckets['noise'])} low-key reactions not needing you.")

if __name__ == "__main__":
    main()
