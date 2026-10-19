"""
Conversation logic for CoachGPT: the persona/system prompt, the free mock
coach (built-in datasets), and the Gemini integration.
"""

import random
import time
from typing import Optional

import config
from data import (
    CURRENCY, DIET_LABELS, EXERCISE_LIBRARY, GOAL_LABELS, MOTIVATION_LINES,
)
from planner import best_value_protein, build_mock_workout

def _a(word: str) -> str:
    return ("an " if word[0].lower() in "aeiou" else "a ") + word


DIET_RULES = (
    "Diet rules: vegan = no meat, fish, eggs, dairy or honey; vegetarian = dairy is fine, "
    "but no eggs, meat or fish; eggetarian = vegetarian plus eggs, but no meat or fish; "
    "non-vegetarian = everything."
)


def build_system_prompt(profile: Optional[dict], targets: Optional[dict]) -> str:
    base = (
        "You are CoachGPT, an encouraging AI fitness and nutrition guide. You give safe, "
        "practical workout plans, exercise form cues, food ideas and motivation. You are NOT a "
        "doctor or dietitian and you NEVER give medical diagnoses. If the user mentions pain, "
        "injury, a diagnosed medical condition (including kidney disease or diabetes), pregnancy, "
        "or possible signs of disordered eating, you must: (1) stop giving a normal workout or "
        "meal response, (2) gently say this is outside what an AI coach should advise on, and "
        "(3) point them to the app's 'Talk to a professional' section. Never encourage crash "
        "diets, skipping meals, or eating below the calorie target, and never present "
        "supplements as necessary. Keep answers structured, concise and actionable, with short "
        "headers and bullet points where helpful. " + DIET_RULES
    )
    if profile:
        base += (
            "\n\nUser profile:\n"
            f"- Goal: {GOAL_LABELS.get(profile['goal'], profile['goal'])}\n"
            f"- Diet: {DIET_LABELS.get(profile['diet'], profile['diet'])}\n"
            f"- Experience: {profile['experience']}\n"
            f"- Equipment: {profile['equipment']}\n"
            f"- Height: {profile['height_cm']:g} cm; current weight: {profile['current_weight_kg']:g} kg; "
            f"goal weight: {profile['goal_weight_kg']:g} kg\n"
            f"- Daily food budget: {CURRENCY}{profile['daily_budget']:g} (prices in Indian rupees)\n"
        )
    if targets:
        base += (
            f"Daily targets: about {targets['calories']} kcal and about {targets['protein_g']} g "
            f"protein (general range {targets['protein_low_g']}-{targets['protein_high_g']} g), "
            f"water about {targets['water_litres']} litres.\n"
            "Respect the user's diet strictly and keep food suggestions affordable within their "
            "budget. Tailor every workout and nutrition suggestion to this profile."
        )
    return base


# ---------------------------------------------------------------------------
# Mock coach (LLM_PROVIDER=mock)
# ---------------------------------------------------------------------------
RED_FLAGS = [
    "pain", "hurt", "injur", "pregnan", "diagnosed", "diabetes", "heart condition",
    "kidney", "dizzy", "faint", "eating disorder", "purge", "binge", "doctor said",
    "starv", "crash diet", "stop eating", "not eating", "laxative", "vomit",
]


