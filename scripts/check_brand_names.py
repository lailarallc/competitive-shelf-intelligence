"""Brand-name gate: no real competitor brand in a tracked file, and every seeded competitor is fictional.

Competitors are always anonymized in Lailara output (naming rule, cinderhaven-data-realism
01-purpose-and-target-design.md:38). Two checks, each a failure when it does not hold:

  1. No tracked text file holds a denied name. The denylist is SHA-256 hashes of normalized names (lowercase,
     apostrophes dropped, every other non-alphanumeric run a single space), so this public repo never prints the
     names it denies. Every one-, two- and three-word run of every line is hashed and looked up.
  2. Every brand that scripts/load_synthetic_competitors.py seeds, and every brand config/products.yaml tracks,
     matches "Competitor <letter>". This one is structural: it holds against a real brand the denylist has
     never heard of.

The live database is checked by scripts/owner_rename_live_brands.py, which reuses denied() on the rows.

    python scripts/check_brand_names.py              # exit 0 = clean
    python scripts/check_brand_names.py --self-test  # proves each check can fail
"""
from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LOADER = ROOT / "scripts" / "load_synthetic_competitors.py"
CONFIG = ROOT / "config" / "products.yaml"
FICTIONAL = re.compile(r"Competitor [A-Z]")
#: Normalized real brand names, hashed: the six the demo once used and the 10-K comparables the spec cites
#: (19 spellings, one to three words).
DENIED = frozenset({
    "07b53bfa71fe2eb03d8ca62be5ec1757758615b1f897ef54449b8669291a5693",
    "0a4cef440f3d64214e4b9228bc3136e54bff6bc5a8377a923f92f1a97a2b0e21",
    "0d330215fbded514472c917a753a3c6f55cdd27e0da19e78f618e6b6f4ae0f08",
    "0ebcec7a332dbc73dd75846ec798801a77f9de346eb5a7a311e702332f5b5796",
    "19a52fad18f8b035a7da03f9ab86c9eee47016163dab3c8a81b818910c723749",
    "1f76b0e5058f716c3026eeb07599915e84f2c6de83fee6d1754d55f008689cc0",
    "2c7b1d1257a0455b86098429887cb443fb2ad7c11eb0cbfd9465a9975218298a",
    "4a59f44e6e8fdef0b7af84978d22754ca7182e28d769452a198dcd1b505dd361",
    "50737efb09ea958d57e6c1879d2bbb935c0ca64df4a13d054a4c53e2b51c46f3",
    "621bae240049e035118a2bc97cb0bf23ff2949077eecc8f5439de90eef8e5276",
    "6d629b2d75351871327e773597bfe8a836ec80966565960f657018ee21a1b150",
    "6ec19edc62367fc3b82ca555c346a55c29eb7aca11df4d9541fd2f836fb2fb06",
    "9523158611f4db9f7a9ffc8be583ca70b29e7ac97e89d586b6dbfb87984aaa09",
    "9c9e8ca0182c4c0737a8397c43e14916ac8dad7e04a7dceaacdc6a8e370f0a2c",
    "a5cde2893e1cbec08ad143957bb1356ab68fd886ee5c034e20ffcd5e4dce5c52",
    "a66e7109d7cf60d8dbaa05b13727583314276edc48193ec76f820450acf2723e",
    "b10d5ca2d777fed111caa0d12cd9c4573a9a9ec7f370941b4d69bdf233531ee2",
    "bc15303f4acc2b28fd656bd74b99edfc9422a9e0ccb87c0aca41b558bc1d9911",
    "f0eec2368509a01653ff6f85b7100aaab88957997b778d536cfc6747c728b0ab",
})
BINARY = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".pdf", ".pyc")
SELF = "scripts/check_brand_names.py"


def _norm(s: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"['’]", "", s.lower())).split()


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


#: Invented stand-ins for harness tests of the owner scripts, so no test file prints a real name. They are added
#: (as names to deny, with letters) only when CSI_TEST_PROBE=1; adding names only makes a check stricter.
PROBE_LETTERS = {_h("zeta sauce co"): "A", _h("quill"): "B"}


def deny_set() -> frozenset[str]:
    return DENIED | frozenset(PROBE_LETTERS) if os.environ.get("CSI_TEST_PROBE") == "1" else DENIED


def denied(text: str, deny: frozenset[str] = DENIED) -> bool:
    words = _norm(text)
    runs = words + [" ".join(words[i:i + n]) for n in (2, 3) for i in range(len(words) - n + 1)]
    return any(_h(r) in deny for r in runs)


def scan_files(root: Path, deny: frozenset[str] = DENIED) -> list[str]:
    files = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True).stdout.splitlines()
    bad = []
    for rel in files:
        p = root / rel
        if rel == SELF or rel.endswith(BINARY) or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if denied(line, deny):
                bad.append(f"{rel}:{i} names a real brand")
    return bad


def loader_brands(path: Path = LOADER) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "_COMPETITORS" for t in node.targets):
            return [ast.literal_eval(v) for d in node.value.elts for k, v in zip(d.keys, d.values)
                    if ast.literal_eval(k) == "brand"]
    raise SystemExit(f"{path}: no _COMPETITORS list")


def config_brands(path: Path = CONFIG) -> list[str]:
    return [p["brand"] for p in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("products") or []]


def check_fictional(brands: list[str], where: str) -> list[str]:
    return [f"{where}: brand {b!r} is not \"Competitor <letter>\"" for b in brands if not FICTIONAL.fullmatch(b)]


def check(root: Path = ROOT) -> list[str]:
    return (scan_files(root)
            + check_fictional(loader_brands(root / "scripts" / "load_synthetic_competitors.py"), "loader")
            + check_fictional(config_brands(root / "config" / "products.yaml"), "config/products.yaml"))


def self_test() -> int:
    probe = frozenset({_h("competitor z"), _h("zed")})
    cases = [
        ("a two-word name is caught", denied("Price for Competitor-Z, 6 oz", probe), True),
        ("a one-word name is caught, apostrophe dropped", denied("Ze'd's sauce", frozenset({_h("zeds")})), True),
        ("a three-word name is caught", denied("from Z&Q Foods today", frozenset({_h("z q foods")})), True),
        ("a name inside a longer word is not", denied("zedonk", probe), False),
        ("a fictional brand passes", check_fictional(["Competitor A"], "t") == [], True),
        ("a real-looking brand fails", check_fictional(["Acme Hot"], "t") != [], True),
        ("the shipped loader is fictional", check_fictional(loader_brands(), "loader") == [], True),
    ]
    bad = [name for name, got, want in cases if got != want]
    for name in bad:
        print(f"SELF-TEST FAIL: {name}")
    print(f"self-test: {len(cases) - len(bad)}/{len(cases)} pass")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    bad = check()
    for b in bad:
        print(f"FAIL {b}")
    print(f"brand-name gate: {'clean' if not bad else f'{len(bad)} finding(s)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
