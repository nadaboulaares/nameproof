import json
from pathlib import Path

import pytest

from nameproof import MatchResult, load_policy, match
from nameproof import dedupe as dedupe_module
from nameproof.cli import main
from nameproof.dedupe import DedupeReport, find_duplicates, word_key, word_keys


def _grouped(report: DedupeReport, names: list[str]) -> list[set[str]]:
    return [{names[index] for index in group.members} for group in report.groups]


def test_cross_script_names_are_grouped_for_review() -> None:
    names = ["Fatma Trabelsi", "Ahmed Salah", "فاطمة الطرابلسي", "Ali", "علي"]
    report = find_duplicates(names)
    assert _grouped(report, names) == [{"Fatma Trabelsi", "فاطمة الطرابلسي"}, {"Ali", "علي"}]
    assert all(group.needs_review for group in report.groups)
    assert report.pairs[0].result is MatchResult.CLOSE_MATCH
    assert "transliterated" in report.pairs[0].explanation


def test_identical_names_match_without_being_compared() -> None:
    names = ["Mohamed Ben Ali", "mohamed  ben ali", "MOHAMED BEN ALI"]
    report = find_duplicates(names)
    assert report.compared == 0
    assert [group.members for group in report.groups] == [(0, 1, 2)]
    assert not report.groups[0].needs_review
    assert {pair.explanation for pair in report.pairs} == {()}


def test_official_romanisation_is_a_match_group() -> None:
    names = ["Giorgos Papadopoulos", "Γιώργος Παπαδόπουλος"]
    report = find_duplicates(names)
    assert report.groups[0].members == (0, 1)
    assert not report.groups[0].needs_review


def test_different_people_are_not_grouped() -> None:
    names = ["Mohamed Trabelsi", "Mahmoud Trabelsi", "Mohamed Ben Ali", "Mahmoud Ben Ali"]
    assert find_duplicates(names).groups == ()


def test_unusable_names_are_reported_unchecked() -> None:
    names = ["", "山田太郎", "x" * 200, "Dr", "John Smith", "J. Smith"]
    report = find_duplicates(names)
    assert report.unchecked == (0, 1, 2, 3)
    assert _grouped(report, names) == [{"John Smith", "J. Smith"}]


def test_glued_arabic_names_meet_their_arabic_spelling() -> None:
    names = ["Abdelmalek Benhabyles", "عبد المالك بن حبيلس", "Abderrahmane Hadj", "حاج عبد الرحمان"]
    report = find_duplicates(names)
    assert _grouped(report, names) == [set(names[:2]), set(names[2:])]


def test_crowded_keys_are_narrowed_not_dropped() -> None:
    surnames = [f"Testname{chr(97 + i)}{chr(97 + j)}" for i in range(10) for j in range(10)]
    names = [f"Mohamed {surname}" for surname in surnames]
    names += [
        "Mohamed Trabelsi",
        "محمد الطرابلسي",
        "V. Pavlov",
        "Valentin Pavlov",
        "Vladimir Pavlov",
    ]
    report = find_duplicates(names, max_group=4)
    found = _grouped(report, names)
    assert {"Mohamed Trabelsi", "محمد الطرابلسي"} in found
    assert {"V. Pavlov", "Valentin Pavlov", "Vladimir Pavlov"} in found
    assert report.compared < len(names) * (len(names) - 1) // 20


def test_repeated_key_and_ch_spellings_meet_in_crowded_groups() -> None:
    names = ["Ivanov Ivan", "Иван Иванов", "Christov Christo", "Христо Христов"]
    names += [f"Ivan{suffix}" for suffix in ("ka", "ko", "ek", "ica", "ich", "ushka")]
    report = find_duplicates(names, max_group=3)
    found = _grouped(report, names)
    assert {"Ivanov Ivan", "Иван Иванов"} in found
    assert {"Christov Christo", "Христо Христов"} in found


