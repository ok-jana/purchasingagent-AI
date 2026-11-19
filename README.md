# SmartStock Purchasing Agent

A local browser interface for the Groq purchasing agent. The user enters an item, quantity, budget, and deadline, then reviews the tool results and purchase order draft.

## Run in VS Code

1. Extract this project and open the folder containing `server.py` in VS Code.
2. Use Python 3.10 or later. Open a PowerShell terminal and run:

```powershell
python -m pip install -r requirements.txt
$env:GROQ_API_KEY = Read-Host "Enter your Groq API key"
python server.py
```

3. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. Keep the terminal running.
4. Choose **Live Groq LLM** and click **Run purchasing agent**.

Create your key at [Groq Console](https://console.groq.com/keys). The key is read by the Python server and stays out of the browser. Set it before starting the server. Restart the server if you change the environment variables.

The default model is `openai/gpt-oss-20b`. Set `GROQ_MODEL` before starting the server to select another tool-calling model available to your account. On Windows, use `py` if `python` is unavailable. On macOS/Linux, use `export GROQ_API_KEY="your-key"` and `python3 server.py`.

## Demo

Select a preset, then click **Run purchasing agent**. Presets fill the inputs and preserve your selected decision mode.

| Preset | Expected result |
| --- | --- |
| Standard reorder | 3 calls. Paper stock is 8, below the threshold of 15. Supplier B qualifies at INR 9,600 with 2-day delivery. |
| Tight budget | 2 calls. Both quotes exceed INR 9,000. |
| Sufficient stock | 1 call. Pens have 30 packs in stock. |

Results appear after the run completes. Live mode can take several minutes. The activity panel shows returned tool data and the model's final decision. A successful draft includes a summary and a JSON download button. The original JSON is also saved under `drafts/` beside the application.

## Data and architecture

`agent.py` contains STOCK, THRESHOLD, and QUOTES. These sample values are read by the tools and returned to the model. Supplier A charges INR 230 per pack with 5-day delivery. Supplier B charges INR 240 with 2-day delivery. Rates apply to both demo items.

`server.py` serves the page and launches the existing command-line agent in a separate process for each run. `index.html` provides the form and results view. The interface uses a maximum of three tool calls per run. Draft creation validates the budget and deadline and leaves stock unchanged.

Python's standard library provides the server and HTTP client. No third-party packages are required. The original command-line entry point still works with `python agent.py`.

## Offline rehearsal and troubleshooting

Choose **Offline rehearsal (scripted)** to run the tools without a key or network. You can start `python server.py` without a key for this mode. Rehearsal uses scripted decisions. Use live mode to demonstrate the LLM decision requirement.

- Missing key message: set GROQ_API_KEY and restart the server.
- HTTP 401: check the Groq key. HTTP 429: check account quota and rate limits.
- Network error: check the terminal diagnostic and your connection to api.groq.com.
- Port occupied: run `$env:PORT = "8001"`, then `python server.py`, and open `http://127.0.0.1:8001`.
- A run can save a draft before a later model request fails. Check the displayed draft before retrying.

The interface is intended to run on your own computer through localhost. Keep your API key out of your GitHub repository.

## Verification

The local HTTP endpoints, four offline decision scenarios, concurrent run isolation, invalid inputs, and missing-key handling were checked. Live Groq access and browser interaction should be checked on your demo computer before presenting.
