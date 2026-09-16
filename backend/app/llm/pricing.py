"""Estimated model pricing, per 1,000,000 tokens (FR-073).

Estimates, not billing. Vendor prices change and are the operator's to keep current — this table
exists so cost is recorded from the first call and FR-073/FR-075 are measurable rather than
discovered later (FEASIBILITY §5). An unknown model costs 0, which is safe because the gateway
refuses a model that is not on the allowlist.
"""

from decimal import Decimal

_MILLION = Decimal(1_000_000)

# model id -> (input USD / 1M tokens, output USD / 1M tokens). Estimates only; vendor prices
# change and are the operator's to verify before trusting the budget numbers.
DEFAULT_PRICING: dict[str, tuple[Decimal, Decimal]] = {
    "gemini-2.5-flash": (Decimal("0.30"), Decimal("2.50")),
    "kimi-k2.6": (Decimal("0.60"), Decimal("2.50")),
    "kimi-k3": (Decimal("1.20"), Decimal("5.00")),
    # DeepSeek's published list prices; verify before trusting the budget numbers.
    "deepseek-chat": (Decimal("0.27"), Decimal("1.10")),
    "deepseek-reasoner": (Decimal("0.55"), Decimal("2.19")),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    prices = DEFAULT_PRICING.get(model)
    if prices is None:
        return Decimal(0)
    input_price, output_price = prices
    return (input_price * input_tokens + output_price * output_tokens) / _MILLION
