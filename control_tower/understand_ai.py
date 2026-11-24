"""Optional: a language model that helps understand unusual wording, and does nothing else.

It is asked one thing: "which of these fixed questions is this closest to?" It is sent the person's question and the
list of fixed questions. It is never sent the findings or any data, and it writes none of the answer: the answer is
still built from the findings by fixed patterns (ask.py). It is off unless the person switches it on, and it is only
consulted when the word list did not understand the question.

Two ways to have one, following the event's rule "use a local model or the user's own key":
  - the user's own Anthropic API key, typed into the page (or set as ANTHROPIC_API_KEY before starting). The key is
    held in memory while the page runs. It is never written to disk, never logged and never put in the repository.
    Only the question is sent to Anthropic. The online demo works the same way: the visitor types their own key, it
    stays in that browser tab, and the request goes from the browser straight to Anthropic (see hosted/demo-shim.js);
  - a local model served by Ollama on this computer (http://localhost:11434). Nothing leaves the machine.
The user's key is used when there is one, otherwise the local model. With neither there is no switch and nothing is
ever sent anywhere.

This tool has no dependencies beyond Python's standard library, so the Claude API is called over plain HTTPS here
rather than through the Anthropic SDK.
"""
import json
import os
import urllib.error
import urllib.request

from .ask import INTENTS, words_of

MODEL = os.environ.get("READYSET_UNDERSTAND_MODEL") or "claude-opus-5-5"
API = "https://api.anthropic.com/v1/messages"
LOCAL = (os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
if not LOCAL.startswith("http"):
    LOCAL = "http://" + LOCAL
PREFERRED = ("qwen3:8b", "granite3.3:8b", "granite4:micro-h")         # open models; the first one installed is used
_found = {}


def local_model():
    """The name of a local model to use, or None when no local model server is running on this computer."""
    if "local" not in _found:
        wanted = os.environ.get("READYSET_LOCAL_MODEL")
        try:
            with urllib.request.urlopen(LOCAL + "/api/tags", timeout=0.6) as r:
                names = [m.get("name") for m in json.load(r).get("models", []) if "embed" not in str(m.get("name"))]
        except (OSError, ValueError):
            names = []
        _found["local"] = wanted if wanted in names else next((p for p in PREFERRED if p in names), names[0] if names else None)
    return _found["local"]


def looks_like_a_key(key):
    return isinstance(key, str) and key.startswith("sk-ant-") and 20 <= len(key) <= 400 and key.isprintable() and " " not in key


def available(key=None):
    """How wording can be understood with a model: "your own Anthropic key", "a local model (NAME) on this computer",
    or "" when there is neither."""
    if os.environ.get("READYSET_NO_MODEL"):
        return ""
    if key or os.environ.get("ANTHROPIC_API_KEY"):
        return "your own Anthropic key"
    name = local_model()
    return f"a local model ({name}) on this computer" if name else ""


def make_router(call=None, key=None):
    """A function: question text -> the id of the fixed question it is closest to, or None. One answer per wording is
    kept for as long as the page runs, so asking again never gives a different reading."""
    if call is None:
        how = available(key)
        if not how:
            return None
        secret = key or os.environ.get("ANTHROPIC_API_KEY")
        call = (lambda text: _ask_claude(text, secret)) if how.startswith("your own") else _ask_local
    kept = {}

    def route(text):
        wording = " ".join(words_of(text))
        if wording not in kept:
            try:
                said = call(str(text)[:500])
            except (OSError, ValueError, KeyError, IndexError, TypeError):
                return None                                   # no model, no network, bad key: "I cannot answer that"
            kept[wording] = intent_of(said)
        return kept[wording]
    return route


def _instructions():
    menu = "\n".join(f"{i}: {title}" for i, title, _ in INTENTS)
    return ("You route a researcher's question about a comparison of two releases of a research dataset to one of a fixed "
            "list of questions. Reply with only the id of the closest question (one word), or the word none if none is "
            "close or the question is about anything else (including patient care, treatment or outcomes). Never answer "
            "the question.\n\n" + menu)


def intent_of(said):
    """The id of a fixed question named in a model's reply, or None when the reply is anything else."""
    try:
        word = str(said or "").strip().split()[0].strip('.:"\'` ').lower()
    except IndexError:
        return None
    return word if word in [i for i, _, _ in INTENTS] else None


def claude_request(text):
    """The body of the one Messages request: the question and the list of fixed questions, nothing else."""
    return {"model": MODEL, "max_tokens": 2048, "system": _instructions(), "output_config": {"effort": "low"},
            "fallbacks": "default", "messages": [{"role": "user", "content": str(text)[:500]}]}


def claude_headers(key):
    return {"x-api-key": key, "anthropic-version": "2026-10-21", "anthropic-beta": "server-side-fallback-2026-07-01",
            "Content-Type": "application/json"}


def claude_reply_text(reply):
    """The words of a Messages reply. A declined request counts as "none"."""
    if reply.get("stop_reason") == "refusal":
        return "none"
    return " ".join(b.get("text", "") for b in reply.get("content", []) if isinstance(b, dict) and b.get("type") == "text")


def _ask_claude(text, key):
    """One Messages request. A declined request, or anything but a one-word reply, counts as "not understood"."""
    req = urllib.request.Request(API, data=json.dumps(claude_request(text)).encode("utf-8"), method="POST",
                                 headers=claude_headers(key))
    with urllib.request.urlopen(req, timeout=20) as r:
        return claude_reply_text(json.load(r))


def _ask_local(text):
    body = {"model": local_model(), "stream": False, "think": False, "options": {"temperature": 0, "seed": 0, "num_predict": 12},
            "messages": [{"role": "system", "content": _instructions()}, {"role": "user", "content": text}]}
    req = urllib.request.Request(LOCAL + "/api/chat", data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["message"]["content"]
