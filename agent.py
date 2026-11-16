import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

STOCK = {"paper": 8, "pens": 30}
THRESHOLD = 15
QUOTES = {"A": (230, 5), "B": (240, 2)}
TOOL_DESCRIPTIONS = {
    "get_inventory": "Look up stock and reorder threshold for the requested item.",
    "get_supplier_quotes": "Get approved supplier quotes at the requested quantity.",
    "create_purchase_order_draft": "Save a local draft using the chosen supplier ID.",
}
ORDER = list(TOOL_DESCRIPTIONS)
TOOLS = [
    {"name": name, "description": description}
    for name, description in TOOL_DESCRIPTIONS.items()
]
TOOLS[2]["parameters"] = {
    "type": "OBJECT",
    "properties": {"supplier": {"type": "STRING", "enum": list(QUOTES)}},
    "required": ["supplier"],
}
INSTRUCTIONS = """
You are a purchasing decision agent. Check inventory first. If stock is at or
above the reorder threshold, stop and explain. Otherwise request quotes.
Compare the quote totals and delivery days against the request's maximum
budget and delivery days, both inclusive. If none qualify, stop and explain.
Otherwise choose the cheapest qualifying supplier and create a draft.
Call at most one tool per turn. Use returned facts in your final response.
A draft is for review and never sends an order.
"""


def execute_tool(name, arguments, request):
    item, quantity, budget, days = request
    if name == ORDER[0]:
        return {"item": item, "stock": STOCK[item], "threshold": THRESHOLD}
    if name == ORDER[1]:
        return [
            {"supplier": supplier, "total_inr": price * quantity, "days": delivery}
            for supplier, (price, delivery) in QUOTES.items()
        ]
    supplier = arguments["supplier"]
    price, delivery = QUOTES[supplier]
    if price * quantity > budget or delivery > days:
        return {"error": "Draft rejected because the quote exceeds the budget or deadline."}
    draft = {
        "id": "PO-" + uuid4().hex[:12],
        "status": "draft",
        "item": item,
        "quantity": quantity,
        "supplier": supplier,
        "total_inr": price * quantity,
        "days": delivery,
    }
    directory = Path("drafts")
    directory.mkdir(exist_ok=True)
    path = directory / (draft["id"] + ".json")
    with path.open("x", encoding="utf-8") as output:
        json.dump(draft, output, indent=2)
    return {**draft, "file": str(path)}


def rehearsal_reply(results, request):
    _, _, budget, days = request
    if not results:
        name, args = ORDER[0], {}
    elif len(results) == 1:
        if results[0]["stock"] >= results[0]["threshold"]:
            return {"content": "Stock is sufficient. No draft created."}
        name, args = ORDER[1], {}
    elif len(results) == 2:
        suitable = [
            quote for quote in results[1]
            if quote["total_inr"] <= budget and quote["days"] <= days
        ]
        if not suitable:
            return {"content": "No quote meets both constraints. No draft created."}
        name = ORDER[2]
        args = {"supplier": min(suitable, key=lambda q: q["total_inr"])["supplier"]}
    else:
        return {"content": f"Draft {results[-1]['id']} saved for review."}
    return {"tool_calls": [{
        "id": f"rehearsal-{len(results) + 1}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }]}


def gemini_reply(history, key, tool_count):
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    payload = {
        "systemInstruction": {"parts": [{"text": INSTRUCTIONS}]},
        "contents": history,
        "tools": [{"functionDeclarations": TOOLS}],
        "toolConfig": {"functionCallingConfig": {
            "mode": "NONE" if tool_count == 3 else "AUTO",
        }},
    }
    request = Request(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + quote(model, safe="") + ":generateContent",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        body = json.load(response)
    candidates = body.get("candidates") or []
    if not candidates or not candidates[0].get("content", {}).get("parts"):
        raise RuntimeError("Gemini returned no usable response.")
    return candidates[0]["content"]


def run(request, rehearsal, key):
    item, quantity, budget, days = request
    print("Mode: scripted offline rehearsal" if rehearsal else "Mode: live Gemini LLM")
    history = [{"role": "user", "parts": [{"text": (
        f"Consider reordering {quantity} packs of {item}. "
        f"Maximum budget: INR {budget}. Maximum delivery: {days} days."
    )}]}]
    results = []
    while True:
        if rehearsal:
            reply = rehearsal_reply(results, request)
            calls = [
                {"name": call["function"]["name"],
                 "args": json.loads(call["function"]["arguments"])}
                for call in reply.get("tool_calls", [])
            ]
            decision = reply.get("content")
        else:
            reply = gemini_reply(history, key, len(results))
            calls = [part["functionCall"] for part in reply["parts"] if "functionCall" in part]
            decision = " ".join(
                part["text"] for part in reply["parts"] if "text" in part and not part.get("thought")
            )

        if not calls:
            if not results or not decision:
                raise RuntimeError("The agent did not complete a valid decision.")
            print(f"\nDecision ({len(results)} tool calls): {decision}")
            return
        if len(calls) != 1 or len(results) == 3:
            raise RuntimeError("Expected one tool call at a time, with a maximum of three.")
        call = calls[0]
        name = call["name"]
        if name != ORDER[len(results)]:
            raise RuntimeError(f"Unexpected tool call: {name}")
        if results and results[0]["stock"] >= THRESHOLD:
            raise RuntimeError("The agent attempted to reorder sufficient stock.")
        result = execute_tool(name, call.get("args", {}), request)
        results.append(result)
        print(f"{len(results)}. {name} -> {json.dumps(result)}", flush=True)
        if not rehearsal:
            tool_response = {"name": name, "response": {"result": result}}
            if "id" in call:
                tool_response["id"] = call["id"]
            # Keep Gemini's original parts, including any thought signatures.
            history.extend([
                reply,
                {"role": "user", "parts": [{"functionResponse": tool_response}]},
            ])


def main():
    parser = argparse.ArgumentParser(description="Low-stock purchasing assistant")
    parser.add_argument("--item", choices=STOCK, default="paper")
    parser.add_argument("--quantity", type=int, default=40)
    parser.add_argument("--budget", type=int, default=10000, help="Maximum total in INR")
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--rehearse", action="store_true", help="Run a scripted offline walkthrough")
    args = parser.parse_args()
    if min(args.quantity, args.budget, args.days) <= 0:
        parser.error("quantity, budget, and days must be positive")
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not args.rehearse and not key:
        parser.error("set GEMINI_API_KEY for live mode or use --rehearse")
    try:
        run((args.item, args.quantity, args.budget, args.days), args.rehearse, key)
    except HTTPError as error:
        print(f"Gemini returned HTTP {error.code}. See README for troubleshooting.", file=sys.stderr)
        return 1
    except (URLError, TimeoutError):
        print("Gemini connection failed or timed out. Check your internet and retry.", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, KeyError, OSError) as error:
        print(f"Run stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
