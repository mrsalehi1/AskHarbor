from .models import BotDefinition


class BotRepository:
    """Holds the complete set of loaded bots and swaps it as one unit.

    ``replace`` assigns a new mapping in a single step, so a request handler
    always sees either the previous set or the new one, never a mixture. The
    caller validates the whole batch before calling it.
    """

    def __init__(self, bots: dict[str, BotDefinition] | None = None) -> None:
        self._bots: dict[str, BotDefinition] = dict(bots or {})

    def get(self, bot_id: str) -> BotDefinition | None:
        return self._bots.get(bot_id)

    def ids(self) -> list[str]:
        return sorted(self._bots)

    def replace(self, bots: dict[str, BotDefinition]) -> None:
        self._bots = dict(bots)
