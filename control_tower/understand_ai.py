"""Optional: a language model that helps understand unusual wording, and does nothing else.

It is asked one thing: "which of these fixed questions is this closest to?" It is sent the person's question and the
list of fixed questions. It is never sent the findings or any data, and it writes none of the answer: the answer is
still built from the findings by fixed patterns (ask.py). It is off unless the person switches it on, and it is only
consulted when the word list did not understand the question.

Needs an API key in the environment (OPENAI_API_KEY). With no key there is no switch and nothing is ever sent.
"""
import json
import os
import urllib.error
import urllib.request

from .ask import INTENTS, words_of

MODEL = os.environ.get("READYSET_UNDERSTAND_MODEL") or "gpt-4o-mini"
URL = "https://api.openai.com/v1/chat/completions"


def available():
    return bool(os.environ.get("OPENAI_API_KEY"))


def make_router(call=None):
    """A function: question text -> the id of the fixed question it is closest to, or None. One answer per wording is
    kept for as long as the page runs, so asking again never gives a different reading."""
    if call is None and not available():
        return None
    call = call or _ask_model
    kept = {}
    ids = [i for i, _, _ in INTENTS]

    def route(text):
        key = " ".join(words_of(text))
        if key not in kept:
            try:
                said = str(call(str(text)[:500]) or "").strip().strip('."\'` ').lower()
            except (OSError, ValueError, KeyError, IndexError, TypeError):
                return None                                   # no network, bad key: fall back to "I cannot answer that"
            kept[key] = said if said in ids else None
        return kept[key]
    return route


def _ask_model(text):
    menu = "\n".join(f"{i}: {title}" for i, title, _ in INTENTS)
    body = {"model": MODEL, "temperature": 0, "max_tokens": 8, "messages": [
        {"role": "system", "content":
            "You route a researcher's question about a comparison of two releases of a research dataset to one of a fixed "
            "list of questions. Reply with only the id of the closest question, or the word none if none is close or the "
            "question is about anything else (including patient care, treatment or outcomes). Never answer the question.\n\n" + menu},
        {"role": "user", "content": text}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode("utf-8"), method="POST", headers={
        "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.load(r)["choices"][0]["message"]["content"]
