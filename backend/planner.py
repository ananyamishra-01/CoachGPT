"""
Deterministic nutrition and planning logic for CoachGPT.

The arithmetic that matters for health and money (calorie targets, protein
targets, meal costs, budget checks) is done here in plain Python, not by the
language model, because language models are unreliable at exact sums. The AI
is used for conversation and for explaining the plan in friendly language.
"""

import math
import random
from datetime import date, timedelta
from typing import Optional

from data import (
    CURRENCY, DIET_LABELS, DIET_LEVEL, EQUIPMENT_RANK, EXERCISE_LIBRARY,
    FOOD_DB, GOAL_LABELS, HYDRATION_TIPS, MOTIVATION_LINES,
)

CAL_FLOOR = 1400          # never plan below this many kcal a day
CAL_CEIL = 4500
MIN_HEALTHY_BMI = 18.5    # goal weights below this are not accepted
LOSS_RATE_KG_WEEK = 0.45  # ~500 kcal/day deficit
GAIN_RATE_KG_WEEK = 0.35  # ~400 kcal/day surplus
KCAL_PER_KG = 31          # rough maintenance estimate for light/moderate activity
PROTEIN_G_PER_KG = {"weight_loss": 1.6, "weight_gain": 1.8, "maintenance": 1.4}


# ---------------------------------------------------------------------------
# Body metrics, validation and daily targets
# ---------------------------------------------------------------------------
def bmi(weight_kg: float, height_cm: float) -> float:
    return weight_kg / ((height_cm / 100) ** 2)


def bmi_category(value: float) -> str:
    if value < 18.5:
        return "underweight range"
    if value < 25:
        return "healthy range"
    if value < 30:
        return "overweight range"
    return "obese range"


def validate_profile(p: dict) -> None:
    """Raises ValueError with a user-friendly message if the goal is unsafe
    or inconsistent. CoachGPT is meant for adults."""
    w, gw, h, goal = p["current_weight_kg"], p["goal_weight_kg"], p["height_cm"], p["goal"]
    if goal == "weight_loss" and gw >= w:
        raise ValueError("For weight loss, your goal weight must be lower than your current weight.")
    if goal == "weight_gain" and gw <= w:
        raise ValueError("For weight gain, your goal weight must be higher than your current weight.")
    if bmi(gw, h) < MIN_HEALTHY_BMI:
        min_w = math.ceil(MIN_HEALTHY_BMI * (h / 100) ** 2 * 10) / 10
        raise ValueError(
            f"A goal weight of {gw:g} kg would put your BMI below 18.5, which is in the underweight "
            f"range. Please choose a goal weight of at least {min_w:g} kg, or speak to a doctor or "
            f"registered dietitian first (see the 'Talk to a professional' tab)."
        )


def compute_targets(p: dict) -> dict:
    w, h, gw, goal = p["current_weight_kg"], p["height_cm"], p["goal_weight_kg"], p["goal"]
    maintenance = round(w * KCAL_PER_KG / 10) * 10
    adjust = {"weight_loss": -500, "weight_gain": 400, "maintenance": 0}[goal]
    override = p.get("daily_calorie_target")
    source = "your own target" if override else "estimated"
    calories = override if override else maintenance + adjust
    calories = int(max(CAL_FLOOR, min(calories, CAL_CEIL)))

    protein = round(w * PROTEIN_G_PER_KG[goal])
    rate = {"weight_loss": LOSS_RATE_KG_WEEK, "weight_gain": GAIN_RATE_KG_WEEK}.get(goal)
    diff = abs(gw - w)
    weeks = math.ceil(diff / rate) if rate and diff > 0.05 else 0
    cur_bmi, goal_bmi = bmi(w, h), bmi(gw, h)
    return {
        "calories": calories,
        "calorie_source": source,
        "maintenance_calories": int(maintenance),
        "protein_g": int(protein),
        "protein_low_g": int(round(w * 1.2)),
        "protein_high_g": int(round(w * 2.0)),
        "water_litres": round(w * 0.035, 1),
        "weekly_rate_kg": rate,
        "weeks_to_goal": weeks,
        "bmi": round(cur_bmi, 1),
        "bmi_category": bmi_category(cur_bmi),
        "goal_bmi": round(goal_bmi, 1),
        "weight_to_change_kg": round(diff, 1),
    }


# ---------------------------------------------------------------------------
# Food helpers
# ---------------------------------------------------------------------------
def fmt_item(item: dict, mult: float) -> str:
    qty = item["qty"] * mult
    unit = item["unit_sing"] if abs(qty - 1) < 1e-9 else item["unit_plur"]
    return f"{item['name']} \u2014 {qty:g} {unit}"


