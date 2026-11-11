import pytest

from nameproof.explain import Reason
from nameproof.translit import (
    BGN_PCGN,
    BULGARIAN,
    ENGLISH_COMMON,
    ICAO_9303,
    SERBIAN_LATIN,
    UKRAINIAN,
    Mode,
    arabic_skeleton,
    cyrillic,
    greek_elot743,
    greek_phonetic,
    latin_skeleton,
    latin_skeleton_variants,
    renderings,
    scripts,
    worst,
)


def test_scripts() -> None:
    assert scripts("jose 123") == {"LATIN"}
    assert scripts("γιώργος smith") == {"GREEK", "LATIN"}
    assert scripts("محمد") == {"ARABIC"}
    assert scripts("王小明") == {"CJK"}
    assert scripts("123 -") == frozenset()


def test_worst_mode() -> None:
    assert worst(Mode.EXACT, Mode.APPROXIMATE) is Mode.APPROXIMATE
    assert worst(Mode.SKELETON, Mode.EXACT, Mode.APPROXIMATE) is Mode.SKELETON


@pytest.mark.parametrize(
    ("greek", "latin"),
    [
        ("γιώργος παπαδόπουλος", "giorgos papadopoulos"),
        ("γεώργιος", "georgios"),
        ("ευάγγελος", "evangelos"),  # ευ before a vowel -> ev; γγ -> ng
        ("ευθύμιος", "efthymios"),  # ευ before a voiceless consonant -> ef
        ("αντετοκούνμπο", "antetokounmpo"),  # ντ and μπ inside a word
        ("μπακογιάννη", "bakogianni"),  # μπ at the start -> b
        ("ντίνος", "dinos"),
        ("αγκαλιά", "angalia"),  # γκ inside a word -> ng
        ("γκίκας", "gikas"),
        ("χρήστος", "christos"),
        ("ψαράς", "psaras"),
        ("αθηναϊκή", "athinaiki"),  # dialytika breaks the αι digraph
        ("προϋπόθεση", "proypothesi"),  # ...and the ου digraph
        ("σφίγξ", "sfinx"),
        ("smith", "smith"),
    ],
)
def test_greek_elot743(greek: str, latin: str) -> None:
    assert greek_elot743(greek) == latin


@pytest.mark.parametrize(
    ("greek", "latin"),
    [
        ("γιάννης", "yannis"),
        ("χρήστος", "hristos"),
        ("αικατερίνη", "ekaterini"),
        ("γεωργία", "yeorya"),  # γι + vowel -> y, as in Yannis
        ("αντώνης", "adonis"),
    ],
)
def test_greek_phonetic(greek: str, latin: str) -> None:
    assert greek_phonetic(greek) == latin


@pytest.mark.parametrize(
    ("scheme", "cyr", "latin"),
    [
        (ICAO_9303, "владимир путин", "vladimir putin"),
        (ICAO_9303, "шевченко щука", "shevchenko shchuka"),
        (ICAO_9303, "юрий", "iurii"),
        (BGN_PCGN, "юрий", "yuriy"),
        (BGN_PCGN, "елена", "yelena"),
        (BGN_PCGN, "андреев", "andreyev"),
        (ENGLISH_COMMON, "пётр фёдор", "pyotr fyodor"),
        (ENGLISH_COMMON, "дмитрий юрий", "dmitry yury"),
        (ENGLISH_COMMON, "ильич евгений", "ilyich yevgeny"),
        (ENGLISH_COMMON, "горбачёв", "gorbacho" + "v"),
        (BULGARIAN, "бойко борисов", "boyko borisov"),
        (BULGARIAN, "христо", "hristo"),
        (BULGARIAN, "мария", "maria"),
        (BULGARIAN, "щерев", "shterev"),
        (UKRAINIAN, "володимир зеленський", "volodymyr zelenskyi"),
        (UKRAINIAN, "юлія", "yuliia"),
        (UKRAINIAN, "згорани", "zghorany"),
        (SERBIAN_LATIN, "новак ђоковић", "novak đoković"),
        (ICAO_9303, "smith", "smith"),
    ],
)
def test_cyrillic_schemes(scheme: object, cyr: str, latin: str) -> None:
    assert cyrillic(cyr, scheme) == latin  # type: ignore[arg-type]


def test_renderings_of_latin_text_is_just_the_text() -> None:
    assert [(r.text, r.mode) for r in renderings("john smith")] == [("john smith", Mode.EXACT)]


def test_renderings_of_greek() -> None:
    found = {(r.text, r.mode) for r in renderings("γιάννης")}
    assert ("giannis", Mode.EXACT) in found
    assert ("yannis", Mode.APPROXIMATE) in found
    assert ("γιάννης", Mode.EXACT) in found


def test_cyrillic_scheme_choice() -> None:
    serbian = {r.text for r in renderings("ђоковић")}
    assert "đoković" in serbian
    ukrainian = {r.text for r in renderings("юлія")}
    assert "yuliia" in ukrainian
    assert "iuliia" in ukrainian  # ICAO is always offered too


def test_mixed_greek_and_cyrillic_are_both_romanised() -> None:
    texts = {r.text for r in renderings("γιώργος иванов")}
    assert "giorgos ivanov" in texts


def test_arabic_renderings_are_skeletons() -> None:
    skeletons = [r for r in renderings("محمد علي") if r.mode is Mode.SKELETON]
    assert [r.text for r in skeletons] == ["mhmd al"]
    assert skeletons[0].reasons == (
        Reason.TRANSLITERATED,
        Reason.APPROXIMATE_TRANSLITERATION,
    )


@pytest.mark.parametrize(
    ("arabic", "skeleton"),
    [
        ("محمد", "mhmd"),
        ("مُحَمَّد", "mhmd"),  # vowel marks and shadda are ignored
        ("أحمد", "ahmd"),  # word-initial alef keeps a vowel marker
        ("حامد", "hmd"),
        ("فاطمة", "ftm"),  # ta marbuta is silent
        ("الزهراء", "zhr"),  # the article is dropped
        ("عبد الله", "abd l"),
        ("يوسف", "ysf"),
        ("خالد", "Kld"),
        ("ـمحمـد", "mhmd"),  # tatweel
        ("محمد smith", "mhmd smt"),
    ],
)
def test_arabic_skeleton(arabic: str, skeleton: str) -> None:
    assert arabic_skeleton(arabic) == skeleton


@pytest.mark.parametrize(
    ("latin", "skeleton"),
    [
        ("mohammed", "mhmd"),
        ("muhammad", "mhmd"),
        ("ahmed", "ahmd"),
        ("hamid", "hmd"),
        ("fatimah", "ftm"),
        ("fatima", "ftm"),
        ("youssef", "ysf"),
        ("khaled", "Kld"),
        ("cherif", "Srf"),
        ("djamel", "jml"),
        ("gamal", "jml"),
        ("qasim", "ksm"),
    ],
)
def test_latin_skeleton(latin: str, skeleton: str) -> None:
    assert latin_skeleton(latin) == skeleton


def test_latin_skeleton_variants_drop_articles_and_split_abd() -> None:
    assert latin_skeleton_variants(("abdel", "rahman")) == [("abdl", "rhmn"), ("abd", "rhmn")]
    assert latin_skeleton_variants(("fatima", "al", "zahra")) == [("ftm", "zhr")]
    assert latin_skeleton_variants(("al",)) == [("al",)]  # a lone article is kept
