import AppKit
import SwiftUI

@main
struct DashSpotlightApp: App {
    @StateObject private var queryModel = QueryViewModel()
    private let hotkey = HotkeyController()

    init() {
        NSApp.setActivationPolicy(.regular)
    }

    var body: some Scene {
        WindowGroup {
            QueryOverlayView(model: queryModel)
                .onAppear {
                    hotkey.onHotkey = {
                        NSApp.activate(ignoringOtherApps: true)
                        for window in NSApplication.shared.windows {
                            window.makeKeyAndOrderFront(nil)
                        }
                    }
                    hotkey.start()
                }
        }
        .windowStyle(.hiddenTitleBar)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }
}
