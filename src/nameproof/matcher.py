"""The matching pipeline behind :func:`nameproof.match`.

Every name is expanded into spellings (romanisations, diacritic folds, with and
without legal form, particles, titles...). Each pair of spellings is aligned and
judged; the best verdict wins. The safety checks always look at what the name
was *before* anything was stripped, so removing a word can never by itself turn
a different name into a ``MATCH``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from nameproof._lexicon import (
    CONNECTORS,
    HONORIFICS,
    PARTICLES,
    POSTNOMINALS,
    STOPWORDS,
    SYMBOL_CONNECTORS,
)
from nameproof._types import MatchResult, Verdict
from nameproof.arabic_names import different_names
from nameproof.explain import Reason, ordered
from nameproof.legal_forms import LEGAL_FORM_WORDS, LegalForm, same_legal_form, split_legal_form
from nameproof.normalize import fold_variants, normalize_text
from nameproof.policy import DEFAULT_POLICY, Policy, load_policy
from nameproof.score import Alignment, PairKind, align, approximate
from nameproof.tokens import (
    Tokens,
    merge_compounds,
    particle_variants,
    split_joint,
    split_suffix,
    strip_titles,
)
from nameproof.translit import Mode, latin_skeleton_variants, renderings, scripts, worst

# SEPA name fields are limited to 140 characters; longer input is not a real name.
MAX_NAME_LENGTH = 140
MAX_ACCOUNT_NAMES = 20
# Bounds on the work per name, so crafted input can't make a check slow.
MAX_TOKENS = 10
MAX_FORMS = 16

# Absorbs float rounding when a score lands exactly on a threshold.
_EPSILON = 1e-9

# East Slavic female patronymics ("Mykolaivna", "Pavlovna"). Official names put
# them last ("Derusova Inna Mykolaivna") and payers leave them out. Unlike the
# male forms (-ovich is also a surname: Abramovich), these are never surnames.
_FEMALE_PATRONYMIC = re.compile(r"(?:ivna|yivna|ovna|evna|ichna|ychna|івна|ївна|овна|евна|ична)$")

# Words that can't, on their own, justify revealing an account holder's name.
_NOT_NAME_WORDS = PARTICLES | CONNECTORS | HONORIFICS | POSTNOMINALS | STOPWORDS | LEGAL_FORM_WORDS

_RANK = {
    MatchResult.MATCH: 3,
    MatchResult.CLOSE_MATCH: 2,
    MatchResult.NO_MATCH: 1,
    MatchResult.NOT_POSSIBLE: 0,
}


@dataclass(frozen=True, slots=True)
class _Form:
    """One spelling of a name, and what was done to it."""

    tokens: Tokens
    suffix: str | None
    reasons: tuple[Reason, ...]
    raw_size: int  # words in the name before titles, legal forms etc. were stripped
    mode: Mode = Mode.EXACT
    legal_form: LegalForm | None = None
    legal_form_removed: bool = False
    compound_split: bool = False  # tokens came from splitting a hyphenated name
    particles: Tokens = ()  # particles dropped or glued in this spelling
    legal_form_words: int = 0  # words removed as the legal form
    source: Tokens = ()  # the Arabic words behind a consonant skeleton


@dataclass(frozen=True, slots=True)
class _Comparison:
    alignment: Alignment
    left: Tokens
    right: Tokens
    reasons: frozenset[Reason] = frozenset()
    skeleton: bool = False


@dataclass(frozen=True, slots=True)
class _Outcome:
    result: MatchResult
    score: float
    reasons: tuple[Reason, ...]
    account: str

    @property
    def rank(self) -> tuple[int, float, int]:
        return _RANK[self.result], self.score, -len(self.reasons)


def match(
    provided: str,
    account_names: Sequence[str],
    *,
    policy: str | Policy = DEFAULT_POLICY,
) -> Verdict:
    """Check the name a payer typed against the account holder name(s).

    ``account_names`` lists every name registered on the account (holders,
    aliases). The best-matching one decides the verdict, and only a
    ``CLOSE_MATCH`` reveals which name that was, via ``suggested_name``. Account
    names that are too long to be real names are skipped.

    Raises:
        TypeError: if ``account_names`` is a single string instead of a sequence.
        ValueError: if ``account_names`` is empty or too long, or ``policy`` is unknown.

    """
    active = load_policy(policy)
    names = _check_account_names(account_names)
    provided_forms = _prepare_provided(provided)
    if isinstance(provided_forms, Reason):
        return _not_possible(active, provided_forms)
    return _judge(provided_forms, [(name, _prepare_account(name)) for name in names], active)


def _prepare_provided(name: str) -> list[_Form] | Reason:
    """Spellings of the name a payer typed, or why it can't be checked."""
    tokens = _usable_tokens(name)
    if tokens is None:
        return Reason.NAME_TOO_LONG
    return _forms(tokens, (), 0) or Reason.EMPTY_NAME


