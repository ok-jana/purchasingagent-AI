# Gemini Purchasing Agent

A small store needs to reorder supplies before stock runs out. This project uses Gemini to check inventory, compare supplier quotes against a budget and delivery deadline, and prepare a purchase order draft for review.

## How it works

Gemini receives the purchase request and decides which tool to call based on the results it gets back. The Python tools use local sample data.

| Tool | Purpose |
| --- | --- |
| `get_inventory` | Returns current stock and the reorder threshold. |
| `get_supplier_quotes` | Returns each supplier's total price and delivery time for the requested quantity. |
| `create_purchase_order_draft` | Validates the selected quote against the budget and deadline, then saves a local JSON draft. |

The project uses sample inventory and quotes. Drafts are saved locally for review. No orders are sent to suppliers.

## Setup

1. Clone this repository or download it from GitHub. In VS Code, open the folder containing [`agent.py`](agent.py).
2. Open **Terminal → New Terminal** and select PowerShell. Use Python 3.10 or later.
3. Run the dependency install command from the folder containing [`requirements.txt`](requirements.txt). The current implementation uses only the Python standard library, so pip installs no packages.

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Create a key in [Google AI Studio](https://aistudio.google.com/app/apikey). Set it in your PowerShell session and run the agent.

```powershell
$env:GEMINI_API_KEY = Read-Host "Enter your Gemini API key"
python agent.py
```

If Windows uses the Python launcher, run `py agent.py`. Keep your API key out of GitHub and source files. Live mode uses `gemini-3.5-flash` by default and requires an internet connection and available Gemini API quota.

## Demo cases

| Command | Expected calls | Expected result |
| --- | --- | --- |
| `python agent.py` | 3 | Creates a draft for 40 packs of paper from Supplier B for ₹9,600, with delivery in 2 days. |
| `python agent.py --budget 9000` | 2 | Checks stock and both quotes. Neither quote fits the budget, so no draft is created. |
| `python agent.py --item pens` | 1 | Checks pen stock. There are 30 packs in stock and the reorder threshold is 15, so no quotes are requested. |

## How to interpret the results

Each numbered terminal line shows a tool call and the JSON it returned. The final `Decision (N tool calls)` line summarizes the run in Gemini's own words during live mode.

1. **Inventory.** Compare `stock` with `threshold`. The default paper run returns 8 packs against a threshold of 15, so the agent looks for quotes.
2. **Quotes.** Compare each quote's `total_inr` and `days` with the request. The default budget is ₹10,000 and the deadline is 3 days. Supplier A costs ₹9,200 but takes 5 days. Supplier B costs ₹9,600 and takes 2 days, so it is the only quote that meets both conditions.
3. **Draft.** If the draft tool succeeds, open the path in its `file` field, such as `drafts/PO-<id>.json`. The JSON identifies the order with `id` and records the `item`, `supplier`, `quantity`, `total_inr`, and delivery estimate in `days`. A `status` of `draft` means the order is waiting for review.

A run that stops after one or two calls can be a successful decision. Check the trace for the reason. Existing files in `drafts/` can be from earlier runs, so use the path printed by the current run to identify a new draft.

## Offline rehearsal and troubleshooting

Add `--rehearse` to any demo command to run the same Python tools without an API key or internet connection. The terminal shows `Mode: scripted offline rehearsal` in this mode. Use `Mode: live Gemini LLM` to demonstrate Gemini making the decisions.

If the live run times out, check whether VS Code can reach the Gemini API from PowerShell:

```powershell
Test-NetConnection generativelanguage.googleapis.com -Port 443
```

If Gemini returns HTTP 429, check your project's API quota and rate limits in Google AI Studio. If the draft tool already printed a file path before an error, check that file before rerunning.
