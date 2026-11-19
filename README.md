# Groq Purchasing Agent

A small store needs to reorder supplies before stock runs out. This project uses an LLM hosted by Groq to check inventory, compare supplier quotes against a budget and delivery deadline, and prepare a purchase order draft for review.

## How it works

The LLM receives the purchase request and decides which tool to call based on the results it gets back. The Python tools use local sample data.

| Tool | Purpose |
| --- | --- |
| `get_inventory` | Returns current stock and the reorder threshold. |
| `get_supplier_quotes` | Returns each supplier's total price and delivery time for the requested quantity. |
| `create_purchase_order_draft` | Validates the selected quote against the budget and deadline, then saves a local JSON draft. |

Drafts are saved locally for review. No orders are sent to suppliers.

## Where the data comes from

The demo starts with sample data defined near the top of [`agent.py`](agent.py). The Python tools read these values and pass the results to Groq. This version has no database or supplier API connection.

| Setting | What it contains |
| --- | --- |
| `STOCK` | Packs currently in stock by item. The demo starts with 8 packs of paper and 30 packs of pens. |
| `THRESHOLD` | The shared reorder threshold of 15 packs. Stock below 15 triggers a quote check. |
| `QUOTES` | Each supplier's price per pack in INR and delivery time in days. Supplier A is ₹230 per pack with 5-day delivery. Supplier B is ₹240 per pack with 2-day delivery. These sample rates apply to both items. |

The requested item, quantity, budget, and delivery deadline come from the command line. The defaults are paper, 40 packs, ₹10,000, and 3 days. The quote tool multiplies each supplier's price per pack by the requested quantity. For 40 packs, this gives ₹9,200 for A and ₹9,600 for B.

To try different stock levels, thresholds, or supplier rates, edit the corresponding setting in `agent.py`. Saving a draft writes a JSON file and leaves the stock counts unchanged.

## Setup

1. Clone this repository or download it from GitHub. In VS Code, open the folder containing [`agent.py`](agent.py).
2. Open **Terminal → New Terminal** and select PowerShell. Use Python 3.10 or later.
3. Run the dependency install command from the folder containing [`requirements.txt`](requirements.txt). The current implementation uses only the Python standard library, so pip installs no packages.

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Create a key in [Groq Console](https://console.groq.com/keys). Set it in your PowerShell session and run the agent.

```powershell
$env:GROQ_API_KEY = Read-Host "Enter your Groq API key"
python agent.py
```

If Windows uses the Python launcher, run `py agent.py`. Keep your API key out of GitHub and source files. Live mode uses `openai/gpt-oss-20b` by default and requires an internet connection and available Groq API quota.

## Demo cases

| Command | Expected calls | Expected result |
| --- | --- | --- |
| `python agent.py` | 3 | Creates a draft for 40 packs of paper from Supplier B for ₹9,600, with delivery in 2 days. |
| `python agent.py --budget 9000` | 2 | Checks stock and both quotes. Neither quote fits the budget, so no draft is created. |
| `python agent.py --item pens` | 1 | Checks pen stock. There are 30 packs in stock and the reorder threshold is 15, so no quotes are requested. |

## How to interpret the results

Each numbered terminal line shows a tool call and the JSON it returned. The final `Decision (N tool calls)` line summarizes the run in the model's own words during live mode.

1. **Inventory.** Compare `stock` with `threshold`. The default paper run returns 8 packs against a threshold of 15, so the agent looks for quotes.
2. **Quotes.** Compare each quote's `total_inr` and `days` with the request. The default budget is ₹10,000 and the deadline is 3 days. Supplier A costs ₹9,200 but takes 5 days. Supplier B costs ₹9,600 and takes 2 days, so it is the only quote that meets both conditions.
3. **Draft.** If the draft tool succeeds, open the path in its `file` field, such as `drafts/PO-<id>.json`. The JSON identifies the order with `id` and records the `item`, `supplier`, `quantity`, `total_inr`, and delivery estimate in `days`. A `status` of `draft` means the order is waiting for review.

A run that stops after one or two calls can be a successful decision. Check the trace for the reason. Existing files in `drafts/` can be from earlier runs, so use the path printed by the current run to identify a new draft.

## Offline rehearsal and troubleshooting

Add `--rehearse` to any demo command to run the same Python tools without an API key or internet connection. The terminal shows `Mode: scripted offline rehearsal` in this mode. Use `Mode: live Groq LLM` to demonstrate Groq making the decisions.

If the live run times out, check whether VS Code can reach the Groq API from PowerShell:

```powershell
Test-NetConnection api.groq.com -Port 443
```

If Groq returns HTTP 429, check your project's API quota and rate limits in Groq Console. If the draft tool already printed a file path before an error, check that file before rerunning.

## Choosing a model

The default is OpenAI GPT-OSS 20B hosted by Groq. Set GROQ_MODEL to a tool-calling model available to your Groq account. For example, in PowerShell:

```powershell
$env:GROQ_MODEL = "openai/gpt-oss-120b"
python agent.py
```

Each live demo uses up to three local function calls and up to four model requests. HTTP 401 usually indicates an invalid key, 403 can indicate access restrictions, 404 can indicate model availability, and 429 indicates a rate or quota limit. Network errors include a diagnostic message. Check your connection or try another network if your current connection cannot reach api.groq.com.

[Groq model documentation](https://console.groq.com/docs/models)
[Groq local tool calling](https://console.groq.com/docs/tool-use/local-tool-calling)

## Verification

The offline scenarios and mocked Groq request/response flow were checked for all three demo cases and an extended delivery deadline that makes Supplier A eligible. A live call still needs to be verified with your Groq key and account quota before presenting.
