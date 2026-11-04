// Explicit authorization UI and a bounded, local result channel. No network.
import AppKit
import EventKit
import Foundation
import Darwin

let applicationID = "org.personalassistantdot.calendarreader"
let applicationName = "Personal Assistant Calendar Reader"
var args = Array(CommandLine.arguments.dropFirst()).filter { !$0.hasPrefix("-psn_") }
var resultPath: String? = nil
if args.count >= 2 && args[args.count - 2] == "--result" {
    resultPath = args.removeLast()
    args.removeLast()
}

func finish(_ value: [String: Any]) -> Never {
    var output = value
    output["bundle_id"] = Bundle.main.bundleIdentifier ?? "unbundled"
    let data = try! JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
    if let path = resultPath {
        let destination = URL(fileURLWithPath: path).standardizedFileURL
        let parent = destination.deletingLastPathComponent()
        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: parent.path)
            guard let resolved = realpath(parent.path, nil) else { exit(2) }
            let canonicalParent = String(cString: resolved)
            free(resolved)
            guard destination.path == path,
                  canonicalParent == parent.path,
                  attributes[.type] as? FileAttributeType == .typeDirectory,
                  (attributes[.ownerAccountID] as? NSNumber)?.uint32Value == getuid(),
                  ((attributes[.posixPermissions] as? NSNumber)?.intValue ?? 0) & 0o077 == 0,
                  !FileManager.default.fileExists(atPath: path) else { exit(2) }
            let descriptor = open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
            guard descriptor >= 0 else { exit(2) }
            let stream = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
            try stream.write(contentsOf: data)
            try stream.close()
        } catch { exit(2) }
    } else {
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))
    }
    exit(0)
}

guard Bundle.main.bundleIdentifier == applicationID else {
    finish(["status": "expected_application_bundle_required", "requested_access": false])
}

if args == ["authorize"] {
    // This branch is reachable only through an explicit local launch. It reads
    // no calendars/events and never presses any macOS approval control.
    let app = NSApplication.shared
    class ReaderDelegate: NSObject, NSApplicationDelegate {
        func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    }
    let delegate = ReaderDelegate()
    app.delegate = delegate
    app.setActivationPolicy(.regular)
    let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 580, height: 250),
                          styleMask: [.titled, .closable], backing: .buffered, defer: false)
    window.title = applicationName
    window.center()
    let label = NSTextField(wrappingLabelWithString: "应用：\(applicationName)\n身份：\(applicationID)\n\nmacOS 完整日历访问包含读写权限。本应用仅实现读取，不包含新增、修改或删除日程功能，也不联网。\n\n请亲自处理系统授权提示。此步骤不会读取日程。")
    label.frame = NSRect(x: 24, y: 35, width: 532, height: 180)
    window.contentView?.addSubview(label)
    window.makeKeyAndOrderFront(nil)
    app.activate(ignoringOtherApps: true)
    let store = EKEventStore()
    DispatchQueue.main.async {
        let (status, readable) = calendarAuthorization()
        if readable {
            label.stringValue += "\n\n已有完整访问权限；未读取日程。可关闭此窗口。"
            return
        }
        guard status == "not_determined" else {
            label.stringValue += "\n\n当前状态：\(status)。没有重复请求；请在系统设置中自行核对。"
            return
        }
        if #available(macOS 14.0, *) {
            store.requestFullAccessToEvents { granted, _ in
                DispatchQueue.main.async {
                    label.stringValue = "\(applicationName)\n\(applicationID)\n\n系统返回：\(granted ? "已授予完整日历访问" : "未授予访问")。\n本授权步骤没有读取任何日程，也没有执行写入。\n\n可关闭此窗口，再从项目检查授权状态。"
                }
            }
        } else {
            label.stringValue += "\n\n此授权流程需要 macOS 14 或更高版本。没有请求权限。"
        }
    }
    app.run()
    exit(0)
}

if args.isEmpty { args = ["status"] }
// LaunchServices children are not necessarily in the launcher's process group.
// Bound this read-only process itself as well as the Python open invocation.
DispatchQueue.global().asyncAfter(deadline: .now() + 15) { exit(3) }
finish(calendarRead(args))
