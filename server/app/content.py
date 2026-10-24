"""Bot content files: format, validation and loading.

A bot is described by one JSON file. The file carries a ``format_version``, the
branding and opening questions under ``config`` and the answer nodes as a list
under ``answers``. The bot's identity is ``config.id``; the file name does not
matter. ``validate_bot_content`` is the single validation entry point and is
exercised by the shared fixtures in ``fixtures/content`` at the repository
root, so a browser editor can later apply the same rules to the same cases.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

from .models import AnswerNode, BotConfig, BotDefinition, ChatOption

FORMAT_VERSION = 1

# IDs appear in URLs and request bodies. The request model caps option_id at 100
# characters, so a longer content ID could never be selected.
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
MAX_ID_LENGTH = 100
HEX_COLOR_PATTERN = r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$"

# Length caps keep a content mistake from producing an unusable widget layout.
MAX_NAME_LENGTH = 80
MAX_GREETING_LENGTH = 500
MAX_LAUNCHER_LABEL_LENGTH = 120
MAX_LABEL_LENGTH = 200
MAX_ANSWER_LENGTH = 4000


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("text must not be blank")
    return value


def _text(max_length: int) -> Any:
    return Annotated[str, StringConstraints(max_length=max_length), AfterValidator(_not_blank)]


ContentId = Annotated[str, StringConstraints(pattern=ID_PATTERN, max_length=MAX_ID_LENGTH)]
HexColor = Annotated[str, StringConstraints(pattern=HEX_COLOR_PATTERN)]


class BotContentConfig(BaseModel):
    """Branding and opening questions. Opening labels come from the answers."""

    model_config = ConfigDict(extra="forbid")

    id: ContentId
    name: _text(MAX_NAME_LENGTH)
    greeting: _text(MAX_GREETING_LENGTH)
    launcher_label: _text(MAX_LAUNCHER_LABEL_LENGTH)
    primary_color: HexColor
    opening_option_ids: list[ContentId] = Field(min_length=1)


class AnswerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ContentId
    label: _text(MAX_LABEL_LENGTH)
    answer: _text(MAX_ANSWER_LENGTH)
    next_option_ids: list[ContentId] = Field(default_factory=list)


class BotContentFile(BaseModel):
    """Shape of one bot content file. Cross references are checked separately."""

    model_config = ConfigDict(extra="forbid")

    format_version: int
    config: BotContentConfig
    answers: list[AnswerEntry] = Field(min_length=1)

    @field_validator("format_version")
    @classmethod
    def supported_version(cls, value: int) -> int:
        if value != FORMAT_VERSION:
            raise ValueError(
                f"unsupported format_version {value}; this server reads version {FORMAT_VERSION}"
            )
        return value

    def to_definition(self) -> BotDefinition:
        """Build the runtime definition the API serves, keeping the response shape."""
        answers = {
            entry.id: AnswerNode(
                label=entry.label,
                answer=entry.answer,
                next_option_ids=list(entry.next_option_ids),
            )
            for entry in self.answers
        }
        config = BotConfig(
            id=self.config.id,
            name=self.config.name,
            greeting=self.config.greeting,
            launcher_label=self.config.launcher_label,
            primary_color=self.config.primary_color,
            options=[
                ChatOption(id=option_id, label=answers[option_id].label)
                for option_id in self.config.opening_option_ids
            ],
        )
        return BotDefinition(config=config, answers=answers)


@dataclass(frozen=True)
class ContentProblem:
    """One validation problem. ``path`` locates it in the document, "" is the root."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path or '(document)'}: {self.message}"


class InvalidBotContent(Exception):
    """One document failed validation. ``problems`` lists every issue found."""

    def __init__(self, problems: list[ContentProblem]) -> None:
        self.problems = problems
        super().__init__("; ".join(str(problem) for problem in problems))


@dataclass(frozen=True)
class FileReport:
    path: Path
    problems: list[ContentProblem]


class ContentLoadError(Exception):
    """Loading a content directory failed. Nothing from the batch should be used."""

    def __init__(self, reports: list[FileReport]) -> None:
        self.reports = reports
        super().__init__(self._describe())

    def _describe(self) -> str:
        count = len(self.reports)
        noun = "file" if count == 1 else "files"
        lines = [f"Bot content was rejected ({count} {noun} with problems):"]
        for report in self.reports:
            lines.append(f"  {report.path}")
            lines.extend(f"    {problem}" for problem in report.problems)
        return "\n".join(lines)


def format_path(loc: tuple[int | str, ...]) -> str:
    """Turn a pydantic location into ``answers[1].next_option_ids[0]`` style paths."""
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else part
    return path


def _describe_shape_error(detail: dict[str, Any]) -> str:
    """Give shape errors a small, stable vocabulary that an editor can reproduce."""
    kind = detail["type"]
    context = detail.get("ctx") or {}
    if kind == "missing":
        return "field is required"
    if kind == "extra_forbidden":
        return "unknown field"
    if kind in {"model_type", "dict_type", "model_attributes_type"}:
        return "must be a JSON object"
    if kind == "list_type":
        return "must be a list"
    if kind == "string_type":
        return "must be text"
    if kind in {"int_type", "int_parsing", "int_from_float"}:
        return "must be a whole number"
    if kind == "too_short":
        return f"must have at least {context.get('min_length', 1)} item(s)"
    if kind == "string_too_long":
        return f"must be at most {context.get('max_length')} characters"
    if kind == "string_pattern_mismatch":
        if context.get("pattern") == HEX_COLOR_PATTERN:
            return "must be a hex color like #155eef or #fff"
        if context.get("pattern") == ID_PATTERN:
            return "must start with a letter or digit and use only letters, digits, - and _"
    message = detail["msg"]
    if message.startswith("Value error, "):
        message = message[len("Value error, ") :]
    return message


