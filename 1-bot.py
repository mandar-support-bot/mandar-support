#!/usr/bin/env python3
"""MANDAR SUPPORT - Discord community bot.

Anti-spam (links / file uploads / scam) + FAQ auto-replies in Egyptian Arabic.
All reply texts, keywords, exempt roles and channel names live in config.json
so they can be edited without touching this file.
"""

import asyncio
import json
import logging
import os
import re
import time
import unicodedata
from datetime import timedelta

import discord
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mandar-support")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config():
    with open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8") as f:
        return json.load(f)


CFG = load_config()

# ---------------------------------------------------------------------------
# Text normalization (Egyptian Arabic chat text)
# ---------------------------------------------------------------------------
_AR_DIACRITICS = re.compile(r"[ً-ٟـ]")
_WS = re.compile(r"\s+")

LINK_RE = re.compile(
    r"(https?://|www\.|discord\.gg/|discord\.com/invite/)", re.IGNORECASE
)


def norm(text):
    """Normalize Arabic/Latin chat text so keyword matching ignores spelling noise."""
    t = (text or "").lower()
    t = _AR_DIACRITICS.sub("", t)
    for src, dst in (
        ("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"),
        ("ى", "ي"), ("ئ", "ي"), ("ؤ", "و"), ("ة", "ه"),
    ):
        t = t.replace(src, dst)
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return _WS.sub(" ", t).strip()


def fold(name):
    """Fold a channel/role name for matching (handles stylized unicode letters)."""
    return unicodedata.normalize("NFKC", name or "").casefold()


def match_groups(text_n, groups):
    """True when every non-empty keyword group has at least one hit."""
    groups = [g for g in groups if g]
    if not groups:
        return False
    return all(any(k in text_n for k in g) for g in groups)


# Normalized keyword tables, built once at startup
INTENTS = {
    key: [ [norm(k) for k in group] for group in spec.get("keywords", []) ]
    for key, spec in CFG["faq"].items()
}
SCAM_WORDS = [norm(k) for k in CFG["spam"]["scam_keywords"]]
YES_WORDS = [norm(k) for k in CFG["dialog"]["yes_words"]]
NO_WORDS = [norm(k) for k in CFG["dialog"]["no_words"]]
OLD_WORDS = [norm(k) for k in CFG["dialog"]["old_words"]]
NEW_WORDS = [norm(k) for k in CFG["dialog"]["new_words"]]
QUESTION_HINTS = [norm(k) for k in CFG["dialog"]["question_hints"]]


# ---------------------------------------------------------------------------
# Multi-turn dialog state, keyed by (guild, channel, user)
# ---------------------------------------------------------------------------
class Dialogs:
    def __init__(self, ttl_seconds=300):
        self.ttl = ttl_seconds
        self._d = {}

    def _key(self, msg):
        return (msg.guild.id, msg.channel.id, msg.author.id)

    def get(self, msg):
        st = self._d.get(self._key(msg))
        if st and st["expires"] < time.time():
            del self._d[self._key(msg)]
            return None
        return st

    def set(self, msg, flow, **data):
        self._d[self._key(msg)] = {
            "flow": flow,
            "expires": time.time() + self.ttl,
            **data,
        }

    def clear(self, msg):
        self._d.pop(self._key(msg), None)


DIALOGS = Dialogs(ttl_seconds=CFG["dialog"]["state_ttl_seconds"])
OWNER_CACHE = {}          # guild_id -> discord.Member or None
ROUTE_COOLDOWN = {}       # user_id -> last routed timestamp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def find_channel(guild, configured_name, fallback_word):
    for ch in guild.text_channels:
        if ch.name == configured_name:
            return ch
    for ch in guild.text_channels:
        if fallback_word in fold(ch.name):
            return ch
    return None


def ticket_mention(guild):
    ch = find_channel(guild, CFG["ticket_channel_name"], "ticket")
    return ch.mention if ch else CFG["ticket_channel_name"]


