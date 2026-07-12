from pydantic import BaseModel, Field


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