def _prepare_account(name: str) -> list[_Form] | None:
    """Spellings of an account name and of each joint holder; ``None`` if too long."""
    tokens = _usable_tokens(name)
    if tokens is None:
        return None
    return [
        form
        for holder, holder_reasons, raw_floor in _holders(tokens)
        for form in _forms(holder, holder_reasons, raw_floor)
    ]


def _judge(
    provided_forms: Sequence[_Form],
    accounts: Sequence[tuple[str, Sequence[_Form] | None]],
    policy: Policy,
) -> Verdict:
    """Compare prepared spellings; the best account spelling decides the verdict."""
    best: _Outcome | None = None
    skipped_too_long = False
    for account, account_forms in accounts:
        if account_forms is None:
            skipped_too_long = True
            continue
        for account_form in account_forms:
            for provided_form in provided_forms:
                outcome = _evaluate(provided_form, account_form, account, policy)
                if best is None or outcome.rank > best.rank:
                    best = outcome
    if best is None:
        reason = Reason.NAME_TOO_LONG if skipped_too_long else Reason.EMPTY_NAME
        return _not_possible(policy, reason)
    return Verdict(
        result=best.result,
        score=round(best.score, 4),
        policy_version=policy.id,
        explanation=tuple(reason.value for reason in best.reasons),
        suggested_name=best.account if best.result is MatchResult.CLOSE_MATCH else None,
    )


def _check_account_names(account_names: Sequence[str]) -> Sequence[str]:
    if isinstance(account_names, str):
        msg = "account_names must be a sequence of names, not a single string"
        raise TypeError(msg)
    if not account_names:
        msg = "account_names must contain at least one name"
        raise ValueError(msg)
    if len(account_names) > MAX_ACCOUNT_NAMES:
        msg = f"at most {MAX_ACCOUNT_NAMES} account names are supported"
        raise ValueError(msg)
    return account_names


def _usable_tokens(name: str) -> Tokens | None:
    """Normalised tokens, or ``None`` if the name is too long to be a real name.

    Length is checked before and after Unicode normalisation, because NFKC can
    expand one character into many.
    """
    if len(name) > MAX_NAME_LENGTH:
        return None
    normalized = normalize_text(name)
    tokens = tuple(normalized.split())
    if len(normalized) > MAX_NAME_LENGTH or len(tokens) > MAX_TOKENS:
        return None
    return tokens


def _not_possible(policy: Policy, reason: Reason) -> Verdict:
    return Verdict(
        result=MatchResult.NOT_POSSIBLE,
        score=0.0,
        policy_version=policy.id,
        explanation=(reason.value,),
    )


def _holders(tokens: Tokens) -> list[tuple[Tokens, tuple[Reason, ...], int]]:
    """Return the account name itself, plus each holder of a joint account.

    Each holder carries the word count of the whole account name, so a holder
    reduced to one word ("Gamble" in "Procter & Gamble") still counts as a
    one-word comparison against a longer name.
    """
    whole: list[tuple[Tokens, tuple[Reason, ...], int]] = [(tokens, (), 0)]
    plain = tuple(fold_variants(" ".join(tokens))[0][0].split())
    if split_legal_form(plain)[1] is not None:
        return whole  # "Smith & Sons Ltd" is one company, not two holders
    words = sum(token not in CONNECTORS for token in tokens)
    return [*whole, *((part, reasons, words) for part, reasons in split_joint(tokens))]


def _forms(tokens: Tokens, base_reasons: tuple[Reason, ...], raw_floor: int) -> list[_Form]:
    """Expand one name into the spellings worth comparing (at most ``MAX_FORMS``)."""
    text = " ".join(token for token in tokens if token not in SYMBOL_CONNECTORS)
    forms: dict[tuple[object, ...], _Form] = {}
    for rendering in renderings(text):
        reasons = (*base_reasons, *rendering.reasons)
        raw_size = max(raw_floor, len(rendering.text.split()))
        if rendering.mode is Mode.SKELETON:
            words = tuple(text.split())
            candidates = [
                _Form(tuple(rendering.text.split()), None, reasons, raw_size, Mode.SKELETON,
                      source=words)
            ]  # fmt: skip
        else:
            candidates = [
                form
                for folded, fold_reasons in fold_variants(rendering.text)
                for form in _spellings(folded, (*reasons, *fold_reasons), rendering.mode, raw_size)
            ]
        for form in candidates:
            key = (form.tokens, form.mode, form.legal_form, form.legal_form_removed,
                   form.compound_split, form.particles)  # fmt: skip
            known = forms.get(key)
            if form.tokens and (known is None or len(form.reasons) < len(known.reasons)):
                forms[key] = form
    ranked = sorted(forms.values(), key=lambda form: (len(form.reasons), form.tokens))
    return ranked[:MAX_FORMS]