def fmt(template, guild=None, owner=None, user=None):
    out = template
    if guild is not None:
        out = out.replace("{ticket}", ticket_mention(guild))
    if owner is not None:
        out = out.replace("{owner}", owner.mention)
    if user is not None:
        out = out.replace("{user}", user.mention)
    return out


async def send_log(guild, text):
    ch = find_channel(guild, CFG["log_channel_name"], "log")
    if ch:
        try:
            await ch.send(text)
        except Exception as exc:
            log.warning("could not post to log channel: %s", exc)
    else:
        log.warning("log channel %r not found; entry dropped", CFG["log_channel_name"])


async def resolve_owner(guild):
    if guild.id in OWNER_CACHE:
        return OWNER_CACHE[guild.id]
    uname = CFG["owner_username"].casefold()
    owner = discord.utils.find(
        lambda m: m.name.casefold() == uname, guild.members
    )
    if owner is None and hasattr(guild, "query_members"):
        try:
            results = await guild.query_members(CFG["owner_username"], limit=10)
            owner = discord.utils.find(
                lambda m: m.name.casefold() == uname, results
            )
        except Exception as exc:
            log.warning("owner query failed: %s", exc)
    OWNER_CACHE[guild.id] = owner
    if owner is None:
        log.warning("owner %r not found in %s yet", CFG["owner_username"], guild.name)
    return owner


def is_exempt(member):
    """Members the anti-spam system must never touch."""
    if member.bot:
        return True
    if member == member.guild.owner:
        return True
    exempt = {fold(r) for r in CFG["exempt_role_names"]}
    if any(fold(r.name) in exempt for r in member.roles):
        return True
    if CFG["spam"]["exempt_manage_messages_permission"]:
        perms = member.guild_permissions
        if perms.administrator or perms.manage_messages:
            return True
    return False


def violation_of(msg):
    """Return 'link' | 'file' | 'scam' | None."""
    if SCAM_WORDS and any(w in norm(msg.content) for w in SCAM_WORDS):
        return "scam"
    if LINK_RE.search(msg.content or ""):
        return "link"
    if msg.attachments:
        # A member mid-FAQ-dialog who was asked for a screenshot may send it.
        st = DIALOGS.get(msg)
        if st and st["flow"] in ("fps_details", "tool_confirm", "tool_which"):
            return None
        return "file"
    return None


# ---------------------------------------------------------------------------
# Anti-spam
# ---------------------------------------------------------------------------
async def punish(msg, kind):
    member = msg.author
    labels = CFG["spam"]["violation_labels"]
    label = labels.get(kind, kind)

    try:
        await msg.delete()
    except Exception as exc:
        log.warning("delete failed: %s", exc)

    days = CFG["spam"]["timeout_days"]
    timeout_ok = True
    try:
        await member.timeout(timedelta(days=days), reason=f"MANDAR SUPPORT: {kind}")
    except Exception as exc:
        timeout_ok = False
        log.warning("timeout failed for %s: %s", member, exc)

    warn = fmt(CFG["messages"]["dm_warning"], user=member).format(
        what=label, days=days, guild=msg.guild.name
    )
    dm_ok = True
    try:
        await member.send(warn)
    except Exception:
        dm_ok = False

    log_line = CFG["messages"]["log_action"].format(
        user=str(member),
        user_id=member.id,
        what=label,
        channel=getattr(msg.channel, "mention", "#?"),
        days=days,
        timeout="OK" if timeout_ok else "FAILED (role hierarchy?)",
        content=(msg.content or "")[:200] or "(no text)",
    )
    await send_log(msg.guild, log_line)
    if not dm_ok:
        await send_log(msg.guild, fmt(CFG["messages"]["dm_failed"], user=member))


# ---------------------------------------------------------------------------
# FAQ flows
# ---------------------------------------------------------------------------
def looks_like_question(text_n):
    if "؟" in text_n or "?" in text_n:
        return True
    return any(q in text_n for q in QUESTION_HINTS)


