// Read-only EventKit bridge. Never requests access or saves/removes events.
import EventKit
import Foundation

func emit(_ value: [String: Any]) {
    let data = try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
}

let args = Array(CommandLine.arguments.dropFirst())
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
if args == ["status"] {
    emit(["authorization": label, "readable": readable, "requested_access": false, "writes_implemented": false])
} else if !readable {
    emit(["status": "authorization_required", "authorization": label, "requested_access": false])
} else if args == ["calendars"] {
    let store = EKEventStore()
    let available = store.calendars(for: .event)
    let calendars = available.prefix(100).map {
        ["id": $0.calendarIdentifier, "title": $0.title, "source_title": $0.source.title,
         "source_type": $0.source.sourceType.rawValue] as [String: Any]
    }
    emit(["status": "read", "calendars": calendars, "truncated": available.count > 100, "writes_implemented": false])
} else if args.count == 4 && args[0] == "events" {
    let formatter = ISO8601DateFormatter()
    guard let start = formatter.date(from: args[2]), let end = formatter.date(from: args[3]),
          end > start, end.timeIntervalSince(start) <= 7 * 86400 else {
        emit(["status": "invalid_window"]); exit(2)
    }
    let store = EKEventStore()
    guard let calendar = store.calendar(withIdentifier: args[1]) else {
        emit(["status": "calendar_not_found"]); exit(2)
    }
    let predicate = store.predicateForEvents(withStart: start, end: end, calendars: [calendar])
    let selected = store.events(matching: predicate).sorted { $0.startDate < $1.startDate }
    let events = selected.prefix(200).map { event in
        ["title": String((event.title ?? "").prefix(500)), "start": formatter.string(from: event.startDate),
         "end": formatter.string(from: event.endDate), "all_day": event.isAllDay] as [String: Any]
    }
    emit(["status": "read", "events": events, "truncated": selected.count > 200, "writes_implemented": false])
} else {
    emit(["status": "unsupported_action"]); exit(2)
}
