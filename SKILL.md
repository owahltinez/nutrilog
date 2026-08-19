---
name: nutrilog
description: Fast, privacy-first CLI tool for logging meals, macronutrients, and calories directly to the Google Health API (health.googleapis.com/v4) from any terminal. Syncs live with Google Health, Fitbit, and Pixel Watch. Use when the user asks to log meals, track macros or calories, view meal history, check daily nutrition summaries, or manage Google Health meal logs.
license: MIT
---

# nutrilog

A fast, privacy-first CLI tool for logging meals, macronutrients, and calories directly to the **Google Health API (`health.googleapis.com/v4`)** from any terminal.

Data written by `nutrilog` syncs natively to the user's **Google Health app**, **Fitbit**, and **Pixel Watch**.

---

## 1. Meal Logging

Nutrilog accepts shorthand strings combining numbers, macro letters, and food descriptions in any order:

```bash
# Shorthand notation (protein 'p', fat 'f', carbs 'c', calories 'k' or 'cal')
nutrilog log "38p 18f 54c 580k Tofu Edamame Soba Bowl"

# Explicit units and labels
nutrilog log "Grilled Salmon protein: 35g, fat: 12g, carbs: 5g, calories: 280, fiber: 2g"

# Prefix notation
nutrilog log "p30 f10 c45 390cal Chicken Burrito Bowl"

# Automatic calorie calculation if calories are omitted
nutrilog log "30p 40c 10f Oatmeal"

# Any of the API's 39 nutrients, by name with an explicit unit
nutrilog log "Oat Cortado 0.8p 40k caffeine: 63mg"
```

### Choosing Entry Granularity

Log independently served or described foods as separate entries when their nutrition can be
reasonably estimated separately. Foods eaten at the same sitting do not need to be one entry:
for example, log buffet tempeh salad and rice separately.

Prefer the fewest entries that preserve meaningful distinctions:

- Keep a composed dish, such as a curry, sandwich, stir-fry, or casserole, as one entry when
  its ingredients form a single dish or only a total nutrition estimate is available.
- Do not split a recipe into every ingredient merely because the user listed them. Split an
  ingredient only when it was served or portioned separately, the user requests it, or tracking
  it separately is materially useful.
- Keep distinct sides, drinks, courses, or buffet selections separate when feasible. Assign the
  same meal type and time so they remain associated with the meal.
- If the boundary is genuinely ambiguous and would materially change the record, briefly state
  the proposed grouping and ask before logging. Otherwise infer the simplest sensible grouping.

Only protein, fat, carbs and calories have single-letter shorthand and may be written
without a unit. Every other nutrient is written by name and **requires a unit** (`g`, `mg`,
`µg`); a bare number is an error rather than a guess. `nutrilog nutrients` lists every name.

### Flag-Based Logging

```bash
nutrilog log "Grilled Barramundi & Veggies" \
  --protein 36 \
  --calories 480 \
  --fat 14 \
  --carbs 12 \
  --meal lunch

# -n/--nutrient covers everything else and is repeatable
nutrilog log "Multivitamin" -n "vitamin c=60mg" -n "zinc=10mg"
```

### Dry Run & JSON Output

To preview what will be logged without sending to the API:

```bash
nutrilog log "38p 18f 54c 580k Tofu Bowl" --dry-run
nutrilog log "38p 18f 54c 580k Tofu Bowl" --dry-run --json
```

---

## 2. Reviewing Daily Nutrition & History

```bash
# View today's meals table and total consumed macros
nutrilog history

# View yesterday's meals and totals
nutrilog history --date yesterday

# View a specific past calendar date
nutrilog history --date 2026-08-15

# View past week's meals
nutrilog history --days 7

# Structured JSON output
nutrilog history --json
nutrilog history --days 7 --json
```

---

## 3. Copying a Prior Meal

Use the Data Point ID shown by `nutrilog history`. This creates a new point at
the current time and leaves the source unchanged. It preserves calories,
macros, every additional nutrient, and serving metadata.

```bash
# Copy now with the original name and meal type
nutrilog copy <POINT_ID>

# Choose the time or override descriptive fields
nutrilog copy <POINT_ID> --time 7pm
nutrilog copy <POINT_ID> --name "Pasta Lunch" --meal lunch

# Inspect the copy without creating it
nutrilog copy <POINT_ID> --dry-run --json
```

---

## 4. Discovering Loggable Nutrients

Only protein, fat, carbs and calories have shorthand letters. To see every
other nutrient the API accepts, and how to write it:

```bash
nutrilog nutrients
```

Names are matched case-insensitively and accept spaces, hyphens or underscores,
so `vitamin c`, `Vitamin-C` and `VITAMIN_C` are equivalent. Note that `salt` is
not accepted as a synonym for sodium: 1g of salt is roughly 400mg of sodium, so
equating them would record the wrong value.

---

## 5. Deleting Mistakes or Duplicate Meals

To delete a logged meal, use its Data Point ID (visible directly in `nutrilog history`):

```bash
# Delete by Point ID
nutrilog delete <POINT_ID>

# Delete immediately without prompt
nutrilog delete <POINT_ID> --yes
# Or alias
nutrilog rm <POINT_ID> -y
```

---

## 6. Configuration & Timezone

```bash
# View current timezone configuration
nutrilog config show

# Set active timezone
nutrilog config set --timezone "Australia/Sydney"
nutrilog config set -z AEST

# Reset timezone to machine system local
nutrilog config set --timezone auto
```

---

## 7. Authentication

Nutrilog uses Google OAuth 2.0 with offline refresh tokens. It works out-of-the-box with zero configuration:

```bash
# Check auth status
nutrilog auth status

# Interactive browser login (local)
nutrilog auth login

# Remote SSH login (copy-paste flow)
nutrilog auth login --remote

# Sign out and clear stored tokens
nutrilog auth logout

# (Optional) Override with custom GCP OAuth client credentials:
export NUTRILOG_CLIENT_ID="<YOUR_CLIENT_ID>"
export NUTRILOG_CLIENT_SECRET="<YOUR_CLIENT_SECRET>"
```
