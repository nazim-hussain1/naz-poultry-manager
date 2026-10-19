def egg_stats(birds, collected, broken):
    good = collected - broken
    return {
        "good": good,
        "trays": good // 30,
        "loose": good % 30,
        "dozens": good / 12,
        "production_pct": round(collected / birds * 100, 1) if birds else 0,
    }
def rs(n):
    return f"Rs. {n:,.0f}"