def _mock_reply(profile, targets, last_user_text: str) -> str:
    text = last_user_text.lower()
    diet = (profile or {}).get("diet", "vegetarian")

    if any(w in text for w in RED_FLAGS):
        return (
            "That's outside what I should advise on as an AI coach \u2014 pain, injury, pregnancy, "
            "medical conditions and eating concerns really do need a real person's judgement, not "
            "mine. Please check the **\"Talk to a professional\"** tab in the sidebar \u2014 it has "
            "a safety checklist and links to find a certified trainer or registered dietitian. "
            "I'm still here for general fitness questions whenever you're ready."
        )

    if "protein" in text and targets:
        top = best_value_protein(diet, 4)
        lines = [
            f"Your protein target is about **{targets['protein_g']} g a day** (a sensible range is "
            f"{targets['protein_low_g']}\u2013{targets['protein_high_g']} g for your weight).",
            f"\nBest-value protein sources for {_a(DIET_LABELS[diet])} diet:",
        ]
        lines += [f"- {t['name']} \u2014 about {t['protein_per_10']} g of protein per {CURRENCY}10" for t in top]
        lines.append(
            "\nSpread protein across all meals rather than one big serving. If you have kidney "
            "problems or any medical condition, check protein targets with a doctor first."
        )
        return "\n".join(lines)

    if any(w in text for w in ["budget", "cheap", "afford", "expensive", "cost", "money"]) and profile:
        top = best_value_protein(diet, 4)
        names = ", ".join(t["name"].lower() for t in top)
        return (
            f"On a budget of {CURRENCY}{profile['daily_budget']:g} a day you can still eat well. "
            f"The cheapest ways to hit protein on {_a(DIET_LABELS[diet])} diet are {names}. "
            f"Build lunch and dinner around dal, roti or rice and a vegetable, then add one of "
            f"those protein foods. Open the **Meal planner** tab and I'll cost out a full day for you."
        )

    if any(w in text for w in ["how long", "how many weeks", "goal weight", "when will i", "my progress"]) and profile and targets:
        if targets["weeks_to_goal"]:
            return (
                f"You're at {profile['current_weight_kg']:g} kg and aiming for "
                f"{profile['goal_weight_kg']:g} kg \u2014 about {targets['weight_to_change_kg']:g} kg to go. "
                f"At a steady, safe pace of roughly {targets['weekly_rate_kg']:g} kg a week that's "
                f"around {targets['weeks_to_goal']} weeks. Slow and steady is safer and lasts longer. "
                f"Log your weight in the **Daily progress** tab to track it."
            )
        return "You're maintaining your weight, so the aim now is consistency. Keep logging your days."

    if any(w in text for w in ["motivat", "tired", "lazy", "don't feel", "skip"]):
        return random.choice(MOTIVATION_LINES)

    if any(w in text for w in ["form", "technique", "how do i do"]):
        ex = random.choice(EXERCISE_LIBRARY)
        return f"Form cue for **{ex['name']}**: {ex['form_tip']} Aim for {ex['sets']} sets of {ex['reps']}."

    return build_mock_workout(profile)


def mock_chat_stream(profile, targets, chat_messages: list[dict]):
    last_user_text = ""
    for m in reversed(chat_messages):
        if m["role"] == "user":
            last_user_text = m["content"]
            break
    for word in _mock_reply(profile, targets, last_user_text).split(" "):
        yield word + " "
        time.sleep(0.015)


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------
def gemini_chat_stream(system_prompt: str, messages: list[dict]):
    """Streams the reply from Gemini. Gemini calls the assistant role "model"."""
    from google.genai import types

    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in messages
    ]
    stream = config.client.models.generate_content_stream(
        model=config.MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    for chunk in stream:
        if chunk.text:
            yield chunk.text


def mock_plan_note(plan: dict, profile: dict, targets: dict) -> str:
    top = ", ".join(t["name"].lower() for t in best_value_protein(profile["diet"], 3))
    status = "within" if plan["within_budget"] else "over"
    return (
        f"This {DIET_LABELS[profile['diet']]} plan costs about {CURRENCY}{plan['cost_total']} against your "
        f"{CURRENCY}{plan['budget']:g} budget ({status} budget) and gives roughly {plan['protein_total_g']} g of protein "
        f"toward your {plan['protein_target_g']} g target. To save money, lean on {top}; "
        f"seasonal fruit and home-cooked dal and sabzi keep costs down."
    )


def coach_note(plan: dict, profile: dict, targets: dict) -> tuple[str, str]:
    """Returns (note, source). Uses Gemini when available and falls back to a
    template, so the meal plan itself never fails because of the AI service."""
    if config.LLM_PROVIDER == "gemini" and config.client:
        try:
            from google.genai import types

            summary = "; ".join(
                f"{m['name']}: {', '.join(m['items'])} ({m['calories']} kcal, {m['protein_g']} g protein, "
                f"{CURRENCY}{m['cost']})" for m in plan["meals"]
            )
            prompt = (
                f"A user follows a {DIET_LABELS[profile['diet']]} diet, goal: {GOAL_LABELS[profile['goal']]}, "
                f"daily food budget {CURRENCY}{plan['budget']:g}. Their meal plan for today: {summary}. "
                f"Totals: {plan['calories_total']} kcal, {plan['protein_total_g']} g protein, "
                f"{CURRENCY}{plan['cost_total']}. Targets: {plan['calorie_target']} kcal, "
                f"{plan['protein_target_g']} g protein. Write 3 to 4 short, friendly sentences: why this "
                f"plan suits their goal, one money-saving tip, and one diet-respecting swap. "
                f"Plain text only, no markdown, no medical claims, do not change any numbers."
            )
            response = config.client.models.generate_content(
                model=config.MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=build_system_prompt(profile, targets)),
            )
            text = (response.text or "").strip()
            if text:
                return text, "ai"
        except Exception as exc:  # the plan is still returned without the AI note
            print(f"[coach_note] Gemini unavailable, using template: {exc}")
    return mock_plan_note(plan, profile, targets), "template"
