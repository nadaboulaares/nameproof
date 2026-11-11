"""Word lists used to interpret name tokens.

All entries are lowercase and ASCII-folded, because lookups happen after
normalisation. Ambiguous words that are also common given names or surnames
(for example "don", "pan", "md") are deliberately left out.
"""

from __future__ import annotations

# Honorifics: only removed at the start of a name ("Herr Hugh" yes, "Hugh Herr" no).
HONORIFICS: frozenset[str] = frozenset(
    {
        # English
        "mr", "mrs", "ms", "miss", "mx", "dr", "prof", "sir", "dame",
        # German / Austrian
        "herr", "frau", "dipl", "mag",
        # French
        "mme", "mlle", "monsieur", "madame",
        # Italian / Spanish / Portuguese ("Sr." here means Señor)
        "sig", "sigra", "signor", "signora", "sr", "sra", "srta", "dona",
        # Central / Eastern European
        "mgr", "ing",
    }
)  # fmt: skip

# Post-nominals: only removed at the end of a name.
POSTNOMINALS: frozenset[str] = frozenset({"phd", "esq", "msc", "mba", "bsc"})

# Generational suffixes, mapped to a canonical form for comparison.
SUFFIXES: dict[str, str] = {
    "jr": "jr", "jnr": "jr", "junior": "jr",
    "sr": "sr", "snr": "sr", "senior": "sr",
    "ii": "ii", "iii": "iii", "iv": "iv",
}  # fmt: skip

# Surname particles that may be dropped or glued to the next token. Single
# letters ("y", "e") are left out: they are usually initials.
PARTICLES: frozenset[str] = frozenset(
    {
        "van", "von", "der", "den", "ter", "ten", "zu",
        "de", "del", "della", "dello", "dei", "des", "di", "da", "das", "do", "dos", "du",
        "le", "la", "lo",
        "al", "el", "bin", "ben", "ibn", "bint", "abu",
    }
)  # fmt: skip

# Words joining holders of a joint account ("John & Mary Smith"). Single-letter
# connectors ("y", "i", "a", "e") are excluded: they collide with initials.
CONNECTORS: frozenset[str] = frozenset({"&", "+", "and", "und", "et", "og", "och", "en"})

# Symbol connectors are never part of a name, so they are dropped everywhere.
SYMBOL_CONNECTORS: frozenset[str] = frozenset({"&", "+"})

# Words that never identify a person or company on their own, so they can't be
# the reason a close match reveals the account holder's name.
STOPWORDS: frozenset[str] = frozenset(
    {"of", "the", "and", "for", "bank", "company", "co", "group", "holding", "holdings",
     "international", "services", "trust", "foundation", "association", "fund"}
)  # fmt: skip
