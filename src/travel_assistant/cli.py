from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import schedule, validate_input
from .providers import (
    DuffelFlightProvider,
    MockFlightProvider,
    SkyscannerFlightProvider,
)
from .weather import get_weather


def _add_v2_commands(subparsers) -> None:
    trip = subparsers.add_parser("trip")
    trip_commands = trip.add_subparsers(dest="trip_command", required=True)

    create = trip_commands.add_parser("create")
    create.add_argument("input", type=Path)
    create.add_argument("--database", type=Path, required=True)
    create.add_argument("--trip-id")

    for command in ("plan", "replan"):
        action = trip_commands.add_parser(command)
        action.add_argument("trip_id")
        action.add_argument("--database", type=Path, required=True)
        action.add_argument("--output-dir", type=Path, required=True)

    export = trip_commands.add_parser("export")
    export.add_argument("trip_id")
    export.add_argument("--database", type=Path, required=True)
    export.add_argument("--format", choices=("json", "markdown", "ics", "geojson", "kml"), required=True)
    export.add_argument("--output", type=Path, required=True)

    explain = trip_commands.add_parser("explain")
    explain.add_argument("trip_id")
    explain.add_argument("--database", type=Path, required=True)

    flight = subparsers.add_parser("flight")
    flight_commands = flight.add_subparsers(dest="flight_command", required=True)
    search = flight_commands.add_parser("search")
    search.add_argument("request", type=Path)
    search.add_argument(
        "--provider",
        choices=("mock", "duffel", "skyscanner", "google-link", "fli-experimental"),
        default="mock",
    )
    search.add_argument("--enable-skyscanner", action="store_true")


def markdown(plan: dict) -> str:
    lines = [f"# {plan['origin']} → {plan['destination']} 旅遊規劃", "", "> 價格與班次需重查；本工具未代訂、未付款。", "", "## 逐日行程"]
    for day in plan["itinerary"]:
        lines.append(f"### {day['date']}（{day['minutes']} 分鐘）")
        if day["activities"]:
            lines.extend(f"- {item['name']}（{item['duration_minutes']} 分鐘，{item['cost']} {plan['currency']}）" for item in day["activities"])
        else:
            lines.append("- 無安排")
    lines += ["", "## 航班候選"]
    if plan["flights"]:
        lines.extend(f"- {flight.get('provider')}：{flight.get('origin', '?')} → {flight.get('destination', '?')}；{flight.get('departure_date', '?')}；{flight.get('price', flight.get('total_amount', '?'))} {flight.get('currency', flight.get('total_currency', ''))}" for flight in plan["flights"])
    else:
        lines.append("- 無")
    if "weather" in plan:
        lines += ["", "## 天氣"]
        lines.append("- Open-Meteo 天氣預報已附於 JSON。" if plan["weather"] else "- 未取得天氣：缺少活動座標、日期不在預報範圍或網路服務失敗。")
    lines += ["", f"## 預算摘要\n- 活動費用：{plan['budget_summary']['activities']} {plan['currency']}\n- 預算：{plan['budget_summary']['budget']} {plan['currency']}", "", "## 未排入活動"]
    lines.extend(f"- {item['name']}" for item in plan["unplanned"]) or lines.append("- 無")
    lines += ["", "## 資料來源"]
    sources = {item["name"]: (item["source_url"], item["checked_at"]) for day in plan["itinerary"] for item in day["activities"]}
    sources.update({item["name"]: (item["source_url"], item["checked_at"]) for item in plan["unplanned"]})
    lines.extend(f"- name: {name}\n  source_url: {url}\n  checked_at: {checked_at}" for name, (url, checked_at) in sources.items())
    return "\n".join(lines) + "\n"


