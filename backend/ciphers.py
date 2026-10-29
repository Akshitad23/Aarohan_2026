"""Server-only puzzle catalog. Never send this module or its answers to a browser."""

import json
import os
import re
import secrets
from copy import deepcopy
from pathlib import Path

TECHNIQUES = ("override", "roleplay", "decomposition", "authority", "fiction", "hypothesis")


def technique_groups(index):
    """Balanced three-and-three mappings vary by challenge, not by request."""
    offset = index % len(TECHNIQUES)
    rotated = TECHNIQUES[offset:] + TECHNIQUES[:offset]
    return [list(rotated[:3]), list(rotated[3:])]


def transform(text, protocol, key=0, decode=False):
    """Encode/decode the deliberately small classical cipher set."""
    text = text.upper()
    if protocol in ("caesar", "rot13"):
        shift = 13 if protocol == "rot13" else key
        shift *= -1 if decode else 1
        return "".join(chr((ord(c) - 65 + shift) % 26 + 65) if "A" <= c <= "Z" else c for c in text)
    if protocol == "atbash":
        return "".join(chr(90 - (ord(c) - 65)) if "A" <= c <= "Z" else c for c in text)
    if protocol == "reverse":
        return text[::-1]
    if protocol == "a1z26":
        return "".join(chr(int(n) + 64) for n in text.split("-")) if decode else "-".join(str(ord(c) - 64) for c in text)
    if protocol == "odd_even":
        if not decode:
            return text[::2] + text[1::2]
        split = (len(text) + 1) // 2
        odds, evens = text[:split], text[split:]
        return "".join(odds[i] + (evens[i] if i < len(evens) else "") for i in range(split))
    raise ValueError("Unknown cipher protocol")


PROTOCOLS = {
    "caesar": {
        "name": "Caesar cipher",
        "concept": "Every letter moves the same number of positions in the alphabet, wrapping at either end.",
        "rule": "Encoding moved every letter {key} positions forward. Decode by moving {key} positions backward, wrapping from A to Z.",
        "example": "CAT",
        "understanding": r"fixed|same number|each letter|positions|move letters|circular|wrap",
    },
    "atbash": {
        "name": "Atbash cipher",
        "concept": "The alphabet pairs with its reverse, so each letter has one partner. Applying the rule twice restores the original.",
        "rule": "Pair A with Z, B with Y, C with X, continuing inward. Replace every encrypted letter with its partner.",
        "example": "CAT",
        "understanding": r"opposite|mirror|pair|reverse alphabet|reverse.*alphabet|ends",
    },
    "rot13": {
        "name": "ROT13 cipher",
        "concept": "This letter substitution rotates the 26-letter alphabet by half its length. The same operation encodes and decodes.",
        "rule": "Move each letter 13 alphabet positions, wrapping from Z to A. Applying it again recovers the word.",
        "example": "CAT",
        "understanding": r"13|thirteen|half|rotate|rotation|wrap",
    },
    "reverse": {
        "name": "Reversal cipher",
        "concept": "The letters stay the same, but their positions run in the opposite direction.",
        "rule": "Read the encrypted word from right to left. Do not replace any letters.",
        "example": "CAT",
        "understanding": r"right to left|backward|reverse|positions|order",
    },
    "a1z26": {
        "name": "A1Z26 letter-number substitution",
        "concept": "Each number identifies a letter's one-based position in the alphabet. Hyphens separate the numbers.",
        "rule": "Use A=1, B=2, continuing to Z=26. Convert each hyphen-separated number into its letter.",
        "example": "CAT",
        "understanding": r"a.?1|one.based|number|position|26",
    },
    "odd_even": {
        "name": "Odd-even transposition",
        "concept": "Letters are rearranged, rather than substituted. Encoding writes the odd-position letters followed by the even-position letters.",
        "rule": "Split the encrypted text after ceil(length/2) letters. Interleave the first half and second half, starting with the first half.",
        "example": "PLANET",
        "understanding": r"odd|even|interleave|rearrang|position|half|split",
    },
}

