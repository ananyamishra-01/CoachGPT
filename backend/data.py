"""
Built-in datasets for CoachGPT. Everything here lives in source code:
no external files and no API calls are needed to use it.

FOOD_DB holds rough Indian market prices (in rupees, per base serving),
calories and protein. The numbers are estimates meant for planning, not
lab-measured values, and real prices vary by city and season.
"""

CURRENCY = "\u20b9"  # rupee sign

# Diets form a ladder: a diet may use any food at or below its own level.
#   vegan(0) < vegetarian(1, adds dairy) < eggetarian(2, adds eggs)
#   < non_vegetarian(3, adds meat and fish)
DIET_LEVEL = {"vegan": 0, "vegetarian": 1, "eggetarian": 2, "non_vegetarian": 3}
DIET_LABELS = {
    "vegan": "vegan",
    "vegetarian": "vegetarian",
    "eggetarian": "eggetarian",
    "non_vegetarian": "non-vegetarian",
}
GOAL_LABELS = {
    "weight_loss": "weight loss",
    "weight_gain": "weight gain",
    "maintenance": "maintenance",
}

EQUIPMENT_RANK = {"none": 0, "home_basic": 1, "full_gym": 2}

EXERCISE_LIBRARY = [
    {"name": "Bodyweight Squat", "equipment": "none", "goals": ["weight_loss", "maintenance", "weight_gain"],
     "sets": 3, "reps": "15", "form_tip": "Push your knees out over your toes, chest tall, weight in your heels."},
    {"name": "Push-Up", "equipment": "none", "goals": ["weight_loss", "maintenance", "weight_gain"],
     "sets": 3, "reps": "10-12", "form_tip": "Keep a straight line from head to heels; lower until your chest nearly touches the floor."},
    {"name": "Walking Lunges", "equipment": "none", "goals": ["weight_loss", "weight_gain"],
     "sets": 3, "reps": "12 per leg", "form_tip": "Front knee stays behind your toes; drop the back knee straight down."},
    {"name": "Plank Hold", "equipment": "none", "goals": ["weight_loss", "maintenance"],
     "sets": 3, "reps": "30-45 sec", "form_tip": "Squeeze your glutes and brace your core so your hips don't sag."},
    {"name": "Jumping Jacks", "equipment": "none", "goals": ["weight_loss"],
     "sets": 3, "reps": "40 sec on / 20 sec off", "form_tip": "Land softly on the balls of your feet."},
    {"name": "Mountain Climbers", "equipment": "none", "goals": ["weight_loss"],
     "sets": 3, "reps": "30 sec", "form_tip": "Keep your hips low and drive your knees toward your chest quickly."},
    {"name": "Dumbbell Goblet Squat", "equipment": "home_basic", "goals": ["weight_gain", "maintenance"],
     "sets": 4, "reps": "10", "form_tip": "Hold the dumbbell close to your chest, elbows pointing down."},
    {"name": "Dumbbell Row", "equipment": "home_basic", "goals": ["weight_gain", "maintenance"],
     "sets": 4, "reps": "10 per arm", "form_tip": "Pull your elbow straight back and squeeze your shoulder blade at the top."},
    {"name": "Dumbbell Shoulder Press", "equipment": "home_basic", "goals": ["weight_gain"],
     "sets": 3, "reps": "10", "form_tip": "Avoid arching your lower back; press straight overhead."},
    {"name": "Resistance Band Deadlift", "equipment": "home_basic", "goals": ["weight_gain", "weight_loss"],
     "sets": 3, "reps": "12", "form_tip": "Hinge at your hips and keep the band close to your shins."},
    {"name": "Barbell Back Squat", "equipment": "full_gym", "goals": ["weight_gain", "maintenance"],
     "sets": 4, "reps": "6-8", "form_tip": "Brace your core hard before descending; knees track over your toes."},
    {"name": "Barbell Bench Press", "equipment": "full_gym", "goals": ["weight_gain"],
     "sets": 4, "reps": "6-8", "form_tip": "Retract your shoulder blades and keep your feet planted for a stable base."},
    {"name": "Lat Pulldown", "equipment": "full_gym", "goals": ["weight_gain", "maintenance"],
     "sets": 3, "reps": "10", "form_tip": "Lead with your elbows and avoid leaning back excessively."},
    {"name": "Treadmill Intervals", "equipment": "full_gym", "goals": ["weight_loss"],
     "sets": 6, "reps": "1 min fast / 2 min easy", "form_tip": "Keep your torso upright; don't lean on the handrails."},
    {"name": "Leg Press", "equipment": "full_gym", "goals": ["weight_gain", "weight_loss"],
     "sets": 3, "reps": "12", "form_tip": "Don't let your lower back round off the pad at the bottom."},
    {"name": "Cable Row", "equipment": "full_gym", "goals": ["weight_gain", "maintenance"],
     "sets": 3, "reps": "12", "form_tip": "Keep your spine neutral and avoid using momentum to pull."},
]

