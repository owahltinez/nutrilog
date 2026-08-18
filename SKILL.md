---
name: nutrilog
description: Fast, privacy-first CLI tool for logging meals, macronutrients, and calories directly to the Google Health API (health.googleapis.com/v4) from any terminal. Syncs live with Google Health, Fitbit, and Pixel Watch. Use when the user asks to log meals, track macros or calories, view today's nutrition rollup, check nutrition targets, or manage Google Health meal logs.
license: MIT
---

# nutrilog

A fast, privacy-first CLI tool for logging meals, macronutrients, and calories directly to the **Google Health API (`health.googleapis.com/v4`)** from any terminal.

Data written by `nutrilog` syncs natively to the user's **Google Health app**, **Fitbit**, and **Pixel Watch**.

---

## 1. Quick Meal Logging

Nutrilog accepts shorthand strings combining numbers, macro letters, and food descriptions in any order:

```bash
# Shorthand notation (protein 'p', fat 'f', carbs 'c', calories 'k' or 'cal')
nutrilog "38p 18f 54c 580k Tofu Edamame Soba Bowl"

# Explicit units and labels
nutrilog "Grilled Salmon protein: 35g, fat: 12g, carbs: 5g, calories: 280, fiber: 2g"

# Prefix notation
nutrilog "p30 f10 c45 390cal Chicken Burrito Bowl"

# Automatic calorie calculation if calories are omitted
nutrilog "30p 40c 10f Oatmeal"
```

### Flag-Based Logging
```bash
nutrilog log "Grilled Barramundi & Veggies" \
  --protein 36 \
  --calories 480 \
  --fat 14 \
  --carbs 12 \
  --meal lunch
```

### Dry Run & JSON Output
To preview what will be logged without sending to the API:
```bash
nutrilog "38p 18f 54c 580k Tofu Bowl" --dry-run
nutrilog "38p 18f 54c 580k Tofu Bowl" --json
```

---

## 2. Reviewing Daily Nutrition & History

```bash
# View today's meals table and progress towards daily targets
nutrilog today

# List logged meals with their unique Point IDs
nutrilog list --days 3

# View meal history across past days
nutrilog history --days 7 --ids
```

---

## 3. Deleting Mistakes or Duplicate Meals

To delete a logged meal, use its Data Point ID (obtained from `nutrilog list` or `nutrilog history --ids`):

```bash
# Delete by Point ID
nutrilog delete <POINT_ID>

# Delete immediately without prompt
nutrilog delete <POINT_ID> --yes
# Or alias
nutrilog rm <POINT_ID> -y
```

---

## 4. Configuration & Timezone

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

## 5. Authentication

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
