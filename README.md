# Nutrilog

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Built with Typer & Rich](https://img.shields.io/badge/CLI-Typer%20%26%20Rich-green.svg)](https://typer.tiangolo.com)
[![uvx ready](https://img.shields.io/badge/uvx-ready-purple.svg)](https://github.com/astral-sh/uv)

A fast, privacy-first CLI tool for logging meals, macronutrients, and calories directly to the **Google Health API (`health.googleapis.com/v4`)** from any terminal. Syncs live with your **Google Health app**, **Fitbit**, and **Pixel Watch**.

---

```
                       Today's Nutrition Summary (Mon, Aug 17)
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┓
┃ Time       ┃ Meal Type    ┃ Food                     ┃ Protein ┃ Calories ┃   Carbs ┃    Fat ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━┩
│ 12:30 PM   │ Lunch        │ Tofu Edamame Soba Bowl   │   38.5g │ 580 kcal │   54.0g │  18.0g │
│ 04:00 PM   │ Snack        │ Protein Shake            │   25.0g │ 180 kcal │    4.0g │   2.0g │
└━━━━━━━━━━━━┴━━━━━━━━━━━━━━┴━━━━━━━━━━━━━━━━━━━━━━━━━━┴━━━━━━━━━┴━━━━━━━━━━┴━━━━━━━━━┴━━━━━━━━┘
╭──────────────────────────────────────────────────────────────────────────────────────────────╮
│ Daily Total: 63.5g / 120g Protein (53%) | 760 / 2,000 kcal (38%)                             │
│ Remaining:   56.5g Protein | 1,240 kcal                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────╯
```

---

## ⚡ Quickstart

### 1. Run Instantly with `uvx` (No Installation Required)

```bash
# Log a meal using intuitive shorthand syntax (in dry-run preview)
uvx --from . nutrilog "38p 18f 54c 580k Tofu Edamame Soba Bowl" --dry-run

# View today's summary & daily target progress
uvx --from . nutrilog today

# View command help
uvx --from . nutrilog --help
```

### 2. Install Globally with `uv` or `pip`

```bash
# Install globally via uv
uv tool install .

# Or via standard pip
pip install .
```

---

## 🏗️ Architecture & Cloud Sync

```mermaid
graph LR
    User["User Terminal"] --> CLI["nutrilog CLI<br/>(Typer + Rich)"]
    CLI --> Parser["Macro & Shorthand<br/>Regex Parser"]
    CLI --> Auth["OAuth 2.0 Auth Manager<br/>(PKCE / Loopback)"]
    Auth --> Keyring["Local Token Store<br/>(~/.config/nutrilog/tokens.json)"]
    CLI --> Client["Google Health Client<br/>(health.googleapis.com/v4)"]
    Client --> GoogleHealth["Google Health Platform<br/>(Pixel Watch / Fitbit / Mobile App)"]
```

- **Zero-Friction Logging:** Log any meal in $<2$ seconds directly from your command line.
- **Hardware & Cloud Sync:** Data writes directly to Google Health API and syncs to your Pixel Watch, Fitbit, and phone dashboard.
- **Local & Private:** Auth tokens are stored locally on your machine with strict `0600` permissions.

---

## 🚀 Usage & Commands

### 1. Shorthand Meal Logging

Macros and calorie tokens can appear anywhere in the string in any order:

```bash
# Shorthand notation (protein 'p', fat 'f', carbs 'c', calories 'k' or 'cal')
nutrilog "38p 18f 54c 580k Tofu Edamame Soba Bowl"

# Explicit units and labels
nutrilog "Grilled Salmon protein: 35g, fat: 12g, carbs: 5g, calories: 280, fiber: 2g"

# Prefix notation
nutrilog "p30 f10 c45 390cal Chicken Burrito Bowl"

# Automatic calorie calculation if calories are omitted (4*P + 4*C + 9*F)
nutrilog "30p 40c 10f Oatmeal"
```

#### Shorthand Syntax Cheat-Sheet

| Nutrient | Recognized Formats |
| :--- | :--- |
| **Protein** | `38p`, `p38`, `38g protein`, `protein: 38g`, `pro: 38` |
| **Fat** | `18f`, `f18`, `18g fat`, `fat: 18g`, `total_fat: 18` |
| **Carbohydrates** | `54c`, `c54`, `54g carbs`, `carbs: 54g`, `carb: 54` |
| **Calories / Energy**| `580k`, `580cal`, `580kcal`, `cal: 580`, `calories: 580` |
| **Fiber** | `9fib`, `9g fiber`, `fiber: 9g` |
| **Sugar** | `5sug`, `5g sugar`, `sugar: 5g` |
| **Sodium** | `500mg sod`, `sodium: 0.5g` |

---

### 2. Flag-Based Logging

```bash
# Explicit flags
nutrilog log "Grilled Barramundi & Veggies" \
  --protein 36 \
  --calories 480 \
  --fat 14 \
  --carbs 12 \
  --meal lunch

# Dry run (preview payload without sending)
nutrilog "35p 450k Protein Shake" --dry-run

# Output raw JSON payload
nutrilog "35p 450k Protein Shake" --json
```

---

### 3. Reviewing Today's Totals, History & Listing Meals

```bash
# View today's total consumed nutrition
nutrilog today

# List recent meals with their Data Point IDs
nutrilog list --days 3

# View past week's meal history
nutrilog history --days 7 --ids
```

---

### 4. Deleting Meals

Delete mistakenly logged or duplicate meals using their Data Point ID:

```bash
# Delete with confirmation prompt
nutrilog delete <DATA_POINT_ID>

# Delete immediately (skip prompt)
nutrilog delete <DATA_POINT_ID> --yes
# Or alias
nutrilog rm <DATA_POINT_ID> -y
```

---

### 5. Configuration & Timezone

```bash
# Display active configuration
nutrilog config show

# Set active timezone
nutrilog config set --timezone "Australia/Sydney"
nutrilog config set -z AEST

# Reset timezone to machine system local
nutrilog config set --timezone auto
```

---

## 🤖 AI Agent Skill Integration

Nutrilog includes a packaged **Agent Skill** (`SKILL.md`) that allows AI coding assistants (Gemini, Claude Code, Cursor, Antigravity) to discover and run Nutrilog commands autonomously.

```bash
# Check skill status across detected AI tools
nutrilog skill status

# Install into default shared location (~/.agents/skills)
nutrilog skill install

# Install into all detected agent tool directories
nutrilog skill install --all

# Symlink instead of copying (for live package updates)
nutrilog skill install --all --link
```

---

## 🔑 Google Cloud Authentication (`nutrilog auth`)

Nutrilog connects directly to the Google Health API using OAuth 2.0.

### 1. Instant Zero-Config Login (Default)

Nutrilog includes built-in Desktop App client credentials so you can log in immediately from any terminal:

```bash
# Standard local browser login
nutrilog auth login

# Remote SSH / Headless login (copy-paste flow)
nutrilog auth login --remote

# Check authentication status & token expiry
nutrilog auth status

# Sign out & clear local tokens
nutrilog auth logout
```

### 2. Custom GCP Credentials (Optional / Advanced)

If you prefer to use your own Google Cloud Project instead of the built-in desktop app:

1. Create a project in [Google Cloud Console](https://console.cloud.google.com) and enable the **Google Health API**.
2. Under **Credentials**, create an **OAuth client ID** of type **Desktop App**.
3. Set your environment variables:

```bash
export NUTRILOG_CLIENT_ID="<YOUR_CLIENT_ID>"
export NUTRILOG_CLIENT_SECRET="<YOUR_CLIENT_SECRET>"
```

---

## 🧪 Development & Testing

Each Python module has a corresponding `_test.py` unit test suite alongside it:

```bash
# Set up virtual environment and install dependencies
uv venv
uv pip install -e ".[dev]"

# Run full test suite (57 tests)
uv run pytest

# Run tests with coverage report
uv run pytest --cov=nutrilog
```

---

## 📄 License
MIT License. See [LICENSE](LICENSE) for details.