MOTIVATION_LINES = [
    "You don't need to feel motivated to start \u2014 you just need to start for 5 minutes. "
    "Most days, once you begin, you won't want to stop.",
    "Progress isn't a straight line. A shorter workout today still beats no workout today.",
    "Think about how good you'll feel in 20 minutes, not how hard the first 2 minutes seem.",
    "Consistency beats intensity. Showing up tired still counts \u2014 you're still building the habit.",
    "You've already done the hardest part by opening this chat. Let's turn that into 10 minutes of movement.",
]

HYDRATION_TIPS = {
    "weight_loss": "Drink a glass of water before each meal; it helps with portion control.",
    "weight_gain": "Drink water between meals rather than right before eating, so it doesn't blunt your appetite.",
    "maintenance": "Sip water through the day and add a pinch of salt after very sweaty workouts.",
}


def _f(id, name, role, level, qty, unit, kcal, protein, cost,
       mults=(1, 1.5, 2), supplement=False):
    """One food item. qty/unit describe the base serving; kcal, protein and
    cost are per base serving and scale linearly with the portion multiplier.
    unit may be 'singular|plural' (e.g. 'roti|rotis')."""
    singular, _, plural = unit.partition("|")
    return {
        "id": id, "name": name, "role": role, "level": level,
        "qty": qty, "unit_sing": singular, "unit_plur": plural or singular,
        "kcal": kcal, "protein": protein, "cost": cost,
        "mults": tuple(mults), "supplement": supplement,
    }


