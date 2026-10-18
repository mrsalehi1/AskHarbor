from .models import AnswerNode, BotConfig, BotDefinition, ChatOption


class BotRepository:
    def __init__(self) -> None:
        self._bots = {"demo": self._demo_bot()}

    def get(self, bot_id: str) -> BotDefinition | None:
        return self._bots.get(bot_id)

    @staticmethod
    def _demo_bot() -> BotDefinition:
        answers = {
            "getting-started": AnswerNode(
                label="How do I get started?",
                answer=(
                    "Add the AskHarbor script before your closing body tag and provide your "
                    "server URL and bot ID."
                ),
                next_option_ids=["installation", "customize"],
            ),
            "features": AnswerNode(
                label="What can this chatbot do?",
                answer=(
                    "This version provides guided answers from your server. Questions, follow-ups, "
                    "and branding all come from the bot configuration."
                ),
                next_option_ids=["customize"],
            ),
            "contact": AnswerNode(
                label="How can I contact support?",
                answer="Email your support team at support@example.com.",
            ),
            "installation": AnswerNode(
                label="Show installation details",
                answer=(
                    "Serve the compiled widget, then set data-api-url and data-bot-id on the "
                    "script element."
                ),
            ),
            "customize": AnswerNode(
                label="Can I customize it?",
                answer=(
                    "Yes. Bot name, greeting, launcher label, color, questions, and answers all "
                    "come from the server."
                ),
            ),
        }
        opening_ids = ["getting-started", "features", "contact"]
        config = BotConfig(
            id="demo",
            name="AskHarbor",
            greeting="Hi! What can I help you with?",
            launcher_label="Open support chat",
            primary_color="#155eef",
            options=[
                ChatOption(id=option_id, label=answers[option_id].label)
                for option_id in opening_ids
            ],
        )
        return BotDefinition(config=config, answers=answers)


repository = BotRepository()