def best_value_protein(diet: str, n: int = 4) -> list[dict]:
    """Whole foods ranked by grams of protein per rupee, for this diet."""
    level = DIET_LEVEL[diet]
    pool = [f for f in FOOD_DB if f["level"] <= level and not f["supplement"] and f["protein"] >= 6]
    pool.sort(key=lambda f: f["protein"] / f["cost"], reverse=True)
    return [
        {"name": f["name"], "protein_per_10": round(f["protein"] / f["cost"] * 10)}
        for f in pool[:n]
    ]


# ---------------------------------------------------------------------------
# Budget-aware meal planner
# ---------------------------------------------------------------------------
def _main_meal(rng, pools, protein_item):
    carb = rng.choice(pools["carb"])
    meal = [(carb, rng.choice(carb["mults"])), (protein_item, rng.choice(protein_item["mults"]))]
    sides = rng.sample(pools["side"], 2 if rng.random() < 0.5 and len(pools["side"]) > 1 else 1)
    meal += [(s, 1) for s in sides]
    return meal


def _sample_day(rng, pools):
    b_item = rng.choice(pools["bfast"])
    breakfast = [(b_item, rng.choice(b_item["mults"]))]
    if rng.random() < 0.5:
        breakfast.append((rng.choice(pools["snack"]), 1))

    proteins = rng.sample(pools["protein"], 2) if len(pools["protein"]) >= 2 else pools["protein"] * 2
    lunch = _main_meal(rng, pools, proteins[0])
    dinner = _main_meal(rng, pools, proteins[1])

    k = rng.choice((1, 2, 2, 3))
    snack_items = rng.sample(pools["snack"], min(k, len(pools["snack"])))
    snack = [(i, rng.choice(i["mults"])) for i in snack_items]
    return [("Breakfast", breakfast), ("Lunch", lunch), ("Snack", snack), ("Dinner", dinner)]


def _sum(meal):
    kcal = sum(i["kcal"] * m for i, m in meal)
    prot = sum(i["protein"] * m for i, m in meal)
    cost = sum(i["cost"] * m for i, m in meal)
    supp = sum(1 for i, _ in meal if i["supplement"])
    return kcal, prot, cost, supp


def _score(day, kcal_t, prot_t, budget):
    kcal = prot = cost = supp = 0
    for _, meal in day:
        k, p, c, s = _sum(meal)
        kcal += k; prot += p; cost += c; supp += s
    shortfall = max(0.0, kcal_t - kcal) / kcal_t * 100
    surplus = max(0.0, kcal - kcal_t) / kcal_t * 100
    score = shortfall * 1.5 + surplus * 1.0
    score += max(0.0, shortfall - 12) * 10      # never accept a plan far below target
    score += max(0.0, surplus - 15) * 5
    score += max(0.0, prot_t - prot) / prot_t * 100 * 2.0
    score += max(0.0, cost - budget) / budget * 100 * 8
    score += cost / budget * 3                  # mild preference for cheaper plans
    score += supp * 4                           # prefer whole foods over supplements
    return score



def _mutate(rng, day, pools):
    """Returns a slightly changed copy of a day: one item's portion size is
    changed, or one item is swapped for another food of the same role."""
    new = [(name, list(items)) for name, items in day]
    _, items = new[rng.randrange(len(new))]
    idx = rng.randrange(len(items))
    item, mult = items[idx]
    if rng.random() < 0.5:
        items[idx] = (item, rng.choice(item["mults"]))
    else:
        other = rng.choice(pools[item["role"]])
        if other["id"] not in {i["id"] for i, _ in items}:
            items[idx] = (other, mult if mult in other["mults"] else rng.choice(other["mults"]))
    return new


