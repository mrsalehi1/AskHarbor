"""Run the shared content fixtures through the server's validation.

The fixtures live at the repository root so a browser editor can run the same
cases later. See fixtures/content/README.md for the case format.
"""

import json
from pathlib import Path

import pytest

from app.content import (
    ContentProblem,
    InvalidBotContent,
    format_path,
    parse_bot_content,
    validate_bot_content,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "content"
VALID = sorted((FIXTURES / "valid").glob("*.json"))
INVALID = sorted((FIXTURES / "invalid").glob("*.json"))
MALFORMED = sorted((FIXTURES / "malformed").glob("*.json"))


def test_fixture_directories_are_populated() -> None:
    assert VALID and INVALID and MALFORMED


@pytest.mark.parametrize("path", VALID, ids=lambda path: path.stem)
def test_valid_fixture_is_accepted_and_loads_as_a_bot(path: Path) -> None:
    content = parse_bot_content(path.read_text(encoding="utf-8"))
    bot = content.to_definition()

    assert bot.config.id == content.config.id
    assert [option.id for option in bot.config.options] == content.config.opening_option_ids
    assert set(bot.answers) == {entry.id for entry in content.answers}


@pytest.mark.parametrize("path", INVALID, ids=lambda path: path.stem)
def test_invalid_fixture_reports_every_expected_problem(path: Path) -> None:
    case = json.loads(path.read_text(encoding="utf-8"))
    assert case["expected_problems"], f"{path.name} lists no expected problems"

    with pytest.raises(InvalidBotContent) as excinfo:
        validate_bot_content(case["content"])

    reported = excinfo.value.problems
    for expected in case["expected_problems"]:
        matches = [
            problem
            for problem in reported
            if problem.path == expected["path"] and expected["contains"] in problem.message
        ]
        assert matches, (
            f"{path.name}: expected a problem at '{expected['path']}' containing "
            f"'{expected['contains']}', got {[str(p) for p in reported]}"
        )


@pytest.mark.parametrize("path", MALFORMED, ids=lambda path: path.stem)
def test_malformed_fixture_is_reported_at_the_document_root(path: Path) -> None:
    with pytest.raises(InvalidBotContent) as excinfo:
        parse_bot_content(path.read_text(encoding="utf-8"))

    assert len(excinfo.value.problems) == 1
    problem = excinfo.value.problems[0]
    assert problem.path == ""
    assert "JSON" in problem.message


def test_opening_labels_come_from_the_answers() -> None:
    content = parse_bot_content((FIXTURES / "valid" / "branching.json").read_text())
    bot = content.to_definition()

    labels = {entry.id: entry.label for entry in content.answers}
    assert [(option.id, option.label) for option in bot.config.options] == [
        ("start", labels["start"]),
        ("pricing", labels["pricing"]),
    ]


def test_reference_problems_are_only_checked_once_the_shape_is_valid() -> None:
    # A broken shape would make reference paths meaningless, so they wait.
    document = {"format_version": 1, "config": {"id": "x"}, "answers": "nope"}
    with pytest.raises(InvalidBotContent) as excinfo:
        validate_bot_content(document)
    problems = excinfo.value.problems
    assert any(p.path == "answers" and p.message == "must be a list" for p in problems)
    assert not any("has no matching answer" in p.message for p in problems)


def test_format_path_uses_dots_and_brackets() -> None:
    assert format_path(()) == ""
    assert format_path(("config", "primary_color")) == "config.primary_color"
    assert format_path(("answers", 1, "next_option_ids", 0)) == "answers[1].next_option_ids[0]"


def test_problem_string_names_the_document_root() -> None:
    assert str(ContentProblem("", "malformed JSON")) == "(document): malformed JSON"
    assert str(ContentProblem("config.id", "bad")) == "config.id: bad"
