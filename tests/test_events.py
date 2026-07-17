import asyncio

from nice_pro.core.events import EventBus


def test_event_bus_delivers_payload() -> None:
    bus = EventBus()
    received: list[dict[str, int]] = []

    async def capture(event) -> None:
        received.append(event.payload)

    bus.subscribe("market.quote", capture)
    asyncio.run(bus.publish("market.quote", {"price": 25000}))

    assert received == [{"price": 25000}]