def generate_meal_plan(profile: dict, targets: dict, budget: float,
                       rng: Optional[random.Random] = None, samples: int = 6000) -> dict:
    rng = rng or random.Random()
    level = DIET_LEVEL[profile["diet"]]
    pools = {
        role: [f for f in FOOD_DB if f["role"] == role and f["level"] <= level]
        for role in ("bfast", "protein", "carb", "side", "snack")
    }
    kcal_t, prot_t = targets["calories"], targets["protein_g"]

    best, best_score = None, float("inf")
    for _ in range(samples):
        day = _sample_day(rng, pools)
        s = _score(day, kcal_t, prot_t, budget)
        if s < best_score:
            best, best_score = day, s

    # Refinement: nudge portions and swap foods to squeeze out a better fit.
    for _ in range(3000):
        candidate = _mutate(rng, best, pools)
        s = _score(candidate, kcal_t, prot_t, budget)
        if s <= best_score:
            best, best_score = candidate, s

    meals = []
    for name, items in best:
        kcal, prot, cost, _ = _sum(items)
        meals.append({
            "name": name,
            "items": [fmt_item(i, m) for i, m in items],
            "calories": int(round(kcal)),
            "protein_g": int(round(prot)),
            "cost": int(round(cost)),
        })
    cal_total = sum(m["calories"] for m in meals)
    prot_total = sum(m["protein_g"] for m in meals)
    cost_total = sum(m["cost"] for m in meals)

    within_budget = cost_total <= budget
    protein_met = prot_total >= 0.9 * prot_t
    warnings = []
    if not within_budget:
        cheap = ", ".join(f["name"].lower() for f in best_value_protein(profile["diet"], 3))
        warnings.append(
            f"A budget of {CURRENCY}{budget:g} a day is tight for your targets. The cheapest "
            f"suitable plan found costs about {CURRENCY}{cost_total}. Good-value protein for your "
            f"diet: {cheap}."
        )
    if not protein_met:
        warnings.append(
            f"This plan reaches about {prot_total} g of protein against a target of {prot_t} g. "
            f"A slightly higher budget would make it easier to close the gap."
        )
    if cal_total < 0.88 * kcal_t:
        warnings.append(
            f"This plan is about {kcal_t - cal_total} kcal under your target. Please don't cut "
            f"food further to save money; adjust the budget or the goal instead."
        )

    return {
        "meals": meals,
        "calories_total": cal_total,
        "protein_total_g": prot_total,
        "cost_total": cost_total,
        "budget": budget,
        "currency": CURRENCY,
        "calorie_target": kcal_t,
        "protein_target_g": prot_t,
        "within_budget": within_budget,
        "protein_met": protein_met,
        "water_litres": targets["water_litres"],
        "hydration_tip": HYDRATION_TIPS[profile["goal"]],
        "cost_note": "Costs are rough Indian market estimates per serving and will vary by city and season.",
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Mock workout (dataset-driven)
# ---------------------------------------------------------------------------
def build_mock_workout(profile: Optional[dict]) -> str:
    goal = (profile or {}).get("goal", "maintenance")
    equipment = (profile or {}).get("equipment", "none")
    max_rank = EQUIPMENT_RANK.get(equipment, 0)
    matches = [
        ex for ex in EXERCISE_LIBRARY
        if goal in ex["goals"] and EQUIPMENT_RANK[ex["equipment"]] <= max_rank
    ] or [ex for ex in EXERCISE_LIBRARY if ex["equipment"] == "none"]

    session = random.sample(matches, k=min(4, len(matches)))
    lines = ["Here's today's session, built around your goal and equipment:\n"]
    for ex in session:
        lines.append(f"- **{ex['name']}** \u2014 {ex['sets']} x {ex['reps']}  \n  _Form cue: {ex['form_tip']}_")
    lines.append(f"\n{random.choice(MOTIVATION_LINES)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Progress summary
# ---------------------------------------------------------------------------
def progress_summary(profile: dict, entries: dict, today: date) -> dict:
    dated = sorted(entries.items())
    weights = [(d, e["weight_kg"]) for d, e in dated if e.get("weight_kg")]
    start = profile.get("start_weight_kg") or profile["current_weight_kg"]
    goal = profile["goal_weight_kg"]
    latest = weights[-1][1] if weights else profile["current_weight_kg"]

    percent = None
    if profile["goal"] == "weight_loss" and start - goal > 0:
        percent = (start - latest) / (start - goal) * 100
    elif profile["goal"] == "weight_gain" and goal - start > 0:
        percent = (latest - start) / (goal - start) * 100
    if percent is not None:
        percent = int(round(max(0, min(100, percent))))

    have = set(entries.keys())
    cursor = today if today.isoformat() in have else today - timedelta(days=1)
    streak = 0
    while cursor.isoformat() in have:
        streak += 1
        cursor -= timedelta(days=1)

    week_ago = (today - timedelta(days=6)).isoformat()
    recent = [e["goal_percent_complete"] for d, e in dated if d >= week_ago]
    return {
        "start_weight_kg": start,
        "latest_weight_kg": latest,
        "goal_weight_kg": goal,
        "weight_change_kg": round(latest - start, 1),
        "percent_to_goal": percent,
        "streak_days": streak,
        "workouts_logged": sum(1 for _, e in dated if e.get("workout_done")),
        "avg_plan_percent_7d": int(round(sum(recent) / len(recent))) if recent else None,
        "entries_count": len(dated),
    }
