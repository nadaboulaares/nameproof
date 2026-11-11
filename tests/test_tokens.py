from nameproof.explain import Reason
from nameproof.tokens import (
    merge_compounds,
    particle_variants,
    split_joint,
    split_suffix,
    strip_titles,
)


def test_split_suffix() -> None:
    assert split_suffix(("john", "smith", "junior")) == (("john", "smith"), "jr")
    assert split_suffix(("john", "smith")) == (("john", "smith"), None)
    assert split_suffix(("jr",)) == (("jr",), None)


def test_strip_titles_at_the_edges() -> None:
    assert strip_titles(("dr", "john", "smith", "phd")) == (("john", "smith"), True)
    assert strip_titles(("herr", "prof", "hans", "meier")) == (("hans", "meier"), True)


def test_honorifics_only_at_the_start() -> None:
    # "Hugh Herr" and "Ing Lee" are names, not titles (review finding 3).
    assert strip_titles(("hugh", "herr")) == (("hugh", "herr"), False)
    assert strip_titles(("lee", "ing")) == (("lee", "ing"), False)
    assert strip_titles(("sr", "jose", "garcia")) == (("jose", "garcia"), True)
    assert strip_titles(("garcia", "sr")) == (("garcia", "sr"), False)


def test_strip_titles_never_empties_a_name() -> None:
    assert strip_titles(("dr",)) == (("dr",), False)
    assert strip_titles(("dr", "phd")) == (("dr", "phd"), False)
    # A title-like word next to one other word is a name: Dona Ares, Léon Mba.
    assert strip_titles(("dona", "ares")) == (("dona", "ares"), False)
    assert strip_titles(("leon", "mba")) == (("leon", "mba"), False)


def test_particle_variants() -> None:
    assert particle_variants(("anna", "van", "der", "berg")) == [
        (("anna", "van", "der", "berg"), (), ()),
        (("anna", "berg"), (Reason.PARTICLE_DROPPED,), ("van", "der")),
        (("anna", "vanderberg"), (Reason.PARTICLE_JOINED,), ("van", "der")),
    ]


def test_particle_variants_without_particles() -> None:
    assert particle_variants(("john", "smith")) == [(("john", "smith"), (), ())]


def test_particles_at_the_edges_are_never_dropped() -> None:
    # "Ben Smith" and "Adam Ben": Ben is a name here (review finding 2).
    assert [v[0] for v in particle_variants(("ben", "smith"))] == [("ben", "smith"), ("bensmith",)]
    assert particle_variants(("adam", "ben")) == [(("adam", "ben"), (), ())]
    assert particle_variants(("de", "la")) == [(("de", "la"), (), ())]


def test_single_letters_are_initials_not_particles() -> None:
    assert particle_variants(("john", "e", "smith")) == [(("john", "e", "smith"), (), ())]


def test_merge_compounds_either_side() -> None:
    left, right, merged = merge_compounds(("jean", "pierre", "dupont"), ("jeanpierre", "dupont"))
    assert (left, right, merged) == (("jeanpierre", "dupont"), ("jeanpierre", "dupont"), True)
    left, right, merged = merge_compounds(("jeanpierre",), ("jean", "pierre"))
    assert (right, merged) == (("jeanpierre",), True)
    assert merge_compounds(("a", "b"), ("c",))[2] is False


def test_split_joint_shares_surname() -> None:
    assert split_joint(("john", "&", "mary", "smith")) == [
        (("john", "smith"), (Reason.JOINT_ACCOUNT_HOLDER, Reason.SHARED_SURNAME)),
        (("mary", "smith"), (Reason.JOINT_ACCOUNT_HOLDER,)),
    ]


def test_split_joint_full_names() -> None:
    assert split_joint(("john", "smith", "und", "eva", "braun")) == [
        (("john", "smith"), (Reason.JOINT_ACCOUNT_HOLDER,)),
        (("eva", "braun"), (Reason.JOINT_ACCOUNT_HOLDER,)),
    ]


def test_split_joint_ignores_non_joint_and_dangling_connectors() -> None:
    assert split_joint(("john", "smith")) == []
    assert split_joint(("&", "smith")) == []