FOOD_DB = [
    # ---- breakfast mains ----
    _f("poha", "Vegetable poha", "bfast", 0, 1, "plate|plates", 250, 5, 15, (1, 1.5)),
    _f("upma", "Vegetable upma", "bfast", 0, 1, "plate|plates", 230, 6, 15, (1, 1.5)),
    _f("besan_chilla", "Besan chilla", "bfast", 0, 2, "piece|pieces", 240, 12, 18),
    _f("moong_cheela", "Moong dal cheela", "bfast", 0, 2, "piece|pieces", 220, 14, 20),
    _f("idli", "Idli with sambar", "bfast", 0, 3, "piece|pieces", 270, 9, 25),
    _f("sprouts_salad", "Sprouts salad", "bfast", 0, 1, "bowl|bowls", 180, 12, 20),
    _f("oats_milk", "Oats porridge with milk and banana", "bfast", 1, 1, "bowl|bowls", 330, 12, 25, (1, 1.5)),
    _f("paneer_paratha", "Paneer paratha", "bfast", 1, 1, "piece|pieces", 320, 11, 35, (1, 2)),
    _f("aloo_paratha", "Aloo paratha with curd", "bfast", 1, 2, "piece|pieces", 420, 10, 30, (1,)),
    _f("egg_bhurji", "Egg bhurji with 2 rotis", "bfast", 2, 1, "plate|plates", 340, 17, 30, (1, 1.5)),
    _f("omelette_toast", "Masala omelette (2 eggs) with toast", "bfast", 2, 1, "plate|plates", 360, 17, 28, (1, 1.5)),
    # ---- lunch / dinner proteins ----
    _f("dal_tadka", "Dal tadka", "protein", 0, 1, "katori|katori", 150, 8, 12),
    _f("rajma", "Rajma curry", "protein", 0, 1, "katori|katori", 190, 9, 18),
    _f("chole", "Chole (chickpea curry)", "protein", 0, 1, "katori|katori", 210, 10, 18),
    _f("soya_curry", "Soya chunks curry", "protein", 0, 1, "katori|katori", 200, 24, 15),
    _f("tofu_bhurji", "Tofu bhurji", "protein", 0, 100, "g", 150, 15, 30),
    _f("paneer_sabzi", "Paneer sabzi", "protein", 1, 75, "g", 260, 14, 40),
    _f("egg_curry", "Egg curry", "protein", 2, 2, "egg|eggs", 280, 14, 25),
    _f("boiled_eggs", "Boiled eggs", "protein", 2, 2, "egg|eggs", 150, 12, 14),
    _f("chicken_curry", "Chicken curry", "protein", 3, 150, "g", 230, 25, 40),
    _f("tandoori_chicken", "Tandoori chicken", "protein", 3, 120, "g", 200, 30, 45, (1, 1.5)),
    _f("fish_curry", "Fish curry", "protein", 3, 120, "g", 220, 24, 55, (1, 1.5)),
    # ---- carbs ----
    _f("roti", "Whole wheat roti", "carb", 0, 2, "roti|rotis", 200, 6, 6),
    _f("rice", "Steamed rice", "carb", 0, 1, "katori|katori", 200, 4, 8),
    _f("bajra_roti", "Bajra roti", "carb", 0, 2, "roti|rotis", 220, 7, 10, (1, 1.5)),
    _f("brown_rice", "Brown rice", "carb", 0, 1, "katori|katori", 215, 5, 12, (1, 1.5)),
    # ---- sides ----
    _f("veg_sabzi", "Mixed vegetable sabzi", "side", 0, 1, "katori|katori", 90, 3, 12, (1,)),
    _f("salad", "Cucumber-tomato salad", "side", 0, 1, "bowl|bowls", 40, 2, 8, (1,)),
    _f("palak", "Sauteed spinach", "side", 0, 1, "katori|katori", 80, 4, 12, (1,)),
    _f("raita", "Cucumber raita", "side", 1, 1, "katori|katori", 90, 4, 12, (1,)),
    _f("curd", "Curd (dahi)", "side", 1, 1, "katori|katori", 90, 5, 10, (1,)),
    # ---- snacks ----
    _f("roasted_chana", "Roasted chana", "snack", 0, 30, "g", 110, 6, 5, (1, 2)),
    _f("peanuts", "Roasted peanuts", "snack", 0, 30, "g", 170, 7, 6, (1, 2)),
    _f("banana", "Banana", "snack", 0, 1, "banana|bananas", 105, 1, 7, (1, 2)),
    _f("fruit", "Seasonal fruit", "snack", 0, 1, "serving|servings", 90, 1, 15, (1,)),
    _f("sprouts_chaat", "Sprouts chaat", "snack", 0, 1, "bowl|bowls", 150, 10, 15, (1,)),
    _f("makhana", "Roasted makhana", "snack", 0, 25, "g", 90, 3, 15, (1, 2)),
    _f("almonds", "Almonds", "snack", 0, 15, "almond|almonds", 115, 4, 18, (1, 2)),
    _f("boiled_chana", "Boiled chickpeas (chana)", "snack", 0, 1, "katori|katori", 160, 8, 10, (1,)),
    _f("sattu", "Sattu drink", "snack", 0, 1, "glass|glasses", 140, 8, 8, (1,)),
    _f("soy_milk", "Soy milk", "snack", 0, 250, "ml", 110, 8, 20, (1,)),
    _f("milk", "Milk", "snack", 1, 250, "ml", 150, 8, 14, (1,)),
    _f("boiled_egg", "Boiled egg", "snack", 2, 1, "egg|eggs", 75, 6, 7, (1, 2)),
    _f("whey", "Whey protein", "snack", 1, 1, "scoop|scoops", 120, 24, 60, (1,), supplement=True),
    _f("plant_protein", "Plant protein powder", "snack", 0, 1, "scoop|scoops", 120, 22, 70, (1,), supplement=True),
]
