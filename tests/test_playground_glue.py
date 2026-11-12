import csv
import io
import json

import pytest

from nameproof._playground import find_in_text, inspect_csv
from nameproof._table import csv_header, name_column, read_table


def test_inspect_csv_guesses_the_name_column() -> None:
    text = "\ufeffid;Name;city\n1;Ali;Sfax\n2;علي;Sfax\n"
    assert json.loads(inspect_csv(text)) == {
        "header": ["id", "Name", "city"],
        "column": 1,
        "rows": 2,
    }
    assert csv_header("a,b\n1,2\n") == (["a", "b"], None, 1)


def test_find_in_pasted_text() -> None:
    seen: list[tuple[int, int]] = []
    result = json.loads(
        find_in_text(
            "Fatma Trabelsi\nAhmed Salah\n\nفاطمة الطرابلسي\n",
            True,
            None,
            lambda d, t: seen.append((d, t)),
        )
    )
    assert result["names"] == 4
    assert result["unchecked"] == [3]
    assert result["groups"] == [
        {
            "review": True,
            "members": [
                {"row": 1, "name": "Fatma Trabelsi"},
                {"row": 4, "name": "فاطمة الطرابلسي"},
            ],
            "links": [
                {
                    "rows": [1, 4],
                    "result": "CLOSE_MATCH",
                    "explanation": ["transliterated", "approximate_transliteration", "fuzzy_token"],
                }
            ],
        }
    ]
    assert seen[0] == (0, result["compared"])
    assert seen[-1] == (result["compared"], result["compared"])
    rows = list(csv.reader(io.StringIO(result["csv"])))
    assert rows[0] == ["group", "review", "row", "name"]
    assert rows[1:] == [["1", "yes", "1", "Fatma Trabelsi"], ["1", "yes", "4", "فاطمة الطرابلسي"]]


def test_find_in_csv_with_a_chosen_column() -> None:
    text = "first,full\nx,John Smith\ny,J. Smith\nz,Peter Brown\n"
    result = json.loads(find_in_text(text, False, "full"))
    assert [member["row"] for member in result["groups"][0]["members"]] == [2, 3]
    assert result["policy"] == "epc-default@2"
    with pytest.raises(ValueError, match="choose the name column"):
        find_in_text(text, False)


def test_short_rows_have_empty_names() -> None:
    table = read_table("id,name\n1\n2,Ali\n", plain=False)
    assert table.names == ["", "Ali"]
    assert name_column(["Name"]) == 0


@pytest.mark.parametrize(
    ("header", "column"),
    [
        (["id", "Beneficiary name", "city"], 1),
        (["N°", "Nom et prénom", "Ville"], 1),
        (["الرقم", "الاسم الكامل"], 1),
        (["id", "first name", "last name"], None),  # two candidates: ask
        (["id", "city"], None),
    ],
)
def test_name_column_guess(header: list[str], column: int | None) -> None:
    assert name_column(header) == column