async def route_unknown(msg):
    now = time.time()
    cooldown = CFG["dialog"]["unknown_route_cooldown_seconds"]
    if now - ROUTE_COOLDOWN.get(msg.author.id, 0) < cooldown:
        return
    ROUTE_COOLDOWN[msg.author.id] = now
    owner = await resolve_owner(msg.guild)
    owner_txt = owner.mention if owner else CFG["owner_username"]
    await send_log(
        msg.guild,
        CFG["messages"]["log_unknown"].format(
            owner=owner_txt,
            user=str(msg.author),
            channel=getattr(msg.channel, "mention", "#?"),
            content=(msg.content or "")[:300],
        ),
    )
    await msg.reply(fmt(CFG["messages"]["unknown_routed"], guild=msg.guild))


async def escalate_to_owner(msg, reason_key, extra=""):
    owner = await resolve_owner(msg.guild)
    if owner is None:
        await send_log(
            msg.guild,
            f"ESCALATION (owner unresolved) from {msg.author}: {reason_key} {extra}",
        )
        await msg.reply(fmt(CFG["messages"]["escalated_no_owner"], guild=msg.guild))
        return
    text = fmt(CFG["messages"]["escalation_ping"], guild=msg.guild, owner=owner)
    text = text.format(user=msg.author.mention, reason=reason_key)
    if extra:
        text += "\n" + extra
    await msg.channel.send(text)
    await send_log(
        msg.guild,
        CFG["messages"]["log_escalation"].format(
            user=str(msg.author), reason=reason_key,
            channel=getattr(msg.channel, "mention", "#?"),
        ),
    )


async def continue_dialog(msg, st, text_n):
    flow = st["flow"]

    if flow == "keymap_version":
        if any(w in text_n for w in OLD_WORDS):
            await msg.reply(fmt(CFG["faq"]["keymapping"]["reply_old"], guild=msg.guild))
            DIALOGS.clear(msg)
        elif any(w in text_n for w in NEW_WORDS):
            await msg.reply(CFG["faq"]["keymapping"]["reply_new"])
            DIALOGS.clear(msg)
        else:
            await msg.reply(CFG["messages"]["ask_old_or_new"])
        return True

    if flow == "fps_details":
        has_version = any(w in text_n for w in OLD_WORDS + NEW_WORDS)
        has_media = bool(msg.attachments)
        long_text = len(text_n.split()) >= 8
        if has_media or long_text:
            extra = ""
            if msg.attachments:
                extra = "\n".join(a.url for a in msg.attachments[:4])
            await escalate_to_owner(msg, "مشكلة FPS", extra=extra)
            await msg.reply(fmt(CFG["messages"]["fps_escalated"], guild=msg.guild))
            DIALOGS.clear(msg)
        elif has_version:
            await msg.reply(CFG["messages"]["fps_need_details"])
        else:
            await msg.reply(CFG["messages"]["fps_need_details"])
        return True

    if flow == "tool_which":
        tool = CFG["tools"]["quality"]
        if any(norm(a) in text_n for a in tool["aliases"]):
            DIALOGS.set(msg, "tool_confirm", tool="quality", shots=[])
            await msg.reply(CFG["messages"]["tool_ask_screenshot"])
        else:
            await msg.reply(CFG["messages"]["tool_ask_which"])
        return True

    if flow == "tool_confirm":
        if msg.attachments:
            st.setdefault("shots", [])
            st["shots"].extend(a.url for a in msg.attachments[:4])
            await msg.reply(CFG["messages"]["tool_confirm_steps"])
            return True
        if any(w in text_n for w in YES_WORDS):
            extra = "\n".join(st.get("shots") or [])
            await escalate_to_owner(msg, "الأداة لا تعمل", extra=extra)
            await msg.reply(fmt(CFG["messages"]["tool_escalated"], guild=msg.guild))
            DIALOGS.clear(msg)
        elif any(w in text_n for w in NO_WORDS):
            tool = CFG["tools"]["quality"]
            steps = "\n".join(tool["steps"])
            await msg.reply(CFG["messages"]["tool_do_steps"].format(steps=steps))
            DIALOGS.clear(msg)
        else:
            await msg.reply(CFG["messages"]["tool_ask_screenshot"])
        return True

    return False


