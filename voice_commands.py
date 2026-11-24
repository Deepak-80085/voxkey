"""Turn a spoken sentence into a command. Pure rules: no Windows calls, no I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher, get_close_matches

THRESHOLD = 0.65  # name similarity needed ("slab" -> Slack is 0.67, "slate" is 0.6)
PERSON_THRESHOLD = 0.8
AMBIGUOUS = "ambiguous"  # Command.account markers: the caller shows an error note
UNKNOWN = "unknown"

BUILTIN_SITES = {
    "YouTube": "https://www.youtube.com",
    "YouTube Music": "https://music.youtube.com",
    "GitHub": "https://github.com",
    "Gmail": "https://mail.google.com",
    "Google Meet": "https://meet.google.com",
}
_SEARCHABLE = {"slack", "whatsapp", "t3 code"}
_KEYWORDS = {"channel", "chat", "thread"}
_FILLER = {"the", "a", "an", "app", "application", "desktop"}
_ACCOUNT_FILLER = {"in", "on", "at", "of", "and", "again", "account", "profile", "chrome", "open"}
_FOLDER_BREAK = {"in", "on", "at", "to", "and", "folder", "directory"}
_FOLDER_FILLER = _FOLDER_BREAK | {"open", "the", "a", "my", "terminal", "claude", "code"}


@dataclass(frozen=True)
class Known:
    """What the user has set up. Lowercase keys in orgs; accounts are emails."""
    apps: tuple[str, ...] = ("Slack", "T3 Code", "Claude", "ChatGPT", "WhatsApp", "Chrome", "Terminal")
    sites: dict[str, str] = field(default_factory=lambda: dict(BUILTIN_SITES))
    accounts: tuple[str, ...] = ()
    self_name: str = ""
    default_account: str = ""  # used for "my account" / "<self> account" with no org word
    orgs: dict[str, str] = field(default_factory=dict)  # spoken word -> email domain
    workspaces: tuple[str, ...] = ()  # Slack workspace names


@dataclass(frozen=True)
class Command:
    kind: str  # "app" | "search" | "site" | "terminal"
    name: str = ""
    target: str = ""
    workspace: str = ""
    url: str = ""
    account: str | None = None  # email, AMBIGUOUS, UNKNOWN, or None (no account spoken)
    drive: str = ""
    words: tuple[str, ...] = ()
    run_claude: bool = False


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def _who(email: str) -> str:
    return re.split(r"[^a-z]", email.casefold(), maxsplit=1)[0]


def _find(tokens: list[str], names) -> tuple[str, int, int] | None:
    """Best fuzzy match of any name against equal-length token windows: (name, start, length)."""
    best = None
    for name in names:
        words = _tokens(name)
        for i in range(len(tokens) - len(words) + 1):
            score = SequenceMatcher(None, " ".join(tokens[i:i + len(words)]), " ".join(words)).ratio()
            key = (score, len(words), -i)
            if score >= THRESHOLD and (best is None or key > best[0]):
                best = (key, name, i, len(words))
    return best and best[1:]


def _account(words: list[str], known: Known) -> str | None:
    me = org = person = extra = None
    self_name = known.self_name.casefold()
    persons = sorted({_who(a) for a in known.accounts} | {self_name})
    for word in words:
        if word in _ACCOUNT_FILLER:
            continue
        if word == "my":
            me = True
        elif close := get_close_matches(word, list(known.orgs), 1, THRESHOLD):
            org = known.orgs[close[0]]
        elif close := get_close_matches(word, persons, 1, PERSON_THRESHOLD):
            person = close[0]
        else:
            extra = True
    if not (me or org or person):
        return UNKNOWN if extra else None
    person = person or self_name
    if org is None and person == self_name and known.default_account:
        return known.default_account
    found = [a for a in known.accounts
             if _who(a) == person and (org is None or a.casefold().endswith("@" + org))]
    return found[0] if len(found) == 1 else UNKNOWN if not found else AMBIGUOUS


def _terminal(text: str, run: bool) -> Command:
    drive, words = "", []
    for part in re.split(r"[,;.]", text):
        tokens = _tokens(part)
        if "run" in tokens:
            run = run or "claude" in tokens
            tokens = tokens[:tokens.index("run")]
        for i, token in enumerate(tokens):
            if token == "drive" and i and len(tokens[i - 1]) == 1:
                drive = tokens[i - 1]
                tokens[i - 1:i + 1] = ["", ""]
            elif re.fullmatch(r"[a-z]drive", token):
                drive, tokens[i] = token[0], ""
        phrase = [[]]  # "clients folder in AI interview" (no commas heard) is two folder words
        for token in tokens:
            if token in _FOLDER_BREAK:
                phrase.append([])
            elif token and token not in _FOLDER_FILLER:
                phrase[-1].append(token)
        words += [" ".join(p) for p in phrase if p]
    return Command("terminal", "Terminal", drive=drive, words=tuple(words), run_claude=run)


_CONNECT = {"in", "on", "at", ","}
_STRONG = 0.85  # below this a name must share its first letter and stand alone ("open slab")


def _skip(tokens: list[str]) -> list[str]:
    n = 0
    while n < len(tokens) and tokens[n] in _FILLER | {"my"}:
        n += 1
    return tokens[n:]


def _head(tokens: list[str], names) -> tuple[float, str, int] | None:
    """Best name at the very start of tokens: (score, name, token count)."""
    best = None
    for name in names:
        words = _tokens(name)
        score = SequenceMatcher(None, " ".join(tokens[:len(words)]), " ".join(words)).ratio()
        if score >= THRESHOLD and (best is None or (score, len(words)) > best[:1] + best[2:]):
            best = (score, name, len(words))
    return best


def _known_word(word: str, known: Known) -> bool:
    persons = [_who(a) for a in known.accounts] + [known.self_name.casefold()]
    return (word in ("my", "account", "profile") or bool(get_close_matches(word, list(known.orgs), 1, THRESHOLD))
            or bool(get_close_matches(word, persons, 1, PERSON_THRESHOLD))
            or bool(get_close_matches(word, list(known.workspaces), 1, THRESHOLD)))


def parse(text: str, known: Known) -> Command | None:
    """A Command only when the whole sentence is "open NAME [in/on/at ...]"; None means type it as today."""
    toks = re.findall(r"[a-z0-9]+|,", text.casefold())
    raw = [t for t in toks if t != ","]
    if not raw or raw[0] != "open":
        return None
    rest = _skip(toks[1:])
    names = [*known.apps, "Claude Code", *known.sites]
    target, pre = "", []
    head = _head(rest, names)
    if head is None:  # "open [the] <1-4 words> channel in [workspace] NAME"
        k = next((i for i, t in enumerate(rest[:5]) if t in _KEYWORDS), 0)
        if not k or "open" in rest[:k] or rest[k + 1:k + 2] != ["in"]:
            return None
        target, after = " ".join(rest[:k]), _skip(rest[k + 2:])
        for j in range(3):
            if j and not get_close_matches(after[j - 1], list(known.workspaces), 1, THRESHOLD):
                return None
            if head := _head(_skip(after[j:]), names):
                pre, rest = after[:j], _skip(after[j:])
                break
        if head is None:
            return None
    score, name, length = head
    lower = name.casefold()
    tail = _skip(rest[length:])
    if score < _STRONG and (tail or target or rest[0][0] != lower[0]):
        return None
    if lower in ("claude code", "terminal"):
        if tail and tail[0] not in _CONNECT:
            return None
        return _terminal(text, lower == "claude code" or ("run" in raw and "claude" in raw))
    if tail[:2] == ["and", "open"]:  # "open WhatsApp and open the X chat"
        more = _skip(tail[2:])
        k = next((i for i, t in enumerate(more[:5]) if t in _KEYWORDS), 0)
        if target or lower not in _SEARCHABLE or not k or k != len(more) - 1:
            return None
        return Command("search", name, target=" ".join(more[:k]))
    if tail and (tail[0] not in _CONNECT or not any(_known_word(t, known) for t in tail)):
        return None
    words = [t for t in pre + tail if t != ","]
    if name in known.sites:
        return Command("site", name, url=known.sites[name], account=_account(words, known))
    if target and lower in _SEARCHABLE:
        close = [w for r in words for w in get_close_matches(r, known.workspaces, 1, THRESHOLD)]
        return Command("search", name, target=target, workspace=close[0] if lower == "slack" and close else "")
    return Command("app", name)