def build_plan(data: dict, provider_name: str, weather: bool = False) -> dict:
    validate_input(data)
    itinerary, unplanned = schedule(data)
    providers = {"mock": MockFlightProvider, "duffel": DuffelFlightProvider, "skyscanner": SkyscannerFlightProvider}
    flights = providers[provider_name]().search({"origin": data["origin"], "destination": data["destination"], "departure_date": data["start_date"], "travellers": data["travellers"], "currency": data["currency"]})
    activity_cost = sum(day["activity_cost"] for day in itinerary)
    result = {"origin": data["origin"], "destination": data["destination"], "currency": data["currency"], "itinerary": itinerary, "flights": flights, "unplanned": unplanned, "budget_summary": {"activities": activity_cost, "budget": data["budget"], "remaining_before_flights": data["budget"] - activity_cost}, "disclaimer": "價格/班次需重查；未代訂、未付款。"}
    if weather:
        activity = next((item for day in itinerary for item in day["activities"]), None) or (unplanned[0] if unplanned else None)
        source_activity = next(item for item in data["activities"] if item["name"] == activity["name"]) if activity else None
        result["weather"] = get_weather(source_activity["latitude"], source_activity["longitude"], data["start_date"], data["end_date"]) if source_activity else None
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("input", type=Path)
    plan.add_argument("--output-dir", type=Path, required=True)
    plan.add_argument("--flight-provider", choices=("mock", "duffel", "skyscanner"), default="mock")
    plan.add_argument("--weather", action="store_true")
    _add_v2_commands(sub)
    args = parser.parse_args()
    if args.command == "plan":
        data = json.loads(args.input.read_text(encoding="utf-8"))
        result = build_plan(data, args.flight_provider, args.weather)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "plan.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "plan.md").write_text(markdown(result), encoding="utf-8")
        return 0
    if args.command == "trip":
        from .v2 import create_trip, export_saved_trip, latest_planned_trip, plan_trip

        if args.trip_command == "create":
            trip, revision = create_trip(args.input, args.database, trip_id=args.trip_id)
            print(json.dumps({"trip_id": trip.id, "revision": revision}, ensure_ascii=False))
            return 0
        if args.trip_command in {"plan", "replan"}:
            payload, revision, paths = plan_trip(args.trip_id, args.database, args.output_dir)
            print(
                json.dumps(
                    {
                        "trip_id": payload["id"],
                        "revision": revision,
                        "outputs": {key: str(value) for key, value in paths.items()},
                        "conflicts": len(payload["conflicts"]),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if args.trip_command == "export":
            path = export_saved_trip(args.trip_id, args.database, args.format, args.output)
            print(json.dumps({"output": str(path), "format": args.format}, ensure_ascii=False))
            return 0
        if args.trip_command == "explain":
            record = latest_planned_trip(args.trip_id, args.database)
            print(
                json.dumps(
                    {
                        "trip_id": args.trip_id,
                        "revision": record.revision,
                        "conflicts": record.plan.get("conflicts", []),
                        "explanations": record.plan.get("explanations", []),
                        "warnings": record.plan.get("warnings", []),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
    if args.command == "flight" and args.flight_command == "search":
        from .providers_v2 import (
            DuffelProvider,
            FliExperimentalProvider,
            GoogleFlightsLinkProvider,
            MockFlightProvider,
            SkyscannerProvider,
        )
        from .providers_v2.models import ProviderError

        request = json.loads(args.request.read_text(encoding="utf-8"))
        providers = {
            "mock": MockFlightProvider(),
            "duffel": DuffelProvider(),
            "skyscanner": SkyscannerProvider(enabled=args.enable_skyscanner),
            "google-link": GoogleFlightsLinkProvider(),
            "fli-experimental": FliExperimentalProvider(),
        }
        try:
            result = providers[args.provider].search(request)
        except ProviderError as exc:
            print(
                json.dumps(
                    {"provider": args.provider, "status": exc.status.value, "error": str(exc)},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        print(
            json.dumps(
                {
                    "provider": result.provider,
                    "status": result.status.value,
                    "retrieved_at": result.retrieved_at,
                    "warning": result.warning,
                    "data": result.data,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    return 1
