# CoachGPT — AI Fitness and Nutrition Coach

A web app with a conversational AI coach (streamed replies), a **budget-aware meal
planner** (vegan, vegetarian, eggetarian, non-vegetarian), protein and calorie targets
worked out from your height and weight, and **daily progress tracking with accounts**
so your history is saved. Dark and light themes, works on phone and desktop.

## Features

- **Accounts**: register and log in; your profile and progress are stored per user.
- **Profile**: goal (weight loss / gain / maintain), diet, experience, equipment,
  height, current weight, goal weight, daily food budget (in rupees), optional calorie target.
- **Targets**: daily calories, protein (g/kg based on goal, with a sensible range),
  water, BMI, and an estimate of weeks to reach the goal at a safe pace.
- **Meal planner**: builds a one-day plan from a built-in food database with rupee
  prices, choosing foods that fit your diet, calorie target, protein target and budget.
  If the budget is too tight it says so instead of quietly cutting calories.
- **Coach chat**: Gemini (or the free mock coach) knows your profile, targets, diet and budget.
- **Daily progress**: weight, workout type and minutes, protein eaten, water, % of plan
  completed, meal-plan adherence, a note. Shows a weight-trend chart, goal progress, streak.
- **Safety**: pain, injury, medical conditions, pregnancy or disordered-eating talk is
  redirected to the "Talk to a professional" tab; goal weights that would put BMI below 18.5
  are refused; calorie plans never go below 1,400 kcal.

## Run it

You need Python 3.12 (3.14 is too new for some packages).

```
cd backend
python -m venv venv
venv\Scripts\activate          (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env         (Mac/Linux: cp .env.example .env)
```

Open `.env` and set `LLM_PROVIDER` (`gemini` with your key, or `mock` for no AI), then:

```
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000**. The server also serves the `frontend` folder, so a
single terminal is enough. (Optional: you can still serve the frontend separately with
`python -m http.server 5500` inside `frontend` and open http://localhost:5500.)

### AI modes (`LLM_PROVIDER` in `.env`)

| Mode | Needs | What it does |
|---|---|---|
| `gemini` | `GEMINI_API_KEY` | Real AI chat, plus an AI-written note on each meal plan |
| `mock` | nothing | Chat answers come from the built-in exercise and food data; fully free and offline |

In both modes the meal plan itself (calories, protein, cost) comes from the built-in
planner. See "Design notes" below for why.

## Where your data is stored

Accounts, profiles and progress are saved in one SQLite file (no database server to
install). By default it is `~/.coachgpt/coachgpt.db` in your home directory, which keeps it
out of OneDrive-synced folders (those can lock SQLite files). Set `DB_PATH` in `.env`
to change it. Passwords are stored only as salted PBKDF2-SHA256 hashes; login tokens are
stored only as SHA-256 hashes. To start fresh, stop the server and delete the file.

## Design notes

- **Numbers come from code, words come from the AI.** Language models are unreliable at
  exact arithmetic, so calorie/protein targets, meal costs and budget checks are computed
  by a deterministic planner (`planner.py`). Gemini is used for conversation and for the
  plain-language note explaining the plan. If Gemini is down or out of quota, the meal
  plan still works.
- **Planner method**: random search over valid meal combinations (respecting the diet
  ladder vegan < vegetarian < eggetarian < non-vegetarian), then a local refinement
  pass that nudges portions and swaps foods. The score penalises calorie error, protein
  shortfall and going over budget, and prefers whole foods to supplements.
- **Prompt design**: persona lock, profile and targets injected into the system prompt on
  every request, explicit diet rules, and an instruction to stop and redirect on medical topics.
- **Costs** are rough Indian market estimates per serving (in `data.py`) and vary by city
  and season. Nutrition values are approximate. This app is not medical advice and is
  meant for adults.

## Tests

```
cd backend
pip install pytest httpx
python -m pytest tests -q
```

The tests cover registration and login, password hashing, profile validation, targets,
meal plans for every diet and goal (diet rules, budget, protein), tight-budget behaviour,
progress logging and weight sync, data isolation between users, the mock coach, and the
Gemini code paths (using a stand-in client, so no key or network is needed).

## Project structure

```
coachgpt/
  backend/
    main.py          routes (accounts, profile, chat, meal plan, progress)
    config.py        reads .env, sets up the Gemini client
    data.py          exercises, motivation lines, food database with prices
    planner.py       targets, goal validation, budget-aware meal planner, progress summary
    chat.py          system prompt, mock coach, Gemini streaming and plan notes
    db.py            SQLite storage, password hashing, login tokens
    tests/test_api.py
    requirements.txt
    .env.example
  frontend/
    index.html  style.css  app.js
```

## Known limitations

- No password reset (there is no email service); delete the database file to start over.
- One-day plans only; no weekly planner or grocery list yet.
- Prices are static estimates, not live market prices.
