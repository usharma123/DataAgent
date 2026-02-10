# DashSpotlight (macOS)

Minimal macOS Spotlight-style shell for the personal data agent.

## Features
- Global hotkey: `Cmd+Shift+Space`
- Query input and answer display
- Citation list rendering from `/native/v1/personal/ask`

## Run
1. Ensure API is running locally on `http://127.0.0.1:8000`
2. Build/run from `mac_app`:

```sh
swift run
```

If hotkey capture does not fire, grant Accessibility permissions to Terminal/Xcode.