async def handle_faq(msg, text_n):
    st = DIALOGS.get(msg)
    if st:
        return await continue_dialog(msg, st, text_n)

    faq = CFG["faq"]

    if match_groups(text_n, INTENTS.get("tool_not_working", [])):
        aliases = [norm(a) for a in CFG["tools"]["quality"]["aliases"]]
        if any(a in text_n for a in aliases):
            DIALOGS.set(msg, "tool_confirm", tool="quality", shots=[])
            await msg.reply(CFG["messages"]["tool_ask_screenshot"])
        else:
            DIALOGS.set(msg, "tool_which")
            await msg.reply(CFG["messages"]["tool_ask_which"])
        return True

    if match_groups(text_n, INTENTS.get("bad_quality", [])):
        await msg.reply(fmt(faq["bad_quality"]["reply"], guild=msg.guild))
        return True

    if match_groups(text_n, INTENTS.get("file_request", [])):
        await msg.reply(fmt(faq["file_request"]["reply"], guild=msg.guild))
        return True

    if match_groups(text_n, INTENTS.get("mouse_stutter", [])):
        await msg.reply(faq["mouse_stutter"]["reply"])
        return True

    if match_groups(text_n, INTENTS.get("keymapping", [])):
        DIALOGS.set(msg, "keymap_version")
        await msg.reply(CFG["messages"]["ask_old_or_new"])
        return True

    if match_groups(text_n, INTENTS.get("fps", [])):
        DIALOGS.set(msg, "fps_details")
        await msg.reply(CFG["messages"]["fps_ask"])
        return True

    if CFG["dialog"]["route_unknown_questions"] and looks_like_question(text_n):
        await route_unknown(msg)
        return True

    return False


# ---------------------------------------------------------------------------
# Entry point for every guild message
# ---------------------------------------------------------------------------
async def handle_message(msg):
    if msg.author.bot or not msg.guild:
        return

    # Anti-spam never touches exempt members, but FAQ answers are for everyone.
    if not is_exempt(msg.author):
        kind = violation_of(msg)
        if kind:
            await punish(msg, kind)
            return

    await handle_faq(msg, norm(msg.content))


# ---------------------------------------------------------------------------
# Discord client wiring
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True   # enable in Developer Portal too
intents.members = True           # enable in Developer Portal too

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    log.info("MANDAR SUPPORT online as %s", client.user)
    avatar_path = os.path.join(BASE_DIR, CFG.get("avatar_file", "avatar.png"))
    if CFG.get("set_avatar_on_startup") and os.path.exists(avatar_path):
        try:
            with open(avatar_path, "rb") as f:
                await client.user.edit(avatar=f.read())
            log.info("avatar applied")
        except Exception as exc:
            log.warning("avatar set failed (rate limit is fine to ignore): %s", exc)
    for guild in client.guilds:
        owner = await resolve_owner(guild)
        log.info("guild %s | owner resolved: %s", guild.name, owner)
        await send_log(guild, CFG["messages"]["startup_notice"])


@client.event
async def on_message(msg):
    try:
        await handle_message(msg)
    except Exception:
        log.exception("error handling message %s", getattr(msg, "id", "?"))


# ---------------------------------------------------------------------------
# Tiny HTTP server so the host (Render) sees an open port + keep-alive pings
# ---------------------------------------------------------------------------
async def health(_request):
    return web.Response(text="MANDAR SUPPORT OK")


async def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN environment variable is not set")

    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", "10000"))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("health endpoint on :%s", port)

    await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
