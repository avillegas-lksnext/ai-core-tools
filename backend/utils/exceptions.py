class ToolRoundLimitReached(Exception):
    def __init__(
        self,
        rounds_used: int,
        max_rounds: int,
    ):
        self.rounds_used = rounds_used
        self.max_rounds = max_rounds

        super().__init__(
            f"Tool round limit reached "
            f"({rounds_used}/{max_rounds})"
        )