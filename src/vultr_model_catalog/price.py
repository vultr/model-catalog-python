from decimal import Decimal, InvalidOperation


def usd_per_million(cost_usd: str) -> float:
    """cost_usd is a decimal string in USD per unit; Decimal keeps "0.0000001" exact (0.1)."""
    try:
        return float(Decimal(cost_usd.strip()) * 1_000_000)
    except InvalidOperation:
        return float("nan")
