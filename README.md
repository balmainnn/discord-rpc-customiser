# Discord RPC Customizer

A small Windows/macOS/Linux desktop utility for creating a custom Discord Rich Presence using Python, Tkinter, and `pypresence`. The app runs its Discord IPC work on a background thread, retries when Discord is unavailable, and can minimize to the system tray.

## Features

- Start/stop Rich Presence broadcasting.
- Application Client ID, state, and details.
- Large and small image keys with hover text.
- Optional elapsed count-up timer.
- Up to two external URL buttons.
- Saves settings to `config.json`.
- System-tray menu to open, start/stop, or exit.
- Reconnects when Discord closes or becomes available.

## Requirements

- Python 3.10 or newer.
- Discord desktop client installed and running. The browser version of Discord does not expose the local RPC IPC endpoint.
- A Discord application and its Application ID.

## 1. Register a Discord application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications).
2. Sign in and choose **New Application**.
3. Give it a name. This name is associated with the application used for your Rich Presence.
4. Open **General Information** and copy the **Application ID**. Paste this numeric value into the app's Application Client ID field.
5. Open **Rich Presence → Art Assets** (the exact navigation label may change). Upload any artwork you want to use.
6. Use each uploaded asset's key/name in the Large Image Key or Small Image Key fields. Keys are not image file paths; they are the asset identifiers shown by the Developer Portal.
7. Allow time for newly uploaded assets to become available.

The application ID is not a bot token. Do not paste a bot token, client secret, or other secret credential into this app.

## 2. Install and run from source

Open a terminal in the project folder:

```bash
python -m venv .venv
```

Activate it:

**Windows PowerShell**
```powershell
.venv\Scripts\Activate.ps1
```

**Windows Command Prompt**
```bat
.venv\Scripts\activate.bat
```

**macOS / Linux**
```bash
source .venv/bin/activate
```

Install dependencies and launch:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Enter your Application ID and presence fields, then click **Start Broadcasting**. Discord must be running as a desktop application. If Discord is closed, the app remains active and retries automatically.

Closing the main window hides it to the tray. Use the tray icon's **Open** item to show it again, or **Exit** to quit. The tray integration depends on a working desktop environment and system tray implementation.

## 3. Presence image assets and buttons

- Image keys must match uploaded Rich Presence asset keys in the Developer Portal.
- Hover text is optional.
- Button labels are limited to 32 characters by Discord.
- Button URLs must be complete `http://` or `https://` URLs.
- Discord supports at most two buttons. A button is included only when both its label and URL are filled in.
- Rich Presence is shown only where Discord's client and user privacy/activity settings permit it.

## 4. Configuration

The app saves values in `config.json` beside `main.py`. You can edit this file while the app is closed. The default file contains blank image keys and no buttons. The Client ID is intentionally blank and must be supplied by you.

## 5. Build a standalone executable with PyInstaller

Install PyInstaller in the active environment:

```bash
pip install pyinstaller
```

Build a one-folder distribution:

```bash
pyinstaller --noconfirm --clean --windowed --name DiscordRPC_Customizer --add-data "config.json;." main.py
```

On macOS/Linux, use a colon instead of a semicolon in `--add-data`:

```bash
pyinstaller --noconfirm --clean --windowed --name DiscordRPC_Customizer --add-data "config.json:." main.py
```

The executable and support files are placed in `dist/DiscordRPC_Customizer/`. Copy `config.json` beside the executable if you want to preconfigure it. The app writes its settings beside the executable/script location.

For a single-file build, replace the command with:

```bash
pyinstaller --noconfirm --clean --onefile --windowed --name DiscordRPC_Customizer main.py
```

A one-file build extracts bundled resources to a temporary directory. The application configuration is still read/written beside the executable. PyInstaller builds should be produced on the target operating system; Windows builds are not generally cross-compiled from Linux/macOS.

## Troubleshooting

- **Discord not detected:** Start the Discord desktop app, wait for it to finish loading, then leave this utility running. The app retries every few seconds.
- **Invalid Client ID:** Copy the numeric Application ID from Developer Portal → General Information.
- **Images do not appear:** Confirm the exact asset key, ensure the asset has finished processing, and restart the presence.
- **Presence not visible:** Check Discord activity/privacy settings and test with the desktop client.
- **Tray icon missing:** Some Linux desktop environments do not provide a compatible tray host. Run the app in a desktop session with a tray extension or use the window's Exit control.
- **Logs:** Runtime diagnostics are written to `~/.discord_rpc_customizer.log` (on Windows, in your user home directory).

## Notes

This is a community utility using Discord's local Rich Presence IPC interface through `pypresence`. It is not affiliated with or endorsed by Discord. Discord may change client behavior or platform restrictions over time.
