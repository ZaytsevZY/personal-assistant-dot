// Shared read-only EventKit operations. Authorization UI is a separate explicit entry point.
import EventKit
import Foundation

func calendarAuthorization() -> (String, Bool) {
let status = EKEventStore.authorizationStatus(for: .event)
var label = "unknown"
var readable = false
if #available(macOS 14.0, *) {
    if status == .fullAccess { label = "full_access"; readable = true }
    else if status == .writeOnly { label = "write_only" }
}
if status == .notDetermined { label = "not_determined" }
else if status == .denied { label = "denied" }
else if status == .restricted { label = "restricted" }
if #unavailable(macOS 14.0) {
    if status == .authorized { label = "authorized"; readable = true }
}
return (label, readable)
}

func calendarRead(_ args: [String]) -> [String: Any] {
let (label, readable) = calendarAuthorization()
if args == ["status"] {
    return ["authorization": label, "readable": readable, "requested_access": false, "writes_implemented": false]
} else if !readable {
    return ["status": "authorization_required", "authorization": label, "requested_access": false]
} else if args.count == 3 && args[0] == "resolve" {
    let store = EKEventStore()
    let matches = store.calendars(for: .event).filter {
        $0.title == args[2] && $0.source.title.caseInsensitiveCompare(args[1]) == .orderedSame
    }
    return ["status": "resolved", "match_count": matches.count,
            "matches": matches.prefix(10).map { ["id": $0.calendarIdentifier] }, "writes_implemented": false]
} else if args == ["calendars"] {
    let store = EKEventStore()
    let available = store.calendars(for: .event)
    let calendars = available.prefix(100).map {
        ["id": $0.calendarIdentifier, "title": $0.title, "source_title": $0.source.title,
         "source_type": $0.source.sourceType.rawValue] as [String: Any]
    }
    return ["status": "read", "calendars": calendars, "truncated": available.count > 100, "writes_implemented": false]
} else if args.count == 4 && ["events", "verify"].contains(args[0]) {
    let formatter = ISO8601DateFormatter()
    guard let start = formatter.date(from: args[2]), let end = formatter.date(from: args[3]),
          end > start, end.timeIntervalSince(start) <= 7 * 86400 else {
        return ["status": "invalid_window"]
    }
    let store = EKEventStore()
    guard let calendar = store.calendar(withIdentifier: args[1]) else {
        return ["status": "calendar_not_found"]
    }
    let predicate = store.predicateForEvents(withStart: start, end: end, calendars: [calendar])
    let selected = store.events(matching: predicate).sorted { $0.startDate < $1.startDate }
    if args[0] == "verify" {
        return ["status": "read_verified", "event_count": selected.count, "window_seconds": Int(end.timeIntervalSince(start)),
                "event_content_returned": false, "writes_implemented": false]
    }
    let events = selected.prefix(200).map { event in
        ["title": String((event.title ?? "").prefix(500)), "start": formatter.string(from: event.startDate),
         "end": formatter.string(from: event.endDate), "all_day": event.isAllDay] as [String: Any]
    }
    return ["status": "read", "events": events, "truncated": selected.count > 200, "writes_implemented": false]
} else {
    return ["status": "unsupported_action"]
}

}
