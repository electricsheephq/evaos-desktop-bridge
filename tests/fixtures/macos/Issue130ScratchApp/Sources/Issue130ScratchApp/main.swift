import AppKit
import Foundation

private let targetMarker = "ISSUE130_TARGET_PIXELS"
private let occluderMarker = "ISSUE130_OCCLUDER"

final class ScratchDelegate: NSObject, NSApplicationDelegate, NSTextFieldDelegate {
    private let stateURL: URL
    private let readyURL: URL
    private let commandURL: URL
    private var counter = 0
    private var deniedText = ""
    private var lastCommandNonce = ""
    private var targetWindow: NSWindow?
    private var occluderWindow: NSWindow?
    private var timer: Timer?
    private let textField = NSTextField(frame: NSRect(x: 32, y: 76, width: 360, height: 28))
    private let counterLabel = NSTextField(labelWithString: "\(targetMarker) counter: 0")

    init(stateURL: URL, readyURL: URL, commandURL: URL) {
        self.stateURL = stateURL
        self.readyURL = readyURL
        self.commandURL = commandURL
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        makeTargetWindow()
        makeOccluderWindow()
        writeState()
        writeReady()
        NSApp.activate(ignoringOtherApps: true)
        targetWindow?.makeKeyAndOrderFront(nil)
        timer = Timer.scheduledTimer(withTimeInterval: 0.15, repeats: true) { [weak self] _ in
            self?.pollCommand()
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
    }

    func controlTextDidChange(_ obj: Notification) {
        deniedText = textField.stringValue
        writeState()
    }

    @objc private func increment() {
        counter += 1
        counterLabel.stringValue = "\(targetMarker) counter: \(counter)"
        writeState()
    }

    private func makeTargetWindow() {
        let window = NSWindow(
            contentRect: NSRect(x: 240, y: 240, width: 520, height: 260),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Issue130 Target Window"
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 520, height: 260))
        root.wantsLayer = true
        root.layer?.backgroundColor = NSColor(calibratedRed: 0.05, green: 0.14, blue: 0.10, alpha: 1).cgColor

        counterLabel.frame = NSRect(x: 32, y: 178, width: 440, height: 24)
        counterLabel.font = NSFont.monospacedSystemFont(ofSize: 18, weight: .semibold)
        counterLabel.textColor = .white
        counterLabel.setAccessibilityLabel(targetMarker)
        root.addSubview(counterLabel)

        let button = NSButton(frame: NSRect(x: 32, y: 126, width: 180, height: 36))
        button.title = "Issue130 Increment"
        button.bezelStyle = .rounded
        button.target = self
        button.action = #selector(increment)
        button.setAccessibilityLabel("Issue130 Increment")
        root.addSubview(button)

        textField.placeholderString = "Denied text should never appear here"
        textField.delegate = self
        textField.setAccessibilityLabel("Issue130 Denied Text Field")
        root.addSubview(textField)

        window.contentView = root
        window.isReleasedWhenClosed = false
        targetWindow = window
    }

    private func makeOccluderWindow() {
        let window = NSWindow(
            contentRect: NSRect(x: 250, y: 280, width: 480, height: 180),
            styleMask: [.titled],
            backing: .buffered,
            defer: false
        )
        window.title = "Issue130 Occluder Window"
        let label = NSTextField(labelWithString: occluderMarker)
        label.frame = NSRect(x: 32, y: 76, width: 360, height: 30)
        label.font = NSFont.monospacedSystemFont(ofSize: 24, weight: .bold)
        label.textColor = .white
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 480, height: 180))
        root.wantsLayer = true
        root.layer?.backgroundColor = NSColor(calibratedRed: 0.38, green: 0.06, blue: 0.06, alpha: 1).cgColor
        root.addSubview(label)
        window.contentView = root
        window.isReleasedWhenClosed = false
        occluderWindow = window
    }

    private func pollCommand() {
        guard let data = try? Data(contentsOf: commandURL),
              let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let nonce = payload["nonce"] as? String,
              nonce != lastCommandNonce else {
            return
        }
        lastCommandNonce = nonce
        let command = payload["command"] as? String
        if command == "show_occluder" {
            occluderWindow?.orderFrontRegardless()
            NSApp.activate(ignoringOtherApps: true)
        } else if command == "hide_occluder" {
            occluderWindow?.orderOut(nil)
            targetWindow?.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
        writeState()
    }

    private func writeReady() {
        let payload: [String: Any] = [
            "ready": true,
            "pid": ProcessInfo.processInfo.processIdentifier,
            "app": "Issue130ScratchApp"
        ]
        writeJSON(payload, to: readyURL)
    }

    private func writeState() {
        let payload: [String: Any] = [
            "counter": counter,
            "denied_text": deniedText,
            "target_marker": targetMarker,
            "occluder_marker": occluderMarker,
            "occluder_visible": occluderWindow?.isVisible == true
        ]
        writeJSON(payload, to: stateURL)
    }

    private func writeJSON(_ payload: [String: Any], to url: URL) {
        guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]) else {
            return
        }
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? data.write(to: url, options: [.atomic])
    }
}

private func value(after flag: String, in args: [String]) -> String? {
    guard let index = args.firstIndex(of: flag), index + 1 < args.count else {
        return nil
    }
    return args[index + 1]
}

let args = CommandLine.arguments
guard let statePath = value(after: "--state", in: args),
      let readyPath = value(after: "--ready", in: args),
      let commandPath = value(after: "--command", in: args) else {
    FileHandle.standardError.write(Data("Usage: Issue130ScratchApp --state PATH --ready PATH --command PATH\n".utf8))
    exit(2)
}

let app = NSApplication.shared
let delegate = ScratchDelegate(
    stateURL: URL(fileURLWithPath: statePath),
    readyURL: URL(fileURLWithPath: readyPath),
    commandURL: URL(fileURLWithPath: commandPath)
)
app.delegate = delegate
app.run()