def _spellings(text: str, reasons: tuple[Reason, ...], mode: Mode, raw_size: int) -> list[_Form]:
    """Interpret a plain name, offering hyphenated names both split and glued."""
    if "-" not in text:
        return _interpret(text, reasons, mode, raw_size, compound_split=False)
    return [
        *_interpret(text.replace("-", " "), reasons, mode, raw_size, compound_split=True),
        *_interpret(
            text.replace("-", ""),
            (*reasons, Reason.COMPOUND_JOINED),
            mode,
            raw_size,
            compound_split=False,
        ),
    ]


def _interpret(
    text: str, reasons: tuple[Reason, ...], mode: Mode, raw_size: int, *, compound_split: bool
) -> list[_Form]:
    """Detach legal form, generational suffix and titles; expand particles."""
    name = tuple(text.split())
    base, legal_form = split_legal_form(name)
    choices = [(name, False), (base, True)] if legal_form else [(name, False)]
    spellings: list[_Form] = []
    for tokens, removed in choices:
        form_words = len(name) - len(base) if removed else 0
        core, suffix = split_suffix(tokens)
        core, titled = strip_titles(core)
        title_reasons = (Reason.TITLE_REMOVED,) if titled else ()
        spellings.extend(
            _Form(
                tokens=variant,
                suffix=suffix,
                reasons=(*reasons, *title_reasons, *particle_reasons),
                raw_size=raw_size,
                mode=mode,
                legal_form=legal_form,
                legal_form_removed=removed,
                compound_split=compound_split,
                particles=particles,
                legal_form_words=form_words,
            )
            for variant, particle_reasons, particles in particle_variants(core)
        )
    return spellings


def _latin_only(tokens: Tokens) -> bool:
    return scripts("".join(tokens)) <= {"LATIN"}


def _compare(provided: _Form, account: _Form, policy: Policy) -> _Comparison | None:
    """Align two forms, or return ``None`` when their scripts can't be compared."""
    mode = worst(provided.mode, account.mode)
    if mode is Mode.SKELETON:
        return _compare_skeletons(provided, account, policy)
    if _latin_only(provided.tokens) != _latin_only(account.tokens):
        return None
    left, right, merged = merge_compounds(provided.tokens, account.tokens)
    alignment = align(left, right)
    both_romanised = (
        Reason.TRANSLITERATED in provided.reasons and Reason.TRANSLITERATED in account.reasons
    )
    if mode is Mode.APPROXIMATE or both_romanised:
        # Two names in the same non-Latin script are compared natively; their
        # romanisations can blur real differences (Greek eta and iota both become i).
        alignment = approximate(alignment)
    extra = frozenset({Reason.COMPOUND_JOINED}) if merged else frozenset()
    return _Comparison(alignment, left, right, extra)


def _compare_skeletons(provided: _Form, account: _Form, policy: Policy) -> _Comparison | None:
    """Compare consonant skeletons (Arabic script against romanised Arabic names)."""
    sides: list[list[Tokens]] = []
    for form in (provided, account):
        if form.mode is Mode.SKELETON:
            sides.append([form.tokens])
        elif _latin_only(form.tokens):
            sides.append(latin_skeleton_variants(form.tokens))
        else:
            return None
    best: _Comparison | None = None
    for left in sides[0]:
        for right in sides[1]:
            pairs = [(left, right)]
            if len(left) > 1 or len(right) > 1:  # "Abdullah" vs "abd allah"
                pairs.append((("".join(left),), ("".join(right),)))
            for joined_a, joined_b in pairs:
                if not joined_a or not joined_b or not joined_a[0] or not joined_b[0]:
                    continue
                a, b, _ = merge_compounds(joined_a, joined_b)  # "abd" + "rhmn"
                alignment = align(a, b)
                penalty = policy.missing_token_penalty
                if best is None or alignment.score(penalty) > best.alignment.score(penalty):
                    best = _Comparison(alignment, a, b, skeleton=True)
    if best is None:
        return None
    return _Comparison(approximate(best.alignment), best.left, best.right, skeleton=True)


