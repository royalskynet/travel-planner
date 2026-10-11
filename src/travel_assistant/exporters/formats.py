from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

from icalendar import Calendar, Event

from .common import (
    day_items,
    iter_locations,
    parse_end,
    parse_start,
    to_plain,
    trip_days,
)


def export_json(trip: Any, *, indent: int = 2) -> str:
    return (
        json.dumps(to_plain(trip), ensure_ascii=False, indent=indent, sort_keys=True)
        + "\n"
    )


def export_markdown(trip: Any) -> str:
    data = to_plain(trip)
    title = data.get("name") or data.get("title") or "旅程計畫"
    lines = [f"# {title}", ""]
    for day in trip_days(data):
        lines.extend([f"## {day.get('date', '未定日期')}", ""])
        items = day_items(day)
        if not items:
            lines.extend(["- 無安排", ""])
            continue
        for item in items:
            name = item.get("name") or item.get("title") or "未命名項目"
            when = item.get("start_at") or item.get("start_time")
            source = item.get("source_url") or item.get("url")
            prefix = f"{when} " if when else ""
            line = f"- {prefix}{name}"
            if source:
                line += f" — {source}"
            lines.append(line)
        lines.append("")
    warnings = data.get("warnings") or []
    if warnings:
        lines.extend(["## 警告", ""] + [f"- {warning}" for warning in warnings] + [""])
    return "\n".join(lines).rstrip() + "\n"


def export_ics(
    trip: Any,
    *,
    calendar_name: str | None = None,
    generated_at: datetime | None = None,
) -> str:
    data = to_plain(trip)
    name = calendar_name or data.get("name") or data.get("title") or "Travel plan"
    calendar = Calendar()
    calendar.add("prodid", "-//travel-planner-assistant//V2//EN")
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("x-wr-calname", name)
    if generated_at is None:
        raw_stamp = data.get("updated_at") or data.get("created_at")
        generated_at = (
            datetime.fromisoformat(str(raw_stamp).replace("Z", "+00:00"))
            if raw_stamp
            else datetime(1970, 1, 1, tzinfo=timezone.utc)
        )
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    for day in trip_days(data):
        day_date = str(day.get("date", ""))
        for order, item in enumerate(day_items(day), 1):
            start, all_day = parse_start(day_date, item)
            end = parse_end(start, all_day, item)
            raw_uid = f"{data.get('id', name)}|{day_date}|{order}|{item.get('name', item.get('title', 'event'))}"
            uid = (
                hashlib.sha256(raw_uid.encode("utf-8")).hexdigest()[:24]
                + "@travel-assistant"
            )
            event = Event()
            event.add("uid", uid)
            event.add("dtstamp", generated_at.astimezone(timezone.utc))
            if isinstance(start, datetime) and start.tzinfo is not None:
                start = start.astimezone(timezone.utc)
            if isinstance(end, datetime) and end.tzinfo is not None:
                end = end.astimezone(timezone.utc)
            event.add("dtstart", start)
            event.add("dtend", end)
            event.add("summary", item.get("name") or item.get("title") or "Travel item")
            if item.get("source_url") or item.get("url"):
                event.add("url", item.get("source_url") or item.get("url"))
            calendar.add_component(event)
    return calendar.to_ical().decode("utf-8")


def export_geojson(trip: Any) -> str:
    features = []
    for item, day_date, order, (latitude, longitude) in iter_locations(trip):
        properties = {
            "name": item.get("name") or item.get("title"),
            "date": day_date,
            "order": order,
            "source_url": item.get("source_url") or item.get("url"),
            "estimated": bool(item.get("estimated", False)),
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                "properties": {
                    key: value for key, value in properties.items() if value is not None
                },
            }
        )
    return (
        json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def export_kml(trip: Any) -> str:
    namespace = "http://www.opengis.net/kml/2.2"
    ET.register_namespace("", namespace)
    root = ET.Element(f"{{{namespace}}}kml")
    document = ET.SubElement(root, f"{{{namespace}}}Document")
    data = to_plain(trip)
    ET.SubElement(document, f"{{{namespace}}}name").text = str(
        data.get("name") or data.get("title") or "Travel plan"
    )
    for item, day_date, order, (latitude, longitude) in iter_locations(data):
        placemark = ET.SubElement(document, f"{{{namespace}}}Placemark")
        ET.SubElement(placemark, f"{{{namespace}}}name").text = str(
            item.get("name") or item.get("title") or "Travel item"
        )
        ET.SubElement(
            placemark, f"{{{namespace}}}description"
        ).text = f"{day_date} #{order}"
        point = ET.SubElement(placemark, f"{{{namespace}}}Point")
        ET.SubElement(
            point, f"{{{namespace}}}coordinates"
        ).text = f"{longitude},{latitude},0"
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"
