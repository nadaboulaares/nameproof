"""Token-level interpretation: titles, suffixes, particles, compounds, joint accounts."""

from __future__ import annotations

from nameproof._lexicon import CONNECTORS, HONORIFICS, PARTICLES, POSTNOMINALS, SUFFIXES
from nameproof.arabic_names import same_name
from nameproof.explain import Reason

Tokens = tuple[str, ...]


def split_suffix(tokens: Tokens) -> tuple[Tokens, str | None]:
    """Detach a trailing generational suffix ("Jr", "III") and return it canonicalised."""
    if len(tokens) > 1 and tokens[-1] in SUFFIXES:
        return tokens[:-1], SUFFIXES[tokens[-1]]
    return tokens, None


def strip_titles(tokens: Tokens) -> tuple[Tokens, bool]:
    """Remove leading honorifics and trailing post-nominals.

    At least two words are always kept, because a title-like word next to a single
    other word is usually a name ("Dona Ares", "Léon Mba").
    """
    start, end = 0, len(tokens)
    while end - start > 2 and tokens[start] in HONORIFICS:
        start += 1
    while end - start > 2 and tokens[end - 1] in POSTNOMINALS:
        end -= 1
    kept = tokens[start:end]
    return kept, len(kept) != len(tokens)


ParticleVariant = tuple[Tokens, tuple[Reason, ...], Tokens]


def particle_variants(tokens: Tokens) -> list[ParticleVariant]:
    """Return ``tokens`` plus forms with surname particles dropped or glued on.

    Each variant also reports the particles it removed. A run of particles is
    only dropped inside a name, before a name word ("Ludwig van Beethoven"), so a
    leading "Ben" or trailing "Ben" (both real names) is never lost. Gluing
    ("van der Berg" -> "vanderberg", "De Luca" -> "deluca") is allowed anywhere
    before a name word, since it removes nothing.
    """
    variants: list[ParticleVariant] = [(tokens, (), ())]
    runs = _particle_runs(tokens)
    if not runs:
        return variants
    inner = [(start, end) for start, end in runs if start > 0]
    if inner:
        removed = {index for start, end in inner for index in range(start, end)}
        dropped = tuple(token for index, token in enumerate(tokens) if index not in removed)
        particles = tuple(tokens[index] for index in sorted(removed))
        variants.append((dropped, (Reason.PARTICLE_DROPPED,), particles))
    joined: list[str] = []
    index = 0
    starts = dict(runs)
    while index < len(tokens):
        if index in starts:
            end = starts[index]
            joined.append("".join(tokens[index : end + 1]))
            index = end + 1
        else:
            joined.append(tokens[index])
            index += 1
    particles = tuple(tokens[i] for start, end in runs for i in range(start, end))
    variants.append((tuple(joined), (Reason.PARTICLE_JOINED,), particles))
    return variants


def _particle_runs(tokens: Tokens) -> list[tuple[int, int]]:
    """``(start, end)`` of each run of particles that is followed by a name word."""
    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(tokens):
        if tokens[index] in PARTICLES:
            end = index
            while end < len(tokens) and tokens[end] in PARTICLES:
                end += 1
            if end < len(tokens):  # followed by a name word
                runs.append((index, end))
            index = end
        else:
            index += 1
    return runs


def merge_compounds(left: Tokens, right: Tokens) -> tuple[Tokens, Tokens, bool]:
    """Glue adjacent tokens on one side when the other side spells them as one word.

    "Jean Pierre" vs "Jeanpierre" becomes "jeanpierre" on both sides, and so does a
    known spelling of the same Arabic name ("Abdul Qadir" vs "Abdelkader").
    """
    new_left, merged_left = _merge_into(left, frozenset(right))
    new_right, merged_right = _merge_into(right, frozenset(new_left))
    return new_left, new_right, merged_left or merged_right


def _joins_into(joined: str, targets: frozenset[str]) -> bool:
    return joined in targets or any(same_name(joined, target) for target in targets)


def _merge_into(tokens: Tokens, targets: frozenset[str]) -> tuple[Tokens, bool]:
    out: list[str] = []
    merged = False
    index = 0
    while index < len(tokens):
        if index + 1 < len(tokens) and _joins_into(tokens[index] + tokens[index + 1], targets):
            out.append(tokens[index] + tokens[index + 1])
            merged = True
            index += 2
        else:
            out.append(tokens[index])
            index += 1
    return tuple(out), merged


def split_joint(tokens: Tokens) -> list[tuple[Tokens, tuple[Reason, ...]]]:
    """Split a joint account name into its holders.

    A holder given by first name only borrows the surname of the last holder:
    "John & Mary Smith" -> "John Smith", "Mary Smith". Returns ``[]`` when the
    name is not a joint account.
    """
    parts: list[list[str]] = [[]]
    for token in tokens:
        if token in CONNECTORS:
            parts.append([])
        else:
            parts[-1].append(token)
    if len(parts) == 1 or any(not part for part in parts):
        return []
    last = parts[-1]
    holders: list[tuple[Tokens, tuple[Reason, ...]]] = []
    for index, part in enumerate(parts):
        if index < len(parts) - 1 and len(part) == 1 and len(last) >= 2:
            holders.append(
                ((*part, last[-1]), (Reason.JOINT_ACCOUNT_HOLDER, Reason.SHARED_SURNAME))
            )
        else:
            holders.append((tuple(part), (Reason.JOINT_ACCOUNT_HOLDER,)))
    return holders