def _shape_problems(error: ValidationError) -> list[ContentProblem]:
    return [
        ContentProblem(format_path(tuple(detail["loc"])), _describe_shape_error(detail))
        for detail in error.errors()
    ]


def find_reference_problems(content: BotContentFile) -> list[ContentProblem]:
    """Report duplicate IDs and references to answers that do not exist."""
    problems: list[ContentProblem] = []
    first_seen: dict[str, int] = {}
    for index, entry in enumerate(content.answers):
        if entry.id in first_seen:
            first = first_seen[entry.id]
            problems.append(
                ContentProblem(
                    f"answers[{index}].id",
                    f"duplicate answer id '{entry.id}' (first defined at answers[{first}])",
                )
            )
        else:
            first_seen[entry.id] = index

    def check_list(path: str, option_ids: list[str], what: str) -> None:
        seen: set[str] = set()
        for index, option_id in enumerate(option_ids):
            location = f"{path}[{index}]"
            if option_id in seen:
                problems.append(ContentProblem(location, f"duplicate {what} '{option_id}'"))
            seen.add(option_id)
            if option_id not in first_seen:
                problems.append(
                    ContentProblem(location, f"{what} '{option_id}' has no matching answer")
                )

    check_list("config.opening_option_ids", content.config.opening_option_ids, "opening option")
    for index, entry in enumerate(content.answers):
        check_list(f"answers[{index}].next_option_ids", entry.next_option_ids, "follow up option")
    return problems


def validate_bot_content(data: Any) -> BotContentFile:
    """Validate parsed JSON data as a bot content document.

    Shape problems (missing or unknown fields, wrong types, blank text, bad
    colors or IDs, an unsupported format version) are collected first. Cross
    reference problems are only checked once the shape is valid, because the
    paths they report assume well formed answers. Raises ``InvalidBotContent``
    with every problem found at that stage.
    """
    try:
        content = BotContentFile.model_validate(data)
    except ValidationError as error:
        raise InvalidBotContent(_shape_problems(error)) from None
    problems = find_reference_problems(content)
    if problems:
        raise InvalidBotContent(problems)
    return content


def parse_bot_content(text: str) -> BotContentFile:
    """Parse and validate raw JSON text. Malformed JSON is reported at the root."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise InvalidBotContent([ContentProblem("", f"malformed JSON: {error}")]) from None
    return validate_bot_content(data)


def load_bot_file(path: Path) -> BotDefinition:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise InvalidBotContent([ContentProblem("", f"file is not UTF-8 text: {error}")]) from None
    return parse_bot_content(text).to_definition()


def load_content_documents(directory: Path) -> dict[str, Any]:
    """Load every ``*.json`` file in ``directory`` as one raw bot document each.

    The returned documents are the parsed JSON values exactly as written, keyed
    by the bot ID inside each one, after passing full validation. Either every
    file is valid and the complete set is returned, or a ``ContentLoadError``
    lists every problem in every file and nothing is returned, so the caller
    never ends up with a partial set. This is the single loading path for both
    the file repository and the database importer.
    """
    if not directory.is_dir():
        raise ContentLoadError(
            [FileReport(directory, [ContentProblem("", "content directory does not exist")])]
        )
    files = sorted(
        path for path in directory.iterdir() if path.is_file() and path.suffix == ".json"
    )
    if not files:
        raise ContentLoadError(
            [FileReport(directory, [ContentProblem("", "content directory has no .json files")])]
        )

    documents: dict[str, Any] = {}
    defined_in: dict[str, Path] = {}
    reports: list[FileReport] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            reports.append(
                FileReport(path, [ContentProblem("", f"file is not UTF-8 text: {error}")])
            )
            continue
        try:
            data = json.loads(text)
            validate_bot_content(data)
        except InvalidBotContent as error:
            reports.append(FileReport(path, error.problems))
            continue
        except json.JSONDecodeError as error:
            reports.append(FileReport(path, [ContentProblem("", f"malformed JSON: {error}")]))
            continue
        bot_id = data["config"]["id"]
        if bot_id in defined_in:
            reports.append(
                FileReport(
                    path,
                    [
                        ContentProblem(
                            "config.id",
                            f"bot id '{bot_id}' is already defined in {defined_in[bot_id].name}",
                        )
                    ],
                )
            )
            continue
        defined_in[bot_id] = path
        documents[bot_id] = data
    if reports:
        raise ContentLoadError(reports)
    return documents


def definition_from_document(document: Any) -> BotDefinition:
    """Build the runtime definition from an already validated raw document."""
    return BotContentFile.model_validate(document).to_definition()


def load_content_directory(directory: Path) -> dict[str, BotDefinition]:
    """Load every bot in ``directory`` as a runtime definition, all or nothing."""
    return {
        bot_id: definition_from_document(document)
        for bot_id, document in load_content_documents(directory).items()
    }
