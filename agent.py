import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
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
    {"type": "function", "function": {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {"supplier": {"type": "string", "enum": list(QUOTES)}}
            if name == ORDER[2] else {},
            "required": ["supplier"] if name == ORDER[2] else [],
            "additionalProperties": False,
        },
    }}
    for name, description in TOOL_DESCRIPTIONS.items()
]
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


def groq_reply(history, key, tool_count):
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    payload = {
        "model": model,
        "messages": history,
        "tools": TOOLS,
        "tool_choice": "none" if tool_count == 3 else "auto",
        "parallel_tool_calls": False,
        "temperature": 0,
        "max_completion_tokens": 4096,
    }
    request = Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}",
                 "User-Agent": "PurchasingAgent/1.0"},
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        body = json.load(response)
    choices = body.get("choices") or []
    if not choices or not choices[0].get("message"):
        raise RuntimeError("Groq returned no usable response.")
    message = choices[0]["message"]
    return {
        "role": "assistant",
        "content": message.get("content"),
        "tool_calls": message.get("tool_calls") or [],
    }


def run(request, rehearsal, key):
    item, quantity, budget, days = request
    print("Mode: scripted offline rehearsal" if rehearsal else "Mode: live Groq LLM")
    history = [
        {"role": "system", "content": INSTRUCTIONS},
        {"role": "user", "content": (
            f"Consider reordering {quantity} packs of {item}. "
            f"Maximum budget: INR {budget}. Maximum delivery: {days} days."
        )},
    ]
    results = []
    while True:
        reply = (rehearsal_reply(results, request) if rehearsal
                 else groq_reply(history, key, len(results)))
        calls = reply.get("tool_calls") or []
        if not calls:
            if not results or not reply.get("content"):
                raise RuntimeError("The agent did not complete a valid decision.")
            print(f"\nDecision ({len(results)} tool calls): {reply['content']}")
            return
        if len(calls) != 1 or len(results) == 3:
            raise RuntimeError("Expected one tool call at a time, with a maximum of three.")
        call = calls[0]
        name = call["function"]["name"]
        if name != ORDER[len(results)]:
            raise RuntimeError(f"Unexpected tool call: {name}")
        if results and results[0]["stock"] >= THRESHOLD:
            raise RuntimeError("The agent attempted to reorder sufficient stock.")
        arguments = json.loads(call["function"]["arguments"])
        expected_keys = {"supplier"} if name == ORDER[2] else set()
        if not isinstance(arguments, dict) or set(arguments) != expected_keys:
            raise RuntimeError(f"Invalid arguments for {name}.")
        if name == ORDER[2] and arguments["supplier"] not in QUOTES:
            raise RuntimeError("Unknown supplier selected.")
        result = execute_tool(name, arguments, request)
        results.append(result)
        print(f"{len(results)}. {name} -> {json.dumps(result)}", flush=True)
        if not rehearsal:
            history.extend([
                reply,
                {"role": "tool", "tool_call_id": call["id"],
                 "content": json.dumps(result)},
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
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not args.rehearse and not key:
        parser.error("set GROQ_API_KEY for live mode or use --rehearse")
    try:
        run((args.item, args.quantity, args.budget, args.days), args.rehearse, key)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        if key:
            detail = detail.replace(key, "[redacted]")
        print(f"Groq returned HTTP {error.code}: {detail[:800]}", file=sys.stderr)
        return 1
    except (URLError, TimeoutError) as error:
        detail = str(getattr(error, "reason", error)).replace(key, "[redacted]") if key else str(error)
        print(f"Groq connection failed: {detail}. See README for troubleshooting.", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, KeyError, OSError) as error:
        print(f"Run stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
