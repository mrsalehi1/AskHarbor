from pydantic import BaseModel, Field, model_validator


class ChatOption(BaseModel):
    id: str
    label: str


class BotConfig(BaseModel):
    id: str
    name: str
    greeting: str
    launcher_label: str
    primary_color: str
    options: list[ChatOption]


class MessageRequest(BaseModel):
    option_id: str = Field(min_length=1, max_length=100)


class MessageResponse(BaseModel):
    answer: str
    options: list[ChatOption] = Field(default_factory=list)


class AnswerNode(BaseModel):
    label: str
    answer: str
    next_option_ids: list[str] = Field(default_factory=list)


class BotDefinition(BaseModel):
    config: BotConfig
    answers: dict[str, AnswerNode]

    @model_validator(mode="after")
    def check_references(self) -> "BotDefinition":
        """Reject content whose options point at answers that do not exist.

        A typo in a follow up reference would otherwise vanish silently from
        the conversation. The error names the bot, the answer holding the bad
        reference and the missing option ID so the content can be corrected.
        """
        problems = [
            f"answer '{answer_id}' references missing option '{option_id}'"
            for answer_id, node in self.answers.items()
            for option_id in node.next_option_ids
            if option_id not in self.answers
        ]
        problems += [
            f"opening option '{option.id}' has no matching answer"
            for option in self.config.options
            if option.id not in self.answers
        ]
        if problems:
            summary = "; ".join(problems)
            raise ValueError(f"Bot '{self.config.id}' has invalid references: {summary}")
        return self