def _legal_form_reasons(provided: _Form, account: _Form) -> tuple[set[Reason], bool]:
    conflict = (
        provided.legal_form is not None
        and account.legal_form is not None
        and not same_legal_form(provided.legal_form, account.legal_form)
    )
    reasons: set[Reason] = {Reason.LEGAL_FORM_CONFLICT} if conflict else set()
    if not conflict and (provided.legal_form_removed or account.legal_form_removed):
        both = provided.legal_form is not None and account.legal_form is not None
        reasons.add(Reason.LEGAL_FORM_MATCHED if both else Reason.LEGAL_FORM_MISSING)
    return reasons, conflict


def _missing_parts_ok(comparison: _Comparison, provided: _Form, account: _Form) -> bool:
    """Whether every unmatched token is a middle name or a trailing female patronymic.

    A missing first name or surname ("Jan Józef Lipski" vs "Józef Lipski"), or a
    missing half of a hyphenated name ("Hans-Joachim" vs "Hans"), may be a
    different person, so it can't be waved through as a MATCH.
    """
    left, right = comparison.left, comparison.right
    if len(left) == len(right):
        return True
    if len(left) > len(right):
        tokens, form = left, provided
        used = {pair.left for pair in comparison.alignment.pairs}
    else:
        tokens, form = right, account
        used = {pair.right for pair in comparison.alignment.pairs}
    if form.compound_split:
        return False
    last = len(tokens) - 1
    return all(
        (0 < index < last and token not in PARTICLES)  # "van" belongs to the surname
        or (index == last and index - 1 in used and _FEMALE_PATRONYMIC.search(token))
        for index, token in enumerate(tokens)
        if index not in used
    )


def _stripped_words(form: _Form, shared_form: bool) -> bool:
    """Whether processing removed words from this spelling of the name.

    A legal form both sides share ("Acme Ltd" vs "Acme Limited") is not lost
    information, so its words don't count.
    """
    kept_form = form.legal_form_words if shared_form else 0
    return form.raw_size - kept_form > len(form.tokens) and not form.compound_split


def _is_name_word(token: str, *, skeleton: bool) -> bool:
    """Whether ``token`` is specific enough to anchor a close match."""
    if len(token) < 2:
        return False
    return skeleton or token not in _NOT_NAME_WORDS


def _blockers(
    comparison: _Comparison, provided: _Form, account: _Form, policy: Policy
) -> tuple[set[Reason], set[Reason]]:
    """Reasons that rule out MATCH, and extra reasons to report."""
    alignment = comparison.alignment
    company = provided.legal_form is not None or account.legal_form is not None
    legal_reasons, legal_conflict = _legal_form_reasons(provided, account)
    blockers: set[Reason] = set()
    sizes = (len(comparison.left), len(comparison.right))
    # Words removed before comparing (titles, legal forms, other joint holders)
    # still count: "Smith" vs "Dr Smith" or "Gamble" vs "Procter & Gamble" is a
    # one-word name against a longer one. Words merged into a compound
    # ("Abdullah" vs "abd allah") are not removed.
    shared_form = (
        provided.legal_form is not None
        and account.legal_form is not None
        and same_legal_form(provided.legal_form, account.legal_form)
    )
    stripped = _stripped_words(provided, shared_form) or _stripped_words(account, shared_form)
    if min(sizes) == 1 and (max(sizes) >= 2 or stripped):
        blockers.add(Reason.SINGLE_TOKEN)
    if provided.suffix and account.suffix and provided.suffix != account.suffix:
        blockers.add(Reason.SUFFIX_CONFLICT)
    if legal_conflict:
        blockers.add(Reason.LEGAL_FORM_CONFLICT)
    if (provided.legal_form_removed or account.legal_form_removed) and not (
        policy.legal_form_variants_can_match
    ):
        blockers |= legal_reasons - {Reason.LEGAL_FORM_CONFLICT}
    if (
        provided.particles
        and account.particles
        and set(provided.particles) != set(account.particles)
    ):
        blockers.add(Reason.PARTICLE_CONFLICT)  # "ibn" vs "abu": son of vs father of
    elif (provided.particles or account.particles) and not policy.particle_variants_can_match:
        blockers |= {*provided.reasons, *account.reasons} & {
            Reason.PARTICLE_DROPPED,
            Reason.PARTICLE_JOINED,
        }
    if (
        provided.legal_form is not None
        and account.legal_form is not None
        and alignment.reordered
        and not policy.company_reorder_can_match
    ):
        blockers.add(Reason.TOKEN_REORDER)  # EPC: company words out of order -> close
    if alignment.unmatched and (company or not _missing_parts_ok(comparison, provided, account)):
        blockers.add(Reason.MISSING_NAME_PART)
    return blockers, legal_reasons