def test_overflowing_groups_are_counted() -> None:
    names = [f"Ali {chr(97 + i)}" for i in range(6)] + ["Ali"] * 1 + ["Alia", "Aly", "Alli"]
    report = find_duplicates(names, max_group=2)
    assert report.crowded_keys >= 1


def test_parallel_and_serial_agree(monkeypatch: pytest.MonkeyPatch) -> None:
    names = [
        "Fatma Trabelsi",
        "فاطمة الطرابلسي",
        "John Smith",
        "J. Smith",
        "Jon Smyth",
        "Ali",
        "علي",
    ]
    serial = find_duplicates(names)
    monkeypatch.setattr(dedupe_module, "_PARALLEL_MIN", 0)
    seen: list[tuple[int, int]] = []
    assert find_duplicates(names, jobs=2, progress=lambda *step: seen.append(step)) == serial
    assert seen[0] == (0, serial.compared)
    assert seen[-1] == (serial.compared, serial.compared)


def test_worker_helpers_run_in_process() -> None:
    names = ["John Smith", "J. Smith"]
    report = find_duplicates(names)
    prepared = [entry for entry in map(dedupe_module._prepare, range(2), names) if entry]
    dedupe_module._start_worker(prepared, load_policy())
    assert dedupe_module._worker_chunk([(0, 1)]) == list(report.pairs)


def test_policy_is_applied_and_recorded() -> None:
    names = ["Mohamed Ben Ali", "Mahmoud Ben Ali"]
    assert find_duplicates(names).groups == ()
    old = find_duplicates(names, policy="epc-default@1")
    assert old.policy_version == "epc-default@1"
    assert len(old.groups) == 1


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"max_group": 1}, ValueError),
        ({"jobs": 0}, ValueError),
        ({"policy": "nope@1"}, ValueError),
    ],
)
def test_invalid_arguments_are_rejected(kwargs: dict[str, object], error: type[Exception]) -> None:
    with pytest.raises(error):
        find_duplicates(["a b"], **kwargs)  # type: ignore[arg-type]


def test_a_single_string_is_rejected() -> None:
    with pytest.raises(TypeError, match="sequence"):
        find_duplicates("John Smith")


def test_report_to_dict_is_json_ready() -> None:
    report = find_duplicates(["John Smith", "J. Smith", ""])
    data = json.loads(json.dumps(report.to_dict()))
    assert data["policy_version"] == "epc-default@2"
    assert data["unchecked"] == [2]
    assert data["groups"] == [{"members": [0, 1], "needs_review": True}]
    assert data["pairs"][0] == {
        "first": 0,
        "second": 1,
        "result": "CLOSE_MATCH",
        "score": report.pairs[0].score,
        "explanation": ["initial"],
    }


@pytest.mark.parametrize(
    ("words", "key"),
    [
        (["mohamed", "muhammad", "mohammed"], "md"),
        (["gherman", "german", "herman"], "jrmn"),
        (["bonaparte", "vonaparti"], "bnbrt"),
        (["titov"], "titov"),  # too short for a consonant key: keeps its spelling
    ],
)
def test_word_keys_join_spellings(words: list[str], key: str) -> None:
    assert {word_key(word) for word in words} == {key}


def test_arabic_skeletons_share_latin_keys() -> None:
    assert word_key("mhmd", skeleton=True) == word_key("mohamed")
    assert word_keys("abdelmalek") == {"abdlmlk", "mlk"}
    assert word_keys("christo") == {"srst", "krst"}


def test_dedupe_matches_match() -> None:
    names = ["Jon Smyth", "John Smith", "Maria Garcia", "Mario Garcia"]
    report = find_duplicates(names)
    for pair in report.pairs:
        verdict = match(names[pair.first], [names[pair.second]])
        assert (pair.result, pair.score, pair.explanation) == (
            verdict.result,
            verdict.score,
            verdict.explanation,
        )


# --- command line -------------------------------------------------------------


