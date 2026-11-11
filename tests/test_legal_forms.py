import pytest

from nameproof.legal_forms import LEGAL_FORM_WORDS, same_legal_form, split_legal_form


@pytest.mark.parametrize(
    ("name", "base", "code"),
    [
        ("acme gmbh", "acme", "curated:gmbh"),
        ("acme gesellschaft mit beschrankter haftung", "acme", "curated:gmbh"),
        ("acme gmbh co kg", "acme", "curated:gmbh-co-kg"),  # longest form wins over "kg"
        ("acme ltd", "acme", "curated:ltd"),
        ("acme limited", "acme", "curated:ltd"),
        ("kowalski sp z o o", "kowalski", "curated:sp-zoo"),
        ("novak s r o", "novak", "curated:sro"),
        ("novak sro", "novak", "curated:sro"),  # dotted forms also appear without dots
        ("athinaiki zythopoiia a e", "athinaiki zythopoiia", "curated:sa"),  # A.E. = S.A.
        ("energo eood", "energo", "curated:eood"),
        ("acme bvba", "acme", "elf:N5NT"),  # from the GLEIF ELF list
        ("john smith", "john smith", None),
        ("gmbh", "gmbh", None),  # never reduce a name to nothing
    ],
)
def test_split_legal_form(name: str, base: str, code: str | None) -> None:
    tokens, found = split_legal_form(tuple(name.split()))
    assert tokens == tuple(base.split())
    if code is None:
        assert found is None
    else:
        assert found is not None
        assert code in found


@pytest.mark.parametrize(
    "name", ["per persson", "persson per", "nguyen van son", "li ou", "dua lipa"]
)
def test_name_words_are_not_legal_forms(name: str) -> None:
    assert split_legal_form(tuple(name.split()))[1] is None


def test_same_legal_form() -> None:
    def form(name: str) -> frozenset[str]:
        found = split_legal_form(("acme", *name.split()))[1]
        assert found is not None
        return found

    assert same_legal_form(form("ltd"), form("limited"))
    assert same_legal_form(form("societe anonyme"), form("spolka akcyjna"))  # S.A. in FR and PL
    assert same_legal_form(form("s a"), form("a e"))  # Greek A.E. is a société anonyme
    assert not same_legal_form(form("gmbh"), form("ag"))
    assert "gmbh" in LEGAL_FORM_WORDS
    assert "smith" not in LEGAL_FORM_WORDS
    assert "stranski" not in LEGAL_FORM_WORDS  # a word inside a long ELF name, also a surname