def _evaluate(provided: _Form, account: _Form, account_name: str, policy: Policy) -> _Outcome:
    comparison = _compare(provided, account, policy)
    if comparison is None:
        return _Outcome(MatchResult.NOT_POSSIBLE, 0.0, (Reason.UNSUPPORTED_SCRIPT,), account_name)
    blockers, legal_reasons = _blockers(comparison, provided, account, policy)
    company = provided.legal_form is not None or account.legal_form is not None
    anchored = any(
        pair.kind in (PairKind.EXACT, PairKind.FUZZY, PairKind.VARIANT)
        and pair.similarity >= policy.close_threshold
        and _is_name_word(comparison.left[pair.left], skeleton=comparison.skeleton)
        for pair in comparison.alignment.pairs
    )
    # A single word ("Smith", "Gamble") is not enough to reveal a person's full
    # name; companies may still close-match on their name without legal form.
    # A close match is for small deviations: in a person's name, one clearly
    # different word ("Mohamed" vs "Mahmoud", "Béla" vs "Eva") rules it out,
    # however many other words agree. Company names are often translated
    # ("Moscow" vs "Москва"), so they are left to the score.
    distinct_word = not company and any(
        pair.kind is PairKind.FUZZY and pair.similarity < policy.distinct_word_threshold
        for pair in comparison.alignment.pairs
    )
    # Known names that don't correspond ("Mahmoud" vs محمد) share a consonant
    # skeleton but are different names.
    if comparison.skeleton and _different_given_names(provided, account):
        blockers.add(Reason.DIFFERENT_GIVEN_NAME)
    allow_close = (
        anchored
        and not distinct_word
        and Reason.DIFFERENT_GIVEN_NAME not in blockers
        and not (Reason.SINGLE_TOKEN in blockers and not company)
    )
    result, score, decision_reasons = _decide(
        comparison.alignment, policy, frozenset(blockers), allow_close=allow_close
    )
    reasons = {
        *provided.reasons,
        *account.reasons,
        *comparison.reasons,
        *decision_reasons,
        *legal_reasons,
    }
    return _Outcome(result, score, ordered(reasons), account_name)


def _different_given_names(provided: _Form, account: _Form) -> bool:
    """Known given names on both sides that don't correspond (via the Arabic words)."""
    left = provided.source if provided.mode is Mode.SKELETON else provided.tokens
    right = account.source if account.mode is Mode.SKELETON else account.tokens
    return different_names(left, right)


def _decide(
    alignment: Alignment, policy: Policy, blockers: frozenset[Reason], *, allow_close: bool
) -> tuple[MatchResult, float, set[Reason]]:
    """Turn an alignment into a verdict; any ``blockers`` rule out ``MATCH``."""
    reasons: set[Reason] = set(blockers)
    for pair in alignment.pairs:
        if pair.kind is PairKind.INITIAL:
            reasons.add(Reason.INITIAL)
        elif pair.kind is PairKind.ABBREVIATION:
            reasons.add(Reason.ABBREVIATION)
        elif pair.kind is PairKind.VARIANT:
            reasons.add(Reason.KNOWN_VARIANT)
        elif pair.kind is PairKind.FUZZY:
            close = pair.similarity >= policy.close_threshold
            reasons.add(Reason.FUZZY_TOKEN if close else Reason.MISMATCHED_TOKEN)
    if alignment.unmatched:
        reasons.add(Reason.MISSING_TOKENS)
    if alignment.reordered:
        reasons.add(Reason.TOKEN_REORDER)

    score = alignment.score(policy.missing_token_penalty)
    identical = all(
        pair.kind is PairKind.EXACT
        or (pair.kind is PairKind.INITIAL and policy.initials_can_match)
        or (pair.kind is PairKind.VARIANT and policy.known_variants_can_match)
        for pair in alignment.pairs
    )
    if (
        identical
        and not blockers
        and score >= policy.match_threshold - _EPSILON
        and alignment.unmatched <= policy.max_missing_tokens_for_match
    ):
        return MatchResult.MATCH, score, reasons
    # A close match reveals the real name, so it needs at least one real name
    # word that genuinely agrees; initials, particles or legal forms never do.
    if allow_close and score >= policy.close_threshold - _EPSILON:
        return MatchResult.CLOSE_MATCH, score, reasons
    if alignment.pairs and all(pair.kind is PairKind.INITIAL for pair in alignment.pairs):
        reasons.add(Reason.INITIALS_ONLY)
    return MatchResult.NO_MATCH, score, reasons