@pytest.fixture
def aid_list(tmp_path: Path) -> Path:
    path = tmp_path / "aid.csv"
    path.write_text(
        "\ufeffid;Name;city\n1;محمد بن علي;Sfax\n2;Mohamed Ben Ali;Sfax\n3;Ahmed Salah;Gabes\n"
        "4;;\n\n5;Mohamed Ben Ali;Sfax\n",
        encoding="utf-8",
    )
    return path


def test_cli_dedupe_prints_groups(aid_list: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["dedupe", str(aid_list), "--jobs", "1"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("1 groups of likely duplicates in 5 names (1 to review)")
    assert "Not checked (empty, too long or unsupported script): rows 5" in out
    assert "row     2  محمد بن علي" in out
    assert "rows 3 & 7: MATCH (identical)" in out
    assert "rows 2 & 3: CLOSE_MATCH (transliterated" in out


def test_cli_dedupe_writes_csv_and_json(
    aid_list: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "groups.csv"
    assert main(["dedupe", str(aid_list), "--output", str(output), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["rows"] == [2, 3, 4, 5, 7]
    assert payload["groups"] == [{"members": [0, 1, 4], "needs_review": True}]
    assert output.read_text(encoding="utf-8").splitlines() == [
        "group,review,row,id,Name,city",
        "1,yes,2,1,محمد بن علي,Sfax",
        "1,yes,3,2,Mohamed Ben Ali,Sfax",
        "1,yes,7,5,Mohamed Ben Ali,Sfax",
    ]


def test_cli_dedupe_reads_text_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "names.txt"
    path.write_text("John Smith\nPeter Brown\nJ. Smith\n", encoding="utf-8")
    assert main(["dedupe", str(path)]) == 0
    out = capsys.readouterr().out
    assert "row     1  John Smith" in out
    assert "row     3  J. Smith" in out


def test_cli_dedupe_column_choice(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "people.csv"
    path.write_text("first,full\nx,John Smith\ny,J. Smith\n", encoding="utf-8")
    assert main(["dedupe", str(path)]) == 2
    assert "choose the name column with --column" in capsys.readouterr().err
    assert main(["dedupe", str(path), "--column", "missing"]) == 2
    assert "no column 'missing'; columns are: first, full" in capsys.readouterr().err
    assert main(["dedupe", str(path), "--column", "FULL"]) == 0
    assert "1 groups" in capsys.readouterr().out


def test_cli_dedupe_single_column_and_crowding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "one.csv"
    names = [f"Ali {chr(97 + i)}" for i in range(6)] + ["Ali", "Alia", "Aly", "Alli"]
    path.write_text("Beneficiary\n" + "\n".join(names) + "\n", encoding="utf-8")
    assert main(["dedupe", str(path), "--max-group", "2"]) == 0
    assert "Some very common names were not all compared" in capsys.readouterr().out


def test_cli_dedupe_lists_many_unchecked_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "blank.csv"
    path.write_text("id,name\n" + "".join(f"{i},\n" for i in range(25)), encoding="utf-8")
    assert main(["dedupe", str(path)]) == 0
    assert capsys.readouterr().out.splitlines()[1].endswith(" ...")


@pytest.mark.parametrize("content", ["", "\ufeff"])
def test_cli_dedupe_rejects_empty_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    path = tmp_path / "empty.csv"
    path.write_text(content, encoding="utf-8")
    assert main(["dedupe", str(path)]) == 2
    assert "the file is empty" in capsys.readouterr().err


def test_cli_dedupe_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["dedupe", str(tmp_path / "nope.csv")]) == 2
    assert "nameproof: error:" in capsys.readouterr().err


def test_readme_example_is_current(capsys: pytest.CaptureFixture[str]) -> None:
    root = Path(__file__).resolve().parent.parent
    assert main(["dedupe", str(root / "examples" / "beneficiaries.csv"), "--jobs", "1"]) == 0
    out = capsys.readouterr().out
    assert out in (root / "README.md").read_text(encoding="utf-8")
