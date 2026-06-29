from typing import Protocol


class Notifier(Protocol):
    async def send_stock_alert(self, telegram_user_id: int, message: str) -> None: ...