# Each pair has an independent protocol per word. Difficulty varies; see docs/CIPHERS.md.
_PAIRS = [
    (("ROVER", "caesar", 7), ("READY", "atbash", 0)),
    (("LUNAR", "caesar", 3), ("ORBIT", "atbash", 0)),
    (("SOLAR", "rot13", 0), ("FLARE", "reverse", 0)),
    (("COMET", "atbash", 0), ("TRAIL", "caesar", 5)),
    (("SPACE", "reverse", 0), ("PROBE", "rot13", 0)),
    (("EARTH", "caesar", 4), ("VENUS", "rot13", 0)),
    (("RADIO", "atbash", 0), ("WAVES", "reverse", 0)),
    (("NOVA", "rot13", 0), ("STAR", "caesar", 9)),
    (("COSMIC", "odd_even", 0), ("SIGNAL", "a1z26", 0)),
    (("GALAXY", "a1z26", 0), ("NEBULA", "odd_even", 0)),
    (("LAUNCH", "odd_even", 0), ("MODULE", "caesar", 6)),
    (("SATURN", "a1z26", 0), ("METEOR", "atbash", 0)),
]


def catalog():
    result = []
    for index, pair in enumerate(_PAIRS, 1):
        words = []
        for number, (answer, protocol, key) in enumerate(pair, 1):
            words.append({"id": "one" if number == 1 else "two", "answer": answer,
                          "protocol": protocol, "key": key,
                          "techniques": technique_groups(index - 1)[number - 1],
                          "ciphertext": transform(answer, protocol, key)})
        result.append({"id": f"TG-{index:02}", "words": words})
    return result


def get_challenge(team_id):
    """Choose once, then persist the selected puzzle with the team's session."""
    private_path = os.getenv("CIPHER_CATALOG_PATH", "").strip()
    private_json = os.getenv("CIPHER_CATALOG_JSON", "").strip()
    if private_path and private_json:
        raise ValueError("Set either CIPHER_CATALOG_PATH or CIPHER_CATALOG_JSON, not both")
    challenges = catalog()
    if private_json or private_path:
        challenges = json.loads(private_json) if private_json else json.loads(Path(private_path).read_text(encoding="utf-8"))
        if not isinstance(challenges, list) or not challenges:
            raise ValueError("Private cipher catalog must be a nonempty list")
        for challenge_index, challenge in enumerate(challenges):
            if len(challenge.get("words", [])) != 2:
                raise ValueError("Each challenge needs exactly two words")
            for index, word in enumerate(challenge["words"]):
                if not _valid_answer(word.get("answer")) or word.get("protocol") not in PROTOCOLS:
                    raise ValueError("Invalid private cipher entry")
                word["id"] = "one" if index == 0 else "two"
                word["key"] = int(word.get("key", 0))
                if word["protocol"] == "caesar" and not 1 <= word["key"] <= 25:
                    raise ValueError("Caesar keys must be from 1 through 25")
                word["ciphertext"] = transform(word["answer"], word["protocol"], word["key"])
                word.setdefault("techniques", technique_groups(challenge_index)[index])
                if (not isinstance(word["techniques"], list) or len(word["techniques"]) != 3
                        or len(set(word["techniques"])) != 3
                        or any(technique not in TECHNIQUES for technique in word["techniques"])):
                    raise ValueError("Each word needs three distinct supported techniques")
            if set(challenge["words"][0]["techniques"]) & set(challenge["words"][1]["techniques"]):
                raise ValueError("The two words must partition the six supported techniques")
            answers = [word["answer"] for word in challenge["words"]]
            public_text = " ".join(word["ciphertext"] for word in challenge["words"])
            for word in challenge["words"]:
                public_text += " " + " ".join(clue_for(word, stage, answers) for stage in (1, 2, 3))
            if any(re.search(r"(?<![A-Z])" + re.escape(answer) + r"(?![A-Z])", public_text.upper()) for answer in answers):
                raise ValueError("Private answers must not appear in ciphertext or protocol teaching text")
    return deepcopy(secrets.choice(challenges))


def _valid_answer(answer):
    return isinstance(answer, str) and 3 <= len(answer) <= 16 and all("A" <= c <= "Z" for c in answer)


def clue_for(word, stage, excluded_words=()):
    protocol = PROTOCOLS[word["protocol"]]
    if stage == 1:
        return f"Protocol identified: {protocol['name']}."
    if stage == 2:
        return protocol["concept"]
    excluded = {str(answer).upper() for answer in excluded_words} | {word["answer"]}
    for sample in (protocol["example"], "DOG", "FISH", "TOKEN", "PUZZLE", "TRAIN"):
        encrypted = transform(sample, word["protocol"], word["key"])
        if sample not in excluded and encrypted not in excluded:
            break
    else:
        raise ValueError("No unrelated cipher example available")
    return f"{protocol['rule'].format(key=word['key'])} Example: {sample} encodes as {encrypted}; decode {encrypted} to recover {sample}."
