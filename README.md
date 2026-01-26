# CMA Compiler

**A smart system that helps real estate agents write property reports using AI.**

## What Does This Do?

When a real estate agent wants to figure out how much a house is worth, they need to:

1. Look at similar houses that recently sold nearby
2. Compare features like bedrooms, bathrooms, and size
3. Write a professional report with their findings

This tool does all of that automatically! You give it some notes about a property, and it:

- **Reads your notes** and figures out what you're looking for
- **Searches a database** to find similar houses that sold recently
- **Calculates adjustments** (like "this house has an extra bedroom, so it's worth more")
- **Writes a report** explaining everything

## Quick Start (Local Demo)

### 1. Simple One-Command Run
The easiest way to start the project is using the provided scripts:
```bash
# First time setup
./scripts/setup.sh

# Start the application
./scripts/dev.sh
```

### 2. Demo the "Human-in-the-Loop" Flow
1. Open your browser to `http://localhost:8000/ui`.
2. **Search**: Enter a sample query like:
   > "3 bed 2 bath in Denver 80202, under $600k"
3. **Review Candidates**:
   - Inspect the ranked list of comparable properties.
   - Hover over the **Score** (e.g., "95%") to see the breakdown logic.
   - Use the **Search Rules** sidebar to adjust Beds, Baths, or Radius.
   - Toggle specific properties to Include/Exclude.
4. **Generate**: Click "Generate Report" to see the final output.
5. **Download**: Use the "Download PDF" button to get a professional PDF.

### 3. Check Disclaimers
Note that every page includes the mandatory footer:
> "Informational only; not an appraisal. Based on data from Mock MLS."
Validated by `tests/test_ui_rendering.py`.

## How It Works (Simple Version)

```
Your Notes → AI Parser → Search Database → Math Calculations → AI Writer → Report
```

**Step 1: Parse Notes**
You write something like: *"3 bed 2 bath house in Denver CO, about 1800 sqft"*
(Specific street address is optimal but NOT required - City/State is enough!)

The AI reads this and understands:
- Location: Denver, CO 80202
- Bedrooms: 3
- Bathrooms: 2
- Size: 1,800 square feet

**Step 2: Find Similar Houses**
The system searches for houses that:
- Are in the same city
- Have similar bedrooms (2-4)
- Are similar in size (within 20%)
- Sold recently (within 1 year)

**Step 3: Do the Math**
For each similar house, it calculates adjustments:
- "This house has 200 more square feet → add $20,000"
- "This house was built 5 years earlier → subtract $5,000"

**Step 4: Write the Report**
The AI writes a professional summary explaining:
- What the house is probably worth
- How confident we are in that number
- Which similar houses we compared it to

## Safety Features

This system has special rules to keep reports accurate:

🛡️ **No Made-Up Numbers** - The AI can ONLY use numbers from the actual data. If it tries to invent a price, the report gets rejected.

🔒 **Privacy Protection** - Personal info (names, emails, phone numbers) is never shown or sent to AI.

📊 **Caps & Limits** - Maximum 200 houses searched, maximum 20 used in final report.

## Configuration

By default, this runs with a local AI (Ollama) so you don't need any API keys!

### Using Local AI (Free, No Account Needed)

1. Install [Ollama](https://ollama.ai)
2. Download a model: `ollama pull llama3.2`
3. That's it! The app uses Ollama by default.

### Using Claude (Anthropic's AI)

```bash
export LLM_PROVIDER=claude
export ANTHROPIC_API_KEY=your-key-here
```

### Environment Variables

| Variable | Default | What It Does |
|----------|---------|--------------|
| `LLM_PROVIDER` | `ollama` | Which AI to use: `ollama`, `claude`, or `mock` |
| `OLLAMA_MODEL` | `llama3.2:latest` | Which Ollama model to use |
| `ANTHROPIC_API_KEY` | (none) | Your Claude API key (if using Claude) |

## Project Structure

```
cma_compiler/
├── app/                 # Web server (FastAPI)
├── domain/              # Core data models
│   ├── intent_ir.py     # What the user is looking for
│   ├── query_plan.py    # How to search the database
│   └── report_schema.py # Final report structure
├── connectors/          # Database connections
├── analytics/           # Math calculations
├── llm/                 # AI integrations
├── renderer/            # Report formatting (HTML)
├── tests/               # Test files
└── data/                # Sample datasets
```

## API Endpoints

| Endpoint | What It Does |
|----------|--------------|
| `GET /` | Service overview and metadata |
| `GET /ui` | **(New)** Interactive Web UI |
| `POST /parse-notes` | Convert your notes into structured data |
| `POST /search-comps` | Find similar houses (auto-generates session) |
| `POST /select-comps` | Pick which houses to use in report |
| `POST /generate-report` | Create the final report |

### Example: Search without Session ID
```bash
curl -X POST http://localhost:8000/search-comps \
  -H "Content-Type: application/json" \
  -d '{
    "intent": {
      "subject_city": "Denver",
      "subject_beds": 3,
      "subject_year_built": 1950
    }
  }'
```
Response includes `"session_id": "..."`.

## Running Tests

```bash
pytest -q
```

All tests should pass ✅ (Note: PDF rendering requires `weasyprint` with compatible `pydyf < 0.12`).

## Glossary

- **CMA** = Comparative Market Analysis (a report showing what a house is worth)
- **Comp** = Comparable sale (a similar house that sold recently)
- **Sqft** = Square feet (how big the house is)
- **DOM** = Days on Market (how long it took to sell)
- **LLM** = Large Language Model (the AI that reads and writes text)

## License

MIT License - do whatever you want with this code!
