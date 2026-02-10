import AppKit
import Carbon

final class HotkeyController {
    private var hotKeyRef: EventHotKeyRef?
    private var hotKeyHandler: EventHandlerRef?
    var onHotkey: (() -> Void)?

    private static var sharedController: HotkeyController?

    func start() {
        HotkeyController.sharedController = self

        let eventType = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, eventRef, _ in
            guard let eventRef else { return noErr }
            var hotKeyID = EventHotKeyID()
            let status = GetEventParameter(
                eventRef,
                EventParamName(kEventParamDirectObject),
                EventParamType(typeEventHotKeyID),
                nil,
                MemoryLayout<EventHotKeyID>.size,
                nil,
                &hotKeyID
            )
            if status == noErr, hotKeyID.id == 1 {
                DispatchQueue.main.async {
                    HotkeyController.sharedController?.onHotkey?()
                }
            }
            return noErr
        }, 1, [eventType], nil, &hotKeyHandler)

        var id = EventHotKeyID(signature: OSType(0x44534850), id: 1) // DSHP
        RegisterEventHotKey(
            UInt32(kVK_Space),
            UInt32(cmdKey | shiftKey),
            id,
            GetApplicationEventTarget(),
            0,
            &hotKeyRef
        )
    }

    deinit {
        if let hotKeyRef {
            UnregisterEventHotKey(hotKeyRef)
        }
        if let hotKeyHandler {
            RemoveEventHandler(hotKeyHandler)
        }
    }
}
